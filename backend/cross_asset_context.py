"""Cross-asset context tracker for BTC and ETH.

Tracks price movements, returns, volatility regime, and trend regime
for major crypto assets to provide broader market context.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Dict, Any
from collections import deque

import requests


@dataclass
class AssetSnapshot:
    """Snapshot of asset price and metrics at a point in time."""
    timestamp_ms: float
    price: float
    volume_24h: Optional[float] = None


@dataclass
class AssetContext:
    """Context metrics for a single asset."""
    symbol: str
    current_price: float
    return_1m: float
    return_5m: float
    return_15m: float
    return_1h: float
    volatility_regime: str  # 'low', 'normal', 'high'
    trend_regime: str  # 'up', 'down', 'range'
    volume_24h: Optional[float] = None


class CrossAssetContextTracker:
    """Tracks BTC and ETH context to provide market-wide signals."""

    def __init__(
        self,
        assets: list[str] = None,
        low_vol_threshold_pct: float = 0.5,
        high_vol_threshold_pct: float = 2.0,
        trend_threshold_pct: float = 0.3,
    ):
        """Initialize cross-asset tracker.

        Args:
            assets: List of asset symbols to track (default: ["BTC", "ETH"])
            low_vol_threshold_pct: Below this 1h return %, consider low volatility
            high_vol_threshold_pct: Above this 1h return %, consider high volatility
            trend_threshold_pct: Above this 15m return %, consider trending
        """
        self.assets = assets or ["BTC", "ETH"]
        self.low_vol_threshold = low_vol_threshold_pct
        self.high_vol_threshold = high_vol_threshold_pct
        self.trend_threshold = trend_threshold_pct

        # Price history for each asset: {asset: deque of AssetSnapshot}
        self.price_history: Dict[str, deque] = {
            asset: deque(maxlen=3600)  # Keep up to 1 hour of 1-second snapshots
            for asset in self.assets
        }

        # Last fetch time to avoid hammering the API
        self.last_fetch_time = 0.0
        self.fetch_interval_seconds = 1.0  # Fetch every 1 second

    def fetch_and_update(self) -> None:
        """Fetch latest prices from Hyperliquid API and update history."""
        current_time = time.time()

        # Rate limit
        if current_time - self.last_fetch_time < self.fetch_interval_seconds:
            return

        try:
            # Fetch all asset contexts in one API call
            response = requests.post(
                "https://api.hyperliquid.xyz/info",
                json={"type": "metaAndAssetCtxs"},
                timeout=5
            )
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list) and len(data) == 2:
                universe = data[0]  # Meta
                contexts = data[1]  # Asset contexts

                # Process each tracked asset
                for asset in self.assets:
                    # Find asset index
                    coin_index = None
                    for idx, coin_meta in enumerate(universe.get("universe", [])):
                        if coin_meta.get("name") == asset:
                            coin_index = idx
                            break

                    if coin_index is not None and coin_index < len(contexts):
                        ctx = contexts[coin_index]
                        mark_px = ctx.get("markPx")
                        day_volume = ctx.get("dayNtlVlm")

                        if mark_px:
                            price = float(mark_px)
                            volume_24h = float(day_volume) if day_volume else None

                            snapshot = AssetSnapshot(
                                timestamp_ms=current_time * 1000,
                                price=price,
                                volume_24h=volume_24h
                            )

                            self.price_history[asset].append(snapshot)

            self.last_fetch_time = current_time

        except Exception as e:
            print(f"[ERROR] Failed to fetch cross-asset data: {e}")

    def _calculate_return(
        self,
        asset: str,
        lookback_seconds: float
    ) -> Optional[float]:
        """Calculate return over a lookback period.

        Returns:
            Return as percentage, or None if insufficient data
        """
        history = self.price_history.get(asset)
        if not history or len(history) < 2:
            return None

        current_time = time.time() * 1000
        cutoff_time = current_time - (lookback_seconds * 1000)

        # Get current price (most recent)
        current_snapshot = history[-1]

        # Find snapshot closest to lookback time
        lookback_snapshot = None
        for snapshot in history:
            if snapshot.timestamp_ms >= cutoff_time:
                lookback_snapshot = snapshot
                break

        if lookback_snapshot is None:
            # Not enough history
            return None

        # Calculate return
        price_change = current_snapshot.price - lookback_snapshot.price
        return_pct = (price_change / lookback_snapshot.price) * 100

        return return_pct

    def _determine_volatility_regime(self, return_1h: Optional[float]) -> str:
        """Determine volatility regime based on 1h return magnitude."""
        if return_1h is None:
            return "unknown"

        abs_return = abs(return_1h)

        if abs_return < self.low_vol_threshold:
            return "low"
        elif abs_return > self.high_vol_threshold:
            return "high"
        else:
            return "normal"

    def _determine_trend_regime(
        self,
        return_1m: Optional[float],
        return_5m: Optional[float],
        return_15m: Optional[float]
    ) -> str:
        """Determine trend regime based on multi-timeframe returns."""
        if return_15m is None:
            return "unknown"

        # Use 15m as primary signal
        if return_15m > self.trend_threshold:
            # Confirm with 5m
            if return_5m and return_5m > 0:
                return "up"
        elif return_15m < -self.trend_threshold:
            # Confirm with 5m
            if return_5m and return_5m < 0:
                return "down"

        return "range"

    def get_context(self, asset: str) -> Optional[AssetContext]:
        """Get current context for a specific asset.

        Args:
            asset: Asset symbol (e.g., "BTC", "ETH")

        Returns:
            AssetContext or None if insufficient data
        """
        history = self.price_history.get(asset)
        if not history or len(history) == 0:
            return None

        # Get current price and volume
        latest = history[-1]
        current_price = latest.price
        volume_24h = latest.volume_24h

        # Calculate returns across timeframes
        return_1m = self._calculate_return(asset, 60)  # 1 minute
        return_5m = self._calculate_return(asset, 300)  # 5 minutes
        return_15m = self._calculate_return(asset, 900)  # 15 minutes
        return_1h = self._calculate_return(asset, 3600)  # 1 hour

        # Determine regimes
        vol_regime = self._determine_volatility_regime(return_1h)
        trend_regime = self._determine_trend_regime(return_1m, return_5m, return_15m)

        return AssetContext(
            symbol=asset,
            current_price=current_price,
            return_1m=return_1m if return_1m is not None else 0.0,
            return_5m=return_5m if return_5m is not None else 0.0,
            return_15m=return_15m if return_15m is not None else 0.0,
            return_1h=return_1h if return_1h is not None else 0.0,
            volatility_regime=vol_regime,
            trend_regime=trend_regime,
            volume_24h=volume_24h,
        )

    def get_all_context(self) -> Dict[str, AssetContext]:
        """Get context for all tracked assets.

        Returns:
            Dictionary mapping asset symbol to AssetContext
        """
        result = {}
        for asset in self.assets:
            ctx = self.get_context(asset)
            if ctx:
                result[asset] = ctx
        return result

    def get_market_sentiment(self) -> str:
        """Aggregate market sentiment from BTC and ETH.

        Returns:
            Overall market sentiment: 'bullish', 'bearish', 'neutral', 'mixed'
        """
        btc_ctx = self.get_context("BTC")
        eth_ctx = self.get_context("ETH")

        if not btc_ctx or not eth_ctx:
            return "unknown"

        # Check if both are trending in same direction
        if btc_ctx.trend_regime == "up" and eth_ctx.trend_regime == "up":
            return "bullish"
        elif btc_ctx.trend_regime == "down" and eth_ctx.trend_regime == "down":
            return "bearish"
        elif btc_ctx.trend_regime == "range" and eth_ctx.trend_regime == "range":
            return "neutral"
        else:
            return "mixed"
