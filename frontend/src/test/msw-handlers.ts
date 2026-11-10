import { http, HttpResponse } from 'msw'

export const handlers = [
  http.get('/api/v1/backtests/strategies', () =>
    HttpResponse.json({
      strategies: [
        {
          class_name: 'SmaCrossover',
          display_name: 'SMA Crossover',
          description: 'Golden/death cross strategy',
          parameters: [
            { key: 'fast_period', type: 'int', default: 20, label: 'Fast Period' },
            { key: 'slow_period', type: 'int', default: 50, label: 'Slow Period' },
          ],
        },
        {
          class_name: 'RsiMeanReversion',
          display_name: 'RSI Mean Reversion',
          description: 'RSI-based strategy',
          parameters: [
            { key: 'rsi_period', type: 'int', default: 14, label: 'RSI Period' },
          ],
        },
      ],
    })
  ),

  http.post('/api/v1/backtests/run', () =>
    HttpResponse.json({
      strategy_name: 'SmaCrossover',
      symbol: 'BTCUSDT',
      timeframe: '1d',
      initial_capital: 10000,
      metrics: {
        total_return_pct: 12.5,
        sharpe_ratio: 1.2,
        max_drawdown_pct: 5.0,
        win_rate: 55.0,
        profit_factor: 1.8,
        total_trades: 10,
        winning_trades: 6,
        losing_trades: 4,
        avg_win: 250,
        avg_loss: -120,
        final_equity: 11250,
      },
      equity_curve: [
        { timestamp: 1700000000000, value: 10000 },
        { timestamp: 1700086400000, value: 11250 },
      ],
      prices: [
        { timestamp: 1700000000000, close: 36000 },
        { timestamp: 1700086400000, close: 37200 },
      ],
      trades: [],
    })
  ),

  http.post('/api/v1/backtests/grid', () =>
    HttpResponse.json({
      symbol: 'BTCUSDT',
      timeframe: '1h',
      allow_intrabar_roundtrip: false,
      funding_rate_caveat: 'SHORT_BIASED grid legs omit perp funding-rate cost.',
      arms: {
        grid_guarded_reanchor: {
          equity_curve: [
            { timestamp: 1700000000000, value: 10000 },
            { timestamp: 1700086400000, value: 10120 },
          ],
          final_equity: 10120, total_return_pct: 1.2, max_drawdown_pct: 3.4, sharpe_ratio: 0.9,
          grid_trades: 50, grid_realized_pnl: 260, forced_exit_pnl: -20, force_close_count: 1,
          mark_to_market_pnl: -120,
          avg_profit_per_grid_pct: 0.26, fill_rate: 52.7, time_in_grid_pct: 86,
          max_inventory_notional: 1052, worst_unrealized_pct: 4.1, time_underwater_pct: 40,
        },
        grid_accumulate_nostop: {
          equity_curve: [
            { timestamp: 1700000000000, value: 10000 },
            { timestamp: 1700086400000, value: 9800 },
          ],
          final_equity: 9800, total_return_pct: -2, max_drawdown_pct: 9.9, sharpe_ratio: -0.3,
          grid_trades: 61, grid_realized_pnl: 310, forced_exit_pnl: 0, force_close_count: 0,
          mark_to_market_pnl: -510,
          avg_profit_per_grid_pct: 0.25, fill_rate: 60.1, time_in_grid_pct: 92,
          max_inventory_notional: 4200, worst_unrealized_pct: 12.5, time_underwater_pct: 71,
        },
      },
    })
  ),

  http.get('/api/v1/settings/risk', () => HttpResponse.json({
    stop_loss_pct: 0.015, take_profit_pct: null, max_open_positions: 5,
    max_daily_drawdown_pct: 0.03, max_total_drawdown_pct: 0.10,
    max_orders_per_minute: 10, kill_switch_enabled: true,
  })),
  http.put('/api/v1/settings/risk', async ({ request }) => HttpResponse.json(await request.json())),

  http.get('/api/v1/brokers', () => HttpResponse.json([])),
  http.get('/api/v1/strategies', () => HttpResponse.json([])),
  http.get('/api/v1/strategies/classes', () => HttpResponse.json([])),
  http.get('/api/v1/strategies/:id/orders', () => HttpResponse.json([])),
  http.get('/api/v1/signals', () => HttpResponse.json([])),
  http.get('/api/v1/portfolio/summary', () => HttpResponse.json({
    total_equity: 0, total_cash: 0, total_unrealized_pnl: 0, positions: [], accounts: [],
  })),
  http.get('/api/v1/portfolio/history', () => HttpResponse.json([])),
  http.get('/api/v1/orders', () => HttpResponse.json({ items: [], total: 0 })),
  http.get('/api/v1/market/ohlcv', () => HttpResponse.json([])),
]
