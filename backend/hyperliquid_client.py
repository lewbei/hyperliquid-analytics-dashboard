"""Hyperliquid public data client (single-coin, data-only for this phase).

The client defined here is intentionally focused on *public* WebSocket data for
one perpetual futures coin. It separates transport concerns from parsing so
that:

- Parsing and event normalization can be tested purely with synthetic
  dictionaries, without any network or external dependencies.
- Real transports (for example using the official ``hyperliquid-python-sdk``
  or a direct WebSocket client) can be plugged in later without changing the
  downstream interface.

Only a minimal skeleton for real network connectivity is provided. For this
phase, tests interact with the client via :meth:`HyperliquidClient.feed_raw_message`
using synthetic messages that mirror the Hyperliquid WebSocket payloads
(``WsBook``, ``WsBbo``, ``WsTrade``, ``Candle``, ``WsActiveAssetCtx``).
"""

from __future__ import annotations

from collections import deque
from typing import Any, Deque, Iterable, Iterator, List, Mapping, Optional, Protocol

from .config import HyperliquidClientConfig, SubscriptionConfig, MAINNET
from .models import (
    Bbo,
    CandleEvent,
    MarketEvent,
    OrderBookLevel,
    OrderBookSnapshot,
    PerpAssetContext,
    TradeEvent,
)


class HyperliquidTransport(Protocol):
    """Protocol for a transport that yields raw WebSocket-like messages.

    A concrete implementation is expected to:

    - Open a WebSocket connection to the configured network's ``ws_url``.
    - Send subscription messages based on ``config.subscription``.
    - Yield each decoded JSON message as a mapping with at least
      ``{"channel": <str>, "data": <object>}``.

    In this phase we do not provide a production transport implementation, so
    :class:`HyperliquidClient` can be used in a fully in-memory mode by calling
    :meth:`HyperliquidClient.feed_raw_message` directly in tests. A real
    transport can be added later without changing the public parsing interface.
    """

    def connect_and_subscribe(self, config: HyperliquidClientConfig) -> Iterable[Mapping[str, Any]]:  # pragma: no cover - interface only
        """Open the connection and start yielding raw messages.

        Implementations should be careful to handle reconnects, backoff, and
        clean shutdown semantics. This is left to a future phase.
        """

        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - interface only
        """Close any underlying network resources."""

        raise NotImplementedError


class HyperliquidMessageParser:
    """Parse raw Hyperliquid WebSocket messages into normalized events.

    The parser has no side effects and no transport knowledge. It expects
    dictionaries that follow the Hyperliquid WebSocket structure, for example:

    ``{"channel": "l2Book", "data": {"coin": "SOL", ...}}``.

    Parameters
    ----------
    coin:
        Optional coin symbol filter. If provided, events for other coins are
        ignored.
    """

    def __init__(self, *, coin: Optional[str] = None) -> None:
        self._coin = coin

    @property
    def coin(self) -> Optional[str]:
        """The configured coin symbol filter (or ``None`` for no filtering)."""

        return self._coin

    def parse_message(self, message: Mapping[str, Any]) -> List[MarketEvent]:
        """Parse a single raw WebSocket message into zero or more events.

        The returned list can be empty if the message is not recognized or if
        it pertains to a different coin than the parser is configured for.
        """

        channel = message.get("channel")
        data = message.get("data")

        if channel is None or data is None:
            return []

        if channel == "l2Book" and isinstance(data, Mapping):
            book = self._parse_l2_book(data)
            return [book] if book is not None else []

        if channel == "bbo" and isinstance(data, Mapping):
            bbo = self._parse_bbo(data)
            return [bbo] if bbo is not None else []

        if channel == "trades" and isinstance(data, list):
            return self._parse_trades(data)

        if channel == "candle" and isinstance(data, list):
            return self._parse_candles(data)

        if channel == "activeAssetCtx" and isinstance(data, Mapping):
            ctx = self._parse_active_asset_ctx(data)
            return [ctx] if ctx is not None else []

        # Unknown channel or shape
        return []

    # ------------------------------------------------------------------
    # Specific channel parsers
    # ------------------------------------------------------------------

    def _coin_matches(self, coin: Optional[str]) -> bool:
        return self._coin is None or coin == self._coin

    def _parse_l2_book(self, data: Mapping[str, Any]) -> Optional[OrderBookSnapshot]:
        coin = data.get("coin")
        if not self._coin_matches(coin):
            return None

        time_ms = int(data.get("time", 0))
        levels = data.get("levels") or [[], []]
        if not isinstance(levels, list) or len(levels) != 2:
            return None

        bids_raw, asks_raw = levels
        bids = [self._parse_level(level) for level in bids_raw]
        asks = [self._parse_level(level) for level in asks_raw]

        return OrderBookSnapshot(coin=str(coin), time_ms=time_ms, bids=bids, asks=asks)

    def _parse_bbo(self, data: Mapping[str, Any]) -> Optional[Bbo]:
        coin = data.get("coin")
        if not self._coin_matches(coin):
            return None

        time_ms = int(data.get("time", 0))
        bbo_field = data.get("bbo") or [None, None]
        if not isinstance(bbo_field, list) or len(bbo_field) != 2:
            return None

        raw_bid, raw_ask = bbo_field
        best_bid = self._parse_level(raw_bid) if isinstance(raw_bid, Mapping) else None
        best_ask = self._parse_level(raw_ask) if isinstance(raw_ask, Mapping) else None

        return Bbo(coin=str(coin), time_ms=time_ms, best_bid=best_bid, best_ask=best_ask)

    def _parse_trades(self, trades: Iterable[Mapping[str, Any]]) -> List[TradeEvent]:
        events: List[TradeEvent] = []
        for trade in trades:
            coin = trade.get("coin")
            if not self._coin_matches(coin):
                continue

            px = float(trade.get("px", 0.0))
            sz = float(trade.get("sz", 0.0))
            side = str(trade.get("side", ""))
            time_ms = int(trade.get("time", 0))
            tid = int(trade.get("tid", 0))
            hash_value = trade.get("hash")
            users = trade.get("users") or [None, None]
            buyer = users[0] if len(users) > 0 else None
            seller = users[1] if len(users) > 1 else None

            events.append(
                TradeEvent(
                    coin=str(coin),
                    side=side,
                    px=px,
                    sz=sz,
                    time_ms=time_ms,
                    tid=tid,
                    hash=str(hash_value) if hash_value is not None else None,
                    buyer=str(buyer) if buyer is not None else None,
                    seller=str(seller) if seller is not None else None,
                )
            )

        # WsTrade[] is usually delivered in chronological order already; we
        # keep the original order.
        return events

    def _parse_candles(self, candles: Iterable[Mapping[str, Any]]) -> List[CandleEvent]:
        events: List[CandleEvent] = []
        for candle in candles:
            coin = candle.get("s")
            if not self._coin_matches(coin):
                continue

            open_time_ms = int(candle.get("t", 0))
            close_time_ms = int(candle.get("T", 0))
            interval = str(candle.get("i", ""))
            open_px = float(candle.get("o", 0.0))
            close_px = float(candle.get("c", 0.0))
            high_px = float(candle.get("h", 0.0))
            low_px = float(candle.get("l", 0.0))
            volume = float(candle.get("v", 0.0))
            n_trades = int(candle.get("n", 0))

            events.append(
                CandleEvent(
                    coin=str(coin),
                    interval=interval,
                    open_time_ms=open_time_ms,
                    close_time_ms=close_time_ms,
                    open=open_px,
                    high=high_px,
                    low=low_px,
                    close=close_px,
                    volume=volume,
                    n_trades=n_trades,
                )
            )

        return events

    def _parse_active_asset_ctx(self, data: Mapping[str, Any]) -> Optional[PerpAssetContext]:
        coin = data.get("coin")
        if not self._coin_matches(coin):
            return None

        ctx = data.get("ctx")
        if not isinstance(ctx, Mapping):
            return None

        day_ntl_vlm = float(ctx.get("dayNtlVlm", 0.0))
        prev_day_px = float(ctx.get("prevDayPx", 0.0))
        mark_px = float(ctx.get("markPx", 0.0))
        mid_px_value = ctx.get("midPx")
        mid_px = float(mid_px_value) if mid_px_value is not None else None
        funding = float(ctx.get("funding", 0.0))
        open_interest = float(ctx.get("openInterest", 0.0))
        oracle_px = float(ctx.get("oraclePx", 0.0))

        # Optional fields that appear in the Python SDK but are not guaranteed
        # by the WebSocket TypeScript docs.
        premium_value = ctx.get("premium")
        premium = float(premium_value) if premium_value is not None else None
        day_base_vlm_value = ctx.get("dayBaseVlm")
        day_base_volume = float(day_base_vlm_value) if day_base_vlm_value is not None else None

        return PerpAssetContext(
            coin=str(coin),
            day_notional_volume=day_ntl_vlm,
            prev_day_px=prev_day_px,
            mark_px=mark_px,
            mid_px=mid_px,
            funding=funding,
            open_interest=open_interest,
            oracle_px=oracle_px,
            premium=premium,
            day_base_volume=day_base_volume,
        )

    @staticmethod
    def _parse_level(level: Mapping[str, Any]) -> OrderBookLevel:
        return OrderBookLevel(
            px=float(level.get("px", 0.0)),
            sz=float(level.get("sz", 0.0)),
            n=int(level.get("n", 0)),
        )


class HyperliquidClient:
    """Single-coin Hyperliquid public data client.

    The client is designed to be easy to integrate into a feature pipeline. It
    exposes a minimal public surface for this phase:

    - :meth:`connect_and_subscribe` (skeleton, requires a real transport).
    - :meth:`feed_raw_message` for tests and offline replay.
    - :meth:`iter_events` to iterate over normalized events buffered so far.
    - :meth:`close` for clean shutdown.

    Network concerns are delegated to a ``HyperliquidTransport`` implementation
    supplied at construction time. In this phase we do not provide a real
    transport; instead, tests rely on :meth:`feed_raw_message`.
    """

    def __init__(
        self,
        *,
        coin: str,
        config: Optional[HyperliquidClientConfig] = None,
        parser: Optional[HyperliquidMessageParser] = None,
        transport: Optional[HyperliquidTransport] = None,
    ) -> None:
        self._coin = coin

        if config is None:
            config = HyperliquidClientConfig.for_coin(coin, network=MAINNET)
        elif config.subscription is None:
            # Ensure there is always a subscription block for this coin.
            config = HyperliquidClientConfig(
                network=config.network,
                subscription=SubscriptionConfig(coin=coin),
            )

        self._config = config
        self._parser = parser or HyperliquidMessageParser(coin=coin)
        self._transport = transport

        self._buffer: Deque[MarketEvent] = deque()
        self._closed: bool = False

    @property
    def coin(self) -> str:
        """Return the perp coin symbol this client is responsible for."""

        return self._coin

    @property
    def config(self) -> HyperliquidClientConfig:
        """Return the client configuration."""

        return self._config

    def feed_raw_message(self, message: Mapping[str, Any]) -> None:
        """Feed a raw WebSocket-style message into the client.

        This is the primary entrypoint used in tests. It runs the message
        through :class:`HyperliquidMessageParser` and appends any resulting
        events to an internal buffer that :meth:`iter_events` will consume.
        """

        if self._closed:
            return

        events = self._parser.parse_message(message)
        self._buffer.extend(events)

    def iter_events(self) -> Iterator[MarketEvent]:
        """Iterate over all buffered events in FIFO order.

        The iterator is finite: it yields each buffered event once and then
        stops. New events added after iteration begins will not be seen by the
        same iterator; callers can create a new iterator to consume later
        events.
        """

        while self._buffer:
            yield self._buffer.popleft()

    def connect_and_subscribe(self) -> None:
        """Connect to Hyperliquid and start consuming public data streams.

        In this phase, this method provides only a skeleton implementation. To
        use it in production you would implement a concrete ``HyperliquidTransport``
        that opens a WebSocket connection (for example with ``websockets`` or
        the official ``hyperliquid-python-sdk``), subscribes to streams based
        on :attr:`config.subscription`, and yields incoming JSON messages.

        For example, a WebSocket transport might look like:

        - Open ``config.network.ws_url``.
        - For each subscription in
          ``config.subscription.build_public_subscriptions()``, send
          ``{"method": "subscribe", "subscription": sub}``.
        - In a loop, read messages, decode JSON, and yield dictionaries with
          ``"channel"`` and ``"data"``.

        Since this project should not depend on external packages in tests, any
        such implementation should live in a separate module and be injected
        into this client via the ``transport`` parameter.
        """

        if self._transport is None:
            raise RuntimeError(
                "No transport configured for HyperliquidClient. "
                "Provide a HyperliquidTransport implementation when you "
                "are ready to connect to the live WebSocket API."
            )

        for message in self._transport.connect_and_subscribe(self._config):
            if self._closed:
                break
            self.feed_raw_message(message)

    def close(self) -> None:
        """Mark the client as closed and close any underlying transport.

        Closing is idempotent; it is safe to call multiple times.
        """

        if self._closed:
            return

        self._closed = True

        transport = self._transport
        if transport is not None:
            try:
                transport.close()
            except Exception:
                # Transport cleanup failures should not crash the client; they
                # can be logged by a higher-level component if needed.
                pass

    def __iter__(self) -> Iterator[MarketEvent]:
        """Allow ``for event in client`` iteration over buffered events."""

        return self.iter_events()
