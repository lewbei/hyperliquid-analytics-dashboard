"""Backend package for Hyperliquid perp scalper.

This package currently exposes public market data models and a Hyperliquid
WebSocket client focused on a single perpetual futures coin.
"""

from . import config, models, hyperliquid_client  # noqa: F401
