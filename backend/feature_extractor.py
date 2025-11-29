import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class FeatureExtractor:
    """
    Extracts numerical features from market data for AI models.
    Ported from ContextBuilder logic.
    """

    def _calculate_buy_sell_ratio(self, buy_val: float, sell_val: float) -> float:
        """Calculate buy/sell ratio safely."""
        if sell_val > 0 and buy_val >= 0:
            return buy_val / sell_val
        elif buy_val > 0 and sell_val == 0:
            return 999.0
        else:
            return 0.0

    def _get_latest_candle(self, candles: Dict[str, Any], key: str) -> Dict[str, Any]:
        """Helper to safely extract latest candle."""
        data = candles.get(key) or {}
        if isinstance(data, list):
            return data[-1] if data else {}
        return data

    def extract_features(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Extract numerical features for ML models from analytics structure.
        """
        # Extract nested data (None-guarded)
        candles = market_data.get("candles") or {}
        
        candle_1m = self._get_latest_candle(candles, "1m")
        candle_5m = self._get_latest_candle(candles, "5m")
        candle_15m = self._get_latest_candle(candles, "15m")
        candle_1h = self._get_latest_candle(candles, "1h")
        
        # Rolling window data (if available)
        rolling_1h = self._get_latest_candle(candles, "rolling_1h")
        rolling_4h = self._get_latest_candle(candles, "rolling_4h")

        orderbook = market_data.get("orderbook") or {}
        trade_flow = market_data.get("trade_flow") or {}
        trade_flow_multi = market_data.get("trade_flow_multi") or {}
        volatility = market_data.get("volatility") or {}
        liquidations_multi = market_data.get("liquidations_multi") or {}
        liq_1m = liquidations_multi.get("1m") or {}
        market_indicators = market_data.get("market_indicators") or {}
        session_context = market_data.get("session_context") or {}
        depth_decay = market_data.get("depth_decay") or {}
        crowding = market_data.get("crowding") or {}
        vpin = market_data.get("vpin") or {}
        regime = market_data.get("regime") or {}

        # Calculate buy/sell ratio
        buy_val = trade_flow.get("buy_ratio")
        sell_val = trade_flow.get("sell_ratio")
        
        if buy_val is None or sell_val is None:
            buy_val = trade_flow.get("buy_volume", 0.0)
            sell_val = trade_flow.get("sell_volume", 0.0)
            
        buy_val = float(buy_val) if buy_val is not None else 0.0
        sell_val = float(sell_val) if sell_val is not None else 0.0

        features = {
            # Price momentum (multi-timeframe)
            "momentum_20s": trade_flow_multi.get("20s", {}).get("return_pct", 0.0), # Note: 20s might not be in trade_flow_multi keys in AnalyticsEngine, check keys
            "momentum_1m": candle_1m.get("return_pct", 0.0),
            "momentum_5m": candle_5m.get("return_pct", 0.0),
            "momentum_15m": candle_15m.get("return_pct", 0.0),
            "momentum_1h": candle_1h.get("return_pct", 0.0),
            
            # Rolling momentum
            "rolling_return_1h": rolling_1h.get("return_pct", 0.0),
            "rolling_return_4h": rolling_4h.get("return_pct", 0.0),

            # Volume & Flow Quality
            "volume_ratio": candle_1m.get("volume_vs_avg", 1.0),
            "session_volume": session_context.get("session_volume_usd", 0.0),
            "vpin": vpin.get("vpin", 0.0),

            # Orderbook & Microstructure
            "spread_bp": orderbook.get("spread_bps", 0.0),
            "orderbook_imbalance": orderbook.get("l5_imbalance", 0.0),
            "depth_decay_bid": depth_decay.get("bid_decay_percent", 0.0),
            "depth_decay_ask": depth_decay.get("ask_decay_percent", 0.0),
            "bid_slope": depth_decay.get("bid_slope", 0.0),
            "ask_slope": depth_decay.get("ask_slope", 0.0),

            # Flow (multi-timeframe)
            # Note: AnalyticsEngine trade_flow_multi keys are likely '1m', '5m', '15m', '1h'. '20s' might be missing.
            "net_flow_20s": trade_flow_multi.get("20s", {}).get("buy_volume", 0.0) - trade_flow_multi.get("20s", {}).get("sell_volume", 0.0),
            "net_flow_1m": trade_flow_multi.get("1m", {}).get("buy_volume", 0.0) - trade_flow_multi.get("1m", {}).get("sell_volume", 0.0),
            "net_flow_5m": trade_flow_multi.get("5m", {}).get("buy_volume", 0.0) - trade_flow_multi.get("5m", {}).get("sell_volume", 0.0),
            "buy_sell_ratio": self._calculate_buy_sell_ratio(buy_val, sell_val),

            # Volatility & Trend Strength
            "atr_1m": volatility.get("atr_1m", 0.0),
            "atr_5m": volatility.get("atr_5m", 0.0),
            "realized_vol_1m": volatility.get("realized_vol_1m", 0.0),
            "realized_vol_5m": volatility.get("realized_vol_5m", 0.0),
            "adx_14": regime.get("adx_strength", 0.0),
            "trend_strength": regime.get("trend_strength", 0.0),

            # Liquidations
            "liq_1m_long": liq_1m.get("long_liquidations", 0),
            "liq_1m_short": liq_1m.get("short_liquidations", 0),
            "liq_volume_long": liq_1m.get("total_long_volume", 0.0),
            "liq_volume_short": liq_1m.get("total_short_volume", 0.0),

            # Market Indicators
            "open_interest_current": market_indicators.get("oi", 0.0),
            "funding_rate": market_indicators.get("funding_rate", 0.0),
            "basis_pct": market_indicators.get("basis", 0.0),

            # Session Context
            "distance_from_vwap_bp": session_context.get("distance_from_vwap_bps", 0.0),
            "distance_from_high_pct": session_context.get("pct_from_high", 0.0),
            "distance_from_low_pct": session_context.get("pct_from_low", 0.0),

            # Crowding
            "crowding_score_long": crowding.get("long_crowding_score", 0.0),
            "crowding_score_short": crowding.get("short_crowding_score", 0.0),
        }

        return features
