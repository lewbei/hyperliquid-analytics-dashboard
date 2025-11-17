"""Data models for normalized Hyperliquid public market data.

All models are simple dataclasses and are independent of any particular
transport or client implementation. They provide a stable interface for the
rest of the backend to consume normalized events from Hyperliquid.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union


@dataclass(frozen=True)
class OrderBookLevel:
    """One level in the L2 order book.

    Attributes
    ----------
    px:
        Price at this level.
    sz:
        Size (base asset units) resting at this level.
    n:
        Number of individual orders contributing to this level.
    """

    px: float
    sz: float
    n: int


@dataclass(frozen=True)
class OrderBookSnapshot:
    """Full L2 snapshot for a single coin.

    This corresponds to the ``WsBook`` structure in the WebSocket docs.
    """

    coin: str
    time_ms: int
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]


@dataclass(frozen=True)
class Bbo:
    """Best bid/offer snapshot for a single coin.

    Derived from the ``WsBbo`` WebSocket payload. Mid and spread are exposed
    as computed properties for convenience.
    """

    coin: str
    time_ms: int
    best_bid: Optional[OrderBookLevel]
    best_ask: Optional[OrderBookLevel]

    @property
    def mid(self) -> Optional[float]:
        """Return the mid price or ``None`` if either side is missing."""

        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid.px + self.best_ask.px) / 2.0

    @property
    def spread(self) -> Optional[float]:
        """Return the best-ask minus best-bid spread, or ``None`` if unavailable."""

        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask.px - self.best_bid.px


@dataclass(frozen=True)
class TradeEvent:
    """Public trade event from the ``trades`` stream (``WsTrade``)."""

    coin: str
    side: str
    px: float
    sz: float
    time_ms: int
    tid: int
    hash: Optional[str] = None
    buyer: Optional[str] = None
    seller: Optional[str] = None


@dataclass(frozen=True)
class CandleEvent:
    """Bar/candle event from the ``candle`` stream.

    This corresponds to the ``Candle`` type in the WebSocket docs, with
    numeric OHLCV fields.
    """

    coin: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    n_trades: int


@dataclass(frozen=True)
class PerpAssetContext:
    """Per-asset context snapshot from ``activeAssetCtx`` (perps only).

    Only the fields guaranteed by the WebSocket TypeScript type are required.
    Additional optional fields that appear in the Python SDK (for example
    premium, dayBaseVlm) are modeled as optional and default to ``None``.
    """

    coin: str
    day_notional_volume: float
    prev_day_px: float
    mark_px: float
    mid_px: Optional[float]
    funding: float
    open_interest: float
    oracle_px: float
    premium: Optional[float] = None
    day_base_volume: Optional[float] = None


MarketEvent = Union[OrderBookSnapshot, Bbo, TradeEvent, CandleEvent, PerpAssetContext]
"""Union of all normalized public market data event types."""
