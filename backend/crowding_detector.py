"""Position crowding detector.

This module detects crowded long or short positions based on:
- Open Interest levels and trends
- Funding rates
- Perp-spot basis

Crowded positions can lead to:
- Potential squeezes (forced liquidations)
- Mean reversion opportunities
- Higher risk of sudden reversals
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class CrowdingFlags:
    """Position crowding flags."""

    # Flags
    crowded_long: bool
    crowded_short: bool

    # Scores (0-1, higher = more crowded)
    long_crowding_score: float
    short_crowding_score: float

    # Supporting metrics
    oi_trend: str  # "up", "down", "flat"
    oi_velocity: float  # % per minute
    funding_rate: float  # %
    funding_trend: str  # "rising", "falling", "stable"
    basis_percent: float  # %
    basis_status: str  # "rich", "fair", "cheap"

    # Interpretation
    interpretation: str


class CrowdingDetector:
    """Detects crowded long/short positions from market indicators."""

    def __init__(
        self,
        # OI thresholds
        oi_increasing_threshold: float = 0.5,  # % increase to consider "increasing"
        oi_velocity_high_threshold: float = 0.05,  # % per minute

        # Funding thresholds
        funding_bullish_threshold: float = 0.01,  # 1% annual = bullish (longs paying)
        funding_bearish_threshold: float = -0.01,  # -1% annual = bearish (shorts paying)

        # Basis thresholds
        basis_rich_threshold: float = 0.1,  # > 0.1% = rich (perp > spot)
        basis_cheap_threshold: float = -0.1,  # < -0.1% = cheap (perp < spot)

        # Crowding score threshold
        crowding_threshold: float = 0.6,  # Score > 0.6 = crowded
    ):
        """Initialize crowding detector with configurable thresholds."""
        self.oi_increasing_threshold = oi_increasing_threshold
        self.oi_velocity_high_threshold = oi_velocity_high_threshold

        self.funding_bullish_threshold = funding_bullish_threshold
        self.funding_bearish_threshold = funding_bearish_threshold

        self.basis_rich_threshold = basis_rich_threshold
        self.basis_cheap_threshold = basis_cheap_threshold

        self.crowding_threshold = crowding_threshold

    def detect(
        self,
        oi_trend: str,
        oi_velocity: float,
        funding_rate: float,
        funding_trend: str,
        basis_percent: float,
        basis_status: str,
    ) -> CrowdingFlags:
        """Detect position crowding.

        Parameters
        ----------
        oi_trend : str
            OI trend ("up", "down", "flat")
        oi_velocity : float
            OI velocity in % per minute
        funding_rate : float
            Current funding rate (%)
        funding_trend : str
            Funding trend ("rising", "falling", "stable")
        basis_percent : float
            Perp-spot basis (%)
        basis_status : str
            Basis status ("rich", "fair", "cheap")

        Returns
        -------
        CrowdingFlags
            Crowding detection result
        """
        # Calculate long crowding score
        long_score = 0.0

        # OI increasing = more positions opened
        if oi_trend == "up":
            long_score += 0.3

        # High OI velocity = rapid position accumulation
        if abs(oi_velocity) > self.oi_velocity_high_threshold:
            long_score += 0.2

        # Positive funding = longs paying shorts (bullish sentiment)
        if funding_rate > self.funding_bullish_threshold:
            long_score += 0.3
            if funding_rate > self.funding_bullish_threshold * 2:
                long_score += 0.1  # Extra for very high funding

        # Positive basis = perp trading rich vs spot (bullish sentiment)
        if basis_percent > self.basis_rich_threshold:
            long_score += 0.2

        # Calculate short crowding score
        short_score = 0.0

        # OI increasing = more positions opened
        if oi_trend == "up":
            short_score += 0.3

        # High OI velocity = rapid position accumulation
        if abs(oi_velocity) > self.oi_velocity_high_threshold:
            short_score += 0.2

        # Negative funding = shorts paying longs (bearish sentiment)
        if funding_rate < self.funding_bearish_threshold:
            short_score += 0.3
            if funding_rate < self.funding_bearish_threshold * 2:
                short_score += 0.1  # Extra for very negative funding

        # Negative basis = perp trading cheap vs spot (bearish sentiment)
        if basis_percent < self.basis_cheap_threshold:
            short_score += 0.2

        # Determine flags
        crowded_long = long_score >= self.crowding_threshold
        crowded_short = short_score >= self.crowding_threshold

        # Generate interpretation
        interpretation = self._generate_interpretation(
            crowded_long, crowded_short,
            long_score, short_score,
            oi_trend, funding_rate, basis_status
        )

        return CrowdingFlags(
            crowded_long=crowded_long,
            crowded_short=crowded_short,
            long_crowding_score=long_score,
            short_crowding_score=short_score,
            oi_trend=oi_trend,
            oi_velocity=oi_velocity,
            funding_rate=funding_rate,
            funding_trend=funding_trend,
            basis_percent=basis_percent,
            basis_status=basis_status,
            interpretation=interpretation,
        )

    def _generate_interpretation(
        self,
        crowded_long: bool,
        crowded_short: bool,
        long_score: float,
        short_score: float,
        oi_trend: str,
        funding_rate: float,
        basis_status: str,
    ) -> str:
        """Generate human-readable interpretation."""
        if crowded_long and crowded_short:
            return "Mixed signals: both longs and shorts show crowding indicators"

        if crowded_long:
            return (
                f"Crowded LONG (score: {long_score:.2f}): "
                f"High OI {oi_trend}, positive funding, perp {basis_status}. "
                "Risk of long liquidations if price drops."
            )

        if crowded_short:
            return (
                f"Crowded SHORT (score: {short_score:.2f}): "
                f"High OI {oi_trend}, negative funding, perp {basis_status}. "
                "Risk of short squeeze if price rises."
            )

        # Not crowded
        if long_score > short_score:
            return f"Lean long (score: {long_score:.2f}) but not crowded"
        elif short_score > long_score:
            return f"Lean short (score: {short_score:.2f}) but not crowded"
        else:
            return "Balanced positioning, no crowding detected"


def format_crowding_summary(crowding: CrowdingFlags) -> str:
    """Format crowding flags as readable summary.

    Parameters
    ----------
    crowding : CrowdingFlags
        Crowding detection result

    Returns
    -------
    str
        Formatted summary
    """
    lines = []
    lines.append("\nPosition Crowding Analysis")
    lines.append("=" * 80)

    lines.append(f"\nCrowded Long:   {'YES' if crowding.crowded_long else 'NO'}  "
                f"(score: {crowding.long_crowding_score:.2f})")
    lines.append(f"Crowded Short:  {'YES' if crowding.crowded_short else 'NO'}  "
                f"(score: {crowding.short_crowding_score:.2f})")

    lines.append(f"\nSupporting Metrics:")
    lines.append(f"  OI Trend:       {crowding.oi_trend.upper()}  "
                f"(velocity: {crowding.oi_velocity:+.3f}% per min)")
    lines.append(f"  Funding Rate:   {crowding.funding_rate:+.4f}%  "
                f"({crowding.funding_trend})")
    lines.append(f"  Basis:          {crowding.basis_percent:+.3f}%  "
                f"({crowding.basis_status})")

    lines.append(f"\nInterpretation:")
    lines.append(f"  {crowding.interpretation}")

    lines.append("=" * 80)

    return "\n".join(lines)
