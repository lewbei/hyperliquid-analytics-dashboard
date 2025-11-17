"""Hyperliquid WebSocket transport using the official Python SDK.

This module provides a concrete implementation of the
:class:`backend.hyperliquid_client.HyperliquidTransport` protocol using the
``hyperliquid-python-sdk`` package.

The design keeps the SDK as an *optional* dependency:

- The SDK is only imported lazily when a real ``Info`` instance is needed.
- Tests can inject a fake ``info_factory`` that returns a stub Info-like
  object, so they do not require the SDK or a real network connection.

The transport is single-purpose for this phase: it streams **public**
Hyperliquid market data for a single perp coin using the subscriptions
configured in :class:`backend.config.SubscriptionConfig`.
"""

from __future__ import annotations

from queue import Queue
from threading import Event
from typing import Any, Callable, Iterable, Mapping, Optional

from .config import HyperliquidClientConfig
from .hyperliquid_client import HyperliquidTransport


InfoFactory = Callable[[str], Any]


def _default_info_factory(base_url: str) -> Any:
    """Create a real ``Info`` instance from the hyperliquid SDK.

    The import is performed lazily so that importing this module does not
    require ``hyperliquid-python-sdk`` to be installed. If the package is not
    available, a clear ``ImportError`` is raised when this function is called.
    """

    try:
        from hyperliquid.info import Info  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover - exercised only when SDK missing at runtime
        message = (
            "hyperliquid-python-sdk is required to use HyperliquidSdkTransport. "
            "Install it in your environment before running the live streamer."
        )
        raise ImportError(message) from exc

    return Info(base_url=base_url)


class HyperliquidSdkTransport(HyperliquidTransport):
    """Concrete transport implementation backed by hyperliquid-python-sdk.

    Parameters
    ----------
    info_factory:
        Optional factory used to create an ``Info``-like object given a
        ``base_url``. Tests can supply a fake implementation to avoid importing
        the real SDK. When omitted, a factory that constructs
        ``hyperliquid.info.Info`` is used.
    """

    def __init__(self, info_factory: Optional[InfoFactory] = None) -> None:
        self._info_factory: InfoFactory = info_factory or _default_info_factory
        self._info: Any = None
        self._queue: Queue[Mapping[str, Any]] = Queue()
        self._closed = False
        self._stop_event = Event()
        self._sentinel: Mapping[str, Any] = {"_sentinel": True}

    def connect_and_subscribe(self, config: HyperliquidClientConfig) -> Iterable[Mapping[str, Any]]:
        """Open the WebSocket connection and yield raw messages.

        This method blocks, yielding messages one by one as they are received
        from the underlying WebSocket. Callers should iterate over the
        resulting iterable until it is exhausted or :meth:`close` is called.
        """

        if self._closed:
            return []

        base_url = config.network.rest_url
        info = self._info_factory(base_url)
        self._info = info

        subscription = config.subscription
        if subscription is not None:
            subs = subscription.build_public_subscriptions()
        else:
            subs = []

        def make_callback() -> Callable[[Mapping[str, Any]], None]:
            def callback(message: Mapping[str, Any]) -> None:
                if self._closed or self._stop_event.is_set():
                    return
                normalized = self._normalize_ws_message(message)
                if normalized is not None:
                    self._queue.put(normalized)

            return callback

        # Register a callback per subscription. The hyperliquid SDK will route
        # incoming messages to the appropriate callback on its internal
        # WebSocket thread.
        for sub in subs:
            info.subscribe(sub, make_callback())

        # Now yield messages from the queue until closed.
        try:
            while not self._closed and not self._stop_event.is_set():
                message = self._queue.get()
                if message is self._sentinel:
                    break
                yield message
        finally:
            # Ensure underlying resources are cleaned up if the consumer stops
            # iterating without calling close() explicitly.
            self.close()

    def close(self) -> None:
        """Signal shutdown and close the underlying Info/WebSocket.

        This method is idempotent and safe to call multiple times.
        """

        if self._closed:
            return

        self._closed = True
        self._stop_event.set()

        # Unblock any waiting consumer.
        try:
            self._queue.put(self._sentinel)
        except Exception:
            # Queue put failures should not crash shutdown.
            pass

        info = self._info
        if info is not None:
            try:
                disconnect = getattr(info, "disconnect_websocket", None)
                if callable(disconnect):
                    disconnect()
                else:
                    ws_manager = getattr(info, "ws_manager", None)
                    stop = getattr(ws_manager, "stop", None)
                    if callable(stop):
                        stop()
            except Exception:
                # Transport cleanup failures should be handled by higher layers
                # if needed; they are not critical for this phase.
                pass

    @staticmethod
    def _normalize_ws_message(message: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        """Normalize a raw WebSocket message from the SDK.

        The SDK delivers messages with ``"channel"`` and ``"data"`` fields.
        For the ``"candle"`` channel, some backends may send a single candle
        object instead of a list; the parser expects a list, so wrap a single
        object into a one-element list.
        """

        channel = message.get("channel")
        data = message.get("data")

        if channel == "candle" and isinstance(data, Mapping):
            return {"channel": "candle", "data": [data]}

        return message
