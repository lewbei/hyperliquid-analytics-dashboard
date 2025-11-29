import asyncio
import logging
import time
import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from backend.database import DatabaseManager
from backend.feature_extractor import FeatureExtractor

logger = logging.getLogger(__name__)

class DataCollector:
    def __init__(self, analytics_engine, database_manager: DatabaseManager):
        self.analytics_engine = analytics_engine
        self.db = database_manager
        self.feature_extractor = FeatureExtractor()
        self.is_running = False
        self.collection_task = None
        self.interval = float(os.getenv("COLLECTION_INTERVAL_SECONDS", "1.0"))
        
        # Stats
        self.total_collected = 0
        self.last_collection_time = 0
        self.errors = 0
        self.last_error = None
        self.last_error_time = None

    async def start(self):
        if self.is_running:
            return
        
        self.is_running = True
        self.collection_task = asyncio.create_task(self._collection_loop())
        logger.info(f"Data collector started (interval={self.interval}s)")

    async def stop(self):
        self.is_running = False
        if self.collection_task:
            self.collection_task.cancel()
            try:
                await self.collection_task
            except asyncio.CancelledError:
                pass
        logger.info("Data collector stopped")

    async def _collection_loop(self):
        while self.is_running:
            try:
                start_time = time.time()
                
                await self._collect_snapshot()
                
                # Calculate sleep time to maintain precise interval
                elapsed = time.time() - start_time
                sleep_time = max(0.0, self.interval - elapsed)
                
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.errors += 1
                self.last_error = str(e)
                self.last_error_time = time.time()
                logger.error(f"Error in collection loop: {e}")
                await asyncio.sleep(1.0) # Backoff on error

    async def _collect_snapshot(self):
        # Get data from analytics engine
        data = self.analytics_engine.get_analytics_data()
        
        # Skip if critical data is missing
        if "orderbook" not in data or "mid_price" not in data["orderbook"]:
            return

        # Extract features
        features = self.feature_extractor.extract_features(data)
        
        # Prepare snapshot
        timestamp = datetime.now(timezone.utc)
        coin = os.getenv("HYPERLIQUID_COIN", "SOL") # Default to SOL if not set, but should be consistent
        
        snapshot = {
            "timestamp": timestamp,
            "coin": coin,
            "price": data["orderbook"].get("mid_price"),
            "volume_24h": data.get("session_context", {}).get("hyperliquid_24h_volume_usd"),
            "bids": data["orderbook"].get("bids", [])[:10], # Top 10 levels
            "asks": data["orderbook"].get("asks", [])[:10], # Top 10 levels
            "spread_bps": data["orderbook"].get("spread_bps"),
            "depth_l5_bid": data["orderbook"].get("l5_depth_bid"),
            "depth_l5_ask": data["orderbook"].get("l5_depth_ask"),
            "imbalance_l5": data["orderbook"].get("l5_imbalance"),
            "trade_flow_1m": {
                "buy_volume": data.get("trade_flow", {}).get("buy_volume"),
                "sell_volume": data.get("trade_flow", {}).get("sell_volume"),
                "net_flow": data.get("trade_flow", {}).get("buy_volume", 0) - data.get("trade_flow", {}).get("sell_volume", 0)
            },
            "funding_rate": data.get("market_indicators", {}).get("funding_rate"),
            "open_interest": data.get("market_indicators", {}).get("oi"),
            "model_features": features
        }

        # Insert into database
        await self.db.insert_snapshot(snapshot)
        
        self.total_collected += 1
        self.last_collection_time = time.time()

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self.is_running,
            "total_collected": self.total_collected,
            "last_collection_time": self.last_collection_time,
            "interval": self.interval,
            "errors": self.errors,
            "last_error": self.last_error,
            "last_error_time": self.last_error_time
        }
