"""Liquidations detector.

This module attempts to detect liquidations from trade data. Since liquidations
are not directly available in public WebSocket feeds, we infer them from:
- Large trades
- Rapid sequence of trades in same direction
- Price movement + volume spikes

Note: This is estimation-based, not definitive liquidation data.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, Optional, Literal


LiquidationSide = Literal["long", "short", "none"]


@dataclass
class SuspectedLiquidation:
    """A suspected liquidation event."""
    timestamp_ms: float
    side: LiquidationSide  # "long" (forced sell) or "short" (forced buy)
    total_volume_usd: float
    price: float
    confidence: float  # 0.0 to 1.0
    reason: str  # Why we think this is a liquidation


@dataclass
class LiquidationStats:
    """Liquidation statistics over a time window."""
    window_seconds: float
    long_liquidations: int  # Number of suspected long liquidations
    short_liquidations: int  # Number of suspected short liquidations
    total_long_volume_usd: float
    total_short_volume_usd: float
    status: str  # "Normal", "Elevated", "High"
    last_liquidation: Optional[SuspectedLiquidation] = None


class LiquidationsDetector:
    """Detects suspected liquidations from trade flow across multiple timeframes."""

    def __init__(
        self,
        window_seconds: float = 60.0,
        large_trade_threshold_usd: float = 10000.0,
        cascade_time_window_ms: float = 5000.0,  # 5 seconds
        max_history_seconds: float = 900.0,  # 15 minutes
    ):
        """Initialize liquidations detector.

        Parameters:
        -----------
        window_seconds : float, default 60.0
            Default time window for statistics (default 1 minute)
        large_trade_threshold_usd : float, default 10000.0
            Trades larger than this are considered potentially liquidations
        cascade_time_window_ms : float, default 5000.0
            Time window for detecting trade cascades (milliseconds)
        max_history_seconds : float, default 900.0
            Maximum history to keep (15 minutes for longest window)
        """
        self.window_seconds = window_seconds
        self.max_history_seconds = max_history_seconds
        self.large_trade_threshold = large_trade_threshold_usd
        self.cascade_window_ms = cascade_time_window_ms

        self.suspected_liquidations: deque[SuspectedLiquidation] = deque()
        self.recent_trades: deque = deque()  # For cascade detection

    def add_trade(
        self,
        timestamp_ms: float,
        price: float,
        size_usd: float,
        side: str,  # "buy" or "sell"
    ) -> Optional[SuspectedLiquidation]:
        """Add a trade and check if it might be a liquidation.

        Parameters:
        -----------
        timestamp_ms : float
            Trade timestamp in milliseconds
        price : float
            Trade price
        size_usd : float
            Trade size in USD
        side : str
            "buy" or "sell" from taker's perspective

        Returns:
        --------
        Optional[SuspectedLiquidation]
            Suspected liquidation if detected, None otherwise
        """
        # Store trade for cascade detection
        self.recent_trades.append({
            'timestamp_ms': timestamp_ms,
            'price': price,
            'size_usd': size_usd,
            'side': side,
        })

        # Clean old trades
        self._cleanup_old_data()

        # Detection logic
        liquidation = None

        # 1. Single large trade detection
        if size_usd >= self.large_trade_threshold:
            confidence = min(size_usd / (self.large_trade_threshold * 5), 1.0)
            # Sell = long liquidation (forced to sell)
            # Buy = short liquidation (forced to buy/cover)
            liq_side = "long" if side == "sell" else "short"

            liquidation = SuspectedLiquidation(
                timestamp_ms=timestamp_ms,
                side=liq_side,
                total_volume_usd=size_usd,
                price=price,
                confidence=confidence,
                reason=f"Large ${size_usd:,.0f} {side} order",
            )

        # 2. Cascade detection (multiple trades in quick succession)
        elif self._detect_cascade(timestamp_ms, side):
            cascade_volume = self._get_cascade_volume(timestamp_ms, side)
            liq_side = "long" if side == "sell" else "short"

            liquidation = SuspectedLiquidation(
                timestamp_ms=timestamp_ms,
                side=liq_side,
                total_volume_usd=cascade_volume,
                price=price,
                confidence=0.7,  # Lower confidence for cascades
                reason=f"Trade cascade: ${cascade_volume:,.0f} in {self.cascade_window_ms/1000}s",
            )

        if liquidation:
            self.suspected_liquidations.append(liquidation)

        return liquidation

    def _detect_cascade(self, current_timestamp_ms: float, side: str) -> bool:
        """Detect if recent trades form a cascade pattern.

        Parameters:
        -----------
        current_timestamp_ms : float
            Current timestamp
        side : str
            Trade side ("buy" or "sell")

        Returns:
        --------
        bool
            True if cascade detected
        """
        cutoff_ms = current_timestamp_ms - self.cascade_window_ms

        # Count trades in same direction within cascade window
        same_direction_count = 0
        total_volume = 0.0

        for trade in reversed(self.recent_trades):
            if trade['timestamp_ms'] < cutoff_ms:
                break

            if trade['side'] == side:
                same_direction_count += 1
                total_volume += trade['size_usd']

        # Cascade = 5+ trades in same direction within window, totaling significant volume
        return same_direction_count >= 5 and total_volume >= self.large_trade_threshold

    def _get_cascade_volume(self, current_timestamp_ms: float, side: str) -> float:
        """Get total volume of cascade.

        Parameters:
        -----------
        current_timestamp_ms : float
            Current timestamp
        side : str
            Trade side

        Returns:
        --------
        float
            Total volume in USD
        """
        cutoff_ms = current_timestamp_ms - self.cascade_window_ms
        total = 0.0

        for trade in reversed(self.recent_trades):
            if trade['timestamp_ms'] < cutoff_ms:
                break
            if trade['side'] == side:
                total += trade['size_usd']

        return total

    def _cleanup_old_data(self) -> None:
        """Remove old data outside retention windows."""
        current_time_ms = time.time() * 1000

        # Clean suspected liquidations (use max history for multi-timeframe support)
        cutoff_ms = current_time_ms - (self.max_history_seconds * 1000)
        while self.suspected_liquidations and self.suspected_liquidations[0].timestamp_ms < cutoff_ms:
            self.suspected_liquidations.popleft()

        # Clean recent trades (use cascade window + buffer)
        trade_cutoff_ms = current_time_ms - (self.cascade_window_ms * 2)
        while self.recent_trades and self.recent_trades[0]['timestamp_ms'] < trade_cutoff_ms:
            self.recent_trades.popleft()

    def get_stats(self, window_seconds: Optional[float] = None) -> LiquidationStats:
        """Get liquidation statistics for a specific time window.

        Parameters:
        -----------
        window_seconds : Optional[float]
            Time window in seconds (if None, uses default window_seconds)

        Returns:
        --------
        LiquidationStats
            Statistics for the specified time window
        """
        self._cleanup_old_data()

        if window_seconds is None:
            window_seconds = self.window_seconds

        # Filter liquidations within the requested window
        current_time_ms = time.time() * 1000
        cutoff_ms = current_time_ms - (window_seconds * 1000)
        windowed_liq = [liq for liq in self.suspected_liquidations if liq.timestamp_ms >= cutoff_ms]

        long_count = 0
        short_count = 0
        long_volume = 0.0
        short_volume = 0.0
        last_liq = None

        for liq in windowed_liq:
            if liq.side == "long":
                long_count += 1
                long_volume += liq.total_volume_usd
            elif liq.side == "short":
                short_count += 1
                short_volume += liq.total_volume_usd

            last_liq = liq  # Will end up being the most recent

        # Determine status
        total_count = long_count + short_count
        if total_count == 0:
            status = "Normal"
        elif total_count < 3:
            status = "Normal"
        elif total_count < 10:
            status = "Elevated"
        else:
            status = "High"

        return LiquidationStats(
            window_seconds=window_seconds,
            long_liquidations=long_count,
            short_liquidations=short_count,
            total_long_volume_usd=long_volume,
            total_short_volume_usd=short_volume,
            status=status,
            last_liquidation=last_liq,
        )

    def get_multi_timeframe_stats(self) -> Dict[str, LiquidationStats]:
        """Get liquidation statistics across multiple timeframes.

        Returns:
        --------
        Dict[str, LiquidationStats]
            Liquidation stats for 60s, 5m, and 15m windows
        """
        return {
            "60s": self.get_stats(60.0),
            "5m": self.get_stats(300.0),
            "15m": self.get_stats(900.0),
        }


def format_liquidation_summary(stats: LiquidationStats) -> str:
    """Format liquidation stats as a readable summary.

    Parameters:
    -----------
    stats : LiquidationStats
        Liquidation statistics

    Returns:
    --------
    str
        Formatted summary string
    """
    lines = []
    lines.append(f"\nLiquidations ({stats.window_seconds}s window)")
    lines.append("=" * 60)
    lines.append(f"Status: {stats.status}")
    lines.append(f"\nLong Liquidations:  {stats.long_liquidations}  (${stats.total_long_volume_usd:,.0f})")
    lines.append(f"Short Liquidations: {stats.short_liquidations}  (${stats.total_short_volume_usd:,.0f})")

    if stats.last_liquidation:
        lines.append(f"\nLast Suspected Liquidation:")
        lines.append(f"  Side: {stats.last_liquidation.side.upper()}")
        lines.append(f"  Volume: ${stats.last_liquidation.total_volume_usd:,.0f}")
        lines.append(f"  Price: ${stats.last_liquidation.price:.2f}")
        lines.append(f"  Confidence: {stats.last_liquidation.confidence*100:.0f}%")
        lines.append(f"  Reason: {stats.last_liquidation.reason}")

    lines.append("=" * 60)

    return "\n".join(lines)
