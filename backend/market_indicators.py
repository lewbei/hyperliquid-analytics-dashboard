"""Market indicators tracker.

This module tracks market-level indicators from activeAssetCtx feed:
- Open Interest (OI) and trend
- Funding Rate and trend
- Basis (perp premium/discount vs spot)

These indicators help understand market sentiment and positioning.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Optional, Literal


TrendDirection = Literal["up", "down", "flat"]


@dataclass
class ActiveAssetContext:
    """Market context data from activeAssetCtx feed.

    This mirrors the data structure from Hyperliquid's activeAssetCtx
    WebSocket subscription.
    """
    timestamp_ms: float
    coin: str

    # Open Interest
    open_interest_usd: float  # Total open interest in USD

    # Funding Rate
    funding_rate: float  # Current funding rate (8h rate)

    # Premium/Basis
    mark_price: float  # Perpetual mark price
    oracle_price: Optional[float] = None  # Spot/oracle price (if available)

    @property
    def basis_percent(self) -> Optional[float]:
        """Calculate basis (perp premium/discount vs spot) in percent.

        Basis = ((mark_price - oracle_price) / oracle_price) * 100

        Positive = perp trading at premium (bullish)
        Negative = perp trading at discount (bearish)
        """
        if self.oracle_price is None or self.oracle_price == 0:
            return None
        return ((self.mark_price - self.oracle_price) / self.oracle_price) * 100


@dataclass
class OIStats:
    """Open Interest statistics."""
    current_oi_usd: float
    trend: TrendDirection  # "up", "down", "flat"
    change_percent: float  # % change over window
    velocity_percent_per_min: float  # % change per minute


@dataclass
class FundingStats:
    """Funding Rate statistics."""
    current_rate: float  # Current funding rate
    trend: TrendDirection  # "up", "down", "flat"
    annualized_rate_percent: float  # Annualized funding rate %


@dataclass
class BasisStats:
    """Basis statistics."""
    current_basis_percent: float  # Current basis %
    status: str  # "Premium", "Discount", "Normal"


@dataclass
class MarketIndicatorsSummary:
    """Summary of all market indicators."""
    timestamp_ms: float
    coin: str

    oi: OIStats
    funding: FundingStats
    basis: BasisStats

    # Market interpretation
    interpretation: str  # Text interpretation of combined signals


class MarketIndicatorsTracker:
    """Tracks market indicators over time with multi-timeframe history."""

    def __init__(
        self,
        oi_window_seconds: float = 300.0,  # 5 minutes for OI trend
        oi_flat_threshold_percent: float = 0.5,  # 0.5% threshold for flat
        funding_flat_threshold: float = 0.0001,  # 0.01% threshold for flat
        basis_spike_threshold_percent: float = 0.1,  # 0.1% basis spike threshold
        max_history_seconds: float = 900.0,  # 15 minutes for history
    ):
        """Initialize market indicators tracker.

        Parameters:
        -----------
        oi_window_seconds : float, default 300.0
            Default time window for OI trend calculation (default 5 minutes)
        oi_flat_threshold_percent : float, default 0.5
            Percentage threshold for OI flat detection
        funding_flat_threshold : float, default 0.0001
            Absolute threshold for funding flat detection
        basis_spike_threshold_percent : float, default 0.1
            Basis threshold for spike detection
        max_history_seconds : float, default 900.0
            Maximum history to keep (15 minutes for multi-timeframe analysis)
        """
        self.oi_window_seconds = oi_window_seconds
        self.max_history_seconds = max_history_seconds
        self.oi_flat_threshold_percent = oi_flat_threshold_percent
        self.funding_flat_threshold = funding_flat_threshold
        self.basis_spike_threshold_percent = basis_spike_threshold_percent

        self.context_history: deque[ActiveAssetContext] = deque()

    def add_context(self, context: ActiveAssetContext) -> None:
        """Add a new market context observation."""
        self.context_history.append(context)
        self._cleanup_old_contexts()

    def _cleanup_old_contexts(self) -> None:
        """Remove contexts older than the retention window."""
        if not self.context_history:
            return

        # Keep data for max history window
        retention_window_ms = self.max_history_seconds * 1000

        current_time_ms = time.time() * 1000
        cutoff_time_ms = current_time_ms - retention_window_ms

        # Remove old contexts from the left
        while self.context_history and self.context_history[0].timestamp_ms < cutoff_time_ms:
            self.context_history.popleft()

    def get_oi_stats(self, window_seconds: Optional[float] = None) -> Optional[OIStats]:
        """Get Open Interest statistics for a specific time window.

        Parameters:
        -----------
        window_seconds : Optional[float]
            Time window in seconds (if None, uses default oi_window_seconds)

        Returns:
        --------
        Optional[OIStats]
            OI stats, or None if not enough data
        """
        self._cleanup_old_contexts()

        if not self.context_history:
            return None

        if window_seconds is None:
            window_seconds = self.oi_window_seconds

        latest = self.context_history[-1]
        current_oi = latest.open_interest_usd

        # Find OI at start of window
        window_start_ms = latest.timestamp_ms - (window_seconds * 1000)
        start_oi = None

        for ctx in self.context_history:
            if ctx.timestamp_ms >= window_start_ms:
                start_oi = ctx.open_interest_usd
                break

        if start_oi is None or start_oi == 0:
            # Not enough data or division by zero
            return OIStats(
                current_oi_usd=current_oi,
                trend="flat",
                change_percent=0.0,
                velocity_percent_per_min=0.0,
            )

        # Calculate change
        change_percent = ((current_oi - start_oi) / start_oi) * 100

        # Determine trend
        if abs(change_percent) < self.oi_flat_threshold_percent:
            trend = "flat"
        elif change_percent > 0:
            trend = "up"
        else:
            trend = "down"

        # Calculate velocity (% change per minute)
        time_elapsed_min = window_seconds / 60.0
        velocity_percent_per_min = change_percent / time_elapsed_min if time_elapsed_min > 0 else 0.0

        return OIStats(
            current_oi_usd=current_oi,
            trend=trend,
            change_percent=change_percent,
            velocity_percent_per_min=velocity_percent_per_min,
        )

    def get_funding_stats(self) -> Optional[FundingStats]:
        """Get Funding Rate statistics.

        Returns:
        --------
        Optional[FundingStats]
            Funding stats, or None if not enough data
        """
        if not self.context_history:
            return None

        latest = self.context_history[-1]
        current_rate = latest.funding_rate

        # Determine trend (usually stable unless major market move)
        if abs(current_rate) < self.funding_flat_threshold:
            trend = "flat"
        elif current_rate > 0:
            trend = "up"
        else:
            trend = "down"

        # Annualize funding rate
        # Hyperliquid uses 8-hour funding, so 3 periods per day
        # Annualized = funding_rate * 3 * 365 * 100 (to get %)
        annualized_rate_percent = current_rate * 3 * 365 * 100

        return FundingStats(
            current_rate=current_rate,
            trend=trend,
            annualized_rate_percent=annualized_rate_percent,
        )

    def get_basis_stats(self) -> Optional[BasisStats]:
        """Get Basis statistics.

        Returns:
        --------
        Optional[BasisStats]
            Basis stats, or None if not enough data
        """
        if not self.context_history:
            return None

        latest = self.context_history[-1]
        basis = latest.basis_percent

        if basis is None:
            return None

        # Determine status
        if abs(basis) > self.basis_spike_threshold_percent:
            status = "Premium" if basis > 0 else "Discount"
        else:
            status = "Normal"

        return BasisStats(
            current_basis_percent=basis,
            status=status,
        )

    def get_multi_timeframe_oi(self) -> dict[str, Optional[OIStats]]:
        """Get OI statistics across multiple timeframes.

        Returns:
        --------
        dict[str, Optional[OIStats]]
            OI stats for 5m and 15m windows
        """
        return {
            "5m": self.get_oi_stats(300.0),
            "15m": self.get_oi_stats(900.0),
        }

    def get_historical_values(self) -> dict[str, list[tuple[float, float]]]:
        """Get historical time series of OI, funding, and basis.

        Returns:
        --------
        dict[str, list[tuple[float, float]]]
            Dictionary with keys 'oi', 'funding', 'basis', each containing
            list of (timestamp_ms, value) tuples
        """
        if not self.context_history:
            return {"oi": [], "funding": [], "basis": []}

        oi_history = []
        funding_history = []
        basis_history = []

        for ctx in self.context_history:
            oi_history.append((ctx.timestamp_ms, ctx.open_interest_usd))
            funding_history.append((ctx.timestamp_ms, ctx.funding_rate))
            if ctx.basis_percent is not None:
                basis_history.append((ctx.timestamp_ms, ctx.basis_percent))

        return {
            "oi": oi_history,
            "funding": funding_history,
            "basis": basis_history,
        }

    def get_summary(self, window_seconds: Optional[float] = None) -> Optional[MarketIndicatorsSummary]:
        """Get complete market indicators summary.

        Parameters:
        -----------
        window_seconds : Optional[float]
            Time window in seconds (if None, uses default oi_window_seconds)

        Returns:
        --------
        Optional[MarketIndicatorsSummary]
            Complete indicators summary, or None if not enough data
        """
        if not self.context_history:
            return None

        latest = self.context_history[-1]

        oi_stats = self.get_oi_stats(window_seconds)
        funding_stats = self.get_funding_stats()
        basis_stats = self.get_basis_stats()

        if oi_stats is None or funding_stats is None:
            return None

        # Generate interpretation
        interpretation = self._interpret_signals(oi_stats, funding_stats, basis_stats)

        return MarketIndicatorsSummary(
            timestamp_ms=latest.timestamp_ms,
            coin=latest.coin,
            oi=oi_stats,
            funding=funding_stats,
            basis=basis_stats if basis_stats else BasisStats(0.0, "Unknown"),
            interpretation=interpretation,
        )

    def _interpret_signals(
        self,
        oi: OIStats,
        funding: FundingStats,
        basis: Optional[BasisStats],
    ) -> str:
        """Interpret combined market signals.

        Returns:
        --------
        str
            Text interpretation of the combined signals
        """
        interpretations = []

        # OI interpretation
        if oi.trend == "up":
            interpretations.append("OI Up: New positions opening (strong trend)")
        elif oi.trend == "down":
            interpretations.append("OI Down: Position unwinding (potential reversal)")
        else:
            interpretations.append("OI Flat: Stable positioning")

        # Funding interpretation
        if funding.trend == "up":
            if funding.current_rate > 0.001:  # High positive funding
                interpretations.append("Funding High Positive: Longs paying shorts (overheated)")
            else:
                interpretations.append("Funding Positive: Slight long bias")
        elif funding.trend == "down":
            if funding.current_rate < -0.001:  # High negative funding
                interpretations.append("Funding High Negative: Shorts paying longs (oversold)")
            else:
                interpretations.append("Funding Negative: Slight short bias")
        else:
            interpretations.append("Funding Stable: Balanced market")

        # Basis interpretation
        if basis is not None:
            if basis.status == "Premium":
                interpretations.append(f"Basis Spike (+{basis.current_basis_percent:.2f}%): Perp premium (overheating)")
            elif basis.status == "Discount":
                interpretations.append(f"Basis Spike ({basis.current_basis_percent:.2f}%): Perp discount (bearish)")
            else:
                interpretations.append("Basis Normal: Fair pricing")

        return " | ".join(interpretations)


def format_market_indicators_summary(summary: MarketIndicatorsSummary) -> str:
    """Format market indicators as a readable summary.

    Parameters:
    -----------
    summary : MarketIndicatorsSummary
        Market indicators summary

    Returns:
    --------
    str
        Formatted summary string
    """
    lines = []
    lines.append("\nMarket Indicators")
    lines.append("=" * 80)

    # Open Interest
    oi_trend_symbol = {
        "up": "↑",
        "down": "↓",
        "flat": "→",
    }[summary.oi.trend]

    lines.append(f"Open Interest:  ${summary.oi.current_oi_usd:>12,.0f}  "
                f"{oi_trend_symbol} {summary.oi.trend}  "
                f"({summary.oi.change_percent:+.2f}%, "
                f"{summary.oi.velocity_percent_per_min:+.3f}%/min)")

    # Funding Rate
    funding_trend_symbol = {
        "up": "↑",
        "down": "↓",
        "flat": "→",
    }[summary.funding.trend]

    lines.append(f"Funding Rate:   {summary.funding.current_rate:>12.4f}%  "
                f"{funding_trend_symbol} {summary.funding.trend}  "
                f"(Annualized: {summary.funding.annualized_rate_percent:+.2f}%)")

    # Basis
    lines.append(f"Basis:          {summary.basis.current_basis_percent:>12.3f}%  "
                f"[{summary.basis.status}]")

    lines.append("\nInterpretation:")
    lines.append("-" * 80)
    lines.append(summary.interpretation)
    lines.append("=" * 80)

    return "\n".join(lines)
