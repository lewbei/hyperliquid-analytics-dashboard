"""Market regime detection.

This module detects different market regimes to help the AI understand
current market conditions at a glance:

- Trend Regime: up/down/range (directional bias)
- Trend Strength: 0-1 score (how strong the trend is)
- Liquidity Regime: high/normal/thin (orderbook quality)
- Market Regime: overall market state (normal/trend/chop/liquidation_event/short_squeeze/crash)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


TrendRegime = Literal["up", "down", "range"]
LiquidityRegime = Literal["high", "normal", "thin"]
MarketRegime = Literal["normal", "trend", "chop", "liquidation_event", "short_squeeze", "crash"]


@dataclass
class RegimeDetection:
    """Complete regime detection result."""

    # Trend analysis
    trend_regime: TrendRegime
    trend_strength: float  # 0.0 to 1.0

    # Liquidity analysis
    liquidity_regime: LiquidityRegime

    # Overall market regime
    market_regime: MarketRegime

    # Supporting details
    details: dict


class RegimeDetector:
    """Detects market regimes from various market signals."""

    def __init__(
        self,
        trend_threshold_pct: float = 0.1,  # 0.1% move to consider directional
        strong_trend_threshold_pct: float = 0.5,  # 0.5% for strong trend
        range_threshold_pct: float = 0.05,  # < 0.05% = range

        # Liquidity thresholds
        tight_spread_bps: float = 5.0,  # < 5 bps = tight
        wide_spread_bps: float = 20.0,  # > 20 bps = wide
        deep_book_usd: float = 100000.0,  # > $100k L5 depth = deep
        thin_book_usd: float = 20000.0,  # < $20k L5 depth = thin

        # Liquidation thresholds
        elevated_liq_count: int = 3,
        high_liq_count: int = 10,
    ):
        """Initialize regime detector with configurable thresholds."""
        self.trend_threshold = trend_threshold_pct
        self.strong_trend_threshold = strong_trend_threshold_pct
        self.range_threshold = range_threshold_pct

        self.tight_spread_bps = tight_spread_bps
        self.wide_spread_bps = wide_spread_bps
        self.deep_book_usd = deep_book_usd
        self.thin_book_usd = thin_book_usd

        self.elevated_liq_count = elevated_liq_count
        self.high_liq_count = high_liq_count

    def detect_trend_regime(
        self,
        ret_1m: float,
        ret_5m: float,
        ret_15m: Optional[float] = None,
    ) -> tuple[TrendRegime, float]:
        """Detect trend regime and strength from multi-timeframe returns.

        Parameters
        ----------
        ret_1m : float
            1-minute return (%)
        ret_5m : float
            5-minute return (%)
        ret_15m : Optional[float]
            15-minute return (%) if available

        Returns
        -------
        tuple[TrendRegime, float]
            (trend_regime, trend_strength)
        """
        # Collect returns
        returns = [ret_1m, ret_5m]
        if ret_15m is not None:
            returns.append(ret_15m)

        # Calculate average return
        avg_return = sum(returns) / len(returns)

        # Check if returns agree on direction
        positive_count = sum(1 for r in returns if r > self.trend_threshold)
        negative_count = sum(1 for r in returns if r < -self.trend_threshold)

        # Determine regime
        if abs(avg_return) < self.range_threshold:
            regime = "range"
        elif positive_count >= 2:  # At least 2 timeframes agree on up
            regime = "up"
        elif negative_count >= 2:  # At least 2 timeframes agree on down
            regime = "down"
        else:
            regime = "range"

        # Calculate strength (0-1)
        # Strength based on magnitude and alignment
        magnitude_strength = min(abs(avg_return) / self.strong_trend_threshold, 1.0)

        alignment = max(positive_count, negative_count) / len(returns)

        strength = magnitude_strength * alignment

        return regime, strength

    def detect_liquidity_regime(
        self,
        spread_bps: float,
        l5_depth_bid: float,
        l5_depth_ask: float,
    ) -> LiquidityRegime:
        """Detect liquidity regime from orderbook metrics.

        Parameters
        ----------
        spread_bps : float
            Current spread in basis points
        l5_depth_bid : float
            Total bid depth in top 5 levels (USD)
        l5_depth_ask : float
            Total ask depth in top 5 levels (USD)

        Returns
        -------
        LiquidityRegime
            Liquidity regime classification
        """
        avg_depth = (l5_depth_bid + l5_depth_ask) / 2

        # High liquidity: tight spread AND deep book
        if spread_bps < self.tight_spread_bps and avg_depth > self.deep_book_usd:
            return "high"

        # Thin liquidity: wide spread OR thin book
        if spread_bps > self.wide_spread_bps or avg_depth < self.thin_book_usd:
            return "thin"

        # Normal otherwise
        return "normal"

    def detect_market_regime(
        self,
        # Trend inputs
        trend_regime: TrendRegime,
        trend_strength: float,

        # Volatility inputs
        vol_regime: str,  # "low", "normal", "high"

        # Flow inputs
        buy_ratio: float,  # 0-1

        # Liquidation inputs
        liq_count: int,
        long_liq_count: int,
        short_liq_count: int,

        # Market indicators
        funding_rate: Optional[float] = None,
        oi_velocity: Optional[float] = None,
    ) -> MarketRegime:
        """Detect overall market regime from combined signals.

        Parameters
        ----------
        trend_regime : TrendRegime
            Current trend regime
        trend_strength : float
            Trend strength (0-1)
        vol_regime : str
            Volatility regime ("low", "normal", "high")
        buy_ratio : float
            Buy/sell ratio from trade flow (0-1)
        liq_count : int
            Total liquidation count (recent window)
        long_liq_count : int
            Long liquidation count
        short_liq_count : int
            Short liquidation count
        funding_rate : Optional[float]
            Funding rate (%)
        oi_velocity : Optional[float]
            OI velocity (% per minute)

        Returns
        -------
        MarketRegime
            Overall market regime classification
        """
        # Liquidation event detection
        if liq_count >= self.high_liq_count:
            # Short squeeze: heavy short liq + up trend + high vol
            if short_liq_count > long_liq_count * 1.5 and trend_regime == "up":
                return "short_squeeze"

            # Crash: heavy long liq + down trend + high vol
            if long_liq_count > short_liq_count * 1.5 and trend_regime == "down":
                return "crash"

            # General liquidation event
            return "liquidation_event"

        # Trend regime: strong directional move with aligned flow
        if trend_strength > 0.6:
            # Check if flow aligns with trend
            if trend_regime == "up" and buy_ratio > 0.6:
                return "trend"
            if trend_regime == "down" and buy_ratio < 0.4:
                return "trend"

        # Chop: high vol but rangebound
        if vol_regime == "high" and trend_regime == "range":
            return "chop"

        # Normal: low/normal vol, balanced
        return "normal"

    def detect_all(
        self,
        # Returns
        ret_1m: float,
        ret_5m: float,
        ret_15m: Optional[float] = None,

        # Orderbook
        spread_bps: float = 10.0,
        l5_depth_bid: float = 50000.0,
        l5_depth_ask: float = 50000.0,

        # Volatility
        vol_regime: str = "normal",

        # Trade flow
        buy_ratio: float = 0.5,

        # Liquidations
        liq_count: int = 0,
        long_liq_count: int = 0,
        short_liq_count: int = 0,

        # Market indicators
        funding_rate: Optional[float] = None,
        oi_velocity: Optional[float] = None,
    ) -> RegimeDetection:
        """Detect all regimes from current market state.

        Parameters
        ----------
        All market state parameters

        Returns
        -------
        RegimeDetection
            Complete regime detection result
        """
        # Detect trend
        trend_regime, trend_strength = self.detect_trend_regime(
            ret_1m, ret_5m, ret_15m
        )

        # Detect liquidity
        liquidity_regime = self.detect_liquidity_regime(
            spread_bps, l5_depth_bid, l5_depth_ask
        )

        # Detect overall market regime
        market_regime = self.detect_market_regime(
            trend_regime=trend_regime,
            trend_strength=trend_strength,
            vol_regime=vol_regime,
            buy_ratio=buy_ratio,
            liq_count=liq_count,
            long_liq_count=long_liq_count,
            short_liq_count=short_liq_count,
            funding_rate=funding_rate,
            oi_velocity=oi_velocity,
        )

        # Build details
        details = {
            "returns": {
                "ret_1m": ret_1m,
                "ret_5m": ret_5m,
                "ret_15m": ret_15m,
            },
            "orderbook": {
                "spread_bps": spread_bps,
                "l5_depth_bid": l5_depth_bid,
                "l5_depth_ask": l5_depth_ask,
            },
            "volatility": vol_regime,
            "flow": {
                "buy_ratio": buy_ratio,
            },
            "liquidations": {
                "total": liq_count,
                "long": long_liq_count,
                "short": short_liq_count,
            },
        }

        return RegimeDetection(
            trend_regime=trend_regime,
            trend_strength=trend_strength,
            liquidity_regime=liquidity_regime,
            market_regime=market_regime,
            details=details,
        )


def format_regime_summary(regime: RegimeDetection) -> str:
    """Format regime detection as readable summary.

    Parameters
    ----------
    regime : RegimeDetection
        Regime detection result

    Returns
    -------
    str
        Formatted summary
    """
    lines = []
    lines.append("\nMarket Regime Detection")
    lines.append("=" * 80)

    lines.append(f"\nTrend Regime:      {regime.trend_regime.upper()}")
    lines.append(f"Trend Strength:    {regime.trend_strength:.2f} / 1.00")

    lines.append(f"\nLiquidity Regime:  {regime.liquidity_regime.upper()}")

    lines.append(f"\nMarket Regime:     {regime.market_regime.upper()}")

    lines.append("=" * 80)

    return "\n".join(lines)
