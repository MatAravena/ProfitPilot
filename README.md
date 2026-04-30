# ProfitPilot

Algorithmic trading platform combining quantitative strategies, ML forecasting models, and automated broker execution.

---

## Project Structure

```
profitpilot/
│
├── backend/                          # FastAPI Python backend
│   ├── app/
│   │   ├── main.py                   # FastAPI app factory + lifespan
│   │   ├── core/
│   │   │   ├── config.py             # pydantic-settings environment config
│   │   │   ├── enums.py              # shared enums (MarketType, Direction, etc.)
│   │   │   └── types.py              # shared Pydantic value objects
│   │   │
│   │   ├── domain/                   # pure business logic — no FastAPI here
│   │   │   ├── strategy/
│   │   │   │   └── base.py           # StrategyBase abstract + StrategyRegistry
│   │   │   │
│   │   │   ├── forecasting/
│   │   │   │   ├── base.py           # ForecastingModelAdapter abstract + Registry
│   │   │   │   └── adapters/
│   │   │   │       ├── xgboost_adapter.py    # XGBoost implementation
│   │   │   │       └── lstm_adapter.py       # PyTorch LSTM implementation
│   │   │   │
│   │   │   ├── broker/
│   │   │   │   ├── base.py           # BrokerAdapter abstract + BrokerRegistry
│   │   │   │   └── adapters/
│   │   │   │       └── alpaca_adapter.py     # Alpaca implementation
│   │   │   │
│   │   │   ├── risk/
│   │   │   │   └── risk_manager.py   # RiskManager — hard veto layer
│   │   │   │
│   │   │   └── llm/
│   │   │       └── base.py           # LLMEnrichmentAdapter (optional layer)
│   │   │
│   │   ├── api/
│   │   │   └── routes/               # FastAPI routers (one per domain)
│   │   │       ├── strategies.py
│   │   │       ├── brokers.py
│   │   │       ├── forecasting.py
│   │   │       ├── backtests.py
│   │   │       ├── signals.py
│   │   │       ├── portfolio.py
│   │   │       └── health.py
│   │   │
│   │   ├── models/
│   │   │   ├── db/                   # SQLAlchemy ORM models
│   │   │   └── schemas/              # Pydantic request/response schemas
│   │   │
│   │   ├── repositories/             # DB access layer (repository pattern)
│   │   ├── services/                 # Application services (orchestration)
│   │   ├── workers/                  # Celery tasks (training, backtests)
│   │   └── websockets/               # WebSocket handlers (live P&L, signals)
│   │
│   ├── migrations/                   # Alembic migrations
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
│
├── rust_math/                        # Rust computation library (PyO3)
│   ├── src/lib.rs                    # Indicators, statistics, Monte Carlo
│   └── Cargo.toml
│
├── frontend/                         # React + TypeScript frontend
│   └── src/
│       ├── components/
│       │   ├── ui/                   # shadcn/ui generated
│       │   ├── strategy/
│       │   ├── model/                # forecasting model components
│       │   ├── portfolio/
│       │   ├── broker/
│       │   └── backtest/
│       ├── pages/
│       ├── stores/                   # Zustand
│       ├── services/                 # React Query API calls
│       ├── hooks/
│       ├── types/                    # Generated from FastAPI OpenAPI schema
│       └── utils/
│
├── docker-compose.yml
└── README.md
```

---

## Quick Start

```bash
# 1. Clone and enter
git clone ... && cd profitpilot

# 2. Copy env and fill in your broker API keys
cp backend/.env.example backend/.env

# 3. Start all services
docker compose up -d

# 4. API docs
open http://localhost:8000/api/docs

# 5. Frontend
open http://localhost:5173
```

---

## Key Architectural Rules

1. **All broker calls go through `BrokerAdapter`** — never call Alpaca/Bybit/Binance directly
2. **All forecasting model calls go through `ForecastingModelAdapter`** — never call PyTorch/XGBoost directly from strategy code
3. **All orders pass through `RiskManager`** before reaching any broker — this cannot be bypassed
4. **LLM enrichment is always Optional** — strategies must work without it
5. **Everything is abstract** — swap any component without touching anything else

---

## Adding a New Forecasting Model

1. Create `backend/app/domain/forecasting/adapters/your_model_adapter.py`
2. Inherit from `ForecastingModelAdapter`
3. Implement: `predict()`, `train()`, `evaluate()`, `load()`, `save()`
4. Register: `ForecastingModelRegistry.register(YourModelAdapter(...))`

## Adding a New Broker

1. Create `backend/app/domain/broker/adapters/your_broker_adapter.py`
2. Inherit from `BrokerAdapter`
3. Implement: `place_order()`, `cancel_order()`, `get_positions()`, `get_account()`, `stream_ticks()`, `connect()`, `disconnect()`, `health_check()`
4. Register: `BrokerRegistry.register(YourBrokerAdapter(...))`

## Adding a New Strategy

1. Create `backend/app/domain/strategy/strategies/your_strategy.py`
2. Inherit from `StrategyBase`
3. Implement: `generate_signals()`, `on_tick()`, `on_fill()`, `get_required_symbols()`, `validate_parameters()`
4. Decorate: `@StrategyRegistry.register`
