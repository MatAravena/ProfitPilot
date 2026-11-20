# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

ProfitPilot is an algorithmic trading platform with ML forecasting (PyTorch, XGBoost, LightGBM, Darts), multi-broker execution (Alpaca, Bybit, Binance), and an optional LLM signal enrichment layer.

**Current status:** Core backend is functional — routes, services, repositories, ORM models, broker adapters, backtest engine, strategy sandbox, and WebSocket layer are all implemented. The strategy executor runs live/paper strategies. All frontend pages are scaffolded and wired to the backend. The schema is owned by Alembic (`backend/migrations/`); the app upgrades to head on startup via `app/db/migrate.py` — never `create_all` on a real database (tests still use it for in-memory DBs).

**Keep this file free of anything that ages faster than the architecture** — model ids, dependency versions, test counts, page counts. Those belong in `config.py`, `requirements.txt`, `package.json`, or `TODO.md`, each with exactly one owner. This file describes structure and rules.

## Start here — what to work on

**`TODO.md` is the single owner of status and priorities.** Before picking up any work, read its top section, **"🚦 Roadmap to a first live track record"**, and take the first unchecked item in step order (host → testnet/paper → walk-forward → risk-based sizing → strategy research → agent layers). Do not start a new strategy family, SaaS item, or anything marked *frozen* there while an earlier step is open, unless the user asks for it explicitly. When you finish or learn something, update `TODO.md` in the same piece of work — tick the item, record the decision and why.

`PROFITPILOT_PROJECT_INSTRUCTIONS.md` is the original **vision / target architecture**, not current state — its status tracker is stale. Use it for intent, never for "what exists".

Standing decisions (user calls — do not relitigate, do not silently undo):

- **No real money.** Bybit testnet and Alpaca paper only. Never create, request, or use a live-trading key. Bybit testnet proves plumbing only; P&L that counts as a track record comes from Alpaca paper or `SimulatedBrokerAdapter` (real prices).
- **An LLM/agent never places, resizes, or opens an order, and never holds a key that can.** `RiskManager` is the only gate. Agents sit around the pipeline (research, ops reporting, event veto) and may only take risk-reducing actions (pause a strategy, trip the kill switch).
- **Rust (`rust_math/`) is kept and never deleted, but not extended.** New hot paths go in Python/numpy first.
- **ML forecasting and LLM enrichment are still wanted** — do not propose removing the adapters or stubs. They are gated: a model must beat the plain trend baseline out-of-sample (walk-forward) before it sizes a trade.
- **No strategy result is reported without out-of-sample evidence and a buy-and-hold benchmark.** An in-sample best-of-sweep is not an edge.

**Evaluating a strategy = the research CLI, never an in-sample sweep.** From `backend/`:
`python scripts/research.py strategies` and
`python scripts/research.py walk-forward <Strategy> --symbol BTCUSDT --grid '{"period":[50,100,150]}'`.
It prints JSON with `passes_bar` first (out-of-sample return/max-DD beats buy-and-hold, > 50 %
of folds profitable, OOS Sharpe ≥ 0.5 — defined once in `domain/backtest/walk_forward.passes_bar`).
Report that verdict and the out-of-sample numbers; never quote an in-sample best as evidence.
A new strategy's hypothesis and pass test go into `TODO.md` *before* its first run.
`scripts/grid_search_strategies.py` is the old in-sample sweep — superseded, don't use it.

Working-copy facts that trip up new sessions:

- **Work directly in the main checkout — no git worktrees** (user's call, 2026-11-15; `.claude/settings.json` sets `worktree.bgIsolation: none` so background sessions may edit main). Leave changes uncommitted for the user to commit.
- `TODO.md` and `CLAUDE.md` are git-tracked. The design/spec docs (`docs/*`) and `PROFITPILOT_PROJECT_INSTRUCTIONS.md` are still git-ignored.
- `backend/profitpilot.db` is the real dev DB. Query it read-only unless the user asks for a change; tests must run against in-memory SQLite (see `conftest.py`).

## Permissions

PowerShell (and Bash) commands that **run tests** — e.g. `pytest`, `vitest`, `cargo test`, `npm run test` — may be executed without asking for confirmation. All other shell commands that affect the filesystem, network, or shared state still require explicit user approval.

**NEVER commit.** Do not run `git commit`, `git push`, or any command that creates commits — not even when a task seems finished, and never ask to. The user handles all git commits themselves. Staging (`git add`) is likewise off-limits unless explicitly requested.

## Commands

### Always-on host (the old PC) — native Windows by default, no Docker (user's call, 2026-11-18)
```powershell
# Once, admin PowerShell: venv + frontend build + boot task "ProfitPilot" (runs deploy\windows\run.ps1)
powershell -ExecutionPolicy Bypass -File deploy\windows\install.ps1
# Update: git pull + packages + build + restart + health check (GitHub deploy calls it with -AppDir/-Source)
powershell -ExecutionPolicy Bypass -File deploy\windows\update.ps1
# Data/settings/logs live in C:\ProfitPilot (profitpilot.env, data\, backups\, logs\) — never in the repo
```
**Running bots must survive every update.** Their state is in the DB and the executor resumes it
on boot (`tests/integration/test_restart_continuity.py`). So: never rename a registered strategy
class or its parameter keys while instances may exist (add a new class/key instead); never write
a migration that drops or rewrites strategy, order or sim-ledger data without a data-preserving
path; and keep re-processing a bar idempotent (a repeated intent must stay a no-op).

Docker (`Dockerfile`, `docker/docker-compose.host.yml`) is kept as an alternative, selected in the
deploy workflow by repo variable `PROFITPILOT_DEPLOY=docker`. `docker/docker-compose.yml` starts
ONLY TimescaleDB + Redis (Phase 2 infra; nothing uses them yet). See README "Run it always-on".

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env        # fill in keys
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Tests
pytest tests/unit -v --cov=app           # unit tests only
pytest tests/integration -v              # integration tests (requires running API)
pytest tests/unit/test_sma_strategy.py  # single test file
pytest -k "test_golden_cross"           # single test by name

# Migrations — every ORM model change needs one, committed with it (read the generated file!)
alembic revision --autogenerate -m "description"
pytest tests/unit/test_migrations.py    # fails if a model changed without a migration
alembic upgrade head                    # the app also runs this on startup
```

### Frontend
```bash
cd frontend
npm install
npm run dev     # Vite dev server → http://localhost:5173
npm run build
npm run test                        # full suite (Vitest)
npm run test -- Backtests           # single file
```

### Rust math library
```bash
cd rust_math
cargo build --release   # generates PyO3 Python bindings
```

API docs: `http://localhost:8000/api/docs` · Frontend: `http://localhost:5173`

## Architecture

### Design principles (non-negotiable)

**SOLID and separation of concerns come first, on every change — not just new features.** This is the top architectural rule of the codebase; hold to it in all code you write or modify:

- **Single responsibility / separation of concerns** — each layer, class, and function does one job. Routers don't hold business logic, domain code doesn't touch the DB or FastAPI, repositories don't decide policy. If a change starts blurring a boundary, stop and refactor instead.
- **Single source of truth** — never hand-maintain the same list/mapping in multiple places. Derive it. Example: per-strategy config field names live only on the `ExecutionConfig` schema; `from_instance` and `_config_columns` derive their field set from `ExecutionConfig.model_fields`, and `test_execution_config_fields_map_to_orm_columns` fails if the schema and ORM model drift. Adding a config field = one column + one Pydantic field, nothing else.
- **Open/closed via adapters** — extend behavior by adding an adapter/strategy/registry entry, not by editing switch-statements in callers (see Non-negotiable abstractions below).
- **Dependency inversion** — depend on the base-class abstraction, inject concrete implementations. Strategies receive broker/model/LLM/risk as injected dependencies.

When a task can be done quickly the messy way or correctly the SOLID way, choose the SOLID way and note the trade-off.

### Layer responsibilities

| Layer | Location | Rule |
|-------|----------|------|
| Routers | `backend/app/api/routes/` | Parse input, call service, format output — no business logic |
| Services | `backend/app/services/` | Orchestration across domain components |
| Domain | `backend/app/domain/` | Pure business logic — no FastAPI, no DB calls |
| Repositories | `backend/app/repositories/` | DB access only — no business logic |
| ORM models | `backend/app/models/db/` | SQLAlchemy 2.0 async models |
| Schemas | `backend/app/models/schemas/` | Pydantic request/response models |

### Non-negotiable abstractions

Every order, model call, and broker operation must go through its adapter — never call SDKs directly:

- **`BrokerAdapter`** (`domain/broker/base.py`) — all Alpaca/Bybit/Binance SDK calls
- **`ForecastingModelAdapter`** (`domain/forecasting/base.py`) — all PyTorch/XGBoost/LightGBM calls
- **`RiskManager`** (`domain/risk/risk_manager.py`) — hard veto before every order reaches the broker; cannot be bypassed
- **`LLMEnrichmentAdapter`** (`domain/llm/base.py`) — always optional; strategies must work without it
- **`InstrumentCatalog`** (`domain/instruments/base.py`) — the only source of what a symbol *is*: per-broker symbol/category translation, tick size, lot step, min notional, spot vs perp. Never infer any of it from the symbol string (`"/" in symbol` and "USDT means linear" are the bugs this replaced). Adapters take the **interface**, injected — never the `INSTRUMENTS` singleton or `InstrumentRegistry` directly.

Strategies are stateless: broker, forecasting models, LLM enrichment, and risk config are injected dependencies.

### Signal pipeline

```
OHLCV/Ticks → Feature Engineer (Rust-accelerated) → ForecastingModelAdapter
                                                   → Quant Indicators
                                                   → LLMEnrichmentAdapter (optional)
                                                           ↓
                                                   StrategyOrchestrator
                                                           ↓
                                                   RiskManager.approve_order()
                                                           ↓
                                               BrokerAdapter.place_order()
```

### Database

Dev uses SQLite (`backend/profitpilot.db`) — the engine auto-detects `sqlite://` in `DATABASE_URL` and uses `StaticPool`. Prod uses TimescaleDB (PostgreSQL + hypertables). Key time-series tables: `signals`, `ohlcv`, `features`, `portfolio_snapshots`, `audit_log`. All DB access is async (SQLAlchemy 2.0).

### Phase 1 — local mode (no auth)

There is no authentication in Phase 1. A single local user is seeded at startup (`LOCAL_USER_ID = UUID("00000000-0000-0000-0000-000000000001")`). `get_current_user()` in `api/deps.py` always returns this user. All routes operate in single-user mode.

### Data provider

`domain/backtest/data_provider.py::fetch_ohlcv` tries **Yahoo Finance** first (stocks, ETFs, forex, crypto), then falls back to **Bybit public API** for crypto symbols. This is used by both the backtest engine and the live strategy executor.

### Strategy system

Built-in strategies live in `domain/strategy/examples/` — `sma_crossover.py` (SMA, RSI, MACD, Bollinger Bands) and `trend.py` (Donchian breakout, trend filter, RSI pullback in uptrend). A new built-in module is added to `_BUILTIN_MODULES` in `loader.py` — the one list everything (backtests, walk-forward, the live executor, the strategy list) loads from. Out-of-sample verdicts for every built-in are in `TODO.md` (🚦 Step 5b pipeline log). User-defined strategies go in `backend/user_strategies/*.py` — they are auto-loaded on import via `domain/strategy/loader.py`. Each file that uses `@StrategyRegistry.register` is registered automatically.

UI metadata (display name, description, parameter schema) for built-in strategies is stored in `_BUILTIN_META` in `loader.py`, not in the strategy classes. User strategies can expose a `STRATEGY_META` dict at module level.

### Strategy sandbox (Builder page)

`/api/v1/builder/run` executes user-supplied Python code in a subprocess with a 30-second timeout. The sandbox injects `StrategyBase`, `signal()`, `LONG/SHORT/CLOSE/NEUTRAL`, `math`, and `statistics`. All other imports are blocked. Results are piped via JSON on stdin/stdout.

`/api/v1/builder/generate` generates strategy code from a plain-English description using Claude. Requires `ANTHROPIC_API_KEY` in `.env`.

**Never pin a Claude model id in this file or at a call site.** Model names change far faster than the docs do, and a stale id fails at request time. The id lives in exactly one place — `ANTHROPIC_MODEL` in `core/config.py` — and is overridable via env.

### WebSocket

Single endpoint at `/ws`. Clients auto-subscribe to `portfolio.snapshot` (pushed every 15s) and `strategy.status`. Supported message types: `subscribe`, `unsubscribe`, `ping`. Broker broadcasts `strategy.signal` when the executor generates signals.

### Strategy executor

`services/strategy_executor.py::executor` is a module-level singleton started in the app lifespan. It spawns one asyncio task per active strategy (status `paper` or `live`), polls market data on the strategy's timeframe, and persists signals to the `signal_records` table. Calling `executor.notify_status_change()` starts/stops individual tasks when status changes via the API.

### Frontend

React 18 + TypeScript (strict), Vite, React Router v6. Pages:

| Route | Page | Notes |
|-------|------|-------|
| `/` | Landing | Marketing / entry point |
| `/dashboard` | Dashboard | Portfolio overview, live P&L, active strategies |
| `/trade` | Trade | Manual trading chart with indicators |
| `/portfolio` | Portfolio | Positions, broker accounts (dir is `pages/Portafolio/`) |
| `/backtests` | Backtests | Run backtests, view equity curve + trades, DCA compare, Monte Carlo |
| `/strategies` | Strategies | Create/manage strategy instances |
| `/strategies/:id` | StrategyDetail | Live chart with fill markers + order history |
| `/builder` | Builder | Monaco code editor + AI generation + sandbox backtest |
| `/settings` | Settings | Language switcher, risk defaults |

State: Zustand stores in `src/stores/` (portfolio, strategy, ui, websocket). Server state: TanStack Query v5. Charts: **Recharts** for equity curves/drawdown; TradingView Lightweight Charts for price/candlesticks. i18n: `react-i18next` with English (`en`) and Spanish (`es`) locales in `src/i18n/locales/`.

### Tech stack summary

- **Backend**: FastAPI 0.115 + Pydantic v2, SQLAlchemy 2.0 async, structlog
- **ML**: PyTorch 2.4, XGBoost 2.1, LightGBM 4.5, Darts 0.30, NeuralProphet
- **Frontend**: React 18 + TypeScript (strict), Vite, Zustand, TanStack Query v5, shadcn/ui + Tailwind, Recharts, react-i18next
- **Rust**: PyO3 bindings — technical indicators, statistics, Monte Carlo (called from Python)

## Risk defaults (RiskConfig)

Max position size 2% of portfolio · Max 5 open positions · Daily drawdown limit 3% · Total drawdown limit 10% · Mandatory stop-loss 1.5% · Max 10 orders/minute. Enforced by `RiskManager`, configurable via `.env`.

## Adding strategies / brokers / models

**New strategy:**
1. Create `backend/app/domain/strategy/examples/your_strategy.py` (built-in) or `backend/user_strategies/your_strategy.py` (user-defined)
2. Inherit from `StrategyBase`, decorate with `@StrategyRegistry.register`
3. Implement: `generate_signals()`, `on_tick()`, `on_fill()`, `get_required_symbols()`, `validate_parameters()`
4. For built-ins, add UI metadata to `_BUILTIN_META` in `loader.py`

**New broker:**
1. Create `backend/app/domain/broker/adapters/your_broker_adapter.py`
2. Inherit from `BrokerAdapter`, implement the full interface
3. Register: `BrokerRegistry.register(YourBrokerAdapter(...))`

**New forecasting model:**
1. Create `backend/app/domain/forecasting/adapters/your_model_adapter.py`
2. Inherit from `ForecastingModelAdapter`
3. Implement: `predict()`, `train()`, `evaluate()`, `load()`, `save()`
4. Register: `ForecastingModelRegistry.register(YourModelAdapter(...))`

## Key files

- `backend/app/core/config.py` — Pydantic Settings; all secrets via env vars
- `backend/app/core/enums.py` — shared enums (MarketType, Direction, OrderStatus, etc.)
- `backend/app/core/types.py` — shared Pydantic types (OHLCV, Signal, Order, Fill, Position, etc.)
- `backend/app/api/deps.py` — FastAPI dependency injection; defines `LOCAL_USER_ID`
- `backend/app/db/base.py` — async SQLAlchemy engine + session factory
- `backend/app/domain/strategy/loader.py` — strategy registry + `_BUILTIN_META` for UI metadata
- `backend/app/domain/instruments/` — `base.py` (the `InstrumentCatalog` interface callers depend on), `instrument.py` (model + `conform_order`), `registry.py`, `seed.py` (shipped instruments). Add a symbol here, nowhere else.
- `backend/app/services/strategy_executor.py` — live strategy loop singleton
- `backend/app/services/strategy_sandbox.py` — subprocess sandbox for Builder page
- `backend/.env.example` — environment variable template
- `docker-compose.yml` — full dev stack definition
- `frontend/src/types/index.ts` — TypeScript types mirroring backend schemas
- `PROFITPILOT_PROJECT_INSTRUCTIONS.md` — detailed project guidelines and decisions

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
