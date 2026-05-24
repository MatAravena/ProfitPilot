# ProfitPilot

Algorithmic trading platform with ML forecasting, multi-broker execution, and an optional LLM signal enrichment layer. Built for running and backtesting trading strategies locally first, with a path toward a multi-tenant SaaS.

---

## Project Status

| Phase | Status | Description |
|---|---|---|
| **Phase 1 — Local** | In progress | Single-user, no auth. Run and backtest strategies locally. Core stack functional. |
| **Phase 1.5 — ML** | Planned | PyTorch, XGBoost, LightGBM, Darts, NeuralProphet forecasting adapters |
| **Phase 2 — SaaS** | Future | Multi-tenant, JWT auth, billing, TimescaleDB, Celery, Redis pub/sub |

---

## What Works Today

- **Backtesting** — run any registered strategy against Yahoo Finance / Bybit historical data, see equity curve, trade markers, and full performance metrics (Sharpe, max drawdown, win rate, profit factor)
- **Strategy system** — built-in SMA crossover, RSI mean reversion, MACD, Bollinger Bands; user-defined strategies auto-loaded from `backend/user_strategies/`
- **AI Strategy Builder** — describe a strategy in plain English, generate Python code via Claude, run a sandbox backtest — all in the browser
- **Live/paper executor** — asyncio loop that polls market data per strategy timeframe, persists signals to DB, notifies via WebSocket
- **Broker adapters** — Alpaca, Bybit, Binance (adapters implemented; Bybit testnet tested)
- **WebSocket** — real-time portfolio snapshots every 15s, strategy status, signal events
- **OHLCV caching** — cache-aside pattern; bars stored in SQLite, fetched from Yahoo Finance / Bybit with pagination
- **6 frontend pages** — Dashboard, Portfolio, Backtests, Strategies, Builder, Settings
- **i18n** — English and Spanish

---

## Tech Stack

### Backend
| Layer | Technology |
|---|---|
| API framework | FastAPI 0.115 + Pydantic v2 |
| ORM | SQLAlchemy 2.0 async |
| Database (dev) | SQLite (auto-detected via `DATABASE_URL`) |
| Database (prod) | TimescaleDB (PostgreSQL + hypertables) |
| Market data | Yahoo Finance (primary), Bybit public API (fallback) |
| ML | PyTorch 2.4, XGBoost 2.1, LightGBM 4.5, Darts 0.30, NeuralProphet |
| Math / indicators | Rust (PyO3 bindings) — Monte Carlo, technical indicators |
| Logging | structlog |
| AI generation | Anthropic Claude API (`claude-sonnet-4-6`) |

### Frontend
| Layer | Technology |
|---|---|
| Framework | React 18 + TypeScript (strict) |
| Build tool | Vite |
| Routing | React Router v6 |
| State | Zustand (stores) + TanStack Query v5 (server state) |
| Charts | Recharts (equity curves, drawdown) + TradingView Lightweight Charts (candlesticks) |
| UI | shadcn/ui + Tailwind CSS |
| i18n | react-i18next (en / es) |
| Code editor | Monaco Editor (Builder page) |

---

## Architecture

### Backend layers

```
Request
  │
  ▼
Routers  (app/api/routes/)        — parse input, call service, format output. No business logic.
  │
  ▼
Services  (app/services/)         — orchestration across domain components
  │
  ▼
Domain  (app/domain/)             — pure business logic. No FastAPI, no DB calls.
  │
  ▼
Repositories  (app/repositories/) — DB access only
  │
  ▼
ORM Models  (app/models/db/)      — SQLAlchemy 2.0 async models
```

### Signal pipeline

```
OHLCV / Ticks
      │
      ▼
Feature Engineer (Rust-accelerated)
      │
      ├──▶ ForecastingModelAdapter  (PyTorch / XGBoost / LightGBM)
      ├──▶ Quant Indicators
      └──▶ LLMEnrichmentAdapter  (optional — strategies work without it)
                    │
                    ▼
           StrategyOrchestrator
                    │
                    ▼
           RiskManager.approve_order()   ← hard veto, cannot be bypassed
                    │
                    ▼
           BrokerAdapter.place_order()   (Alpaca / Bybit / Binance)
```

### Non-negotiable abstractions

Every broker call, model call, and order must go through its adapter — never call SDKs directly:

- `BrokerAdapter` — all exchange SDK calls
- `ForecastingModelAdapter` — all ML model calls
- `RiskManager` — hard veto before every order
- `LLMEnrichmentAdapter` — always optional

### Frontend pages

| Route | Page | Notes |
|---|---|---|
| `/` | Landing | Entry point |
| `/dashboard` | Dashboard | Portfolio overview, live P&L, active strategies |
| `/portfolio` | Portfolio | Positions, broker accounts, order history |
| `/backtests` | Backtests | Run backtests, equity curve, trade chart |
| `/strategies` | Strategies | Create / manage strategy instances |
| `/builder` | Builder | Monaco editor + AI generation + sandbox backtest |
| `/settings` | Settings | Language switcher, risk defaults |

### Risk defaults

Max position 2% · Max 5 open positions · Daily drawdown limit 3% · Total drawdown limit 10% · Mandatory stop-loss 1.5% · Max 10 orders/min. Enforced by `RiskManager`, configurable via `.env`.

---

## Project Structure

```
ProfitPilot/
├── backend/
│   ├── app/
│   │   ├── api/routes/           # FastAPI routers
│   │   ├── core/                 # Config, enums, shared types, datetime utils
│   │   ├── db/                   # Async SQLAlchemy engine + session factory
│   │   ├── domain/
│   │   │   ├── backtest/         # Backtest engine, data provider, metrics
│   │   │   ├── broker/           # BrokerAdapter base + Alpaca/Bybit/Binance adapters
│   │   │   ├── forecasting/      # ForecastingModelAdapter base + ML adapters
│   │   │   ├── market_data/      # Yahoo Finance provider
│   │   │   ├── risk/             # RiskManager
│   │   │   └── strategy/         # StrategyBase, registry, loader, examples
│   │   ├── models/
│   │   │   ├── db/               # SQLAlchemy ORM models
│   │   │   └── schemas/          # Pydantic request/response schemas
│   │   ├── repositories/         # DB access layer
│   │   ├── services/             # BacktestService, StrategyExecutor, StrategyBuilder
│   │   └── main.py               # FastAPI app + lifespan
│   ├── user_strategies/          # Drop-in user strategies (auto-loaded on start)
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/           # Shared UI components (charts, backtest widgets)
│   │   ├── locales/              # i18n strings (en, es)
│   │   ├── pages/                # One folder per route
│   │   ├── stores/               # Zustand stores
│   │   ├── types/                # TypeScript types mirroring backend schemas
│   │   └── lib/                  # API client, utils
│   └── package.json
├── rust_math/                    # PyO3 Rust library — indicators, Monte Carlo
├── docker/docker-compose.yml     # Full prod stack
└── .vscode/launch.json           # F5 → debug BE + FE simultaneously
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Rust (only needed for the math library)

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env        # fill in API keys
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: `http://localhost:8000/api/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev                  # http://localhost:5173
```

### Debug both at once (VS Code)

Press **F5** with **"BE + FE"** selected in the Run & Debug panel. Uvicorn starts with the Python debugger attached; Vite starts and Chrome opens automatically. Set breakpoints in `.py` or `.tsx` files and they just work.

### Rust math library (optional)

```bash
cd rust_math
cargo build --release        # generates PyO3 Python bindings
```

### Environment variables

Copy `backend/.env.example` and fill in:

```env
DATABASE_URL=sqlite:///./profitpilot.db
ANTHROPIC_API_KEY=...        # required for AI Strategy Builder
BYBIT_API_KEY=...
BYBIT_SECRET_KEY=...
BYBIT_TESTNET=true
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
BINANCE_API_KEY=...
BINANCE_SECRET_KEY=...
```

---

## Adding Strategies

Drop a file in `backend/user_strategies/your_strategy.py`:

```python
from app.domain.strategy.base import StrategyBase, StrategyRegistry
from app.core.enums import Direction

@StrategyRegistry.register
class MyStrategy(StrategyBase):
    name = "MyStrategy"

    async def generate_signals(self, market_data):
        # your logic here
        return []

    def get_required_symbols(self): return [self.symbol]
    def validate_parameters(self): pass
    async def on_tick(self, tick): pass
    async def on_fill(self, fill): pass
```

It appears in Backtests and Strategies pages automatically on next restart.

---

## Adding Brokers

```python
# backend/app/domain/broker/adapters/my_broker_adapter.py
from app.domain.broker.base import BrokerAdapter

class MyBrokerAdapter(BrokerAdapter):
    # implement: connect, disconnect, place_order, cancel_order,
    #            get_account, get_positions, stream_ticks
    ...
```

---

## Roadmap

### Phase 1 — Local (current)

- [x] FastAPI backend with layered architecture
- [x] Strategy engine with built-in strategies + user-defined auto-loading
- [x] Backtesting — equity curve, trade chart, performance metrics
- [x] Yahoo Finance + Bybit data providers with OHLCV caching
- [x] AI Strategy Builder (Monaco + Claude + sandbox execution)
- [x] Live/paper strategy executor with WebSocket signals
- [x] Broker adapters: Alpaca, Bybit, Binance
- [x] React frontend — 6 pages wired to backend
- [ ] Fix remaining startup errors (OhlcvBar model, OhlcvRepository)
- [ ] End-to-end test: paper strategy → signals persisted → WebSocket push
- [ ] Bybit testnet integration test
- [ ] Structured FE error messages + toast notifications

### Phase 1.5 — ML Forecasting

- [ ] PyTorch / LSTM price prediction adapter
- [ ] XGBoost feature-based classifier adapter
- [ ] LightGBM adapter
- [ ] Darts adapter (N-BEATS, TFT, Prophet)
- [ ] NeuralProphet integration
- [ ] Rust math library: PyO3 bindings for indicators + Monte Carlo simulation
- [ ] Feature engineering pipeline (rolling stats, momentum, volatility)

### Phase 2 — SaaS

- [ ] JWT auth (register / login)
- [ ] Multi-tenant DB (user_id foreign keys already in place)
- [ ] Billing integration
- [ ] TimescaleDB (PostgreSQL + hypertables for time-series)
- [ ] Migrate strategy executor + snapshot loop to Celery tasks
- [ ] Redis pub/sub for WebSocket broadcasting across workers
- [ ] Gunicorn + UvicornWorkers for horizontal scaling
- [ ] Docker Compose full stack (TimescaleDB, Redis, Celery, API, frontend)

---

## Future Ideas

- **Strategy marketplace** — share and discover community strategies ranked by live Sharpe ratio
- **Portfolio optimizer** — mean-variance optimization, Kelly criterion position sizing across strategies
- **Walk-forward testing** — rolling in/out-of-sample windows to avoid overfitting in backtests
- **Monte Carlo simulation** — run thousands of backtest variations to estimate robustness and worst-case drawdown
- **Strategy correlation matrix** — visualize how running strategies interact; avoid placing correlated bets
- **LLM signal enrichment** — feed earnings reports, news sentiment, and on-chain data into strategy decisions via Claude
- **Automated parameter tuning** — Optuna / Bayesian optimization for strategy hyperparameters
- **Full candlestick chart** — TradingView Lightweight Charts with indicator overlays (already planned, Recharts used for equity curves)
- **Alerting system** — Telegram / Discord / email when a strategy fires a signal or a drawdown limit is hit
- **Paper trading tournament** — run multiple strategies in parallel, rank by risk-adjusted return in real-time
- **Mobile companion** — React Native app for monitoring positions and receiving signal push notifications
