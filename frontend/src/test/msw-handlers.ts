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

  http.get('/api/v1/brokers', () => HttpResponse.json([])),
  http.get('/api/v1/strategies', () => HttpResponse.json([])),
  http.get('/api/v1/strategies/classes', () => HttpResponse.json([])),
  http.get('/api/v1/signals', () => HttpResponse.json([])),
  http.get('/api/v1/portfolio/summary', () => HttpResponse.json({
    total_equity: 0, total_cash: 0, total_unrealized_pnl: 0, positions: [], accounts: [],
  })),
  http.get('/api/v1/portfolio/history', () => HttpResponse.json([])),
  http.get('/api/v1/market/ohlcv', () => HttpResponse.json([])),
]
