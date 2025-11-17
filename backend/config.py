"""Configuration objects for the backend Hyperliquid data client.

This module intentionally stays lightweight and does not perform any network
I/O. It just defines configuration structures describing which network to
connect to and which public feeds to subscribe to for a single perp coin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class NetworkConfig:
    """Configuration for a Hyperliquid network.

    Attributes
    ----------
    name:
        Human-readable name ("mainnet" or "testnet").
    rest_url:
        Base HTTPS URL for the REST API.
    ws_url:
        WebSocket URL for streaming data.
    """

    name: str
    rest_url: str
    ws_url: str


MAINNET = NetworkConfig(
    name="mainnet",
    rest_url="https://api.hyperliquid.xyz",
    ws_url="wss://api.hyperliquid.xyz/ws",
)

TESTNET = NetworkConfig(
    name="testnet",
    rest_url="https://api.hyperliquid-testnet.xyz",
    ws_url="wss://api.hyperliquid-testnet.xyz/ws",
)


@dataclass
class SubscriptionConfig:
    """Configuration for public market-data subscriptions for a single coin.

    This mirrors the WebSocket subscription objects documented in the
    Hyperliquid GitBook. Only public, non-authenticated feeds are included
    here; user/account streams will be added in a later phase.
    """

    coin: str
    subscribe_l2_book: bool = True
    subscribe_bbo: bool = True
    subscribe_trades: bool = True
    subscribe_candles: bool = True
    candle_interval: str = "1m"
    subscribe_active_asset_ctx: bool = True

    def build_public_subscriptions(self) -> List[Dict[str, object]]:
        """Return a list of subscription dictionaries for the configured coin.

        Each element is suitable for use as the ``subscription`` field in a
        WebSocket ``{"method": "subscribe", "subscription": ...}`` message.
        """

        subs: List[Dict[str, object]] = []
        c = self.coin

        if self.subscribe_l2_book:
            subs.append({"type": "l2Book", "coin": c})
        if self.subscribe_bbo:
            subs.append({"type": "bbo", "coin": c})
        if self.subscribe_trades:
            subs.append({"type": "trades", "coin": c})
        if self.subscribe_candles:
            subs.append({"type": "candle", "coin": c, "interval": self.candle_interval})
        if self.subscribe_active_asset_ctx:
            subs.append({"type": "activeAssetCtx", "coin": c})

        return subs


@dataclass
class HyperliquidClientConfig:
    """Configuration for :class:`backend.hyperliquid_client.HyperliquidClient`.

    In this phase the configuration only covers public data for a single perp
    coin. Authenticated endpoints and user-specific WebSocket streams can be
    added later by extending this dataclass (for example with keys, account
    addresses, and user stream toggles).
    """

    network: NetworkConfig = MAINNET
    subscription: SubscriptionConfig | None = None

    @classmethod
    def for_coin(
        cls,
        coin: str,
        *,
        network: NetworkConfig = MAINNET,
        **subscription_overrides: object,
    ) -> "HyperliquidClientConfig":
        """Construct a config for a single coin with sensible defaults.

        Parameters
        ----------
        coin:
            Perp symbol, for example "SOL".
        network:
            Network configuration (mainnet or testnet). Defaults to
            :data:`MAINNET`.
        subscription_overrides:
            Optional keyword arguments forwarded to :class:`SubscriptionConfig`
            to tweak which streams are enabled.
        """

        subscription = SubscriptionConfig(coin=coin, **subscription_overrides)
        return cls(network=network, subscription=subscription)
