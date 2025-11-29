"""FastAPI server that streams analytics data to frontend via WebSocket.

This serves real-time analytics data to the React frontend.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import threading
from typing import Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import httpx

from backend.config import HyperliquidClientConfig, MAINNET, TESTNET
from backend.hyperliquid_client import HyperliquidClient
from backend.transport_hyperliquid_sdk import HyperliquidSdkTransport

from backend.orderbook_metrics import (
    OrderBook,
    OrderBookSide,
    OrderBookLevel,
    calculate_all_metrics,
)
from backend.trade_flow_tracker import Trade, TradeFlowTracker, detect_sweep_direction
from backend.price_momentum import PriceMomentumTracker
from backend.market_indicators import ActiveAssetContext, MarketIndicatorsTracker
from backend.depth_decay import DepthDecayTracker
from backend.liquidations import LiquidationsDetector
from backend.candle_aggregator import CandleAggregator, OHLCV
from backend.volatility import VolatilityTracker
from backend.session_context import SessionContextTracker
from backend.candle_fetcher import HyperliquidCandleFetcher
from backend.regime_detector import RegimeDetector
from backend.slippage_estimator import SlippageEstimator, OrderBookLevel as SlippageOrderBookLevel
from backend.crowding_detector import CrowdingDetector
from backend.cross_asset_context import CrossAssetContextTracker

app = FastAPI(title="Hyperliquid Analytics API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyticsEngine:
    """Analytics engine that processes events and generates data."""

    def __init__(self):
        self.orderbook = None
        self.last_orderbook_update_time = None  # Track last orderbook update

        # Existing trackers
        self.trade_tracker = TradeFlowTracker(window_seconds=30.0, max_history_seconds=900.0)
        self.momentum_tracker = PriceMomentumTracker(short_window_seconds=5.0, long_window_seconds=20.0)
        self.market_tracker = MarketIndicatorsTracker(oi_window_seconds=300.0, max_history_seconds=900.0)
        self.depth_tracker = DepthDecayTracker(window_seconds=15.0)
        self.liq_detector = LiquidationsDetector(window_seconds=60.0, large_trade_threshold_usd=10000.0, max_history_seconds=900.0)

        # New multi-timeframe trackers
        self.candle_aggregator = CandleAggregator(base_interval="1m", max_history=500)
        self.volatility_tracker = VolatilityTracker(
            low_threshold_percentile=33.0,
            high_threshold_percentile=67.0,
            history_window=100
        )
        self.session_tracker = SessionContextTracker(
            session_duration_hours=24.0,
            vwap_window_hours=24.0,
            volume_windows=[1.0, 4.0]
        )
        self.regime_detector = RegimeDetector(
            trend_threshold_pct=0.1,
            strong_trend_threshold_pct=0.5,
            range_threshold_pct=0.05,
            tight_spread_bps=5.0,
            wide_spread_bps=20.0,
            deep_book_usd=100000.0,
            thin_book_usd=20000.0,
            elevated_liq_count=3,
            high_liq_count=10,
        )
        self.slippage_estimator = SlippageEstimator(taker_fee_bps=2.8)
        self.crowding_detector = CrowdingDetector(
            oi_increasing_threshold=0.5,
            oi_velocity_high_threshold=0.05,
            funding_bullish_threshold=0.01,
            funding_bearish_threshold=-0.01,
            basis_rich_threshold=0.1,
            basis_cheap_threshold=-0.1,
            crowding_threshold=0.6,
        )
        self.cross_asset_tracker = CrossAssetContextTracker(
            assets=["BTC", "ETH"],
            low_vol_threshold_pct=0.5,
            high_vol_threshold_pct=2.0,
            trend_threshold_pct=0.3,
        )

        # Current 1m candle tracking
        self.current_candle_bucket_ms = None
        self.current_candle_open = None
        self.current_candle_high = None
        self.current_candle_low = None
        self.current_candle_close = None
        self.current_candle_volume = 0.0
        self.current_candle_trades = 0

        self.event_count = 0
        self.orderbook_updates = 0
        self.trade_events = 0
        self.market_context_updates = 0

        # Rate tracking
        import time
        from collections import deque
        self.message_timestamps = deque(maxlen=1000)  # Track last 1000 messages
        self.start_time = time.time()

        # Hyperliquid volumes from API
        self.hyperliquid_24h_volume = None
        self.hyperliquid_1h_volume = None
        self.hyperliquid_4h_volume = None
        self.last_volume_fetch_time = 0
        self.coin = None

        self._volume_update_interval = 60.0
        self._volume_task: asyncio.Task | None = None
        self._volume_lock = asyncio.Lock()
    async def fetch_hyperliquid_volumes(self, coin: str) -> None:
        """Fetch 24h, 4h, and 1h volumes from Hyperliquid API."""
        current_time = time.time()

        if current_time - self.last_volume_fetch_time < self._volume_update_interval:
            return

        async with self._volume_lock:
            if current_time - self.last_volume_fetch_time < self._volume_update_interval:
                return

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await self._update_meta_volume(client, coin)
                    self.hyperliquid_1h_volume = await self._fetch_candle_volume(client, coin, 60)
                    self.hyperliquid_4h_volume = await self._fetch_candle_volume(client, coin, 240)

                self.last_volume_fetch_time = current_time
                vol_24h = f"${self.hyperliquid_24h_volume:,.0f}" if self.hyperliquid_24h_volume else "N/A"
                vol_4h = f"${self.hyperliquid_4h_volume:,.0f}" if self.hyperliquid_4h_volume else "N/A"
                vol_1h = f"${self.hyperliquid_1h_volume:,.0f}" if self.hyperliquid_1h_volume else "N/A"
                print(f"[INFO] Updated Hyperliquid volumes: 24h={vol_24h}, 4h={vol_4h}, 1h={vol_1h}")

            except Exception as exc:
                print(f"[ERROR] Failed to fetch Hyperliquid volumes: {exc}")

    async def _update_meta_volume(self, client: httpx.AsyncClient, coin: str) -> None:
        response = await client.post(
            "https://api.hyperliquid.xyz/info",
            json={"type": "metaAndAssetCtxs"},
        )
        response.raise_for_status()
        data = response.json()

        if not (isinstance(data, list) and len(data) == 2):
            return

        universe = data[0]
        contexts = data[1]

        coin_index = None
        for idx, name in enumerate(universe.get("universe", [])):
            if name.get("name") == coin:
                coin_index = idx
                break

        if coin_index is None or coin_index >= len(contexts):
            return

        context = contexts[coin_index]
        day_volume = context.get("dayNtlVlm")
        if day_volume:
            self.hyperliquid_24h_volume = float(day_volume)

    async def _fetch_candle_volume(self, client: httpx.AsyncClient, coin: str, count: int) -> float | None:
        end_time_ms = int(time.time() * 1000)
        start_time_ms = end_time_ms - (count * 60 * 1000)

        request_data = {
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": "1m",
                "startTime": start_time_ms,
                "endTime": end_time_ms,
            },
        }

        response = await client.post(
            "https://api.hyperliquid.xyz/info",
            json=request_data,
        )
        response.raise_for_status()
        candles = response.json()

        if not isinstance(candles, list):
            return None

        total_volume = 0.0
        for candle_data in candles:
            if not isinstance(candle_data, dict):
                continue
            try:
                volume = float(candle_data.get("v", 0.0))
                close = float(candle_data.get("c", 0.0))
                total_volume += volume * close
            except (TypeError, ValueError):
                continue

        return total_volume if total_volume > 0 else None

    async def start_volume_updater(self, coin: str) -> None:
        self.coin = coin
        if self._volume_task and not self._volume_task.done():
            return

        self._volume_task = asyncio.create_task(self._volume_update_loop())

    def stop_volume_updater(self) -> None:
        if self._volume_task:
            self._volume_task.cancel()
            self._volume_task = None

    async def _volume_update_loop(self) -> None:
        try:
            while self.coin:
                await self.fetch_hyperliquid_volumes(self.coin)
                await asyncio.sleep(self._volume_update_interval)
        except asyncio.CancelledError:
            return

    def preload_historical_data(self, coin: str) -> None:
        """Preload historical candle data from Hyperliquid REST API.

        This fetches historical candles for 1m, 5m, 15m, 1h intervals
        and pre-populates the candle aggregator so that ATR and other
        metrics are immediately available.
        """
        import time
        self.coin = coin  # Store coin for volume fetching
        print(f"[INFO] Preloading historical candle data for {coin}...")

        try:
            fetcher = HyperliquidCandleFetcher(coin=coin)

            # Fetch 1-minute candles (last 500)
            candles_1m = fetcher.fetch_recent_candles("1m", count=500)
            print(f"[INFO] Fetched {len(candles_1m)} 1-minute candles")

            # Convert and add to aggregator
            for hl_candle in candles_1m:
                ohlcv = OHLCV(
                    timestamp_ms=hl_candle.timestamp_ms,
                    open=hl_candle.open,
                    high=hl_candle.high,
                    low=hl_candle.low,
                    close=hl_candle.close,
                    volume=hl_candle.volume,
                    n_trades=0  # Not available from API
                )
                self.candle_aggregator.add_candle(ohlcv)

            # Get daily candle for session context
            daily_range = fetcher.get_current_daily_range()
            if daily_range:
                daily_high, daily_low, current_close = daily_range
                print(f"[INFO] Daily range: High ${daily_high:.2f}, Low ${daily_low:.2f}")

                # Initialize session tracker with daily data
                current_time_ms = time.time() * 1000
                self.session_tracker.reset_session(current_time_ms, current_close)
                self.session_tracker.daily_high = daily_high
                self.session_tracker.daily_low = daily_low
                self.session_tracker.current_price = current_close

            print(f"[INFO] Historical data preload complete")

        except Exception as e:
            print(f"[ERROR] Failed to preload historical data: {e}")
            print(f"[INFO] Will continue with live data only")

    def process_event(self, event) -> None:
        """Process a WebSocket event."""
        import time
        self.event_count += 1
        self.message_timestamps.append(time.time())
        event_type = type(event).__name__

        try:
            if event_type == "OrderBookSnapshot":
                self._process_orderbook(event)
                self.orderbook_updates += 1
            elif event_type == "TradeEvent":
                self._process_trades(event)
                self.trade_events += 1
            elif event_type == "PerpAssetContext":
                self._process_market_context(event)
                self.market_context_updates += 1
        except Exception as e:
            print(f"[ERROR] Failed to process {event_type}: {e}")

    def get_message_rate(self) -> Dict[str, Any]:
        """Calculate message rate statistics."""
        import time
        now = time.time()

        # Messages in last minute
        cutoff_60s = now - 60.0
        messages_last_60s = sum(1 for ts in self.message_timestamps if ts >= cutoff_60s)

        # Messages in last 10 seconds
        cutoff_10s = now - 10.0
        messages_last_10s = sum(1 for ts in self.message_timestamps if ts >= cutoff_10s)

        # Overall average
        uptime = now - self.start_time
        avg_per_minute = (self.event_count / uptime * 60.0) if uptime > 0 else 0.0

        return {
            "messages_per_minute": messages_last_60s,
            "messages_last_10s": messages_last_10s,
            "average_per_minute": avg_per_minute,
            "total_messages": self.event_count,
            "uptime_seconds": uptime,
        }

    def _process_orderbook(self, event) -> None:
        """Process orderbook event."""
        import time
        timestamp_ms = float(event.time_ms)

        bid_levels = []
        for bid in event.bids[:20]:
            price = float(bid.px)
            size = float(bid.sz)
            if price > 0 and size > 0:
                bid_levels.append(OrderBookLevel(price=price, size=size))

        ask_levels = []
        for ask in event.asks[:20]:
            price = float(ask.px)
            size = float(ask.sz)
            if price > 0 and size > 0:
                ask_levels.append(OrderBookLevel(price=price, size=size))

        if bid_levels and ask_levels:
            self.orderbook = OrderBook(
                bids=OrderBookSide(levels=bid_levels),
                asks=OrderBookSide(levels=ask_levels),
                timestamp_ms=timestamp_ms,
            )
            # Track orderbook update time
            self.last_orderbook_update_time = time.time()

            if self.orderbook.mid_price:
                self.momentum_tracker.add_price(self.orderbook.mid_price, timestamp_ms)
                # Update session tracker with current price
                self.session_tracker.update_price(timestamp_ms, self.orderbook.mid_price)

            bid_depth_l5, ask_depth_l5 = self.orderbook.l5_depth_usd()
            self.depth_tracker.add_snapshot(bid_depth_l5, ask_depth_l5, timestamp_ms)

    def _process_trades(self, event) -> None:
        """Process trade event."""
        price = float(event.px)
        size = float(event.sz)
        # Hyperliquid uses "B" for buy and "A" for sell
        side = "buy" if event.side == "B" else "sell"
        timestamp_ms = float(event.time_ms)

        if price > 0 and size > 0:
            trade = Trade(timestamp_ms=timestamp_ms, price=price, size=size, side=side)
            self.trade_tracker.add_trade(trade)

            size_usd = price * size
            self.liq_detector.add_trade(timestamp_ms, price, size_usd, side)

            # Update session tracker with trade
            self.session_tracker.add_trade(timestamp_ms, price, size_usd)

            # Update 1-minute candles
            self._update_candle(timestamp_ms, price, size)

    def _update_candle(self, timestamp_ms: float, price: float, size: float) -> None:
        """Update current 1-minute candle with new trade."""
        # Determine which 1-minute bucket this trade belongs to
        candle_minutes = int(timestamp_ms / 1000 / 60)
        bucket_ms = candle_minutes * 60 * 1000

        # Check if we've moved to a new candle
        if self.current_candle_bucket_ms != bucket_ms:
            # Finalize previous candle if it exists
            if self.current_candle_bucket_ms is not None:
                candle = OHLCV(
                    timestamp_ms=self.current_candle_bucket_ms,
                    open=self.current_candle_open,
                    high=self.current_candle_high,
                    low=self.current_candle_low,
                    close=self.current_candle_close,
                    volume=self.current_candle_volume,
                    n_trades=self.current_candle_trades,
                )
                self.candle_aggregator.add_candle(candle)

            # Start new candle
            self.current_candle_bucket_ms = bucket_ms
            self.current_candle_open = price
            self.current_candle_high = price
            self.current_candle_low = price
            self.current_candle_close = price
            self.current_candle_volume = size
            self.current_candle_trades = 1
        else:
            # Update existing candle
            self.current_candle_high = max(self.current_candle_high, price)
            self.current_candle_low = min(self.current_candle_low, price)
            self.current_candle_close = price
            self.current_candle_volume += size
            self.current_candle_trades += 1

    def _process_market_context(self, event) -> None:
        """Process market context event."""
        import time
        timestamp_ms = time.time() * 1000

        context = ActiveAssetContext(
            timestamp_ms=timestamp_ms,
            coin=event.coin,
            open_interest_usd=float(event.open_interest),
            funding_rate=float(event.funding),
            mark_price=float(event.mark_px),
            oracle_price=float(event.oracle_px) if event.oracle_px is not None else None,
        )

        self.market_tracker.add_context(context)

    def get_analytics_data(self) -> Dict[str, Any]:
        """Get current analytics data as JSON."""
        # Get rate metrics
        rate_stats = self.get_message_rate()

        data = {
            "stats": {
                "events": self.event_count,
                "orderbook_updates": self.orderbook_updates,
                "trade_events": self.trade_events,
                "market_context_updates": self.market_context_updates,
            },
            "rate": rate_stats,
        }

        # Orderbook metrics
        if self.orderbook:
            try:
                metrics = calculate_all_metrics(self.orderbook)
                l2_bid, l2_ask = self.orderbook.l2_depth_usd()
                l3_bid, l3_ask = self.orderbook.l3_depth_usd()
                l4_bid, l4_ask = self.orderbook.l4_depth_usd()

                # Build orderbook ladder (top 10 levels each side)
                bids_ladder = []
                for i, level in enumerate(self.orderbook.bids.levels[:10]):
                    bids_ladder.append({
                        "price": level.price,
                        "size": level.size,
                        "total_usd": level.notional_usd,
                    })

                asks_ladder = []
                for i, level in enumerate(self.orderbook.asks.levels[:10]):
                    asks_ladder.append({
                        "price": level.price,
                        "size": level.size,
                        "total_usd": level.notional_usd,
                    })

                data["orderbook"] = {
                    "mid_price": metrics.mid_price,
                    "spread_bps": metrics.spread_bps,
                    "best_bid": metrics.best_bid,
                    "best_ask": metrics.best_ask,
                    "l1_depth_bid": metrics.l1_depth_bid_usd,
                    "l1_depth_ask": metrics.l1_depth_ask_usd,
                    "l2_depth_bid": l2_bid,
                    "l2_depth_ask": l2_ask,
                    "l3_depth_bid": l3_bid,
                    "l3_depth_ask": l3_ask,
                    "l4_depth_bid": l4_bid,
                    "l4_depth_ask": l4_ask,
                    "l5_depth_bid": metrics.l5_depth_bid_usd,
                    "l5_depth_ask": metrics.l5_depth_ask_usd,
                    "l1_imbalance": metrics.l1_imbalance,
                    "l5_imbalance": metrics.l5_imbalance,
                    "bids": bids_ladder,
                    "asks": asks_ladder,
                }
            except Exception as e:
                data["orderbook"] = {"error": str(e)}

        # Trade flow
        try:
            trade_stats = self.trade_tracker.get_stats()
            sweep = detect_sweep_direction(trade_stats, threshold=0.65)
            data["trade_flow"] = {
                "trade_count": trade_stats.trade_count,
                "total_volume": trade_stats.total_volume_usd,
                "buy_volume": trade_stats.buy_volume_usd,
                "sell_volume": trade_stats.sell_volume_usd,
                "buy_ratio": trade_stats.buy_ratio,
                "sell_ratio": trade_stats.sell_ratio,
                "sweep_direction": sweep,
                "largest": trade_stats.largest_trade_usd,
                "median": trade_stats.median_trade_usd,
                "average": trade_stats.average_trade_usd,
            }
        except Exception as e:
            data["trade_flow"] = {"error": str(e)}

        # Momentum
        try:
            short, long = self.momentum_tracker.get_all_momentum()
            data["momentum"] = {}
            if short:
                data["momentum"]["short"] = {
                    "direction": short.direction,
                    "change_percent": short.change_percent,
                    "is_usable": short.is_usable,
                }
            if long:
                data["momentum"]["long"] = {
                    "direction": long.direction,
                    "change_percent": long.change_percent,
                    "is_usable": long.is_usable,
                }
        except Exception as e:
            data["momentum"] = {"error": str(e)}

        # Depth decay
        try:
            decay_stats = self.depth_tracker.get_decay_stats()
            if decay_stats:
                data["depth_decay"] = {
                    "bid_decay_percent": decay_stats.bid_decay_percent,
                    "ask_decay_percent": decay_stats.ask_decay_percent,
                    "bid_status": decay_stats.bid_status,
                    "ask_status": decay_stats.ask_status,
                }
        except Exception as e:
            data["depth_decay"] = {"error": str(e)}

        # Liquidations
        try:
            liq_stats = self.liq_detector.get_stats()
            data["liquidations"] = {
                "status": liq_stats.status,
                "long_liquidations": liq_stats.long_liquidations,
                "short_liquidations": liq_stats.short_liquidations,
                "total_long_volume": liq_stats.total_long_volume_usd,
                "total_short_volume": liq_stats.total_short_volume_usd,
            }
        except Exception as e:
            data["liquidations"] = {"error": str(e)}

        # Market indicators
        try:
            market_summary = self.market_tracker.get_summary()
            if market_summary:
                data["market_indicators"] = {
                    "oi": market_summary.oi.current_oi_usd,
                    "oi_trend": market_summary.oi.trend,
                    "oi_velocity": market_summary.oi.velocity_percent_per_min,
                    "funding_rate": market_summary.funding.current_rate,
                    "funding_trend": market_summary.funding.trend,
                    "basis": market_summary.basis.current_basis_percent,
                    "basis_status": market_summary.basis.status,
                }
        except Exception as e:
            data["market_indicators"] = {"error": str(e)}

        # Multi-timeframe candles
        try:
            candles_data = {}
            for interval in ['1m', '5m', '15m', '1h']:
                metrics = self.candle_aggregator.get_metrics(interval)
                if metrics and metrics.current_candle:
                    candles_data[interval] = {
                        "return_pct": metrics.return_pct,
                        "volume_vs_avg": metrics.volume_vs_avg,
                        "atr": metrics.atr,
                        "realized_vol": metrics.realized_vol,
                        "close": metrics.current_candle.close,
                        "high": metrics.current_candle.high,
                        "low": metrics.current_candle.low,
                        "volume": metrics.current_candle.volume,
                    }
            if candles_data:
                data["candles"] = candles_data
        except Exception as e:
            data["candles"] = {"error": str(e)}

        # Volatility metrics
        try:
            # Get ATR and realized vol from candle metrics
            metrics_1m = self.candle_aggregator.get_metrics('1m')
            metrics_5m = self.candle_aggregator.get_metrics('5m')

            if metrics_1m and metrics_5m:
                vol_metrics = self.volatility_tracker.calculate_metrics(
                    atr_1m=metrics_1m.atr,
                    atr_5m=metrics_5m.atr,
                    realized_vol_1m=metrics_1m.realized_vol,
                    realized_vol_5m=metrics_5m.realized_vol,
                )
                data["volatility"] = {
                    "atr_1m": vol_metrics.atr_1m,
                    "atr_5m": vol_metrics.atr_5m,
                    "realized_vol_1m": vol_metrics.realized_vol_1m,
                    "realized_vol_5m": vol_metrics.realized_vol_5m,
                    "regime": vol_metrics.regime,
                    "percentile": vol_metrics.percentile,
                }
        except Exception as e:
            data["volatility"] = {"error": str(e)}

        # Multi-timeframe trade flow
        try:
            trade_flow_mtf = self.trade_tracker.get_multi_timeframe_stats()
            data["trade_flow_multi"] = {}
            for window, stats in trade_flow_mtf.items():
                sweep = detect_sweep_direction(stats, threshold=0.65)
                data["trade_flow_multi"][window] = {
                    "trade_count": stats.trade_count,
                    "total_volume": stats.total_volume_usd,
                    "buy_volume": stats.buy_volume_usd,
                    "sell_volume": stats.sell_volume_usd,
                    "buy_ratio": stats.buy_ratio,
                    "sell_ratio": stats.sell_ratio,
                    "sweep_direction": sweep,
                    "largest": stats.largest_trade_usd,
                    "median": stats.median_trade_usd,
                    "average": stats.average_trade_usd,
                }
        except Exception as e:
            data["trade_flow_multi"] = {"error": str(e)}

        # Multi-timeframe liquidations
        try:
            liq_mtf = self.liq_detector.get_multi_timeframe_stats()
            data["liquidations_multi"] = {}
            for window, stats in liq_mtf.items():
                data["liquidations_multi"][window] = {
                    "status": stats.status,
                    "long_liquidations": stats.long_liquidations,
                    "short_liquidations": stats.short_liquidations,
                    "total_long_volume": stats.total_long_volume_usd,
                    "total_short_volume": stats.total_short_volume_usd,
                }
        except Exception as e:
            data["liquidations_multi"] = {"error": str(e)}

        # Multi-timeframe OI
        try:
            oi_mtf = self.market_tracker.get_multi_timeframe_oi()
            data["oi_multi"] = {}
            for window, oi_stats in oi_mtf.items():
                if oi_stats:
                    data["oi_multi"][window] = {
                        "change_percent": oi_stats.change_percent,
                        "trend": oi_stats.trend,
                        "velocity": oi_stats.velocity_percent_per_min,
                    }
        except Exception as e:
            data["oi_multi"] = {"error": str(e)}

        # Session/Daily Context
        try:
            session_ctx = self.session_tracker.get_context()
            if session_ctx:
                data["session_context"] = {
                    "daily_high": session_ctx.daily_high,
                    "daily_low": session_ctx.daily_low,
                    "current_price": session_ctx.current_price,
                    "pct_from_low": session_ctx.pct_from_low,
                    "pct_from_high": session_ctx.pct_from_high,
                    "pct_through_range": session_ctx.pct_through_range,
                    "session_vwap": session_ctx.session_vwap,
                    "distance_from_vwap_bps": session_ctx.distance_from_vwap_bps,
                    "session_volume_usd": session_ctx.session_volume_usd,
                    "last_1h_volume_usd": session_ctx.last_1h_volume_usd,
                    "last_4h_volume_usd": session_ctx.last_4h_volume_usd,
                    "hyperliquid_24h_volume_usd": self.hyperliquid_24h_volume,
                    "hyperliquid_1h_volume_usd": self.hyperliquid_1h_volume,
                    "hyperliquid_4h_volume_usd": self.hyperliquid_4h_volume,
                    "session_duration_hours": session_ctx.session_duration_hours,
                }
        except Exception as e:
            data["session_context"] = {"error": str(e)}

        # Regime detection
        try:
            # Gather inputs from existing data
            ret_1m = data.get("candles", {}).get("1m", {}).get("return_pct", 0.0)
            ret_5m = data.get("candles", {}).get("5m", {}).get("return_pct", 0.0)
            ret_15m = data.get("candles", {}).get("15m", {}).get("return_pct", None)

            spread_bps = data.get("orderbook", {}).get("spread_bps", 10.0)
            l5_depth_bid = data.get("orderbook", {}).get("l5_depth_bid", 50000.0)
            l5_depth_ask = data.get("orderbook", {}).get("l5_depth_ask", 50000.0)

            vol_regime = data.get("volatility", {}).get("regime", "normal")

            buy_ratio = data.get("trade_flow", {}).get("buy_ratio", 0.5)

            # Use 5m window for regime detection (balanced between responsive and stable)
            liq_5m = data.get("liquidations_multi", {}).get("5m", {})
            liq_count = liq_5m.get("long_liquidations", 0) + liq_5m.get("short_liquidations", 0)
            long_liq_count = liq_5m.get("long_liquidations", 0)
            short_liq_count = liq_5m.get("short_liquidations", 0)

            funding_rate = data.get("market_indicators", {}).get("funding_rate", None)
            oi_velocity = data.get("market_indicators", {}).get("oi_velocity", None)

            # Detect regimes
            regime = self.regime_detector.detect_all(
                ret_1m=ret_1m,
                ret_5m=ret_5m,
                ret_15m=ret_15m,
                spread_bps=spread_bps,
                l5_depth_bid=l5_depth_bid,
                l5_depth_ask=l5_depth_ask,
                vol_regime=vol_regime,
                buy_ratio=buy_ratio,
                liq_count=liq_count,
                long_liq_count=long_liq_count,
                short_liq_count=short_liq_count,
                funding_rate=funding_rate,
                oi_velocity=oi_velocity,
            )

            data["regime"] = {
                "trend_regime": regime.trend_regime,
                "trend_strength": regime.trend_strength,
                "liquidity_regime": regime.liquidity_regime,
                "market_regime": regime.market_regime,
            }
        except Exception as e:
            data["regime"] = {"error": str(e)}

        # Slippage estimates
        try:
            if self.orderbook and self.orderbook.bids and self.orderbook.asks:
                # Convert orderbook levels to slippage estimator format
                bids = [
                    SlippageOrderBookLevel(
                        price=level.price,
                        size=level.size,
                        total_usd=level.notional_usd
                    )
                    for level in self.orderbook.bids.levels[:20]  # Use top 20 levels
                ]
                asks = [
                    SlippageOrderBookLevel(
                        price=level.price,
                        size=level.size,
                        total_usd=level.notional_usd
                    )
                    for level in self.orderbook.asks.levels[:20]  # Use top 20 levels
                ]

                # Standard trade sizes
                trade_sizes = [500.0, 1000.0, 5000.0]

                estimates = self.slippage_estimator.estimate_for_sizes(
                    bids=bids,
                    asks=asks,
                    trade_sizes_usd=trade_sizes,
                    best_bid=self.orderbook.bids.best_price,
                    best_ask=self.orderbook.asks.best_price,
                    spread_bps=data.get("orderbook", {}).get("spread_bps", 10.0),
                )

                # Format for API response
                slippage_data = {}
                for size_label, size_estimates in estimates.items():
                    buy_est = size_estimates["buy"]
                    sell_est = size_estimates["sell"]

                    slippage_data[size_label] = {
                        "buy": {
                            "avg_fill_price": buy_est.avg_fill_price,
                            "slippage_bps": buy_est.slippage_bps,
                            "round_trip_cost_bps": buy_est.round_trip_cost_bps,
                            "is_feasible": buy_est.is_feasible,
                            "liquidity_used_pct": buy_est.liquidity_used_pct,
                        },
                        "sell": {
                            "avg_fill_price": sell_est.avg_fill_price,
                            "slippage_bps": sell_est.slippage_bps,
                            "round_trip_cost_bps": sell_est.round_trip_cost_bps,
                            "is_feasible": sell_est.is_feasible,
                            "liquidity_used_pct": sell_est.liquidity_used_pct,
                        },
                        "spread_bps": buy_est.spread_bps,
                        "fee_bps": buy_est.fee_bps,
                    }

                data["slippage"] = slippage_data
        except Exception as e:
            import traceback
            print(f"[ERROR] Slippage calculation failed: {e}")
            traceback.print_exc()
            data["slippage"] = {"error": str(e)}

        # Crowding flags
        try:
            market_indicators = data.get("market_indicators", {})
            if market_indicators and "error" not in market_indicators:
                crowding = self.crowding_detector.detect(
                    oi_trend=market_indicators.get("oi_trend", "flat"),
                    oi_velocity=market_indicators.get("oi_velocity", 0.0),
                    funding_rate=market_indicators.get("funding_rate", 0.0),
                    funding_trend=market_indicators.get("funding_trend", "stable"),
                    basis_percent=market_indicators.get("basis", 0.0),
                    basis_status=market_indicators.get("basis_status", "fair"),
                )

                data["crowding"] = {
                    "crowded_long": crowding.crowded_long,
                    "crowded_short": crowding.crowded_short,
                    "long_crowding_score": crowding.long_crowding_score,
                    "short_crowding_score": crowding.short_crowding_score,
                    "interpretation": crowding.interpretation,
                }
        except Exception as e:
            data["crowding"] = {"error": str(e)}

        # System Status - check data quality and module health
        try:
            current_time = time.time()

            # Check if we have recent data from each module
            has_orderbook = "orderbook" in data and "error" not in data["orderbook"]
            has_trades = "trade_flow" in data and "error" not in data["trade_flow"]
            has_liquidations = "liquidations" in data and "error" not in data["liquidations"]
            has_market_indicators = "market_indicators" in data and "error" not in data["market_indicators"]
            has_candles = "candles" in data and "error" not in data["candles"]
            has_session_context = "session_context" in data and "error" not in data["session_context"]

            # Check if orderbook is recent (within last 5 seconds)
            orderbook_fresh = False
            if self.orderbook and self.last_orderbook_update_time:
                orderbook_age = current_time - self.last_orderbook_update_time
                orderbook_fresh = orderbook_age < 5.0

            # Check if we've received trades recently (within last 60 seconds)
            trades_fresh = False
            if has_trades:
                trade_count = data["trade_flow"].get("trade_count", 0)
                trades_fresh = trade_count > 0

            # Check if market indicators are present
            market_data_fresh = has_market_indicators and has_liquidations

            # Check if Hyperliquid volumes were fetched
            volumes_fresh = (
                self.hyperliquid_24h_volume is not None and
                self.hyperliquid_1h_volume is not None and
                self.hyperliquid_4h_volume is not None
            )

            # Overall data quality
            data_quality_ok = (
                has_orderbook and orderbook_fresh and
                has_trades and
                has_candles and
                has_session_context and
                market_data_fresh
            )

            # Feed connection status (if orderbook is recent, feed is connected)
            feed_connected = orderbook_fresh

            data["system_status"] = {
                "data_quality_ok": data_quality_ok,
                "feed_connected": feed_connected,
                "modules": {
                    "orderbook": {"ok": has_orderbook, "fresh": orderbook_fresh},
                    "trades": {"ok": has_trades, "fresh": trades_fresh},
                    "liquidations": {"ok": has_liquidations, "fresh": market_data_fresh},
                    "market_indicators": {"ok": has_market_indicators, "fresh": market_data_fresh},
                    "candles": {"ok": has_candles, "fresh": has_candles},
                    "session_context": {"ok": has_session_context, "fresh": has_session_context},
                    "hyperliquid_volumes": {"ok": volumes_fresh, "fresh": volumes_fresh},
                },
                "last_check": current_time,
            }
        except Exception as e:
            data["system_status"] = {
                "data_quality_ok": False,
                "feed_connected": False,
                "error": str(e)
            }

        # Cross-asset context (BTC/ETH)
        try:
            # Update cross-asset tracker with latest prices
            self.cross_asset_tracker.fetch_and_update()

            # Get context for all tracked assets
            cross_asset_data = {}
            all_context = self.cross_asset_tracker.get_all_context()

            for symbol, ctx in all_context.items():
                cross_asset_data[symbol] = {
                    "current_price": ctx.current_price,
                    "return_1m": ctx.return_1m,
                    "return_5m": ctx.return_5m,
                    "return_15m": ctx.return_15m,
                    "return_1h": ctx.return_1h,
                    "volatility_regime": ctx.volatility_regime,
                    "trend_regime": ctx.trend_regime,
                    "volume_24h": ctx.volume_24h,
                }

            # Add overall market sentiment
            market_sentiment = self.cross_asset_tracker.get_market_sentiment()

            data["cross_asset_context"] = {
                "assets": cross_asset_data,
                "market_sentiment": market_sentiment,
            }
        except Exception as e:
            data["cross_asset_context"] = {"error": str(e)}

        return data


# Global analytics engine
analytics_engine: AnalyticsEngine = None
hyperliquid_client: HyperliquidClient = None


async def start_analytics():
    """Start analytics engine in background."""
    global analytics_engine, hyperliquid_client

    coin = os.getenv("HYPERLIQUID_COIN", "SOL")
    network_name = os.getenv("HYPERLIQUID_NETWORK", "mainnet").lower()
    network = TESTNET if network_name == "testnet" else MAINNET

    print(f"Starting analytics for {coin} on {network.name}...")

    config = HyperliquidClientConfig.for_coin(coin, network=network)
    transport = HyperliquidSdkTransport()
    hyperliquid_client = HyperliquidClient(coin=coin, config=config, transport=transport)

    analytics_engine = AnalyticsEngine()

    # Preload historical candle data
    analytics_engine.preload_historical_data(coin)

    await analytics_engine.start_volume_updater(coin)

    # Start streaming in background thread
    import threading

    def _stream_loop():
        try:
            hyperliquid_client.connect_and_subscribe()
        except Exception as exc:
            print(f"[stream_loop] error: {exc}")

    stream_thread = threading.Thread(target=_stream_loop, daemon=True)
    stream_thread.start()

    # Process events in background
    async def process_events():
        import time
        while True:
            for event in hyperliquid_client.iter_events():
                analytics_engine.process_event(event)
            await asyncio.sleep(0.01)

    asyncio.create_task(process_events())


@app.on_event("startup")
async def startup_event():
    """Start analytics on server startup."""
    await start_analytics()


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Hyperliquid Analytics API", "version": "1.0.0"}


@app.get("/api/analytics")
async def get_analytics():
    """Get current analytics data."""
    if analytics_engine is None:
        return {"error": "Analytics engine not initialized"}
    return analytics_engine.get_analytics_data()


@app.websocket("/ws/analytics")
async def websocket_analytics(websocket: WebSocket, coin: str = "SOL"):
    """WebSocket endpoint for real-time analytics.

    Args:
        coin: The cryptocurrency symbol to track (default: SOL)
    """
    await websocket.accept()

    # Create dedicated analytics engine and client for this connection
    connection_analytics_engine = None
    connection_hyperliquid_client = None
    stream_thread = None

    try:
        print(f"[WebSocket] Client connected, initializing analytics for {coin}...")

        network_name = os.getenv("HYPERLIQUID_NETWORK", "mainnet").lower()
        network = TESTNET if network_name == "testnet" else MAINNET

        config = HyperliquidClientConfig.for_coin(coin, network=network)
        transport = HyperliquidSdkTransport()
        connection_hyperliquid_client = HyperliquidClient(coin=coin, config=config, transport=transport)

        connection_analytics_engine = AnalyticsEngine()

        # Preload historical candle data
        connection_analytics_engine.preload_historical_data(coin)

        await connection_analytics_engine.start_volume_updater(coin)

        # Start streaming in background thread
        def _stream_loop():
            try:
                connection_hyperliquid_client.connect_and_subscribe()
            except Exception as exc:
                print(f"[stream_loop] error for {coin}: {exc}")

        stream_thread = threading.Thread(target=_stream_loop, daemon=True)
        stream_thread.start()

        # Process events in background
        async def process_events():
            while True:
                try:
                    for event in connection_hyperliquid_client.iter_events():
                        connection_analytics_engine.process_event(event)
                    await asyncio.sleep(0.01)
                except Exception as e:
                    print(f"[process_events] error: {e}")
                    break

        # Start event processing
        event_task = asyncio.create_task(process_events())

        # Stream analytics data to client
        while True:
            if connection_analytics_engine is not None:
                data = connection_analytics_engine.get_analytics_data()
                await websocket.send_json(data)

            await asyncio.sleep(1)  # Send update every second

    except WebSocketDisconnect:
        print(f"[WebSocket] Client disconnected from {coin}")
    except Exception as e:
        print(f"[WebSocket] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if 'event_task' in locals():
            event_task.cancel()
        if connection_analytics_engine:
            connection_analytics_engine.stop_volume_updater()
        if connection_hyperliquid_client:
            try:
                connection_hyperliquid_client.close()
            except:
                pass
        print(f"[WebSocket] Cleaned up connection for {coin}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
