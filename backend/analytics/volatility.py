"""Volatility metrics and regime detection.

This module calculates volatility measures (ATR, realized vol) and detects
volatility regimes (low/normal/high) to help inform trading decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal

VolatilityRegime = Literal["low", "normal", "high"]


@dataclass
class VolatilityMetrics:
    """Volatility metrics across timeframes."""
    atr_1m: float
    atr_5m: float
    realized_vol_1m: float  # Std dev of 1m returns
    realized_vol_5m: float  # Std dev of 5m returns
    regime: VolatilityRegime
    percentile: float  # Current vol as percentile of historical


class VolatilityTracker:
    """Track volatility and detect regime changes."""

    def __init__(
        self,
        low_threshold_percentile: float = 33.0,
        high_threshold_percentile: float = 67.0,
        history_window: int = 100,
    ):
        """Initialize volatility tracker.

        Parameters
        ----------
        low_threshold_percentile : float
            Below this percentile = low volatility (default 33rd percentile)
        high_threshold_percentile : float
            Above this percentile = high volatility (default 67th percentile)
        history_window : int
            Number of historical values to keep for percentile calculation
        """
        self.low_threshold = low_threshold_percentile
        self.high_threshold = high_threshold_percentile
        self.history_window = history_window

        # Store historical ATR values for regime detection
        self.atr_1m_history: List[float] = []
        self.atr_5m_history: List[float] = []

    def calculate_metrics(
        self,
        atr_1m: float,
        atr_5m: float,
        realized_vol_1m: float,
        realized_vol_5m: float,
    ) -> VolatilityMetrics:
        """Calculate volatility metrics and determine regime.

        Parameters
        ----------
        atr_1m : float
            1-minute ATR
        atr_5m : float
            5-minute ATR
        realized_vol_1m : float
            1-minute realized volatility
        realized_vol_5m : float
            5-minute realized volatility

        Returns
        -------
        VolatilityMetrics
            Comprehensive volatility metrics
        """
        # Store historical values
        self.atr_1m_history.append(atr_1m)
        self.atr_5m_history.append(atr_5m)

        # Keep only recent history
        if len(self.atr_1m_history) > self.history_window:
            self.atr_1m_history = self.atr_1m_history[-self.history_window:]
        if len(self.atr_5m_history) > self.history_window:
            self.atr_5m_history = self.atr_5m_history[-self.history_window:]

        # Determine regime based on 5m ATR (more stable than 1m)
        regime, percentile = self._detect_regime(atr_5m, self.atr_5m_history)

        return VolatilityMetrics(
            atr_1m=atr_1m,
            atr_5m=atr_5m,
            realized_vol_1m=realized_vol_1m,
            realized_vol_5m=realized_vol_5m,
            regime=regime,
            percentile=percentile,
        )

    def _detect_regime(
        self,
        current_value: float,
        history: List[float],
    ) -> tuple[VolatilityRegime, float]:
        """Detect volatility regime based on historical percentile.

        Parameters
        ----------
        current_value : float
            Current ATR value
        history : List[float]
            Historical ATR values

        Returns
        -------
        tuple[VolatilityRegime, float]
            (regime, percentile)
        """
        if len(history) < 10:
            # Not enough history, assume normal
            return "normal", 50.0

        # Calculate percentile
        sorted_history = sorted(history)
        rank = sum(1 for v in sorted_history if v <= current_value)
        percentile = (rank / len(sorted_history)) * 100.0

        # Determine regime
        if percentile <= self.low_threshold:
            regime = "low"
        elif percentile >= self.high_threshold:
            regime = "high"
        else:
            regime = "normal"

        return regime, percentile
