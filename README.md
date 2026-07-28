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

- **Backtesting** — run any registered strategy against Yahoo Finance / Bybit historical data, see equity curve, trade markers, and full performance metrics (Sharpe, max drawdown, win rate, profit factor). Positions are sized with the **same risk model as live trading** (`position_size_pct`, default 2%), so a backtest's equity curve reflects the magnitude the strategy would actually trade live — not an all-in curve that overstates returns. Fills carry realistic costs: flat **commission** plus **adverse slippage** (`slippage_pct`, default 5 bps — buys fill higher, sells lower), so results aren't optimistically frictionless
- **Strategy system** — built-in SMA crossover, RSI mean reversion, MACD, Bollinger Bands; user-defined strategies auto-loaded from `backend/user_strategies/`
- **AI Strategy Builder** — describe a strategy in plain English, generate Python code via Claude, run a sandbox backtest — all in the browser
- **Live/paper trade pipeline** — one executor loop per active strategy runs the full chain: `signal → position sizing → RiskManager veto → broker → fill → persistence`. Paper trading uses a built-in `SimulatedBrokerAdapter` with a durable virtual ledger (zero broker setup); live uses a real broker connection. Signals and every order attempt are persisted; orders broadcast over WebSocket
- **Risk profile + per-strategy overrides** — a per-user risk profile (SL/TP, drawdown limits, max positions, order rate, kill switch) sets the defaults, edited in Settings; each strategy carries behavioral config (position size, `allow_short`, poll) plus **optional risk overrides** (blank = inherit the profile). Editing a strategy's config restarts only that bot (live-adapts); changing the profile only refreshes form defaults, never running bots. Backtests take arrangeable SL/TP **and position size %** per run (position size defaults to the live 2%, so backtest ≈ live)
- **Loop-managed stops + new-bar gating** — stop-loss / take-profit are checked every poll and never blocked by the risk veto; signals regenerate only once per closed bar
- **Restart-safe** — positions, peak equity, open-position count, and today's realized P&L are rehydrated from persisted state on boot
- **Broker adapters** — Alpaca, Bybit, Binance (through a common `BrokerAdapter`). Live path is covered by integration tests with a fake adapter; a Bybit **testnet** smoke-test runbook is in `docs/runbooks/testnet-smoke-test.md`
- **WebSocket** — real-time portfolio snapshots every 15s, strategy status, signal events
- **OHLCV caching** — cache-aside pattern; bars stored in SQLite, fetched from Yahoo Finance / Bybit with pagination
- **6 frontend pages** — Dashboard, Portfolio, Backtests, Strategies, Builder, Settings
- **i18n** — English and Spanish

---

## How It Works

Three pieces do the heavy lifting: the **backtest engine** (simulates a strategy on past data), the
**backtesting flow** (feeds it historical data), and the **live/paper executor** (runs a strategy
forward on fresh data). They deliberately share the same sizing and cost model so a backtest is an
honest preview of live — not an optimistic one.

### 1. The backtest engine — `app/domain/backtest/engine.py`

Walks the price history **one bar at a time**. On each bar it shows the strategy only the data up to
and including that bar (never the future), asks for a signal, and — if there's one — **fills it at the
next bar's open**, never at the same bar's close. That one rule kills the most common way backtests
lie to you (acting on a price you couldn't actually have traded at).

- **One position at a time**, long or short.
- **Position sizing = equity × `position_size_pct`** (default 2%) — the *same* formula the live
  executor uses, so the equity curve reflects live magnitude, not an all-in curve.
- **Realistic costs on every fill**: a flat **commission** per side **plus adverse slippage**
  (`slippage_pct`, default 5 bps) — you buy a touch higher and sell a touch lower, modeling the
  spread + market impact.
- **Stops & targets** are checked against each bar's high/low and fill at the trigger price (stop
  before target, i.e. the conservative outcome when a bar hits both).
- Produces the **equity curve, every trade, and metrics** (total return, Sharpe, max drawdown, win
  rate, profit factor).

_Could be improved:_ slippage is a flat rate (a volatility-scaled version would cost more in choppy
markets); there's no partial-fill or latency modeling. Robustness tooling (walk-forward, Monte Carlo)
is planned, not built.

### 2. Backtesting flow — `app/services/backtest_service.py`

Fetches historical OHLCV from **Yahoo Finance** (primary) with a **Bybit** fallback for crypto, using
a **cache-aside** pattern (bars are stored in SQLite and reused when a later run covers the same
range). All bars are normalized to **naive UTC** and passed through a single `dedupe_sort_bars`
chokepoint, so timestamps are always ascending and unique regardless of source (guards against
provider pagination overlap and DST-boundary duplicates). It needs at least 60 bars, then hands them
to the engine and returns the result to the `/backtests` page.

_Could be improved:_ data quality depends on the free providers (gaps, no true tick history);
survivorship/point-in-time correctness isn't guaranteed for all symbols.

### 3. Live / paper executor — `app/services/strategy_executor.py`

One background task per active strategy. Each cycle it fetches the latest bars on the strategy's
timeframe, and **only when a new bar has closed** asks for a signal (stops are still checked every
poll). A signal then flows through the full chain:

```
signal → position sizing (equity × size%) → RiskManager veto (hard, cannot be bypassed) → broker → fill → persist → WebSocket broadcast
```

- **Paper** uses a built-in `SimulatedBrokerAdapter` — a durable virtual ledger, zero broker setup,
  fills at the latest close **with the same commission + slippage the backtest applies** (config
  `SIM_COMMISSION_PCT` / `SIM_SLIPPAGE_PCT`), so paper P&L matches a backtest and previews real live
  costs. **Live** uses a real broker connection (Alpaca / Bybit / Binance).
- **Same decision logic as the backtest.** Intent → action (open / close / full reversal) comes from
  one shared `plan_actions` policy used by *both* the live executor and the backtest engine, so a
  strategy that flips direction trades identically in both (a long→short flip closes **and** re-opens).
- Signals and **every order attempt** are persisted; the frontend strategy page renders them live.
- **Restart-safe**: positions, peak equity, open-position count, and today's realized P&L are
  rehydrated on boot.

_Could be improved:_ "live data" is currently **repeated polling** of recent bars, not a true tick
stream (`stream_ticks()` is unimplemented); live broker fill-confirmation (real fill price/commission)
is reconciled on the next poll rather than captured immediately. The one remaining intentional
backtest↔live difference is fill *timing* (backtest fills next-bar open, live fills at the just-closed
bar) — negligible for 24/7 crypto, and the honest choice for daily bars.

### What this means for you (user side)

- A good backtest is **necessary, not sufficient.** Keep `slippage_pct`, commission, and
  `position_size_pct` realistic for your asset — a strategy that only works at zero cost is fragile.
- **Validate out-of-sample.** One great backtest can be luck or overfitting; test on data you didn't
  tune on.
- **Always run paper before live**, and expect live results to sit *inside* the backtest's range, not
  exactly on its line.
- Write strategies that **only look at past bars** — the engine won't hand you the future, so don't
  build logic that assumes it.

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

### Design principles

**SOLID and separation of concerns are enforced on every change**, not just new features. Each layer above has one responsibility and stays inside it — routers don't hold business logic, domain code never touches the DB or FastAPI, repositories don't decide policy. Behavior is extended by adding adapters/strategies (open/closed), and concrete implementations are injected against base-class abstractions (dependency inversion).

**Single source of truth for shared mappings.** Field lists and mappings are derived, never hand-maintained in parallel. For example, a strategy's per-strategy execution/risk config field set is defined once on the `ExecutionConfig` schema; the ORM-read (`from_instance`) and ORM-write (`_config_columns`) paths both derive their fields from `ExecutionConfig.model_fields`, and a guard test fails if the schema and the `StrategyInstance` model ever drift. Adding a config field means one new column plus one Pydantic field — nothing else to keep in sync.

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

Max position 2% · Max 5 open positions · Daily drawdown limit 3% · Total drawdown limit 10% · Mandatory stop-loss 1.5% · Max 10 orders/min. Enforced by `RiskManager`. These are the global defaults (via `.env`); **each strategy instance can override them** through its own execution/risk config (editable in the Strategies page and applied live).

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
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

> Bind to `127.0.0.1` (loopback) for local use. Phase 1 has **no authentication** and the strategy
> sandbox is not a hardened security boundary, so `--host 0.0.0.0` would expose the full API — order
> placement, broker connections, arbitrary strategy code — to everyone on your network. Only use
> `0.0.0.0` if you deliberately intend to share on a trusted LAN.

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

It appears in Backtests and Strategies pages automatically on next restart. For copy-paste
starting points, see `backend/user_strategies/TEMPLATE.py` (fully commented) and
`always_long.py` (a minimal deterministic strategy used for execution smoke tests). Define a
module-level `STRATEGY_META` dict to get a parameter form in the UI.

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
- [x] Full trade pipeline: sizing → RiskManager → broker → fill → persistence (paper via built-in simulator)
- [x] Per-strategy risk/execution config (live-editable), loop-managed stops, new-bar gating, restart rehydration
- [x] Broker adapters: Alpaca, Bybit, Binance; live path covered by tests (fake adapter)
- [x] React frontend — 6 pages wired to backend; per-strategy config form on the Strategies page
- [x] Structured FE error messages + toast notifications
- [ ] Real Bybit **testnet** smoke run (runbook ready — needs API keys)
- [ ] Live broker fill-confirmation (Bybit returns `submitted`; reconciled next poll)

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
