export interface OrderBookLevel {
  price: number;
  size: number;
  total_usd: number;
}

export interface AnalyticsData {
  stats: {
    events: number;
    orderbook_updates: number;
    trade_events: number;
    market_context_updates: number;
  };
  rate: {
    messages_per_minute: number;
    messages_last_10s: number;
    average_per_minute: number;
    total_messages: number;
    uptime_seconds: number;
  };
  orderbook?: {
    mid_price: number;
    spread_bps: number;
    best_bid: number;
    best_ask: number;
    l1_depth_bid: number;
    l1_depth_ask: number;
    l2_depth_bid: number;
    l2_depth_ask: number;
    l3_depth_bid: number;
    l3_depth_ask: number;
    l4_depth_bid: number;
    l4_depth_ask: number;
    l5_depth_bid: number;
    l5_depth_ask: number;
    l1_imbalance: number;
    l5_imbalance: number;
    bids: OrderBookLevel[];
    asks: OrderBookLevel[];
  };
  trade_flow?: {
    trade_count: number;
    total_volume: number;
    buy_volume: number;
    sell_volume: number;
    buy_ratio: number;
    sell_ratio: number;
    sweep_direction: 'up' | 'down' | null;
    largest: number;
    median: number;
    average: number;
  };
  momentum?: {
    short?: {
      direction: string;
      change_percent: number;
      is_usable: boolean;
    };
    long?: {
      direction: string;
      change_percent: number;
      is_usable: boolean;
    };
  };
  depth_decay?: {
    bid_decay_percent: number;
    ask_decay_percent: number;
    bid_status: string;
    ask_status: string;
  };
  liquidations?: {
    status: string;
    long_liquidations: number;
    short_liquidations: number;
    total_long_volume: number;
    total_short_volume: number;
  };
  market_indicators?: {
    oi: number;
    oi_trend: string;
    oi_velocity: number;
    funding_rate: number;
    funding_trend: string;
    basis: number;
    basis_status: string;
  };
  candles?: {
    [interval: string]: {
      return_pct: number;
      volume_vs_avg: number;
      atr: number;
      realized_vol: number;
      close: number;
      high: number;
      low: number;
      volume: number;
    };
  };
  volatility?: {
    atr_1m: number;
    atr_5m: number;
    realized_vol_1m: number;
    realized_vol_5m: number;
    regime: 'low' | 'normal' | 'high';
    percentile: number;
  };
  trade_flow_multi?: {
    [window: string]: {
      trade_count: number;
      total_volume: number;
      buy_volume: number;
      sell_volume: number;
      buy_ratio: number;
      sell_ratio: number;
      sweep_direction: 'up' | 'down' | null;
      largest: number;
      median: number;
      average: number;
    };
  };
  liquidations_multi?: {
    [window: string]: {
      status: string;
      long_liquidations: number;
      short_liquidations: number;
      total_long_volume: number;
      total_short_volume: number;
    };
  };
  oi_multi?: {
    [window: string]: {
      change_percent: number;
      trend: string;
      velocity: number;
    };
  };
  session_context?: {
    daily_high: number;
    daily_low: number;
    current_price: number;
    pct_from_low: number;
    pct_from_high: number;
    pct_through_range: number;
    session_vwap: number;
    distance_from_vwap_bps: number;
    session_volume_usd: number;
    last_1h_volume_usd: number;
    last_4h_volume_usd: number;
    session_duration_hours: number;
    hyperliquid_24h_volume_usd?: number;
    hyperliquid_1h_volume_usd?: number;
    hyperliquid_4h_volume_usd?: number;
  };
  regime?: {
    trend_regime: 'up' | 'down' | 'range';
    trend_strength: number;
    liquidity_regime: 'high' | 'normal' | 'thin';
    market_regime: 'normal' | 'trend' | 'chop' | 'liquidation_event' | 'short_squeeze' | 'crash';
  };
  slippage?: {
    [size: string]: {
      buy: {
        avg_fill_price: number;
        slippage_bps: number;
        round_trip_cost_bps: number;
        is_feasible: boolean;
        liquidity_used_pct: number;
      };
      sell: {
        avg_fill_price: number;
        slippage_bps: number;
        round_trip_cost_bps: number;
        is_feasible: boolean;
        liquidity_used_pct: number;
      };
      spread_bps: number;
      fee_bps: number;
    };
  };
  crowding?: {
    crowded_long: boolean;
    crowded_short: boolean;
    long_crowding_score: number;
    short_crowding_score: number;
    interpretation: string;
  };
  system_status?: {
    data_quality_ok: boolean;
    feed_connected: boolean;
    modules?: {
      orderbook: { ok: boolean; fresh: boolean };
      trades: { ok: boolean; fresh: boolean };
      liquidations: { ok: boolean; fresh: boolean };
      market_indicators: { ok: boolean; fresh: boolean };
      candles: { ok: boolean; fresh: boolean };
      session_context: { ok: boolean; fresh: boolean };
      hyperliquid_volumes: { ok: boolean; fresh: boolean };
    };
    last_check?: number;
    error?: string;
    collector?: {
      ok: boolean;
      fresh: boolean;
      stats: {
        running: boolean;
        total_collected: number;
        last_collection_time: number;
        interval: number;
        errors: number;
        last_error: string | null;
        last_error_time: number | null;
      };
    };
  };
  cross_asset_context?: {
    assets: {
      [symbol: string]: {
        current_price: number;
        return_1m: number;
        return_5m: number;
        return_15m: number;
        return_1h: number;
        volatility_regime: string;
        trend_regime: string;
        volume_24h?: number;
      };
    };
    market_sentiment: string;
  };
}
