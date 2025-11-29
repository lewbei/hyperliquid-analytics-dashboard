"""Trade flow tracker.

This module tracks trade events and calculates real-time statistics:
- Trade size distribution over time windows
- Volume buckets (0-1k, 1k-5k, 5k-10k, etc.)
- Buy vs sell volume breakdown
- Largest, median, average trade sizes

All calculations are based on trade events from the WebSocket feed.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import statistics


@dataclass
class Trade:
    """A single trade event."""
    timestamp_ms: float  # Unix timestamp in milliseconds
    price: float
    size: float  # Quantity in base asset
    side: str  # "buy" or "sell" (from taker's perspective)

    @property
    def notional_usd(self) -> float:
        """Trade size in USD."""
        return self.price * self.size


@dataclass
class TradeBucket:
    """Statistics for a trade size bucket."""
    min_usd: float
    max_usd: Optional[float]  # None for unbounded (e.g., 250k+)
    count: int = 0
    total_volume_usd: float = 0.0
    buy_volume_usd: float = 0.0
    sell_volume_usd: float = 0.0

    @property
    def bucket_label(self) -> str:
        """Human-readable bucket label."""
        if self.max_usd is None:
            return f"{int(self.min_usd/1000)}k+"
        elif self.max_usd >= 1000:
            return f"{int(self.min_usd/1000)}k-{int(self.max_usd/1000)}k"
        else:
            return f"{int(self.min_usd)}-{int(self.max_usd)}"

    def add_trade(self, trade: Trade) -> None:
        """Add a trade to this bucket."""
        self.count += 1
        notional = trade.notional_usd
        self.total_volume_usd += notional

        if trade.side == "buy":
            self.buy_volume_usd += notional
        else:
            self.sell_volume_usd += notional

    def matches(self, trade_size_usd: float) -> bool:
        """Check if a trade size belongs to this bucket."""
        if self.max_usd is None:
            return trade_size_usd >= self.min_usd
        return self.min_usd <= trade_size_usd < self.max_usd


@dataclass
class TradeFlowStats:
    """Trade flow statistics over a time window."""
    window_seconds: float
    trade_count: int
    total_volume_usd: float
    buy_volume_usd: float
    sell_volume_usd: float

    # Trade size stats
    largest_trade_usd: float
    median_trade_usd: float
    average_trade_usd: float

    # Volume by bucket
    buckets: List[TradeBucket]

    @property
    def buy_ratio(self) -> float:
        """Ratio of buy volume to total volume."""
        if self.total_volume_usd == 0:
            return 0.0
        return self.buy_volume_usd / self.total_volume_usd

    @property
    def sell_ratio(self) -> float:
        """Ratio of sell volume to total volume."""
        if self.total_volume_usd == 0:
            return 0.0
        return self.sell_volume_usd / self.total_volume_usd


class TradeFlowTracker:
    """Tracks trade flow and calculates real-time statistics across multiple timeframes."""

    def __init__(
        self,
        window_seconds: float = 30.0,
        bucket_thresholds: List[Tuple[float, Optional[float]]] = None,
        max_history_seconds: float = 900.0,  # 15 minutes
    ):
        """Initialize trade flow tracker.

        Parameters:
        -----------
        window_seconds : float, default 30.0
            Default time window in seconds for calculating statistics
        bucket_thresholds : List[Tuple[float, Optional[float]]], optional
            Custom bucket thresholds as (min, max) tuples
            Default: [(0, 1k), (1k, 5k), (5k, 10k), (10k, 50k), (50k, 250k), (250k, None)]
        max_history_seconds : float, default 900.0
            Maximum history to keep (15 minutes for longest window)
        """
        self.window_seconds = window_seconds  # Default window
        self.max_history_seconds = max_history_seconds
        self.trades: deque[Trade] = deque()

        # Default bucket thresholds
        if bucket_thresholds is None:
            bucket_thresholds = [
                (0, 1000),
                (1000, 5000),
                (5000, 10000),
                (10000, 50000),
                (50000, 250000),
                (250000, None),
            ]

        self.bucket_defs = bucket_thresholds

    def add_trade(self, trade: Trade) -> None:
        """Add a new trade event."""
        self.trades.append(trade)
        self._cleanup_old_trades()

    def _cleanup_old_trades(self) -> None:
        """Remove trades outside the maximum history window."""
        if not self.trades:
            return

        current_time_ms = time.time() * 1000
        cutoff_time_ms = current_time_ms - (self.max_history_seconds * 1000)

        # Remove old trades from the left
        while self.trades and self.trades[0].timestamp_ms < cutoff_time_ms:
            self.trades.popleft()

    def get_stats(self, window_seconds: Optional[float] = None) -> TradeFlowStats:
        """Calculate current trade flow statistics for a specific time window.

        Parameters:
        -----------
        window_seconds : Optional[float]
            Time window in seconds (if None, uses default window_seconds)

        Returns:
        --------
        TradeFlowStats
            Statistics for trades in the specified time window
        """
        self._cleanup_old_trades()

        if window_seconds is None:
            window_seconds = self.window_seconds

        # Filter trades within the requested window
        current_time_ms = time.time() * 1000
        cutoff_time_ms = current_time_ms - (window_seconds * 1000)
        windowed_trades = [t for t in self.trades if t.timestamp_ms >= cutoff_time_ms]

        if not windowed_trades:
            # No trades in window - return empty stats
            buckets = [
                TradeBucket(min_usd=min_usd, max_usd=max_usd)
                for min_usd, max_usd in self.bucket_defs
            ]
            return TradeFlowStats(
                window_seconds=window_seconds,
                trade_count=0,
                total_volume_usd=0.0,
                buy_volume_usd=0.0,
                sell_volume_usd=0.0,
                largest_trade_usd=0.0,
                median_trade_usd=0.0,
                average_trade_usd=0.0,
                buckets=buckets,
            )

        # Initialize buckets
        buckets = [
            TradeBucket(min_usd=min_usd, max_usd=max_usd)
            for min_usd, max_usd in self.bucket_defs
        ]

        # Calculate stats
        trade_sizes_usd = []
        total_volume_usd = 0.0
        buy_volume_usd = 0.0
        sell_volume_usd = 0.0

        for trade in windowed_trades:
            notional = trade.notional_usd
            trade_sizes_usd.append(notional)
            total_volume_usd += notional

            if trade.side == "buy":
                buy_volume_usd += notional
            else:
                sell_volume_usd += notional

            # Add to appropriate bucket
            for bucket in buckets:
                if bucket.matches(notional):
                    bucket.add_trade(trade)
                    break

        # Calculate trade size stats
        largest_trade_usd = max(trade_sizes_usd) if trade_sizes_usd else 0.0
        median_trade_usd = statistics.median(trade_sizes_usd) if trade_sizes_usd else 0.0
        average_trade_usd = statistics.mean(trade_sizes_usd) if trade_sizes_usd else 0.0

        return TradeFlowStats(
            window_seconds=window_seconds,
            trade_count=len(windowed_trades),
            total_volume_usd=total_volume_usd,
            buy_volume_usd=buy_volume_usd,
            sell_volume_usd=sell_volume_usd,
            largest_trade_usd=largest_trade_usd,
            median_trade_usd=median_trade_usd,
            average_trade_usd=average_trade_usd,
            buckets=buckets,
        )

    def get_multi_timeframe_stats(self) -> Dict[str, TradeFlowStats]:
        """Get trade flow statistics across multiple timeframes.

        Returns:
        --------
        Dict[str, TradeFlowStats]
            Trade flow stats for 30s, 5m, and 15m windows
        """
        return {
            "30s": self.get_stats(30.0),
            "5m": self.get_stats(300.0),
            "15m": self.get_stats(900.0),
        }

    def get_bucket_distribution(self, window_seconds: Optional[float] = None) -> Dict[str, TradeBucket]:
        """Get trade distribution by bucket.

        Parameters:
        -----------
        window_seconds : Optional[float]
            Time window in seconds (if None, uses default window_seconds)

        Returns:
        --------
        Dict[str, TradeBucket]
            Map of bucket labels to bucket statistics
        """
        stats = self.get_stats(window_seconds)
        return {bucket.bucket_label: bucket for bucket in stats.buckets}


def format_trade_flow_summary(stats: TradeFlowStats) -> str:
    """Format trade flow stats as a readable summary.

    Parameters:
    -----------
    stats : TradeFlowStats
        Trade flow statistics

    Returns:
    --------
    str
        Formatted summary string
    """
    lines = []
    lines.append(f"\nTrade Flow Summary (Window: {stats.window_seconds}s)")
    lines.append("=" * 80)
    lines.append(f"Total Trades: {stats.trade_count}")
    lines.append(f"Total Volume: ${stats.total_volume_usd:,.0f}")
    lines.append(f"Buy Volume:   ${stats.buy_volume_usd:,.0f} ({stats.buy_ratio*100:.1f}%)")
    lines.append(f"Sell Volume:  ${stats.sell_volume_usd:,.0f} ({stats.sell_ratio*100:.1f}%)")
    lines.append(f"\nLargest: ${stats.largest_trade_usd:,.0f}  |  "
                f"Median: ${stats.median_trade_usd:,.0f}  |  "
                f"Average: ${stats.average_trade_usd:,.0f}")

    lines.append("\nTrade Size Distribution:")
    lines.append("-" * 80)
    lines.append(f"{'Bucket':<15} {'Count':<8} {'Total Vol':<15} {'Buy Vol':<15} {'Sell Vol':<15}")
    lines.append("-" * 80)

    for bucket in stats.buckets:
        lines.append(
            f"{bucket.bucket_label:<15} "
            f"{bucket.count:<8} "
            f"${bucket.total_volume_usd:>12,.0f}  "
            f"${bucket.buy_volume_usd:>12,.0f}  "
            f"${bucket.sell_volume_usd:>12,.0f}"
        )

    lines.append("=" * 80)
    return "\n".join(lines)


def detect_sweep_direction(stats: TradeFlowStats, threshold: float = 0.65) -> Optional[str]:
    """Detect if there's a directional sweep in recent trades.

    A sweep is detected when buy or sell volume significantly dominates.

    Parameters:
    -----------
    stats : TradeFlowStats
        Trade flow statistics
    threshold : float, default 0.65
        Minimum ratio to detect sweep (0.65 = 65% of volume)

    Returns:
    --------
    Optional[str]
        "up" if buy sweep, "down" if sell sweep, None if balanced
    """
    if stats.trade_count < 3:  # Need minimum trades
        return None

    if stats.buy_ratio >= threshold:
        return "up"
    elif stats.sell_ratio >= threshold:
        return "down"

    return None
