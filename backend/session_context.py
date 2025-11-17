"""Session/Daily context tracker.

This module tracks intraday/session-level market context:
- Daily high/low
- Session VWAP
- 24h volume
- Current position within daily range
- Volume statistics

These metrics give the AI essential context about where the market is
within the trading session/day.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Optional, Tuple
import statistics


@dataclass
class Trade:
    """A single trade for VWAP calculation."""
    timestamp_ms: float
    price: float
    size_usd: float


@dataclass
class SessionContext:
    """Session/daily market context."""
    # Daily extremes
    daily_high: float
    daily_low: float
    current_price: float

    # Position in range
    pct_from_low: float  # 0-100%
    pct_from_high: float  # 0-100%
    pct_through_range: float  # 0-100%, where 0=low, 100=high

    # VWAP
    session_vwap: float
    distance_from_vwap_bps: float  # basis points from VWAP

    # Volume (tracked from session)
    session_volume_usd: float
    last_1h_volume_usd: float
    last_4h_volume_usd: float

    # Time context
    session_start_ms: float
    session_duration_hours: float

    # Hyperliquid API volumes (real market data)
    hyperliquid_24h_volume_usd: Optional[float] = None
    hyperliquid_1h_volume_usd: Optional[float] = None
    hyperliquid_4h_volume_usd: Optional[float] = None


class SessionContextTracker:
    """Tracks session/daily context for market analysis."""

    def __init__(
        self,
        session_duration_hours: float = 24.0,
        vwap_window_hours: float = 24.0,
        volume_windows: list[float] = None,  # in hours
    ):
        """Initialize session context tracker.

        Parameters:
        -----------
        session_duration_hours : float, default 24.0
            How long is a "session" (24h for crypto)
        vwap_window_hours : float, default 24.0
            Window for VWAP calculation
        volume_windows : list[float], optional
            Volume lookback windows in hours (default [1.0, 4.0])
        """
        self.session_duration_hours = session_duration_hours
        self.vwap_window_hours = vwap_window_hours
        self.volume_windows = volume_windows or [1.0, 4.0]

        # Session tracking
        self.session_start_ms: Optional[float] = None
        self.daily_high: Optional[float] = None
        self.daily_low: Optional[float] = None
        self.current_price: Optional[float] = None

        # Trade history for VWAP and volume
        self.trades: deque[Trade] = deque()

    def reset_session(self, timestamp_ms: float, starting_price: float) -> None:
        """Reset session (e.g., at day boundary or manually)."""
        self.session_start_ms = timestamp_ms
        self.daily_high = starting_price
        self.daily_low = starting_price
        self.current_price = starting_price
        # Keep trades for VWAP continuity

    def add_trade(self, timestamp_ms: float, price: float, size_usd: float) -> None:
        """Add a trade to session tracking."""
        # Initialize session if first trade
        if self.session_start_ms is None:
            self.reset_session(timestamp_ms, price)

        # Check if we need to reset (new session)
        time_since_session_start = (timestamp_ms - self.session_start_ms) / (1000 * 3600)
        if time_since_session_start >= self.session_duration_hours:
            self.reset_session(timestamp_ms, price)

        # Update extremes
        if self.daily_high is None or price > self.daily_high:
            self.daily_high = price
        if self.daily_low is None or price < self.daily_low:
            self.daily_low = price

        self.current_price = price

        # Store trade
        trade = Trade(timestamp_ms=timestamp_ms, price=price, size_usd=size_usd)
        self.trades.append(trade)

        # Cleanup old trades
        self._cleanup_old_trades(timestamp_ms)

    def update_price(self, timestamp_ms: float, price: float) -> None:
        """Update current price (from orderbook mid, for example)."""
        if self.session_start_ms is None:
            self.reset_session(timestamp_ms, price)

        # Update extremes
        if self.daily_high is None or price > self.daily_high:
            self.daily_high = price
        if self.daily_low is None or price < self.daily_low:
            self.daily_low = price

        self.current_price = price

    def _cleanup_old_trades(self, current_time_ms: float) -> None:
        """Remove trades outside VWAP window."""
        if not self.trades:
            return

        # Keep trades within VWAP window
        cutoff_ms = current_time_ms - (self.vwap_window_hours * 3600 * 1000)

        while self.trades and self.trades[0].timestamp_ms < cutoff_ms:
            self.trades.popleft()

    def _calculate_vwap(self, trades: list[Trade]) -> Optional[float]:
        """Calculate VWAP from trades."""
        if not trades:
            return None

        total_notional = 0.0
        total_volume = 0.0

        for trade in trades:
            total_notional += trade.price * trade.size_usd
            total_volume += trade.size_usd

        if total_volume == 0:
            return None

        return total_notional / total_volume

    def _calculate_volume_for_window(
        self,
        trades: list[Trade],
        window_hours: float,
        current_time_ms: float
    ) -> float:
        """Calculate volume for a specific time window."""
        cutoff_ms = current_time_ms - (window_hours * 3600 * 1000)
        volume = sum(t.size_usd for t in trades if t.timestamp_ms >= cutoff_ms)
        return volume

    def get_context(self) -> Optional[SessionContext]:
        """Get current session context.

        Returns:
        --------
        Optional[SessionContext]
            Session context, or None if not enough data
        """
        if self.current_price is None or self.daily_high is None or self.daily_low is None:
            return None

        if self.session_start_ms is None:
            return None

        current_time_ms = time.time() * 1000

        # Calculate position in range
        price_range = self.daily_high - self.daily_low

        if price_range > 0:
            pct_from_low = ((self.current_price - self.daily_low) / self.daily_low) * 100
            pct_from_high = ((self.daily_high - self.current_price) / self.daily_high) * 100
            pct_through_range = ((self.current_price - self.daily_low) / price_range) * 100
        else:
            # Price hasn't moved
            pct_from_low = 0.0
            pct_from_high = 0.0
            pct_through_range = 50.0  # Middle

        # Calculate VWAP
        session_vwap = self._calculate_vwap(list(self.trades))
        if session_vwap is None:
            session_vwap = self.current_price  # Fallback

        distance_from_vwap_bps = ((self.current_price - session_vwap) / session_vwap) * 10000

        # Calculate volumes
        session_volume_usd = sum(t.size_usd for t in self.trades)
        last_1h_volume = self._calculate_volume_for_window(list(self.trades), 1.0, current_time_ms)
        last_4h_volume = self._calculate_volume_for_window(list(self.trades), 4.0, current_time_ms)

        # Session duration
        session_duration_hours = (current_time_ms - self.session_start_ms) / (1000 * 3600)

        return SessionContext(
            daily_high=self.daily_high,
            daily_low=self.daily_low,
            current_price=self.current_price,
            pct_from_low=pct_from_low,
            pct_from_high=pct_from_high,
            pct_through_range=pct_through_range,
            session_vwap=session_vwap,
            distance_from_vwap_bps=distance_from_vwap_bps,
            session_volume_usd=session_volume_usd,
            last_1h_volume_usd=last_1h_volume,
            last_4h_volume_usd=last_4h_volume,
            session_start_ms=self.session_start_ms,
            session_duration_hours=session_duration_hours,
        )


def format_session_context(ctx: SessionContext) -> str:
    """Format session context as readable summary.

    Parameters:
    -----------
    ctx : SessionContext
        Session context

    Returns:
    --------
    str
        Formatted summary
    """
    lines = []
    lines.append("\nSession/Daily Context")
    lines.append("=" * 80)

    lines.append(f"\nPrice Action:")
    lines.append(f"  Current Price:    ${ctx.current_price:,.2f}")
    lines.append(f"  Daily High:       ${ctx.daily_high:,.2f}  ({ctx.pct_from_high:+.2f}% away)")
    lines.append(f"  Daily Low:        ${ctx.daily_low:,.2f}  ({ctx.pct_from_low:+.2f}% away)")
    lines.append(f"  Through Range:    {ctx.pct_through_range:.1f}%")

    lines.append(f"\nVWAP:")
    lines.append(f"  Session VWAP:     ${ctx.session_vwap:,.2f}")
    lines.append(f"  Distance:         {ctx.distance_from_vwap_bps:+.1f} bps")

    lines.append(f"\nVolume:")
    lines.append(f"  Session Volume:   ${ctx.session_volume_usd:,.0f}")
    lines.append(f"  Last 1h:          ${ctx.last_1h_volume_usd:,.0f}")
    lines.append(f"  Last 4h:          ${ctx.last_4h_volume_usd:,.0f}")

    lines.append(f"\nSession Info:")
    lines.append(f"  Duration:         {ctx.session_duration_hours:.1f} hours")

    lines.append("=" * 80)

    return "\n".join(lines)
