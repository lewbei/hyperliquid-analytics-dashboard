"""Multi-timeframe candle aggregator.

This module aggregates 1m candles into higher timeframes (5m, 15m, 1h) and
computes derived metrics like returns, ATR, and volume ratios.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class OHLCV:
    """OHLCV candle data."""
    timestamp_ms: float  # Candle open time
    open: float
    high: float
    low: float
    close: float
    volume: float
    n_trades: int = 0

    @property
    def return_pct(self) -> float:
        """Return percentage: (close - open) / open * 100."""
        if self.open == 0:
            return 0.0
        return ((self.close - self.open) / self.open) * 100.0

    @property
    def range_pct(self) -> float:
        """High-low range as percentage of open."""
        if self.open == 0:
            return 0.0
        return ((self.high - self.low) / self.open) * 100.0


@dataclass
class CandleMetrics:
    """Comprehensive candle metrics for a specific timeframe."""
    interval: str  # '1m', '5m', '15m', '1h'
    current_candle: Optional[OHLCV]
    return_pct: float
    volume_vs_avg: float  # Current volume / average volume
    atr: float  # Average True Range
    realized_vol: float  # Realized volatility (std dev of returns)


def aggregate_candles(candles: List[OHLCV]) -> OHLCV:
    """Aggregate multiple candles into one.

    Parameters
    ----------
    candles : List[OHLCV]
        List of candles to aggregate (must be chronological)

    Returns
    -------
    OHLCV
        Aggregated candle
    """
    if not candles:
        raise ValueError("Cannot aggregate empty candle list")

    return OHLCV(
        timestamp_ms=candles[0].timestamp_ms,
        open=candles[0].open,
        high=max(c.high for c in candles),
        low=min(c.low for c in candles),
        close=candles[-1].close,
        volume=sum(c.volume for c in candles),
        n_trades=sum(c.n_trades for c in candles),
    )


class CandleAggregator:
    """Multi-timeframe candle aggregator."""

    def __init__(
        self,
        base_interval: str = "1m",
        max_history: int = 500,  # Keep up to 500 base candles (8+ hours)
    ):
        """Initialize candle aggregator.

        Parameters
        ----------
        base_interval : str
            Base candle interval (default '1m')
        max_history : int
            Maximum number of base candles to keep in history
        """
        self.base_interval = base_interval
        self.max_history = max_history

        # Store base candles (1m)
        self.candles_1m: deque[OHLCV] = deque(maxlen=max_history)

        # Interval configurations: (name, minutes)
        self.intervals = {
            '1m': 1,
            '5m': 5,
            '15m': 15,
            '1h': 60,
        }

    def add_candle(self, candle: OHLCV) -> None:
        """Add a new 1m candle.

        Parameters
        ----------
        candle : OHLCV
            1-minute candle data
        """
        self.candles_1m.append(candle)

    def get_candles(self, interval: str, count: int = 100) -> List[OHLCV]:
        """Get aggregated candles for a specific interval.

        Parameters
        ----------
        interval : str
            Interval ('1m', '5m', '15m', '1h')
        count : int
            Number of candles to return (most recent)

        Returns
        -------
        List[OHLCV]
            List of candles (most recent last)
        """
        if interval not in self.intervals:
            raise ValueError(f"Unknown interval: {interval}")

        if interval == '1m':
            # Return raw 1m candles
            return list(self.candles_1m)[-count:]

        # Aggregate into higher timeframe
        minutes = self.intervals[interval]
        aggregated = []

        if not self.candles_1m:
            return []

        # Group candles by interval
        current_group = []
        group_start_ms = None

        for candle in self.candles_1m:
            # Determine which interval bucket this candle belongs to
            candle_minutes = int(candle.timestamp_ms / 1000 / 60)
            bucket_minutes = (candle_minutes // minutes) * minutes
            bucket_start_ms = bucket_minutes * 60 * 1000

            if group_start_ms is None:
                group_start_ms = bucket_start_ms

            if bucket_start_ms == group_start_ms:
                # Same bucket, add to current group
                current_group.append(candle)
            else:
                # New bucket, aggregate previous group
                if current_group:
                    aggregated.append(aggregate_candles(current_group))
                current_group = [candle]
                group_start_ms = bucket_start_ms

        # Aggregate final group
        if current_group:
            aggregated.append(aggregate_candles(current_group))

        return aggregated[-count:]

    def get_metrics(self, interval: str) -> Optional[CandleMetrics]:
        """Get comprehensive metrics for a specific interval.

        Parameters
        ----------
        interval : str
            Interval ('1m', '5m', '15m', '1h')

        Returns
        -------
        Optional[CandleMetrics]
            Candle metrics or None if insufficient data
        """
        candles = self.get_candles(interval, count=100)

        if len(candles) < 2:
            return None

        current = candles[-1]

        # Calculate return
        return_pct = current.return_pct

        # Calculate volume vs average
        volumes = [c.volume for c in candles]
        avg_volume = sum(volumes) / len(volumes)
        volume_vs_avg = current.volume / avg_volume if avg_volume > 0 else 1.0

        # Calculate ATR (Average True Range)
        atr = self._calculate_atr(candles, period=14)

        # Calculate realized volatility
        returns = [c.return_pct for c in candles[-20:]]  # Last 20 periods
        realized_vol = self._std_dev(returns) if len(returns) >= 2 else 0.0

        return CandleMetrics(
            interval=interval,
            current_candle=current,
            return_pct=return_pct,
            volume_vs_avg=volume_vs_avg,
            atr=atr,
            realized_vol=realized_vol,
        )

    def get_multi_timeframe_returns(self) -> Dict[str, float]:
        """Get returns across all timeframes.

        Returns
        -------
        Dict[str, float]
            Returns for each interval: {'1m': 0.5, '5m': 1.2, ...}
        """
        returns = {}

        for interval in ['1m', '5m', '15m', '1h']:
            metrics = self.get_metrics(interval)
            if metrics:
                returns[interval] = metrics.return_pct
            else:
                returns[interval] = 0.0

        return returns

    def _calculate_atr(self, candles: List[OHLCV], period: int = 14) -> float:
        """Calculate Average True Range.

        Parameters
        ----------
        candles : List[OHLCV]
            Candles to analyze
        period : int
            ATR period (default 14)

        Returns
        -------
        float
            ATR value
        """
        if len(candles) < period + 1:
            return 0.0

        true_ranges = []

        for i in range(1, len(candles)):
            high = candles[i].high
            low = candles[i].low
            prev_close = candles[i-1].close

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)

        # Simple moving average of true ranges
        if len(true_ranges) >= period:
            return sum(true_ranges[-period:]) / period

        return sum(true_ranges) / len(true_ranges) if true_ranges else 0.0

    def _std_dev(self, values: List[float]) -> float:
        """Calculate standard deviation.

        Parameters
        ----------
        values : List[float]
            Values to analyze

        Returns
        -------
        float
            Standard deviation
        """
        if len(values) < 2:
            return 0.0

        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return variance ** 0.5
