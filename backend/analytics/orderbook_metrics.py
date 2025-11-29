"""Orderbook metrics calculator.

This module calculates comprehensive orderbook analytics including:
- Spread (absolute and basis points)
- Mid price
- Depth metrics (L1, L5, by level)
- Imbalance metrics (L1, L5, by level)
- Liquidity metrics for different trade sizes (slippage, VWAP, levels, etc.)

All calculations are based on the orderbook state from L2Book WebSocket events.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Optional
from decimal import Decimal


@dataclass
class OrderBookLevel:
    """A single price level in the orderbook."""
    price: float
    size: float  # Quantity in base asset (e.g., SOL)

    @property
    def notional_usd(self) -> float:
        """Total USD value at this level."""
        return self.price * self.size


@dataclass
class OrderBookSide:
    """One side of the orderbook (bids or asks)."""
    levels: List[OrderBookLevel]  # Sorted: bids descending, asks ascending

    @property
    def best_price(self) -> Optional[float]:
        """Best price on this side (highest bid or lowest ask)."""
        if not self.levels:
            return None
        return self.levels[0].price

    @property
    def best_size(self) -> Optional[float]:
        """Size at best price."""
        if not self.levels:
            return None
        return self.levels[0].size

    def cumulative_depth_usd(self, num_levels: int = 5) -> float:
        """Cumulative depth in USD for top N levels."""
        total = 0.0
        for i, level in enumerate(self.levels[:num_levels]):
            total += level.notional_usd
        return total

    def depth_by_level(self, max_levels: int = 5) -> List[float]:
        """Cumulative depth in USD for each level up to max_levels.

        Returns:
            List of cumulative USD depth for L1, L2, ..., L{max_levels}
        """
        depths = []
        cumulative = 0.0
        for i, level in enumerate(self.levels[:max_levels]):
            cumulative += level.notional_usd
            depths.append(cumulative)
        return depths


@dataclass
class OrderBook:
    """Full orderbook state."""
    bids: OrderBookSide
    asks: OrderBookSide
    timestamp_ms: float  # Unix timestamp in milliseconds

    @property
    def mid_price(self) -> Optional[float]:
        """Mid price between best bid and ask."""
        best_bid = self.bids.best_price
        best_ask = self.asks.best_price
        if best_bid is None or best_ask is None:
            return None
        return (best_bid + best_ask) / 2.0

    @property
    def spread_absolute(self) -> Optional[float]:
        """Absolute spread (ask - bid)."""
        best_bid = self.bids.best_price
        best_ask = self.asks.best_price
        if best_bid is None or best_ask is None:
            return None
        return best_ask - best_bid

    @property
    def spread_bps(self) -> Optional[float]:
        """Spread in basis points (bps).

        bps = (spread / mid_price) * 10000
        """
        spread = self.spread_absolute
        mid = self.mid_price
        if spread is None or mid is None or mid == 0:
            return None
        return (spread / mid) * 10000.0

    def l1_depth_usd(self) -> Tuple[float, float]:
        """L1 depth in USD for (bids, asks)."""
        bid_depth = self.bids.levels[0].notional_usd if self.bids.levels else 0.0
        ask_depth = self.asks.levels[0].notional_usd if self.asks.levels else 0.0
        return (bid_depth, ask_depth)

    def l2_depth_usd(self) -> Tuple[float, float]:
        """L2 cumulative depth in USD for (bids, asks)."""
        bid_depth = self.bids.cumulative_depth_usd(2)
        ask_depth = self.asks.cumulative_depth_usd(2)
        return (bid_depth, ask_depth)

    def l3_depth_usd(self) -> Tuple[float, float]:
        """L3 cumulative depth in USD for (bids, asks)."""
        bid_depth = self.bids.cumulative_depth_usd(3)
        ask_depth = self.asks.cumulative_depth_usd(3)
        return (bid_depth, ask_depth)

    def l4_depth_usd(self) -> Tuple[float, float]:
        """L4 cumulative depth in USD for (bids, asks)."""
        bid_depth = self.bids.cumulative_depth_usd(4)
        ask_depth = self.asks.cumulative_depth_usd(4)
        return (bid_depth, ask_depth)

    def l5_depth_usd(self) -> Tuple[float, float]:
        """L5 cumulative depth in USD for (bids, asks)."""
        bid_depth = self.bids.cumulative_depth_usd(5)
        ask_depth = self.asks.cumulative_depth_usd(5)
        return (bid_depth, ask_depth)

    def imbalance(self, bid_depth: float, ask_depth: float) -> float:
        """Calculate imbalance ratio.

        Imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth)

        Returns value between -1 and 1:
        - Positive: More bid liquidity (bullish)
        - Negative: More ask liquidity (bearish)
        """
        total = bid_depth + ask_depth
        if total == 0:
            return 0.0
        return (bid_depth - ask_depth) / total

    def l1_imbalance(self) -> float:
        """L1 imbalance ratio."""
        bid_depth, ask_depth = self.l1_depth_usd()
        return self.imbalance(bid_depth, ask_depth)

    def l5_imbalance(self) -> float:
        """L5 imbalance ratio."""
        bid_depth, ask_depth = self.l5_depth_usd()
        return self.imbalance(bid_depth, ask_depth)

    def depth_and_imbalance_by_level(self, max_levels: int = 5) -> List[Tuple[float, float, float]]:
        """Get cumulative depth and imbalance for each level.

        Returns:
            List of (bid_cum_usd, ask_cum_usd, imbalance_cum) for L1..L{max_levels}
        """
        bid_depths = self.bids.depth_by_level(max_levels)
        ask_depths = self.asks.depth_by_level(max_levels)

        results = []
        for i in range(max(len(bid_depths), len(ask_depths))):
            bid_cum = bid_depths[i] if i < len(bid_depths) else 0.0
            ask_cum = ask_depths[i] if i < len(ask_depths) else 0.0
            imb = self.imbalance(bid_cum, ask_cum)
            results.append((bid_cum, ask_cum, imb))

        return results


@dataclass
class LiquidityMetrics:
    """Liquidity metrics for a specific trade size."""
    trade_size_usd: float
    side: str  # "buy" or "sell"

    # Execution metrics
    slippage_bps: float  # Slippage in basis points
    vwap: float  # Volume-weighted average price
    levels_consumed: int  # Number of orderbook levels consumed
    executed_usd: float  # Total USD executed (may be less than trade_size if unfilled)
    executed_qty: float  # Quantity executed in base asset
    is_filled: bool  # Whether order can be fully filled


def calculate_liquidity_metrics(
    orderbook: OrderBook,
    trade_size_usd: float,
    side: str,
) -> LiquidityMetrics:
    """Calculate liquidity metrics for a given trade size.

    Parameters:
    -----------
    orderbook : OrderBook
        Current orderbook state
    trade_size_usd : float
        Trade size in USD
    side : str
        "buy" (consume asks) or "sell" (consume bids)

    Returns:
    --------
    LiquidityMetrics
        Calculated metrics for this trade size
    """
    # Select the side we're consuming
    if side == "buy":
        levels = orderbook.asks.levels
        reference_price = orderbook.asks.best_price
    elif side == "sell":
        levels = orderbook.bids.levels
        reference_price = orderbook.bids.best_price
    else:
        raise ValueError(f"Invalid side: {side}. Must be 'buy' or 'sell'")

    if reference_price is None:
        # No liquidity available
        return LiquidityMetrics(
            trade_size_usd=trade_size_usd,
            side=side,
            slippage_bps=0.0,
            vwap=0.0,
            levels_consumed=0,
            executed_usd=0.0,
            executed_qty=0.0,
            is_filled=False,
        )

    # Walk through orderbook levels and accumulate execution
    remaining_usd = trade_size_usd
    executed_qty_total = 0.0
    executed_usd_total = 0.0
    levels_consumed = 0

    for level in levels:
        if remaining_usd <= 0:
            break

        levels_consumed += 1
        level_usd_available = level.notional_usd

        if level_usd_available >= remaining_usd:
            # This level can fill the remaining order
            qty_from_level = remaining_usd / level.price
            executed_qty_total += qty_from_level
            executed_usd_total += remaining_usd
            remaining_usd = 0.0
        else:
            # Consume this entire level and move to next
            executed_qty_total += level.size
            executed_usd_total += level_usd_available
            remaining_usd -= level_usd_available

    # Check if order is fully filled
    is_filled = (remaining_usd <= 0.01)  # Allow small rounding errors

    # Calculate VWAP
    if executed_qty_total > 0:
        vwap = executed_usd_total / executed_qty_total
    else:
        vwap = reference_price

    # Calculate slippage
    # Slippage = (VWAP - reference_price) / reference_price * 10000 (bps)
    if reference_price > 0:
        if side == "buy":
            # Buying at higher price = positive slippage
            slippage_bps = ((vwap - reference_price) / reference_price) * 10000
        else:
            # Selling at lower price = positive slippage (negative impact)
            slippage_bps = ((reference_price - vwap) / reference_price) * 10000
    else:
        slippage_bps = 0.0

    return LiquidityMetrics(
        trade_size_usd=trade_size_usd,
        side=side,
        slippage_bps=slippage_bps,
        vwap=vwap,
        levels_consumed=levels_consumed,
        executed_usd=executed_usd_total,
        executed_qty=executed_qty_total,
        is_filled=is_filled,
    )


def calculate_liquidity_by_trade_sizes(
    orderbook: OrderBook,
    trade_sizes_usd: List[float] = [20, 100, 500, 1000, 5000],
) -> List[Tuple[LiquidityMetrics, LiquidityMetrics]]:
    """Calculate liquidity metrics for multiple trade sizes.

    Parameters:
    -----------
    orderbook : OrderBook
        Current orderbook state
    trade_sizes_usd : List[float]
        List of trade sizes in USD to analyze

    Returns:
    --------
    List[Tuple[LiquidityMetrics, LiquidityMetrics]]
        List of (buy_metrics, sell_metrics) for each trade size
    """
    results = []
    for size in trade_sizes_usd:
        buy_metrics = calculate_liquidity_metrics(orderbook, size, "buy")
        sell_metrics = calculate_liquidity_metrics(orderbook, size, "sell")
        results.append((buy_metrics, sell_metrics))
    return results


@dataclass
class OrderBookMetricsSummary:
    """Complete summary of orderbook metrics."""
    timestamp_ms: float

    # Basic metrics
    mid_price: Optional[float]
    spread_absolute: Optional[float]
    spread_bps: Optional[float]
    best_bid: Optional[float]
    best_ask: Optional[float]

    # Depth metrics
    l1_depth_bid_usd: float
    l1_depth_ask_usd: float
    l5_depth_bid_usd: float
    l5_depth_ask_usd: float

    # Imbalance metrics
    l1_imbalance: float
    l5_imbalance: float

    # Depth by level (L1-L5)
    depth_by_level: List[Tuple[float, float, float]]  # (bid_cum, ask_cum, imbalance)

    # Liquidity by trade size
    liquidity_by_size: List[Tuple[LiquidityMetrics, LiquidityMetrics]]  # (buy, sell)


def calculate_all_metrics(
    orderbook: OrderBook,
    trade_sizes_usd: List[float] = [20, 100, 500, 1000, 5000],
) -> OrderBookMetricsSummary:
    """Calculate all orderbook metrics.

    Parameters:
    -----------
    orderbook : OrderBook
        Current orderbook state
    trade_sizes_usd : List[float]
        List of trade sizes to analyze

    Returns:
    --------
    OrderBookMetricsSummary
        Complete metrics summary
    """
    # Basic metrics
    l1_bid, l1_ask = orderbook.l1_depth_usd()
    l5_bid, l5_ask = orderbook.l5_depth_usd()

    # Depth and imbalance by level
    depth_by_level = orderbook.depth_and_imbalance_by_level(max_levels=5)

    # Liquidity by trade size
    liquidity_by_size = calculate_liquidity_by_trade_sizes(orderbook, trade_sizes_usd)

    return OrderBookMetricsSummary(
        timestamp_ms=orderbook.timestamp_ms,
        mid_price=orderbook.mid_price,
        spread_absolute=orderbook.spread_absolute,
        spread_bps=orderbook.spread_bps,
        best_bid=orderbook.bids.best_price,
        best_ask=orderbook.asks.best_price,
        l1_depth_bid_usd=l1_bid,
        l1_depth_ask_usd=l1_ask,
        l5_depth_bid_usd=l5_bid,
        l5_depth_ask_usd=l5_ask,
        l1_imbalance=orderbook.l1_imbalance(),
        l5_imbalance=orderbook.l5_imbalance(),
        depth_by_level=depth_by_level,
        liquidity_by_size=liquidity_by_size,
    )
