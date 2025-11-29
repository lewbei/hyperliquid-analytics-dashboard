import { useState } from 'react';
import { useWebSocket } from './useWebSocket';


const getWsUrl = () => {
  if (import.meta.env.VITE_WS_URL) {
    return import.meta.env.VITE_WS_URL;
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  return `${protocol}//${host}/ws/analytics`;
};

const WS_BASE_URL = getWsUrl();


// All active perpetual symbols from Hyperliquid (non-delisted)
// Top 3 major assets, then rest alphabetically
const PERPETUAL_SYMBOLS = [
  "BTC", "ETH", "SOL",
  "0G", "2Z", "AAVE", "ACE", "ADA", "AERO", "AIXBT", "ALGO", "ALT", "ANIME", "APE",
  "APEX", "APT", "AR", "ARB", "ARK", "ASTER", "ATOM", "AVAX", "AVNT", "BABY", "BANANA",
  "BCH", "BERA", "BIGTIME", "BIO", "BLAST", "BLUR", "BNB", "BOME", "BRETT", "BSV", "CAKE",
  "CC", "CELO", "CFX", "CHILLGUY", "COMP", "CRV", "DOGE", "DOOD", "DOT", "DYM", "DYDX",
  "EIGEN", "ENA", "ENS", "ETC", "ETHFI", "FARTCOIN", "FET", "FIL", "FTT", "FXS", "GALA",
  "GAS", "GMT", "GMX", "GOAT", "GRASS", "GRIFFAIN", "HBAR", "HEMI", "HMSTR", "HYPER", "HYPE",
  "ICP", "IMX", "INIT", "INJ", "IO", "IOTA", "IP", "JTO", "JUP", "KAITO", "KAS", "kBONK",
  "kFLOKI", "kLUNC", "kNEIRO", "kPEPE", "kSHIB", "LAYER", "LDO", "LINEA", "LINK", "LTC",
  "MANTA", "MAV", "ME", "MEGA", "MELANIA", "MEME", "MERL", "MET", "MEW", "MINA", "MNT",
  "MON", "MOODENG", "MORPHO", "MOVE", "NEAR", "NEO", "NIL", "NOT", "NXPC", "OM", "ONDO",
  "OP", "ORDI", "PAXG", "PENDLE", "PENGU", "PEOPLE", "PNUT", "POL", "POLYX", "POPCAT",
  "PROMPT", "PROVE", "PURR", "PUMP", "PYTH", "RENDER", "RESOLV", "REZ", "RSR", "RUNE",
  "S", "SAGA", "SAND", "SCR", "SEI", "SKY", "SNX", "SOPH", "SPX", "STBL", "STRK", "STX",
  "SUI", "SUPER", "SUSHI", "SYRUP", "TAO", "TIA", "TNSR", "TON", "TRB", "TRUMP", "TRX",
  "TST", "TURBO", "UMA", "UNI", "USUAL", "USTC", "VINE", "VIRTUAL", "VVV", "W", "WCT",
  "WLFI", "WIF", "WLD", "XAI", "XLM", "XPL", "XRP", "YGG", "YZY", "ZEC", "ZEN", "ZEREBRO",
  "ZETA", "ZK", "ZORA", "ZRO",
];

function Dashboard() {
  const [selectedCoin, setSelectedCoin] = useState<string>('SOL');
  const wsUrl = `${WS_BASE_URL}?coin=${selectedCoin}`;
  const { data, isConnected } = useWebSocket(wsUrl);

  const formatNumber = (num: number | undefined, decimals: number = 2): string => {
    if (num === undefined || num === null) return 'N/A';
    return num.toFixed(decimals);
  };

  const formatPercent = (num: number | undefined, decimals: number = 3): string => {
    if (num === undefined || num === null) return 'N/A';
    return `${num >= 0 ? '+' : ''}${num.toFixed(decimals)}%`;
  };

  const formatUSD = (num: number | undefined): string => {
    if (num === undefined || num === null) return '$N/A';
    return `$${num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const getValueClass = (value: number | undefined, inverted: boolean = false): string => {
    if (value === undefined || value === null) return '';
    const isPositive = value > 0;
    if (inverted) {
      return isPositive ? 'negative' : 'positive';
    }
    return isPositive ? 'positive' : 'negative';
  };

  const getStatusClass = (status: string): string => {
    const lower = status.toLowerCase();
    if (lower.includes('ok') || lower.includes('good') || lower.includes('normal')) return 'status-ok';
    if (lower.includes('medium') || lower.includes('warning')) return 'status-warning';
    if (lower.includes('high') || lower.includes('critical')) return 'status-critical';
    return '';
  };

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>Hyperliquid Analytics Dashboard</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label htmlFor="coin-selector" style={{ fontSize: '0.9em', opacity: 0.8 }}>Asset:</label>
            <select
              id="coin-selector"
              value={selectedCoin}
              onChange={(e) => setSelectedCoin(e.target.value)}
              style={{
                padding: '6px 12px',
                fontSize: '0.9em',
                borderRadius: '4px',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                background: 'rgba(255, 255, 255, 0.05)',
                color: 'white',
                cursor: 'pointer',
              }}
            >
              {PERPETUAL_SYMBOLS.map((symbol) => (
                <option key={symbol} value={symbol} style={{ color: 'black' }}>{symbol}</option>
              ))}
            </select>
          </div>
          <div className={`status-indicator ${isConnected ? 'connected' : 'disconnected'}`}>
            {isConnected ? '🟢 Connected' : '🔴 Disconnected'}
          </div>
        </div>
      </header>

      {!data ? (
        <div className="loading">Loading analytics data...</div>
      ) : (
        <div className="analytics-grid">
          {/* Stats Card */}
          <div className="card">
            <h2>Event Statistics</h2>
            <div className="stat-row">
              <span>Total Events:</span>
              <span className="value">{data.stats.events}</span>
            </div>
            <div className="stat-row">
              <span>Orderbook Updates:</span>
              <span className="value">{data.stats.orderbook_updates}</span>
            </div>
            <div className="stat-row">
              <span>Trade Events:</span>
              <span className="value">{data.stats.trade_events}</span>
            </div>
            <div className="stat-row">
              <span>Market Updates:</span>
              <span className="value">{data.stats.market_context_updates}</span>
            </div>
          </div>

          {/* API Rate Card */}
          {data.rate && (
            <div className="card">
              <h2>API Rate (Hyperliquid)</h2>
              <div className="stat-row">
                <span>Messages/Min:</span>
                <span className="value highlight">{Math.round(data.rate.messages_per_minute)}</span>
              </div>
              <div className="stat-row">
                <span>Last 10s:</span>
                <span className="value">{data.rate.messages_last_10s}</span>
              </div>
              <div className="stat-row">
                <span>Average/Min:</span>
                <span className="value">{formatNumber(data.rate.average_per_minute, 1)}</span>
              </div>
              <div className="stat-row">
                <span>Total Messages:</span>
                <span className="value">{data.rate.total_messages}</span>
              </div>
              <div className="stat-row">
                <span>Uptime:</span>
                <span className="value">{Math.round(data.rate.uptime_seconds)}s</span>
              </div>
            </div>
          )}

          {/* System Status Card */}
          {data.system_status && (
            <div className="card">
              <h2>System Status</h2>
              <div className="stat-row">
                <span>Data Quality:</span>
                <span className={`value highlight ${data.system_status.data_quality_ok ? 'positive' : 'negative'}`}>
                  {data.system_status.data_quality_ok ? '✓ OK' : '✗ DEGRADED'}
                </span>
              </div>
              <div className="stat-row">
                <span>Feed Connected:</span>
                <span className={`value highlight ${data.system_status.feed_connected ? 'positive' : 'negative'}`}>
                  {data.system_status.feed_connected ? '✓ CONNECTED' : '✗ DISCONNECTED'}
                </span>
              </div>
              {data.system_status.modules && (
                <>
                  <h3 style={{ marginTop: '12px', marginBottom: '6px', fontSize: '0.9em' }}>Modules</h3>
                  {Object.entries(data.system_status.modules).map(([moduleName, status]) => (
                    <div key={moduleName} className="stat-row" style={{ fontSize: '0.85em' }}>
                      <span style={{ textTransform: 'capitalize' }}>{moduleName.replace(/_/g, ' ')}:</span>
                      <span className={`value ${status.ok && status.fresh ? 'positive' : status.ok ? '' : 'negative'}`}>
                        {status.ok && status.fresh ? '✓' : status.ok ? '⚠' : '✗'}
                      </span>
                    </div>
                  ))}
                </>
              )}
              {data.system_status.collector && (
                <>
                  <h3 style={{ marginTop: '12px', marginBottom: '6px', fontSize: '0.9em' }}>Data Collector</h3>
                  <div className="stat-row">
                    <span>Status:</span>
                    <span className={`value highlight ${data.system_status.collector.running ? 'positive' : 'negative'}`}>
                      {data.system_status.collector.running ? '▶ RUNNING' : '⏹ STOPPED'}
                    </span>
                  </div>
                  <div className="stat-row">
                    <span>Collected:</span>
                    <span className="value">{data.system_status.collector.total_collected}</span>
                  </div>
                  {data.system_status.collector.errors > 0 && (
                    <div className="stat-row">
                      <span>Errors:</span>
                      <span className="value negative">{data.system_status.collector.errors}</span>
                    </div>
                  )}
                </>
              )}
              {data.system_status.error && (
                <div style={{ marginTop: '8px', padding: '8px', background: 'rgba(255,0,0,0.1)', borderRadius: '4px', fontSize: '0.85em' }}>
                  Error: {data.system_status.error}
                </div>
              )}
            </div>
          )}

          {/* Cross-Asset Context Card (BTC/ETH) */}
          {data.cross_asset_context && data.cross_asset_context.assets && (
            <div className="card">
              <h2>Market Context</h2>
              <div className="stat-row">
                <span>Market Sentiment:</span>
                <span className={`value highlight ${data.cross_asset_context.market_sentiment === 'bullish' ? 'positive' :
                  data.cross_asset_context.market_sentiment === 'bearish' ? 'negative' : ''
                  }`}>
                  {data.cross_asset_context.market_sentiment.toUpperCase()}
                </span>
              </div>
              {Object.entries(data.cross_asset_context.assets)
                .filter(([symbol]) => symbol !== selectedCoin) // Exclude the currently selected coin
                .map(([symbol, assetData]) => (
                  <div key={symbol} style={{ marginTop: '12px' }}>
                    <h3 style={{ fontSize: '0.95em', marginBottom: '6px', opacity: 0.9 }}>{symbol}</h3>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px', fontSize: '0.85em' }}>
                      <div>Price: <span className="value">{formatUSD(assetData.current_price)}</span></div>
                      {assetData.volume_24h && (
                        <div>24h Vol: <span className="value">{formatUSD(assetData.volume_24h)}</span></div>
                      )}
                      <div>1m Return: <span className={getValueClass(assetData.return_1m)}>{formatPercent(assetData.return_1m, 3)}</span></div>
                      <div>5m Return: <span className={getValueClass(assetData.return_5m)}>{formatPercent(assetData.return_5m, 3)}</span></div>
                      <div>15m Return: <span className={getValueClass(assetData.return_15m)}>{formatPercent(assetData.return_15m, 3)}</span></div>
                      <div>1h Return: <span className={getValueClass(assetData.return_1h)}>{formatPercent(assetData.return_1h, 3)}</span></div>
                      <div>Vol Regime: <span className={`value ${assetData.volatility_regime === 'low' ? '' :
                        assetData.volatility_regime === 'high' ? 'negative' : ''
                        }`}>{assetData.volatility_regime.toUpperCase()}</span></div>
                      <div>Trend: <span className={`value ${assetData.trend_regime === 'up' ? 'positive' :
                        assetData.trend_regime === 'down' ? 'negative' : ''
                        }`}>{assetData.trend_regime.toUpperCase()}</span></div>
                    </div>
                  </div>
                ))}
            </div>
          )}

          {/* Session/Daily Context Card */}
          {data.session_context && (
            <div className="card">
              <h2>Session/Daily Context</h2>
              <div className="stat-row">
                <span>Current Price:</span>
                <span className="value highlight">{formatUSD(data.session_context.current_price)}</span>
              </div>
              <div className="stat-row">
                <span>Daily High:</span>
                <span className="value positive">{formatUSD(data.session_context.daily_high)}</span>
              </div>
              <div className="stat-row">
                <span>Daily Low:</span>
                <span className="value negative">{formatUSD(data.session_context.daily_low)}</span>
              </div>
              <div className="stat-row">
                <span>Through Range:</span>
                <span className="value">{formatNumber(data.session_context.pct_through_range, 3)}%</span>
              </div>
              <div className="stat-row">
                <span>From Low:</span>
                <span className={`value ${getValueClass(data.session_context.pct_from_low)}`}>
                  {formatPercent(data.session_context.pct_from_low, 3)}
                </span>
              </div>
              <div className="stat-row">
                <span>From High:</span>
                <span className={`value ${getValueClass(-data.session_context.pct_from_high)}`}>
                  {formatPercent(data.session_context.pct_from_high, 3)}
                </span>
              </div>
              <h3>VWAP</h3>
              <div className="stat-row">
                <span>Session VWAP:</span>
                <span className="value">{formatUSD(data.session_context.session_vwap)}</span>
              </div>
              <div className="stat-row">
                <span>Distance:</span>
                <span className={`value ${getValueClass(data.session_context.distance_from_vwap_bps)}`}>
                  {formatNumber(data.session_context.distance_from_vwap_bps, 1)} bps
                </span>
              </div>
              <h3>Volume (Hyperliquid API)</h3>
              <div className="stat-row">
                <span>24h:</span>
                <span className="value">{data.session_context.hyperliquid_24h_volume_usd ? formatUSD(data.session_context.hyperliquid_24h_volume_usd) : 'N/A'}</span>
              </div>
              <div className="stat-row">
                <span>4h:</span>
                <span className="value">{data.session_context.hyperliquid_4h_volume_usd ? formatUSD(data.session_context.hyperliquid_4h_volume_usd) : 'N/A'}</span>
              </div>
              <div className="stat-row">
                <span>1h:</span>
                <span className="value">{data.session_context.hyperliquid_1h_volume_usd ? formatUSD(data.session_context.hyperliquid_1h_volume_usd) : 'N/A'}</span>
              </div>
            </div>
          )}

          {/* Orderbook Card */}
          {data.orderbook && (
            <div className="card">
              <h2>Orderbook</h2>
              <div className="stat-row">
                <span>Mid Price:</span>
                <span className="value">{formatUSD(data.orderbook.mid_price)}</span>
              </div>
              <div className="stat-row">
                <span>Spread:</span>
                <span className="value">{formatNumber(data.orderbook.spread_bps)} bps</span>
              </div>
              <div className="stat-row">
                <span>Best Bid:</span>
                <span className="value positive">{formatUSD(data.orderbook.best_bid)}</span>
              </div>
              <div className="stat-row">
                <span>Best Ask:</span>
                <span className="value negative">{formatUSD(data.orderbook.best_ask)}</span>
              </div>

              <h3>Depth (USD)</h3>
              <div className="stat-row">
                <span>L1 Depth:</span>
                <span className="value">
                  <span className="positive">{formatUSD(data.orderbook.l1_depth_bid)}</span>
                  {' / '}
                  <span className="negative">{formatUSD(data.orderbook.l1_depth_ask)}</span>
                </span>
              </div>
              <div className="stat-row">
                <span>L2 Depth:</span>
                <span className="value">
                  <span className="positive">{formatUSD(data.orderbook.l2_depth_bid)}</span>
                  {' / '}
                  <span className="negative">{formatUSD(data.orderbook.l2_depth_ask)}</span>
                </span>
              </div>
              <div className="stat-row">
                <span>L3 Depth:</span>
                <span className="value">
                  <span className="positive">{formatUSD(data.orderbook.l3_depth_bid)}</span>
                  {' / '}
                  <span className="negative">{formatUSD(data.orderbook.l3_depth_ask)}</span>
                </span>
              </div>
              <div className="stat-row">
                <span>L4 Depth:</span>
                <span className="value">
                  <span className="positive">{formatUSD(data.orderbook.l4_depth_bid)}</span>
                  {' / '}
                  <span className="negative">{formatUSD(data.orderbook.l4_depth_ask)}</span>
                </span>
              </div>
              <div className="stat-row">
                <span>L5 Depth:</span>
                <span className="value">
                  <span className="positive">{formatUSD(data.orderbook.l5_depth_bid)}</span>
                  {' / '}
                  <span className="negative">{formatUSD(data.orderbook.l5_depth_ask)}</span>
                </span>
              </div>

              <h3>Imbalance</h3>
              <div className="stat-row">
                <span>L1 Imbalance:</span>
                <span className={`value ${getValueClass(data.orderbook.l1_imbalance)}`}>
                  {formatPercent(data.orderbook.l1_imbalance)}
                </span>
              </div>
              <div className="stat-row">
                <span>L5 Imbalance:</span>
                <span className={`value ${getValueClass(data.orderbook.l5_imbalance)}`}>
                  {formatPercent(data.orderbook.l5_imbalance)}
                </span>
              </div>
            </div>
          )}

          {/* Trade Flow Card */}
          {data.trade_flow && (
            <div className="card">
              <h2>Trade Flow (30s)</h2>
              <div className="stat-row">
                <span>Trade Count:</span>
                <span className="value">{data.trade_flow.trade_count}</span>
              </div>
              <div className="stat-row">
                <span>Total Volume:</span>
                <span className="value">{formatUSD(data.trade_flow.total_volume)}</span>
              </div>
              <div className="stat-row">
                <span>Buy Volume:</span>
                <span className="value positive">{formatUSD(data.trade_flow.buy_volume)}</span>
              </div>
              <div className="stat-row">
                <span>Sell Volume:</span>
                <span className="value negative">{formatUSD(data.trade_flow.sell_volume)}</span>
              </div>
              <div className="stat-row">
                <span>Buy Ratio:</span>
                <span className="value positive">{formatPercent(data.trade_flow.buy_ratio * 100, 5)}</span>
              </div>
              {data.trade_flow.sweep_direction && (
                <div className="stat-row highlight">
                  <span>Sweep Direction:</span>
                  <span className={`value ${data.trade_flow.sweep_direction === 'up' ? 'positive' : 'negative'}`}>
                    {data.trade_flow.sweep_direction === 'up' ? '⬆️ UP' : '⬇️ DOWN'}
                  </span>
                </div>
              )}
              <div className="stat-row">
                <span>Largest Trade:</span>
                <span className="value">{formatUSD(data.trade_flow.largest)}</span>
              </div>
              <div className="stat-row">
                <span>Average Trade:</span>
                <span className="value">{formatUSD(data.trade_flow.average)}</span>
              </div>
            </div>
          )}

          {/* Momentum Card */}
          {data.momentum && (
            <div className="card">
              <h2>Price Momentum</h2>
              {data.momentum.short && (
                <>
                  <h3>Short Term (5s)</h3>
                  <div className="stat-row">
                    <span>Direction:</span>
                    <span className={`value ${data.momentum.short.direction === 'up' ? 'positive' : data.momentum.short.direction === 'down' ? 'negative' : ''}`}>
                      {data.momentum.short.direction.toUpperCase()}
                    </span>
                  </div>
                  <div className="stat-row">
                    <span>Change:</span>
                    <span className={`value ${getValueClass(data.momentum.short.change_percent)}`}>
                      {formatPercent(data.momentum.short.change_percent)}
                    </span>
                  </div>
                </>
              )}
              {data.momentum.long && (
                <>
                  <h3>Long Term (20s)</h3>
                  <div className="stat-row">
                    <span>Direction:</span>
                    <span className={`value ${data.momentum.long.direction === 'up' ? 'positive' : data.momentum.long.direction === 'down' ? 'negative' : ''}`}>
                      {data.momentum.long.direction.toUpperCase()}
                    </span>
                  </div>
                  <div className="stat-row">
                    <span>Change:</span>
                    <span className={`value ${getValueClass(data.momentum.long.change_percent)}`}>
                      {formatPercent(data.momentum.long.change_percent)}
                    </span>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Depth Decay Card */}
          {data.depth_decay && (
            <div className="card">
              <h2>Depth Decay (15s)</h2>
              <div className="stat-row">
                <span>Bid Decay:</span>
                <span className={`value ${getValueClass(data.depth_decay.bid_decay_percent, true)}`}>
                  {formatPercent(data.depth_decay.bid_decay_percent)}
                </span>
              </div>
              <div className="stat-row">
                <span>Bid Status:</span>
                <span className={`value ${getStatusClass(data.depth_decay.bid_status)}`}>
                  {data.depth_decay.bid_status}
                </span>
              </div>
              <div className="stat-row">
                <span>Ask Decay:</span>
                <span className={`value ${getValueClass(data.depth_decay.ask_decay_percent, true)}`}>
                  {formatPercent(data.depth_decay.ask_decay_percent)}
                </span>
              </div>
              <div className="stat-row">
                <span>Ask Status:</span>
                <span className={`value ${getStatusClass(data.depth_decay.ask_status)}`}>
                  {data.depth_decay.ask_status}
                </span>
              </div>
            </div>
          )}

          {/* Liquidations Card */}
          {data.liquidations && (
            <div className="card">
              <h2>Liquidations (60s)</h2>
              <div className="stat-row">
                <span>Status:</span>
                <span className={`value ${getStatusClass(data.liquidations.status)}`}>
                  {data.liquidations.status}
                </span>
              </div>
              <div className="stat-row">
                <span>Long Liqs:</span>
                <span className="value negative">{data.liquidations.long_liquidations}</span>
              </div>
              <div className="stat-row">
                <span>Short Liqs:</span>
                <span className="value positive">{data.liquidations.short_liquidations}</span>
              </div>
              <div className="stat-row">
                <span>Long Volume:</span>
                <span className="value negative">{formatUSD(data.liquidations.total_long_volume)}</span>
              </div>
              <div className="stat-row">
                <span>Short Volume:</span>
                <span className="value positive">{formatUSD(data.liquidations.total_short_volume)}</span>
              </div>
            </div>
          )}

          {/* Market Indicators Card */}
          {data.market_indicators && (
            <div className="card">
              <h2>Market Indicators</h2>
              <div className="stat-row">
                <span>Open Interest:</span>
                <span className="value">{formatUSD(data.market_indicators.oi)}</span>
              </div>
              <div className="stat-row">
                <span>OI Trend:</span>
                <span className={`value ${data.market_indicators.oi_trend === 'increasing' ? 'positive' : data.market_indicators.oi_trend === 'decreasing' ? 'negative' : ''}`}>
                  {data.market_indicators.oi_trend.toUpperCase()}
                </span>
              </div>
              <div className="stat-row">
                <span>OI Velocity:</span>
                <span className={`value ${getValueClass(data.market_indicators.oi_velocity)}`}>
                  {formatPercent(data.market_indicators.oi_velocity, 5)}/min
                </span>
              </div>
              <div className="stat-row">
                <span>Funding Rate:</span>
                <span className={`value ${getValueClass(data.market_indicators.funding_rate)}`}>
                  {formatPercent(data.market_indicators.funding_rate * 100, 5)}
                </span>
              </div>
              <div className="stat-row">
                <span>Funding Trend:</span>
                <span className="value">{data.market_indicators.funding_trend.toUpperCase()}</span>
              </div>
              <div className="stat-row">
                <span>Basis:</span>
                <span className={`value ${getValueClass(data.market_indicators.basis)}`}>
                  {formatPercent(data.market_indicators.basis, 5)}
                </span>
              </div>
              <div className="stat-row">
                <span>Basis Status:</span>
                <span className={`value ${getStatusClass(data.market_indicators.basis_status)}`}>
                  {data.market_indicators.basis_status}
                </span>
              </div>
            </div>
          )}

          {/* Position Crowding Card */}
          {data.crowding && (
            <div className="card">
              <h2>Position Crowding</h2>
              <div className="stat-row">
                <span>Crowded Long:</span>
                <span className={`value highlight ${data.crowding.crowded_long ? 'status-high' : ''}`}>
                  {data.crowding.crowded_long ? 'YES' : 'NO'}
                </span>
              </div>
              <div className="stat-row">
                <span>Long Score:</span>
                <span className="value">{formatNumber(data.crowding.long_crowding_score * 100, 3)}%</span>
              </div>
              <div className="stat-row">
                <span>Crowded Short:</span>
                <span className={`value highlight ${data.crowding.crowded_short ? 'status-high' : ''}`}>
                  {data.crowding.crowded_short ? 'YES' : 'NO'}
                </span>
              </div>
              <div className="stat-row">
                <span>Short Score:</span>
                <span className="value">{formatNumber(data.crowding.short_crowding_score * 100, 3)}%</span>
              </div>
              <div style={{ marginTop: '12px', padding: '8px', background: 'rgba(255,255,255,0.05)', borderRadius: '4px', fontSize: '0.85em' }}>
                {data.crowding.interpretation}
              </div>
            </div>
          )}

          {/* Orderbook Ladder Card */}
          {data.orderbook && data.orderbook.bids && data.orderbook.asks && (
            <div className="card orderbook-ladder">
              <h2>Order Book Ladder</h2>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                {/* Bids (left) */}
                <div>
                  <h3 style={{ color: '#4ade80', fontSize: '0.9em', marginBottom: '8px' }}>Bids</h3>
                  <div style={{ fontSize: '0.75em' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '4px', marginBottom: '4px', opacity: 0.6 }}>
                      <div>Price</div>
                      <div>Size</div>
                      <div>Total</div>
                    </div>
                    {data.orderbook.bids.slice(0, 10).map((bid, idx) => (
                      <div key={idx} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '4px', padding: '2px 0' }}>
                        <div style={{ color: '#4ade80' }}>{formatNumber(bid.price, 2)}</div>
                        <div>{formatNumber(bid.size, 3)}</div>
                        <div>{formatNumber(bid.total_usd, 0)}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Asks (right) */}
                <div>
                  <h3 style={{ color: '#f87171', fontSize: '0.9em', marginBottom: '8px' }}>Asks</h3>
                  <div style={{ fontSize: '0.75em' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '4px', marginBottom: '4px', opacity: 0.6 }}>
                      <div>Price</div>
                      <div>Size</div>
                      <div>Total</div>
                    </div>
                    {data.orderbook.asks.slice(0, 10).map((ask, idx) => (
                      <div key={idx} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '4px', padding: '2px 0' }}>
                        <div style={{ color: '#f87171' }}>{formatNumber(ask.price, 2)}</div>
                        <div>{formatNumber(ask.size, 3)}</div>
                        <div>{formatNumber(ask.total_usd, 0)}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Volatility Metrics */}
          {data.volatility && (
            <div className="card">
              <h2>Volatility</h2>
              <div className="stat-row">
                <span>Regime:</span>
                <span className={`value highlight status-${data.volatility.regime}`}>{data.volatility.regime.toUpperCase()}</span>
              </div>
              <div className="stat-row">
                <span>Percentile:</span>
                <span className="value">{formatNumber(data.volatility.percentile, 1)}</span>
              </div>
              <div className="stat-row">
                <span>ATR 1m:</span>
                <span className="value">{formatNumber(data.volatility.atr_1m, 4)}</span>
              </div>
              <div className="stat-row">
                <span>ATR 5m:</span>
                <span className="value">{formatNumber(data.volatility.atr_5m, 4)}</span>
              </div>
              <div className="stat-row">
                <span>Realized Vol 1m:</span>
                <span className="value">{formatPercent(data.volatility.realized_vol_1m)}</span>
              </div>
              <div className="stat-row">
                <span>Realized Vol 5m:</span>
                <span className="value">{formatPercent(data.volatility.realized_vol_5m)}</span>
              </div>
            </div>
          )}

          {/* Market Regime */}
          {data.regime && (
            <div className="card">
              <h2>Market Regime</h2>
              <div className="stat-row">
                <span>Market State:</span>
                <span className={`value highlight status-${data.regime.market_regime}`}>
                  {data.regime.market_regime.toUpperCase().replace(/_/g, ' ')}
                </span>
              </div>

              <h3>Trend</h3>
              <div className="stat-row">
                <span>Direction:</span>
                <span className={`value ${data.regime.trend_regime === 'up' ? 'positive' :
                  data.regime.trend_regime === 'down' ? 'negative' : ''
                  }`}>
                  {data.regime.trend_regime.toUpperCase()}
                </span>
              </div>
              <div className="stat-row">
                <span>Strength:</span>
                <span className="value">{formatNumber(data.regime.trend_strength * 100, 3)}%</span>
              </div>

              <h3>Liquidity</h3>
              <div className="stat-row">
                <span>Regime:</span>
                <span className={`value ${data.regime.liquidity_regime === 'high' ? 'positive' :
                  data.regime.liquidity_regime === 'thin' ? 'negative' : ''
                  }`}>
                  {data.regime.liquidity_regime.toUpperCase()}
                </span>
              </div>
            </div>
          )}

          {/* Slippage Estimates */}
          {data.slippage && (
            <div className="card">
              <h2>Slippage & Execution Costs</h2>
              {Object.entries(data.slippage).map(([size, estimates]) => (
                <div key={size} style={{ marginBottom: '12px' }}>
                  <h3 style={{ fontSize: '0.9em', marginBottom: '6px', opacity: 0.8 }}>{size} Trade</h3>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px', fontSize: '0.85em' }}>
                    <div style={{ gridColumn: '1 / -1', marginBottom: '4px', opacity: 0.7 }}>
                      Spread: {formatNumber(estimates.spread_bps, 1)} bps | Fee: {formatNumber(estimates.fee_bps, 1)} bps
                    </div>
                    <div>
                      <strong>BUY</strong><br />
                      VWAP: <span className="value">{formatNumber(estimates.buy.avg_fill_price, 2)}</span><br />
                      Slippage: <span className="value">{formatNumber(estimates.buy.slippage_bps, 1)} bps</span><br />
                      RT Cost: <span className={`value ${estimates.buy.round_trip_cost_bps > 20 ? 'negative' : ''}`}>
                        {formatNumber(estimates.buy.round_trip_cost_bps, 1)} bps
                      </span><br />
                      Liq Used: <span className={`value ${estimates.buy.liquidity_used_pct > 50 ? 'negative' : ''}`}>
                        {formatNumber(estimates.buy.liquidity_used_pct, 3)}%
                      </span>
                    </div>
                    <div>
                      <strong>SELL</strong><br />
                      VWAP: <span className="value">{formatNumber(estimates.sell.avg_fill_price, 2)}</span><br />
                      Slippage: <span className="value">{formatNumber(estimates.sell.slippage_bps, 1)} bps</span><br />
                      RT Cost: <span className={`value ${estimates.sell.round_trip_cost_bps > 20 ? 'negative' : ''}`}>
                        {formatNumber(estimates.sell.round_trip_cost_bps, 1)} bps
                      </span><br />
                      Liq Used: <span className={`value ${estimates.sell.liquidity_used_pct > 50 ? 'negative' : ''}`}>
                        {formatNumber(estimates.sell.liquidity_used_pct, 3)}%
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Multi-Timeframe Candles */}
          {data.candles && (
            <div className="card">
              <h2>Multi-Timeframe Candles</h2>
              {Object.entries(data.candles).map(([interval, candle]) => (
                <div key={interval} style={{ marginBottom: '12px' }}>
                  <h3 style={{ fontSize: '0.9em', marginBottom: '6px', opacity: 0.8 }}>{interval}</h3>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px', fontSize: '0.85em' }}>
                    <div>Return: <span className={getValueClass(candle.return_pct)}>{formatPercent(candle.return_pct)}</span></div>
                    <div>Close: <span className="value">{formatNumber(candle.close, 2)}</span></div>
                    <div>ATR: <span className="value">{formatNumber(candle.atr, 4)}</span></div>
                    <div>Vol: <span className="value">{formatPercent(candle.realized_vol)}</span></div>
                    <div>Vol vs Avg: <span className={getValueClass((candle.volume_vs_avg - 1) * 100)}>{formatNumber(candle.volume_vs_avg, 2)}x</span></div>
                    <div>Raw Vol: <span className="value">{formatUSD(candle.volume)}</span></div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Multi-Timeframe Trade Flow */}
          {data.trade_flow_multi && (
            <div className="card">
              <h2>Trade Flow (Multi-Timeframe)</h2>
              {Object.entries(data.trade_flow_multi).map(([window, flow]) => (
                <div key={window} style={{ marginBottom: '12px' }}>
                  <h3 style={{ fontSize: '0.9em', marginBottom: '6px', opacity: 0.8 }}>{window}</h3>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px', fontSize: '0.85em' }}>
                    <div>Trades: <span className="value">{flow.trade_count}</span></div>
                    <div>Total Volume: <span className="value">{formatUSD(flow.total_volume)}</span></div>
                    <div>Buy Volume: <span className="value positive">{formatUSD(flow.buy_volume)}</span></div>
                    <div>Sell Volume: <span className="value negative">{formatUSD(flow.sell_volume)}</span></div>
                    <div>Buy Ratio: <span className={getValueClass(flow.buy_ratio * 100 - 50)}>{formatPercent(flow.buy_ratio * 100, 3)}</span></div>
                    <div>Sell Ratio: <span className={getValueClass(50 - flow.sell_ratio * 100)}>{formatPercent(flow.sell_ratio * 100, 3)}</span></div>
                    <div>Sweep: <span className="value">{flow.sweep_direction?.toUpperCase() || 'NONE'}</span></div>
                    <div>Largest: <span className="value">{formatUSD(flow.largest)}</span></div>
                    <div>Average: <span className="value">{formatUSD(flow.average)}</span></div>
                    <div>Median: <span className="value">{formatUSD(flow.median)}</span></div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Multi-Timeframe Liquidations */}
          {data.liquidations_multi && (
            <div className="card">
              <h2>Liquidations (Multi-Timeframe)</h2>
              {Object.entries(data.liquidations_multi).map(([window, liq]) => (
                <div key={window} style={{ marginBottom: '12px' }}>
                  <h3 style={{ fontSize: '0.9em', marginBottom: '6px', opacity: 0.8 }}>{window}</h3>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px', fontSize: '0.85em' }}>
                    <div>Status: <span className={`value ${getStatusClass(liq.status)}`}>{liq.status}</span></div>
                    <div>Total Vol: <span className="value">{formatUSD(liq.total_long_volume + liq.total_short_volume)}</span></div>
                    <div>Long Liqs: <span className="value">{liq.long_liquidations}</span></div>
                    <div>Long Vol: <span className="value negative">{formatUSD(liq.total_long_volume)}</span></div>
                    <div>Short Liqs: <span className="value">{liq.short_liquidations}</span></div>
                    <div>Short Vol: <span className="value positive">{formatUSD(liq.total_short_volume)}</span></div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Multi-Timeframe OI */}
          {data.oi_multi && data.market_indicators && (
            <div className="card">
              <h2>Open Interest (Multi-Timeframe)</h2>
              {Object.entries(data.oi_multi).map(([window, oi]) => (
                <div key={window} style={{ marginBottom: '12px' }}>
                  <h3 style={{ fontSize: '0.9em', marginBottom: '6px', opacity: 0.8 }}>{window}</h3>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px', fontSize: '0.85em' }}>
                    <div>Current OI: <span className="value">{data.market_indicators?.oi ? formatUSD(data.market_indicators.oi) : 'N/A'}</span></div>
                    <div>Change: <span className={getValueClass(oi.change_percent)}>{formatPercent(oi.change_percent, 3)}</span></div>
                    <div>Trend: <span className="value">{oi.trend.toUpperCase()}</span></div>
                    <div>Velocity: <span className={getValueClass(oi.velocity)}>{formatPercent(oi.velocity, 5)}/min</span></div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default Dashboard;
