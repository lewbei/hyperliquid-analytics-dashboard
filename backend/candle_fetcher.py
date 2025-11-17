"""Hyperliquid candle data fetcher.

This module fetches historical OHLCV candle data from Hyperliquid's REST API
and can subscribe to live candle updates via WebSocket.

Hyperliquid provides candles for intervals:
1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 8h, 12h, 1d, 3d, 1w, 1M

Maximum 5000 candles available per request.
"""

from __future__ import annotations

import time
import requests
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class HyperliquidCandle:
    """OHLCV candle from Hyperliquid."""
    timestamp_ms: float  # Opening time in milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: float  # Volume in base asset

    @property
    def time_s(self) -> int:
        """Opening time in seconds (epoch)."""
        return int(self.timestamp_ms / 1000)


class HyperliquidCandleFetcher:
    """Fetches historical candle data from Hyperliquid REST API."""

    BASE_URL = "https://api.hyperliquid.xyz/info"

    SUPPORTED_INTERVALS = [
        "1m", "3m", "5m", "15m", "30m",
        "1h", "2h", "4h", "8h", "12h",
        "1d", "3d", "1w", "1M"
    ]

    def __init__(self, coin: str = "SOL"):
        """Initialize candle fetcher.

        Parameters:
        -----------
        coin : str
            Coin symbol (e.g., "SOL", "BTC", "ETH")
        """
        self.coin = coin

    def fetch_candles(
        self,
        interval: str,
        start_time_ms: Optional[float] = None,
        end_time_ms: Optional[float] = None,
        limit: int = 500
    ) -> List[HyperliquidCandle]:
        """Fetch historical candles from Hyperliquid.

        Parameters:
        -----------
        interval : str
            Candle interval (e.g., "1m", "5m", "15m", "1h", "1d")
        start_time_ms : Optional[float]
            Start time in milliseconds (if None, fetches most recent candles)
        end_time_ms : Optional[float]
            End time in milliseconds (default: now)
        limit : int
            Maximum number of candles to fetch (max 5000)

        Returns:
        --------
        List[HyperliquidCandle]
            List of candles (oldest to newest)
        """
        if interval not in self.SUPPORTED_INTERVALS:
            raise ValueError(f"Unsupported interval: {interval}. Must be one of {self.SUPPORTED_INTERVALS}")

        if limit > 5000:
            limit = 5000

        # If no times specified, fetch most recent candles
        if end_time_ms is None:
            end_time_ms = time.time() * 1000

        if start_time_ms is None:
            # Calculate start time based on interval and limit
            interval_ms = self._interval_to_ms(interval)
            start_time_ms = end_time_ms - (interval_ms * limit)

        request_data = {
            "type": "candleSnapshot",
            "req": {
                "coin": self.coin,
                "interval": interval,
                "startTime": int(start_time_ms),
                "endTime": int(end_time_ms),
            }
        }

        try:
            response = requests.post(
                self.BASE_URL,
                json=request_data,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            candles = []
            for candle_data in data:
                # Hyperliquid returns dictionaries with keys:
                # t: opening timestamp, o: open, h: high, l: low, c: close, v: volume
                if isinstance(candle_data, dict):
                    candles.append(HyperliquidCandle(
                        timestamp_ms=float(candle_data['t']),
                        open=float(candle_data['o']),
                        high=float(candle_data['h']),
                        low=float(candle_data['l']),
                        close=float(candle_data['c']),
                        volume=float(candle_data['v']),
                    ))

            return candles

        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Failed to fetch candles for {self.coin} {interval}: {e}")
            return []

    def fetch_recent_candles(self, interval: str, count: int = 500) -> List[HyperliquidCandle]:
        """Fetch most recent N candles.

        Parameters:
        -----------
        interval : str
            Candle interval
        count : int
            Number of candles to fetch (max 5000)

        Returns:
        --------
        List[HyperliquidCandle]
            List of recent candles
        """
        return self.fetch_candles(interval, limit=count)

    def fetch_daily_candles(self, days: int = 30) -> List[HyperliquidCandle]:
        """Fetch daily candles for the last N days.

        Parameters:
        -----------
        days : int
            Number of days to fetch

        Returns:
        --------
        List[HyperliquidCandle]
            List of daily candles
        """
        return self.fetch_recent_candles("1d", count=days)

    def _interval_to_ms(self, interval: str) -> int:
        """Convert interval string to milliseconds.

        Parameters:
        -----------
        interval : str
            Interval string (e.g., "1m", "5m", "1h", "1d")

        Returns:
        --------
        int
            Interval in milliseconds
        """
        # Parse interval
        unit = interval[-1]
        value = int(interval[:-1])

        if unit == 'm':
            return value * 60 * 1000
        elif unit == 'h':
            return value * 60 * 60 * 1000
        elif unit == 'd':
            return value * 24 * 60 * 60 * 1000
        elif unit == 'w':
            return value * 7 * 24 * 60 * 60 * 1000
        elif unit == 'M':
            return value * 30 * 24 * 60 * 60 * 1000  # Approximate
        else:
            raise ValueError(f"Unknown interval unit: {unit}")

    def get_current_daily_range(self) -> tuple[float, float, float] | None:
        """Get current daily high, low, and close.

        Returns:
        --------
        tuple[float, float, float] | None
            (daily_high, daily_low, current_close) or None if no data
        """
        candles = self.fetch_recent_candles("1d", count=1)
        if not candles:
            return None

        current_day = candles[-1]
        return (current_day.high, current_day.low, current_day.close)


def format_candle(candle: HyperliquidCandle) -> str:
    """Format candle as readable string.

    Parameters:
    -----------
    candle : HyperliquidCandle
        Candle to format

    Returns:
    --------
    str
        Formatted string
    """
    from datetime import datetime
    dt = datetime.fromtimestamp(candle.time_s)
    return (
        f"[{dt.strftime('%Y-%m-%d %H:%M')}] "
        f"O: {candle.open:.2f}, H: {candle.high:.2f}, "
        f"L: {candle.low:.2f}, C: {candle.close:.2f}, "
        f"V: {candle.volume:.2f}"
    )
