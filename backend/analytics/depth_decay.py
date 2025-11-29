"""Depth Decay calculator.

This module tracks how orderbook depth changes over time, measuring
the percentage decay in bid/ask liquidity. This helps detect if
liquidity is being consumed (aggressive buying/selling).

Depth Decay indicates:
- High bid decay + price down = Strong selling pressure
- High ask decay + price up = Strong buying pressure
- Low decay = Stable market
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class DepthSnapshot:
    """Snapshot of orderbook depth at a point in time."""
    timestamp_ms: float
    bid_depth_usd: float  # Total bid liquidity (e.g., L5 depth)
    ask_depth_usd: float  # Total ask liquidity (e.g., L5 depth)


@dataclass
class DepthDecayStats:
    """Depth decay statistics."""
    bid_decay_percent: float  # % decay in bid depth (positive = depth decreased)
    ask_decay_percent: float  # % decay in ask depth (positive = depth decreased)
    window_seconds: float  # Time window for decay calculation
    current_bid_depth: float
    current_ask_depth: float
    reference_bid_depth: float  # Depth at start of window
    reference_ask_depth: float  # Depth at start of window

    @property
    def bid_status(self) -> str:
        """Status of bid depth."""
        if self.bid_decay_percent > 30:
            return "Critical"
        elif self.bid_decay_percent > 15:
            return "High"
        elif self.bid_decay_percent > 5:
            return "Medium"
        else:
            return "OK"

    @property
    def ask_status(self) -> str:
        """Status of ask depth."""
        if self.ask_decay_percent > 30:
            return "Critical"
        elif self.ask_decay_percent > 15:
            return "High"
        elif self.ask_decay_percent > 5:
            return "Medium"
        else:
            return "OK"


class DepthDecayTracker:
    """Tracks depth decay over time."""

    def __init__(self, window_seconds: float = 15.0):
        """Initialize depth decay tracker.

        Parameters:
        -----------
        window_seconds : float, default 15.0
            Time window for decay calculation (default 15 seconds)
        """
        self.window_seconds = window_seconds
        self.snapshots: deque[DepthSnapshot] = deque()

    def add_snapshot(
        self,
        bid_depth_usd: float,
        ask_depth_usd: float,
        timestamp_ms: Optional[float] = None,
    ) -> None:
        """Add a new depth snapshot.

        Parameters:
        -----------
        bid_depth_usd : float
            Total bid liquidity (e.g., L5 depth)
        ask_depth_usd : float
            Total ask liquidity (e.g., L5 depth)
        timestamp_ms : float, optional
            Timestamp in milliseconds. If None, uses current time.
        """
        if timestamp_ms is None:
            timestamp_ms = time.time() * 1000

        snapshot = DepthSnapshot(
            timestamp_ms=timestamp_ms,
            bid_depth_usd=bid_depth_usd,
            ask_depth_usd=ask_depth_usd,
        )

        self.snapshots.append(snapshot)
        self._cleanup_old_snapshots()

    def _cleanup_old_snapshots(self) -> None:
        """Remove snapshots older than the window."""
        if not self.snapshots:
            return

        # Keep data for window + 10% buffer
        retention_window_ms = self.window_seconds * 1000 * 1.1

        current_time_ms = time.time() * 1000
        cutoff_time_ms = current_time_ms - retention_window_ms

        # Remove old snapshots from the left
        while self.snapshots and self.snapshots[0].timestamp_ms < cutoff_time_ms:
            self.snapshots.popleft()

    def get_decay_stats(self) -> Optional[DepthDecayStats]:
        """Calculate depth decay statistics.

        Returns:
        --------
        Optional[DepthDecayStats]
            Decay stats, or None if not enough data
        """
        self._cleanup_old_snapshots()

        if len(self.snapshots) < 2:
            # Need at least 2 snapshots
            return None

        current_time_ms = time.time() * 1000
        window_start_ms = current_time_ms - (self.window_seconds * 1000)

        # Find reference snapshot at start of window
        reference_snapshot = None
        for snapshot in self.snapshots:
            if snapshot.timestamp_ms >= window_start_ms:
                reference_snapshot = snapshot
                break

        if reference_snapshot is None:
            # No data in window
            return None

        # Latest snapshot
        current_snapshot = self.snapshots[-1]

        # Calculate decay percentages
        # Decay = ((reference - current) / reference) * 100
        # Positive decay = depth decreased (liquidity consumed)
        # Negative decay = depth increased (liquidity added)

        if reference_snapshot.bid_depth_usd > 0:
            bid_decay_percent = (
                (reference_snapshot.bid_depth_usd - current_snapshot.bid_depth_usd)
                / reference_snapshot.bid_depth_usd
                * 100
            )
        else:
            bid_decay_percent = 0.0

        if reference_snapshot.ask_depth_usd > 0:
            ask_decay_percent = (
                (reference_snapshot.ask_depth_usd - current_snapshot.ask_depth_usd)
                / reference_snapshot.ask_depth_usd
                * 100
            )
        else:
            ask_decay_percent = 0.0

        return DepthDecayStats(
            bid_decay_percent=bid_decay_percent,
            ask_decay_percent=ask_decay_percent,
            window_seconds=self.window_seconds,
            current_bid_depth=current_snapshot.bid_depth_usd,
            current_ask_depth=current_snapshot.ask_depth_usd,
            reference_bid_depth=reference_snapshot.bid_depth_usd,
            reference_ask_depth=reference_snapshot.ask_depth_usd,
        )

    def detect_aggressive_buying(self, decay_stats: Optional[DepthDecayStats]) -> bool:
        """Detect aggressive buying (ask depth being consumed).

        Parameters:
        -----------
        decay_stats : Optional[DepthDecayStats]
            Depth decay statistics

        Returns:
        --------
        bool
            True if aggressive buying detected
        """
        if decay_stats is None:
            return False

        # Aggressive buying = high ask decay (asks being consumed)
        return decay_stats.ask_decay_percent > 15.0

    def detect_aggressive_selling(self, decay_stats: Optional[DepthDecayStats]) -> bool:
        """Detect aggressive selling (bid depth being consumed).

        Parameters:
        -----------
        decay_stats : Optional[DepthDecayStats]
            Depth decay statistics

        Returns:
        --------
        bool
            True if aggressive selling detected
        """
        if decay_stats is None:
            return False

        # Aggressive selling = high bid decay (bids being consumed)
        return decay_stats.bid_decay_percent > 15.0


def format_depth_decay_summary(stats: Optional[DepthDecayStats]) -> str:
    """Format depth decay stats as a readable summary.

    Parameters:
    -----------
    stats : Optional[DepthDecayStats]
        Depth decay statistics

    Returns:
    --------
    str
        Formatted summary string
    """
    if stats is None:
        return "Depth Decay: No data"

    lines = []
    lines.append(f"\nDepth Decay ({stats.window_seconds}s window)")
    lines.append("=" * 60)
    lines.append(f"Bid Depth Decay:  {stats.bid_decay_percent:>6.1f}%  [{stats.bid_status}]")
    lines.append(f"  Current:  ${stats.current_bid_depth:>12,.0f}")
    lines.append(f"  Reference: ${stats.reference_bid_depth:>12,.0f}")
    lines.append(f"\nAsk Depth Decay:  {stats.ask_decay_percent:>6.1f}%  [{stats.ask_status}]")
    lines.append(f"  Current:  ${stats.current_ask_depth:>12,.0f}")
    lines.append(f"  Reference: ${stats.reference_ask_depth:>12,.0f}")
    lines.append("=" * 60)

    return "\n".join(lines)


def interpret_depth_decay(
    bid_decay: float,
    ask_decay: float,
    price_change: float,
) -> str:
    """Interpret depth decay combined with price movement.

    Parameters:
    -----------
    bid_decay : float
        Bid depth decay percentage
    ask_decay : float
        Ask depth decay percentage
    price_change : float
        Price change percentage

    Returns:
    --------
    str
        Interpretation of the combined signals
    """
    # High bid decay + price down = Strong selling
    if bid_decay > 15 and price_change < -0.05:
        return "Strong selling pressure (bid depth consumed)"

    # High ask decay + price up = Strong buying
    if ask_decay > 15 and price_change > 0.05:
        return "Strong buying pressure (ask depth consumed)"

    # High bid decay but price up = Absorption (bulls defending)
    if bid_decay > 15 and price_change > 0.05:
        return "Bid absorption (selling absorbed by bulls)"

    # High ask decay but price down = Absorption (bears defending)
    if ask_decay > 15 and price_change < -0.05:
        return "Ask absorption (buying absorbed by bears)"

    # Low decay = Stable
    if bid_decay < 5 and ask_decay < 5:
        return "Stable depth (low consumption)"

    return "Normal market activity"
