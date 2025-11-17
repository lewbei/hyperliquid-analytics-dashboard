"""Slippage and execution cost estimator.

This module estimates slippage, VWAP, and round-trip costs for different
trade sizes by walking through the orderbook.

This helps the AI understand execution costs before deciding whether
M (expected profit) > 2 × cost (spread + slippage + fees).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class OrderBookLevel:
    """Single orderbook level."""
    price: float
    size: float  # in base asset
    total_usd: float


@dataclass
class SlippageEstimate:
    """Slippage estimate for a specific trade size."""
    trade_size_usd: float
    side: str  # "buy" or "sell"

    # Execution metrics
    avg_fill_price: float  # VWAP
    best_price: float  # Best bid/ask
    slippage_bps: float  # Slippage in basis points from best price
    spread_bps: float  # Current spread

    # Cost breakdown
    fee_bps: float  # Assumed trading fee (typically 2-5 bps for taker)
    round_trip_cost_bps: float  # spread + slippage + 2*fee

    # Feasibility
    is_feasible: bool  # Whether there's enough liquidity
    liquidity_used_pct: float  # % of available liquidity used


class SlippageEstimator:
    """Estimates slippage and execution costs from orderbook."""

    def __init__(
        self,
        taker_fee_bps: float = 2.8,  # Hyperliquid taker fee ~2.8 bps (0.028%)
    ):
        """Initialize slippage estimator.

        Parameters
        ----------
        taker_fee_bps : float
            Taker fee in basis points (default 2.8 for Hyperliquid)
        """
        self.taker_fee_bps = taker_fee_bps

    def estimate_buy(
        self,
        asks: List[OrderBookLevel],
        trade_size_usd: float,
        best_ask: float,
        spread_bps: float,
    ) -> SlippageEstimate:
        """Estimate slippage for a buy order.

        Parameters
        ----------
        asks : List[OrderBookLevel]
            Ask side of orderbook (sorted best to worst)
        trade_size_usd : float
            Trade size in USD
        best_ask : float
            Best ask price
        spread_bps : float
            Current spread in basis points

        Returns
        -------
        SlippageEstimate
            Slippage estimate for this buy
        """
        if not asks or trade_size_usd <= 0:
            return self._empty_estimate(trade_size_usd, "buy", best_ask, spread_bps)

        # Walk through asks to fill the order
        total_usd_filled = 0.0
        total_notional = 0.0
        total_liquidity_usd = sum(level.total_usd for level in asks)

        for level in asks:
            if total_usd_filled >= trade_size_usd:
                break

            # How much can we fill at this level?
            remaining_usd = trade_size_usd - total_usd_filled
            fill_usd = min(remaining_usd, level.total_usd)

            total_usd_filled += fill_usd
            total_notional += fill_usd * level.price

        # Check if feasible
        is_feasible = total_usd_filled >= trade_size_usd * 0.99  # Allow 1% shortfall

        # Calculate VWAP
        avg_fill_price = total_notional / total_usd_filled if total_usd_filled > 0 else best_ask

        # Calculate slippage from best price
        slippage_bps = ((avg_fill_price - best_ask) / best_ask) * 10000

        # Round-trip cost
        round_trip_cost_bps = spread_bps + slippage_bps + (2 * self.taker_fee_bps)

        # Liquidity used
        liquidity_used_pct = (total_usd_filled / total_liquidity_usd * 100) if total_liquidity_usd > 0 else 100.0

        return SlippageEstimate(
            trade_size_usd=trade_size_usd,
            side="buy",
            avg_fill_price=avg_fill_price,
            best_price=best_ask,
            slippage_bps=slippage_bps,
            spread_bps=spread_bps,
            fee_bps=self.taker_fee_bps,
            round_trip_cost_bps=round_trip_cost_bps,
            is_feasible=is_feasible,
            liquidity_used_pct=liquidity_used_pct,
        )

    def estimate_sell(
        self,
        bids: List[OrderBookLevel],
        trade_size_usd: float,
        best_bid: float,
        spread_bps: float,
    ) -> SlippageEstimate:
        """Estimate slippage for a sell order.

        Parameters
        ----------
        bids : List[OrderBookLevel]
            Bid side of orderbook (sorted best to worst)
        trade_size_usd : float
            Trade size in USD
        best_bid : float
            Best bid price
        spread_bps : float
            Current spread in basis points

        Returns
        -------
        SlippageEstimate
            Slippage estimate for this sell
        """
        if not bids or trade_size_usd <= 0:
            return self._empty_estimate(trade_size_usd, "sell", best_bid, spread_bps)

        # Walk through bids to fill the order
        total_usd_filled = 0.0
        total_notional = 0.0
        total_liquidity_usd = sum(level.total_usd for level in bids)

        for level in bids:
            if total_usd_filled >= trade_size_usd:
                break

            # How much can we fill at this level?
            remaining_usd = trade_size_usd - total_usd_filled
            fill_usd = min(remaining_usd, level.total_usd)

            total_usd_filled += fill_usd
            total_notional += fill_usd * level.price

        # Check if feasible
        is_feasible = total_usd_filled >= trade_size_usd * 0.99  # Allow 1% shortfall

        # Calculate VWAP
        avg_fill_price = total_notional / total_usd_filled if total_usd_filled > 0 else best_bid

        # Calculate slippage from best price (negative for sells that get worse price)
        slippage_bps = ((best_bid - avg_fill_price) / best_bid) * 10000

        # Round-trip cost
        round_trip_cost_bps = spread_bps + slippage_bps + (2 * self.taker_fee_bps)

        # Liquidity used
        liquidity_used_pct = (total_usd_filled / total_liquidity_usd * 100) if total_liquidity_usd > 0 else 100.0

        return SlippageEstimate(
            trade_size_usd=trade_size_usd,
            side="sell",
            avg_fill_price=avg_fill_price,
            best_price=best_bid,
            slippage_bps=slippage_bps,
            spread_bps=spread_bps,
            fee_bps=self.taker_fee_bps,
            round_trip_cost_bps=round_trip_cost_bps,
            is_feasible=is_feasible,
            liquidity_used_pct=liquidity_used_pct,
        )

    def estimate_for_sizes(
        self,
        bids: List[OrderBookLevel],
        asks: List[OrderBookLevel],
        trade_sizes_usd: List[float],
        best_bid: float,
        best_ask: float,
        spread_bps: float,
    ) -> dict[str, dict[str, SlippageEstimate]]:
        """Estimate slippage for multiple trade sizes.

        Parameters
        ----------
        bids : List[OrderBookLevel]
            Bid side of orderbook
        asks : List[OrderBookLevel]
            Ask side of orderbook
        trade_sizes_usd : List[float]
            Trade sizes to estimate (e.g., [500, 1000, 5000])
        best_bid : float
            Best bid price
        best_ask : float
            Best ask price
        spread_bps : float
            Current spread in basis points

        Returns
        -------
        dict[str, dict[str, SlippageEstimate]]
            Nested dict: {size_label: {"buy": estimate, "sell": estimate}}
        """
        results = {}

        for size_usd in trade_sizes_usd:
            # Format size label
            if size_usd >= 1000:
                size_label = f"${int(size_usd/1000)}k"
            else:
                size_label = f"${int(size_usd)}"

            buy_est = self.estimate_buy(asks, size_usd, best_ask, spread_bps)
            sell_est = self.estimate_sell(bids, size_usd, best_bid, spread_bps)

            results[size_label] = {
                "buy": buy_est,
                "sell": sell_est,
            }

        return results

    def _empty_estimate(
        self,
        trade_size_usd: float,
        side: str,
        best_price: float,
        spread_bps: float,
    ) -> SlippageEstimate:
        """Create empty estimate when orderbook is empty."""
        return SlippageEstimate(
            trade_size_usd=trade_size_usd,
            side=side,
            avg_fill_price=best_price,
            best_price=best_price,
            slippage_bps=0.0,
            spread_bps=spread_bps,
            fee_bps=self.taker_fee_bps,
            round_trip_cost_bps=spread_bps + (2 * self.taker_fee_bps),
            is_feasible=False,
            liquidity_used_pct=100.0,
        )


def format_slippage_summary(estimates: dict[str, dict[str, SlippageEstimate]]) -> str:
    """Format slippage estimates as readable summary.

    Parameters
    ----------
    estimates : dict
        Slippage estimates from estimate_for_sizes()

    Returns
    -------
    str
        Formatted summary
    """
    lines = []
    lines.append("\nSlippage & Execution Cost Estimates")
    lines.append("=" * 80)

    for size_label, size_estimates in estimates.items():
        lines.append(f"\n{size_label} Trade Size:")
        lines.append("-" * 40)

        buy_est = size_estimates["buy"]
        sell_est = size_estimates["sell"]

        lines.append(f"  BUY:  VWAP ${buy_est.avg_fill_price:.2f}  |  "
                    f"Slippage: {buy_est.slippage_bps:.1f} bps  |  "
                    f"Round-trip: {buy_est.round_trip_cost_bps:.1f} bps")
        lines.append(f"        Liquidity Used: {buy_est.liquidity_used_pct:.1f}%  |  "
                    f"Feasible: {buy_est.is_feasible}")

        lines.append(f"  SELL: VWAP ${sell_est.avg_fill_price:.2f}  |  "
                    f"Slippage: {sell_est.slippage_bps:.1f} bps  |  "
                    f"Round-trip: {sell_est.round_trip_cost_bps:.1f} bps")
        lines.append(f"        Liquidity Used: {sell_est.liquidity_used_pct:.1f}%  |  "
                    f"Feasible: {sell_est.is_feasible}")

    lines.append("=" * 80)

    return "\n".join(lines)
