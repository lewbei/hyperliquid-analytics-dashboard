import os
import logging
import json
import asyncio
import asyncpg
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.pool = None
        self.url = os.getenv("DATACOLLECTION_URL")
        if not self.url:
            logger.warning("DATACOLLECTION_URL not set. Database features will be disabled.")

    async def connect(self):
        if not self.url:
            return
        try:
            self.pool = await asyncpg.create_pool(self.url, min_size=1, max_size=10)
            logger.info("Connected to database")
            await self.init_schema()
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            logger.info("Disconnected from database")

    async def init_schema(self):
        if not self.pool:
            return
        
        schema_sql = """
        CREATE TABLE IF NOT EXISTS market_snapshots (
            timestamp TIMESTAMPTZ NOT NULL,
            coin VARCHAR(20) NOT NULL,
            price DECIMAL,
            volume_24h DECIMAL,
            bids JSONB,
            asks JSONB,
            spread_bps DECIMAL,
            depth_l5_bid DECIMAL,
            depth_l5_ask DECIMAL,
            imbalance_l5 DECIMAL,
            trade_flow_1m JSONB,
            funding_rate DECIMAL,
            open_interest DECIMAL,
            model_features JSONB,
            PRIMARY KEY (timestamp, coin)
        );
        
        -- Try to create hypertable, ignore if extension not available or already exists
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
                PERFORM create_hypertable('market_snapshots', 'timestamp', if_not_exists => TRUE);
            END IF;
        EXCEPTION WHEN OTHERS THEN
            NULL; -- Ignore errors if TimescaleDB is not available
        END $$;

        CREATE INDEX IF NOT EXISTS idx_market_snapshots_coin_time ON market_snapshots (coin, timestamp DESC);
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(schema_sql)
            logger.info("Database schema initialized")

    async def insert_snapshot(self, snapshot: dict):
        if not self.pool:
            return

        query = """
        INSERT INTO market_snapshots (
            timestamp, coin, price, volume_24h, bids, asks, 
            spread_bps, depth_l5_bid, depth_l5_ask, imbalance_l5, 
            trade_flow_1m, funding_rate, open_interest, model_features
        ) VALUES (
            $1, $2, $3, $4, $5, $6, 
            $7, $8, $9, $10, 
            $11, $12, $13, $14
        )
        """
        
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    query,
                    snapshot['timestamp'],
                    snapshot['coin'],
                    snapshot.get('price'),
                    snapshot.get('volume_24h'),
                    json.dumps(snapshot.get('bids', [])),
                    json.dumps(snapshot.get('asks', [])),
                    snapshot.get('spread_bps'),
                    snapshot.get('depth_l5_bid'),
                    snapshot.get('depth_l5_ask'),
                    snapshot.get('imbalance_l5'),
                    json.dumps(snapshot.get('trade_flow_1m', {})),
                    snapshot.get('funding_rate'),
                    snapshot.get('open_interest'),
                    json.dumps(snapshot.get('model_features', {}))
                )
        except Exception as e:
            logger.error(f"Failed to insert snapshot: {e}")

    async def batch_insert_snapshots(self, snapshots: list):
        if not self.pool or not snapshots:
            return

        query = """
        INSERT INTO market_snapshots (
            timestamp, coin, price, volume_24h, bids, asks, 
            spread_bps, depth_l5_bid, depth_l5_ask, imbalance_l5, 
            trade_flow_1m, funding_rate, open_interest, model_features
        ) VALUES (
            $1, $2, $3, $4, $5, $6, 
            $7, $8, $9, $10, 
            $11, $12, $13, $14
        )
        """
        
        data = []
        for s in snapshots:
            data.append((
                s['timestamp'],
                s['coin'],
                s.get('price'),
                s.get('volume_24h'),
                json.dumps(s.get('bids', [])),
                json.dumps(s.get('asks', [])),
                s.get('spread_bps'),
                s.get('depth_l5_bid'),
                s.get('depth_l5_ask'),
                s.get('imbalance_l5'),
                json.dumps(s.get('trade_flow_1m', {})),
                s.get('funding_rate'),
                s.get('open_interest'),
                json.dumps(s.get('model_features', {}))
            ))

        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(query, data)
        except Exception as e:
            logger.error(f"Failed to batch insert snapshots: {e}")
