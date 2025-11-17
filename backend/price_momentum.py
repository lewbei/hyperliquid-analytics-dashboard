"""Price momentum calculator.

This module tracks price changes over different time windows and detects
real-time trends from WebSocket mid-price updates.

Calculates:
- Short-term momentum (e.g., 5 seconds)
- Long-term momentum (e.g., 20 seconds)
- Trend direction (up, down, flat)
- Price change percentage
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Optional, Literal


TrendDirection = Literal["up", "down", "flat"]


@dataclass
class PricePoint:
    """A single price observation."""
    timestamp_ms: float  # Unix timestamp in milliseconds
    price: float


@dataclass
class MomentumStats:
    """Momentum statistics for a time window."""
    window_seconds: float
    direction: TrendDirection
    change_percent: float  # Percentage change from start to latest
    latest_price: float
    start_price: float
    latest_timestamp_ms: float
    is_usable: bool  # Whether we have enough data for reliable signal


class PriceMomentumTracker:
    """Tracks price momentum over multiple time windows."""

    def __init__(
        self,
        short_window_seconds: float = 5.0,
        long_window_seconds: float = 20.0,
        flat_threshold_percent: float = 0.01,  # 0.01% = 1 bps
    ):
        """Initialize price momentum tracker.

        Parameters:
        -----------
        short_window_seconds : float, default 5.0
            Time window for short-term momentum
        long_window_seconds : float, default 20.0
            Time window for long-term momentum
        flat_threshold_percent : float, default 0.01
            Percentage threshold for flat detection (absolute value)
            e.g., 0.01 = +/- 0.01% = +/- 1 bps
        """
        self.short_window_seconds = short_window_seconds
        self.long_window_seconds = long_window_seconds
        self.flat_threshold_percent = flat_threshold_percent

        # Store price points in a deque for efficient removal of old data
        self.price_history: deque[PricePoint] = deque()

    def add_price(self, price: float, timestamp_ms: Optional[float] = None) -> None:
        """Add a new price observation.

        Parameters:
        -----------
        price : float
            Current price
        timestamp_ms : float, optional
            Timestamp in milliseconds. If None, uses current time.
        """
        if timestamp_ms is None:
            timestamp_ms = time.time() * 1000

        self.price_history.append(PricePoint(timestamp_ms=timestamp_ms, price=price))
        self._cleanup_old_prices()

    def _cleanup_old_prices(self) -> None:
        """Remove prices older than the longest window."""
        if not self.price_history:
            return

        # Keep data for longest window + 10% buffer
        max_window = max(self.short_window_seconds, self.long_window_seconds)
        retention_window_ms = max_window * 1000 * 1.1

        current_time_ms = time.time() * 1000
        cutoff_time_ms = current_time_ms - retention_window_ms

        # Remove old prices from the left
        while self.price_history and self.price_history[0].timestamp_ms < cutoff_time_ms:
            self.price_history.popleft()

    def get_momentum(self, window_seconds: float) -> Optional[MomentumStats]:
        """Get momentum statistics for a specific time window.

        Parameters:
        -----------
        window_seconds : float
            Time window in seconds

        Returns:
        --------
        Optional[MomentumStats]
            Momentum stats, or None if not enough data
        """
        self._cleanup_old_prices()

        if not self.price_history:
            return None

        current_time_ms = time.time() * 1000
        window_start_ms = current_time_ms - (window_seconds * 1000)

        # Find the first price point within the window
        start_price = None
        for point in self.price_history:
            if point.timestamp_ms >= window_start_ms:
                start_price = point.price
                break

        if start_price is None:
            # Not enough data for this window
            return None

        # Latest price is the last point
        latest_point = self.price_history[-1]
        latest_price = latest_point.price
        latest_timestamp_ms = latest_point.timestamp_ms

        # Calculate percentage change
        if start_price != 0:
            change_percent = ((latest_price - start_price) / start_price) * 100
        else:
            change_percent = 0.0

        # Determine trend direction
        if abs(change_percent) < self.flat_threshold_percent:
            direction = "flat"
        elif change_percent > 0:
            direction = "up"
        else:
            direction = "down"

        # Check if signal is usable (have we collected enough data?)
        # We want at least 50% of the window filled with data
        oldest_in_window_ms = self.price_history[0].timestamp_ms
        data_duration_ms = latest_timestamp_ms - oldest_in_window_ms
        is_usable = data_duration_ms >= (window_seconds * 1000 * 0.5)

        return MomentumStats(
            window_seconds=window_seconds,
            direction=direction,
            change_percent=change_percent,
            latest_price=latest_price,
            start_price=start_price,
            latest_timestamp_ms=latest_timestamp_ms,
            is_usable=is_usable,
        )

    def get_short_momentum(self) -> Optional[MomentumStats]:
        """Get short-term momentum statistics."""
        return self.get_momentum(self.short_window_seconds)

    def get_long_momentum(self) -> Optional[MomentumStats]:
        """Get long-term momentum statistics."""
        return self.get_momentum(self.long_window_seconds)

    def get_all_momentum(self) -> tuple[Optional[MomentumStats], Optional[MomentumStats]]:
        """Get both short and long-term momentum statistics.

        Returns:
        --------
        tuple[Optional[MomentumStats], Optional[MomentumStats]]
            (short_momentum, long_momentum)
        """
        return (self.get_short_momentum(), self.get_long_momentum())


def format_momentum_summary(
    short: Optional[MomentumStats],
    long: Optional[MomentumStats],
) -> str:
    """Format momentum stats as a readable summary.

    Parameters:
    -----------
    short : Optional[MomentumStats]
        Short-term momentum stats
    long : Optional[MomentumStats]
        Long-term momentum stats

    Returns:
    --------
    str
        Formatted summary string
    """
    lines = []
    lines.append("\nPrice Momentum")
    lines.append("=" * 60)

    def format_stat(label: str, stat: Optional[MomentumStats]) -> str:
        if stat is None:
            return f"{label:<15}: No data"

        direction_symbol = {
            "up": "↑",
            "down": "↓",
            "flat": "→",
        }[stat.direction]

        usable = "✓" if stat.is_usable else "✗"

        return (
            f"{label:<15}: {direction_symbol} {stat.direction:<5} "
            f"{stat.change_percent:>+7.3f}%  "
            f"(${stat.latest_price:.2f})  "
            f"[{usable}]"
        )

    lines.append(format_stat(f"Short ({short.window_seconds if short else 0}s)", short))
    lines.append(format_stat(f"Long ({long.window_seconds if long else 0}s)", long))
    lines.append("=" * 60)

    return "\n".join(lines)


def detect_trend_alignment(
    short: Optional[MomentumStats],
    long: Optional[MomentumStats],
) -> Optional[str]:
    """Detect if short and long-term trends are aligned.

    Returns:
    --------
    Optional[str]
        "bullish" if both up, "bearish" if both down,
        "reversal_up" if short up but long down,
        "reversal_down" if short down but long up,
        None if no clear alignment
    """
    if short is None or long is None:
        return None

    if not short.is_usable or not long.is_usable:
        return None

    # Both trending up
    if short.direction == "up" and long.direction == "up":
        return "bullish"

    # Both trending down
    if short.direction == "down" and long.direction == "down":
        return "bearish"

    # Short up, long down - potential reversal
    if short.direction == "up" and long.direction == "down":
        return "reversal_up"

    # Short down, long up - potential reversal
    if short.direction == "down" and long.direction == "up":
        return "reversal_down"

    return None
