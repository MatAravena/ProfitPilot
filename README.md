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
- **Strategy Builder (sandbox)** — Monaco code editor + subprocess sandbox backtest, all in the browser. Write a strategy by hand and backtest it immediately, no Claude involved. _The "generate from plain English via Claude" button is deferred — see Phase 3 below; user-facing Claude usage isn't part of the roadmap until well past the current SaaS phase_
- **Live/paper trade pipeline** — one executor loop per active strategy runs the full chain: `signal → position sizing → RiskManager veto → broker → fill → persistence`. Paper trading uses a built-in `SimulatedBrokerAdapter` with a durable virtual ledger (zero broker setup) that charges the **same commission + slippage as the backtest**, and shares the backtest's exact intent→action logic (open / close / full reversal); live uses a real broker connection. Signals and every order attempt are persisted; orders broadcast over WebSocket. The full paper lifecycle is covered by an **end-to-end test** (see How It Works below)
- **Risk profile + per-strategy overrides** — a per-user risk profile (SL/TP, drawdown limits, max positions, order rate, kill switch) sets the defaults, edited in Settings; each strategy carries behavioral config (position size, `allow_short`, poll) plus **optional risk overrides** (blank = inherit the profile). Editing a strategy's config restarts only that bot (live-adapts); changing the profile only refreshes form defaults, never running bots. Backtests take arrangeable SL/TP **and position size %** per run (position size defaults to the live 2%, so backtest ≈ live)
- **Loop-managed stops + new-bar gating** — stop-loss / take-profit are checked every poll and never blocked by the risk veto; signals regenerate only once per closed bar
- **Restart-safe** — positions, peak equity, open-position count, and today's realized P&L are rehydrated from persisted state on boot
- **Broker adapters** — Alpaca, Bybit, Binance (through a common `BrokerAdapter`). Live path is covered by integration tests with a fake adapter; a Bybit **testnet** smoke-test runbook is in `docs/runbooks/testnet-smoke-test.md`
- **Canonical instrument registry** — one source of truth for what a symbol *is*: per-broker symbol translation (`BTCUSDT` → `BTC/USD` at Alpaca), product category (Bybit spot vs linear), tick size, lot step, min notional, spot vs perp. Alpaca and Bybit resolve symbols through it instead of guessing from the symbol string, which fixed two real routing bugs. **Order conformance is live** — `ExecutionEngine` rounds every order to the instrument's tick/lot grid before it reaches `RiskManager` or the broker; opens below the exchange minimum are rejected, closes always execute
- **WebSocket** — real-time portfolio snapshots every 15s, strategy status, signal events
- **OHLCV caching** — cache-aside pattern; bars stored in SQLite, fetched from Yahoo Finance / Bybit with pagination
- **Frontend** — Landing, Dashboard, Trade, Portfolio, Backtests, Strategies (+ detail), Builder, Settings
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
- **Verified end-to-end**: an integration test drives the real executor through a full paper
  lifecycle (entry → reversal → close) and asserts the exact data the strategy page consumes — the
  `/strategies/{id}/orders` and `/signals` responses plus the `strategy.order` / `strategy.signal`
  WebSocket stream — so the whole chain (create → poll → risk → simulated fill with costs → persist →
  broadcast → read back) is known to work, not just assumed.

_Could be improved:_ "live data" is currently **repeated polling** of recent bars, not a true tick
stream (`stream_ticks()` is unimplemented); live broker fill-confirmation (real fill price/commission)
is reconciled on the next poll rather than captured immediately. The one remaining intentional
backtest↔live difference is fill *timing* (backtest fills next-bar open, live fills at the just-closed
bar) — negligible for 24/7 crypto, and the honest choice for daily bars.

### Monte Carlo — is the result edge or luck?

A single backtest is one path through history — one *ordering* of one *sample* of trades. From the
**Backtests** page you can opt into a Monte Carlo run (`POST /api/v1/backtests/montecarlo`) that
re-runs the backtest and then resamples its realized trade sequence into a distribution of outcomes:

- **Bootstrap** (sampling risk) draws trades *with replacement* — "were these results luck?"
- **Shuffle** (ordering risk) permutes the same trades — final equity is order-invariant, but the
  drawdown *path* is not, so this isolates "was my drawdown just a lucky order?"

Both resample the **fixed-fractional per-trade return series** (`r_i = pnl_i / equity_before_trade_i`),
which matches this platform's fixed-% sizing — compounding the trades in their original order
reproduces the realized final equity, so the resampling is self-consistent. The panel reports
percentiles of total return and max-drawdown, probability of profit, and risk of ruin, with the
realized single-path result drawn as a reference line. It's pure vectorized numpy (no persistence);
5k simulations run in well under a second.

### DCA vs halving-cycle grid — does timing beat dollar-cost averaging?

> **In plain English (read this first).**
> We tested **7 ways to buy Bitcoin with $100/week** over BTC's whole history to answer one question:
> *can a bot that buys **and sells** beat simply buying every week and holding (DCA)?*
>
> - **Just buying every week and never selling (DCA) is really hard to beat** on an asset that mostly
>   goes up — any time your money sits in cash, it misses the rise.
> - **Selling near the top to buy back cheaper only works if you buy back at the right time** — deep
>   in the crash. Our naive first try sold at the wrong moments and lost badly (−42%).
> - **The winner, "Cycle sell-top redeploy (manual)":** near a cycle top it sells most of the stack,
>   waits, then buys back **gradually as price falls into the second half of the crash** (it doesn't
>   try to nail the exact bottom). Over full history it ended with **~13% more Bitcoin than DCA** (more
>   on shorter windows), *and* it banks cash profit along the way.
> - **Big asterisk:** the manual arm partly "knows" how big past crashes were and when tops happened —
>   that's hindsight. The honest version, **"Cycle sell-top redeploy (auto)"**, only learns from the *past* and does
>   much less well (roughly break-even to a few percent). So treat the edge as **"probably small and
>   uncertain, plus some cash income,"** not free money.
> - **Bottom line for a real bot:** expect a **smoother ride and some realized income**, not a
>   guaranteed way to out-stack buy-and-hold. Everything below is the detailed version.

A separate opt-in tool on the Backtests page (`POST /api/v1/backtests/dca-compare`) runs seven
accumulation strategies over the same BTC history and reports them side by side.

**Arm names describe their *mechanics*, so it's clear what each edge actually is** (renamed 2026-08-01):
`cycle_*` = timing is driven by the **halving-cycle thesis** (overfit-prone — only ~3 completed cycles);
`dca_*` / `dip_*` = plain accumulation mechanics with **no halving input**. Crucially, **none of these
is a fixed-capital rebalancer** — they are all fed by contributions (or a lump sum spread over time),
so the classic "rebalancing bonus" (Shannon's demon) is *not* what drives them. That framing is tested
separately in `scratchpad/run_rebalance_harvest.py` (see the rebalancing note below).

Shared clock for every `cycle_*` arm: halvings are deterministic (~every 1458 days), so "days since
halving" is only-past. The heuristic places a cycle **top ~535 days after a halving** and a **bottom
~380 days after that**.

**Two ways to turn cycle position into behavior** (`cycle.timing_mode`, switchable in the UI):

| Mode | What it does | When you want it |
|---|---|---|
| `gaussian` *(default)* | Buy/sell intensity are **bell curves** around the predicted top/bottom (`sigma_top` / `sigma_bottom` set their width). Always doing a little of everything; intensity fades in and out. | Smooth, forgiving if your date estimate is off by weeks. |
| `windows` | **Hard calendar windows**: nothing before the start day, full intensity from the start day through the end day, nothing after — the literal *"start selling on day 445 after the halving, start buying on day 795"*. Day offsets are tunable per side; leave one blank to derive it from the Gaussian params. `ramp_days` optionally eases the edges *inside* the window, so "zero before day A" always holds exactly. | You have a specific view on **when** the halving supply shock plays out and want the strategy to obey it literally. |

Both are `CycleTiming` implementations (`domain/backtest/halving_cycle.py`); `build_timing()` is the
only place that switches on the mode, so every arm consumes the abstraction and none of them knows
which clock it's running on.

| Arm (key) | How it works | What it *is* |
|---|---|---|
| `dca_flat` | Deploy a fixed amount every period. | **Benchmark.** No timing, no edge claim. |
| `dca_dip_weighted_cycle` | Buy-only; deploy scaled by halving-cycle intensity × how far price sits below its running high (buys more near predicted bottoms / deeper dips). Idle cash saved as **dry powder**. | Accumulation **+ halving-cycle timing bet** (buy side). |
| `cycle_buydip_selltop` | Above, plus *distributes* (sells to cash) into the predicted-top window and redeploys into the next bottom. | Cycle timing, **both sides**. |
| `cycle_ath_trim_rebuy` | ATH-aware **state machine**: trim into the top (keep a ~70% core) → ~3-month cooldown after the top confirms → accumulate the decline until price recovers near the prior ATH. Halving windows say *when*; EMA(50)/SMA(200), Supertrend, and an ATR-percentile gate must *confirm*. Pure-Python, look-ahead-free. | Cycle timing **+ technical confirmation.** Lowest drawdown historically. |
| `dip_deploy_trim` | Hold a cash reserve, deploy it *disproportionately into drawdowns* (deeper dip → more coins/$), never fully exit (ratcheting core floor), take only light trend-gated profit trims near local highs. **No halving input.** | **Pure dip-buying mechanics** — the only non-cycle arm. Edge is on the *buy* side. |
| `cycle_selltop_redeploy_manual` | Sell most of the stack (`sell_fraction_at_ath`, up to ~100%) near a **confirmed** ATH (weighted by halving intensity), then deploy the war chest **across the lower half of the drawdown** (`buy_target = ATH×(1−expected_bear_drop)`), scaling in so it needn't nail the bottom. **You set** the drop. | Cycle timing, **in-sample / optimistic** (assumes the drop). |
| `cycle_selltop_redeploy_auto` | Same engine, but `expected_bear_drop` is **derived from past drawdowns** (only-past) minus a `caution_margin` — deploys a little shallower than the worst case, ~guaranteed a fill while still buying cheap. | Cycle timing, **honest out-of-sample proxy** for the manual arm. |

It's a deliberately separate simulator from the signal-based `BacktestEngine` (accumulation is
multi-buy, not single-position), and it inherits the same commission + slippage cost model.

**Every strategy's knobs are tunable via the request body** (`cycle`, `hunter`, `rotation` blocks on
`POST /dca-compare`) — e.g. `{"rotation": {"sell_fraction_at_ath": 1.0, "expected_bear_drop": 0.65}}`
or `{"hunter": {"sell_cap_frac": 1.0}}` — so you can experiment without code changes. Indicators
(EMA/SMA/ATR/Supertrend, ATR-percentile) live in `domain/backtest/indicators.py`; cycle-drawdown stats
in `domain/backtest/cycle_stats.py`; all pure-Python and look-ahead-free.

**OHLCV is cached in the DB.** The compare path persists fetched bars to the `ohlcv` table and, on
repeat runs, serves from the DB and fetches only the missing recent tail from Yahoo/Bybit (chunked
inserts ≤112 rows for the SQLite bind-var limit; best-effort — a DB error degrades to a plain fetch).

The `AccumulationLedger` uses **moving-average cost basis**: a sell removes cost from the pool at the
running average, so `realized_pnl` (gain on units actually sold) and `avg_cost_basis` (basis of the
units still held) stay correct across repeated buy/sell rotation. (An earlier lifetime-average version
never reduced the cost pool on sells, which wildly inflated `realized_pnl` for any selling arm.)

**What the runs show ($100/week, costs included).** Two contexts: full 1d history (2014→now, Yahoo)
and a matched 2020-03→now window on 1d vs 4h (the only range with 4h data — Bybit perp inception,
starting at the COVID bottom). Final value **vs flat DCA**:

| Strategy | 1d full (2014+) | 1d (2020+) | 4h (2020+) |
|---|--:|--:|--:|
| dca_flat | — | — | — |
| dca_dip_weighted_cycle | −1.6% | −3.5% | −0.9% |
| cycle_buydip_selltop | −41.7% | +17.6% | −10.3% |
| cycle_ath_trim_rebuy | +6.1% | 0.0% | +23.8% |
| dip_deploy_trim | −5.9% | −1.1% | −1.9% |
| **cycle_selltop_redeploy_manual** | **+13.2%** | **+32.7%** | **+15.4%** |
| cycle_selltop_redeploy_auto | −11.8% | +5.4% | +2.7% |

(4h figures use **timeframe-normalized** per-bar rates — the `*_daily` deploy/sell rates are divided by
bars-per-day, so a strategy behaves the same per *calendar day* on 1d and 4h instead of firing 6× as
often on 4h. This removed the earlier 4h inflation; `cycle_selltop_redeploy_manual` on 4h went from a
misleading +46.5% to a comparable +15.4%.)

**The thesis holds when the bottom-buying is done right.** `cycle_selltop_redeploy_manual` — sell ~70%
near a confirmed top, then deploy the war chest across the *lower half* of the drawdown — beats DCA on
every timeframe, on **coins and value** (full-1d: 44.6 vs 39.4 BTC). The earlier `cycle_buydip_selltop`
lost badly because it sold on local highs and dribbled the cash back in; concentrating the rebuy in the
deep-dip zone is what turns "sell high / buy low" into net accumulation.

**But read the manual arm as optimistic/in-sample.** It *assumes* the ~70% drop (hindsight) and sells at
halving-*predicted* tops fitted to the 3 historical tops. The **auto** arm is the honest check — it
learns the drop cautiously from only-past drawdowns — and it earns a far smaller, sometimes negative
edge (+4–5% recent, −12% full-history, where early cycles give it nothing to learn from). So the
durable read is: **a small, uncertain edge plus realized cash income and, for cycle_ath_trim_rebuy, lower
drawdown** — not a reliable +40%. One caveat stays attached: only ~3 completed cycles (fitting risk).
(The earlier 4h-inflation caveat is now fixed — per-bar rates are normalized by bars-per-day, so 1d
and 4h are directly comparable.)

**Honesty caveat (shown in the tool):** only ~3 completed halving cycles exist, so the offsets are fit
to past tops/bottoms — these backtests are *one live out-of-sample cycle, not proof*. All offsets are
tunable parameters. Making any cycle strategy live-deployable is a deliberate follow-up, gated on the
comparison showing a robust edge.

**Do grids shine on *ranging* assets? (tested — surprising answer: no.)** Grid trading is supposed to
beat buy-and-hold on sideways markets by harvesting volatility, so we tested `dip_deploy_trim` (default
and a ranging-tuned config — small `profit_step`, `use_trend_filter=False`) vs DCA across trending
assets (BTC, SPY, gold) and range-bound ones (EUR/USD, GBP/USD), plus a synthetic high-volatility sine.
**No grid config beat DCA — not even an aggressive symmetric grid on a perfect zero-cost sine (−13.5%).**
The reason is structural and elegant: **DCA is *itself* a volatility harvester** — buying a fixed $
every week automatically buys more units when price is low (∑ 100/price is maximized by volatility), so
DCA already gets a low average cost on a ranging asset, and a grid's *selling* just hands units back.
The classic grid/"rebalancing bonus" (Shannon's demon) applies to **fixed-capital rebalancing**, not
dollar-cost *contributions*; real trading costs only widen the gap. (One real improvement did come out
of this: `AccumulatorGridParams.use_trend_filter` — turn the 200-SMA "only trim in an uptrend" gate off
for assets with no trend to respect.)

**Fixed-capital rebalancing — the framing where the harvest bonus *does* exist (tested).** The arms
above are all *contribution*-fed, so none of them can show the classic rebalancing bonus. The honest
test is a **fixed pot** split between BTC and cash, rebalanced back toward a target weight
(`scratchpad/run_rebalance_harvest.py`, $10k lump sum, full 2014→now BTC history). What it shows:

| Strategy | Final $ | CAGR | Vol | Max DD | Sharpe |
|---|--:|--:|--:|--:|--:|
| buy_and_hold (100% BTC) | $1.37M | 51.3% | 66% | 83% | 0.96 |
| static 50/50 (never rebalanced) | $688k | 42.8% | 59% | 82% | 0.90 |
| rebal 50/50 (band 10%) | $261k | 31.6% | 34% | 57% | 0.98 |
| **rebal cycle-timed (halving)** | **$372k** | **35.6%** | 42% | 62% | 0.93 |
| rebal 25/75 (band 10%) | $71k | 18.0% | 17% | 30% | 1.07 |

- **The Shannon's-demon bonus is real but small.** Measured the textbook way — rebalanced CAGR minus
  the constant-mix baseline `w·G(BTC)` — the harvest is **+4 to +5pp** at every weight (e.g. 50/50: 30.1%
  vs 25.6%). So volatility *is* being harvested.
- **…but it can't beat holding a hard-trending asset.** Every rebalancer badly trails buy-and-hold *and*
  the drifted static split, because trimming BTC back to target keeps selling the best compounding asset
  for 0%-yield cash. The harvest shows up as **risk reduction** (vol 66%→34%, max DD 83%→57%, Sharpe up),
  **not** excess return.
- **Costs barely move it** (zero-cost ≈ with-cost): the underperformance is *structural* (trend drag),
  not fees — so it's not a "lower the commissions and it wins" situation.
- **Halving timing helps *within* the rebalancing family:** the cycle-timed target (hold ~90% BTC near
  predicted bottoms, trim toward ~10% into predicted tops) is the best-returning rebalancer (−7pp vs
  static, ~+4pp over dumb 50/50) because it stays heavy through the bull — but it still doesn't beat hold.

**Takeaway (what is vs what is not):** fixed-capital rebalancing is a **smooth-the-ride tool, not a
beat-the-market one**, on an asset that trends as hard as BTC — the same structural reason DCA already
beats grids above. It would earn its keep on a genuinely mean-reverting / range-bound book, or across
*two* volatile uncorrelated assets (not asset-vs-cash). Not wired into the app — it's a research spike.

**Live parameter tuning (done).** The Backtests page now has a collapsible **Tune parameters** form
(`DcaCompareControls`) that drives the `cycle` / `hunter` / `rotation` request blocks — every arm's
knobs are editable from the UI, no code changes needed. It ships **named presets** (Default / Keep core /
Sell everything at top / Aggressive dip buyer), a **Reset to defaults**, and **localStorage persistence**
so an experiment survives a refresh. Field bounds/steps and defaults live in one place
(`frontend/src/lib/dcaCompareParams.ts`, mirroring the backend `Field(...)` constraints); an untouched
run reproduces the built-in defaults exactly. English + Spanish.

**Discrete halving windows (done).** The **Timing mode** selector in that form switches the cycle clock
from Gaussian curves to hard day-windows (see the table above); the day-offset fields appear only in
`windows` mode, and the **Halving windows** preset loads a ready set (sell 445–625, buy 795–1035 days
after the halving). Measured on full BTC daily history (2014-09-17 → 2026-08-04, $100/week, costs on):

| Arm | Gaussian | Windows (445–625 / 795–1035) | Windows tight (490–580 / 855–975) |
|---|---|---|---|
| `cycle_buydip_selltop` — final value | $1.47M | $1.74M | **$2.10M** |
| `cycle_buydip_selltop` — BTC accumulated | 22.93 | 27.12 | **32.65** |
| `cycle_selltop_redeploy_manual` — final value | $2.87M | $2.17M | **$3.23M** |
| `cycle_selltop_redeploy_manual` — BTC accumulated | 44.61 | 33.78 | **50.20** |

Tight windows win on this data (+42% and +13% coins vs Gaussian) — **and that is exactly what
overfitting looks like.** Narrowing a window around tops you already know is free in-sample and
expensive out-of-sample; the broad window is *worse* than Gaussian for the redeploy arm, which is the
tell that the ranking is unstable. Treat the mode as "make the strategy obey my thesis", not as
evidence the thesis is right. Spike: `scratchpad/run_window_timing_compare.py`.

**Still improvable (backlog).** Open ideas: model the observed correlation between each cycle's
ATH-gain and its drawdown more richly (the `auto` arm currently uses only the shallowest past drop);
adapt `expected_bear_drop`/sell-fraction per cycle as BTC matures and bears get shallower; and test the
fixed-capital rebalancer across **two volatile assets** (BTC/ETH or BTC/gold) where the harvest can
actually out-earn holding. Contributions welcome.

### What this means for you (user side)

- A good backtest is **necessary, not sufficient.** Keep `slippage_pct`, commission, and
  `position_size_pct` realistic for your asset — a strategy that only works at zero cost is fragile.
- **Validate out-of-sample.** One great backtest can be luck or overfitting; test on data you didn't
  tune on — and run **Monte Carlo** to see how much of the result survives resampling the trades.
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
| AI generation | Anthropic Claude API (model id in `ANTHROPIC_MODEL`, never pinned in docs) |

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
- `InstrumentCatalog` — the only source of what a symbol *is*

**`InstrumentCatalog` (`domain/instruments/base.py`)** deserves a note, because it replaced two
live bugs. It owns per-broker symbol translation (`BTCUSDT` → `BTC/USD` at Alpaca), product
category (Bybit spot vs linear), tick size, lot step, min notional, multiplier, and spot-vs-perp.
**Never infer any of that from the symbol string.** Bybit spells spot and perp identically
(`BTCUSDT`), so the string cannot answer which product an order is for — the catalog can, because
they are separate instruments (`BTCUSDT` vs `BTCUSDT.P`). Before this existed, Bybit's resolver
always answered `"linear"` and sent every spot order to the perpetual, and Alpaca decided market
type with `"/" in symbol`, which calls the canonical `BTCUSDT` a stock.

Callers depend on the **interface**, injected — never on `InstrumentRegistry` and never on the
`INSTRUMENTS` singleton:

```python
adapter = BybitAdapter(api_key=..., secret_key=..., instruments=my_catalog)
```

That is what lets the hand-written seed be swapped for a broker-refreshed or DB-backed catalog
without touching a single adapter, and lets tests inject three symbols instead of the full seed.
Building a catalog (`register`) is deliberately *not* on the interface: consumers read, they do
not mutate. Add a new tradable symbol in `domain/instruments/seed.py` — nowhere else.

### Strategy families (planned architecture)

Different kinds of strategy need genuinely different execution semantics, and the codebase has
already hit that wall twice: `BacktestEngine` is single-position and flip-based, so the
halving-cycle DCA work needed its own simulator in `domain/backtest/accumulation.py`. A grid bot
needs a third — per-rung lot inventory with intrabar fills, which neither existing path can
express honestly. Left alone this becomes a pattern of accidents, so the direction is one module
per **family** under `domain/strategies/`, behind shared abstractions:

| Contract | Owns |
|---|---|
| `StrategyFamily` | Identity, param schema, factory — the single source of truth for a family's knobs |
| `Ledger` | Position/inventory accounting: single-position, blended cost basis, or per-rung lots |
| `SimulationEngine` | Execution semantics a family needs: flip-based, multi-level accumulation, multi-leg |
| `CostModel` | Fees/slippage, shared so a new consumer can't quietly diverge |
| `FamilyMetrics` | Standard metrics from `metrics.py`, plus family-specific ones without forking it |

**A family depends only on these abstractions — never on another family, never on a concrete
engine.** Adding one must not edit any existing family, any router, or any page, the same
open/closed rule the broker and model adapters already follow. On the frontend that means
schema-derived param forms (extending the pattern `lib/dcaCompareParams.ts` already proves) and a
results-panel contract, with the family list fetched from the backend registry so the two stacks
can't drift.

Planned: `grid` (designed in full) · `arbitrage` · `scalping` · `swing` · `accumulation` (exists) ·
`trend` / `mean-reversion` (exist as built-in strategies, would be re-homed).

Status: **not built.** The contracts come first, then the two existing families get retrofitted
onto them with no behaviour change — so the abstractions are validated by two real users before a
third is written against them.

### Frontend pages

| Route | Page | Notes |
|---|---|---|
| `/` | Landing | Entry point |
| `/dashboard` | Dashboard | Portfolio overview, live P&L, active strategies |
| `/trade` | Trade | Manual trading chart with indicators |
| `/portfolio` | Portfolio | Positions, broker accounts, order history |
| `/backtests` | Backtests | Run backtests, equity curve, trade chart, DCA compare, Monte Carlo |
| `/strategies` | Strategies | Create / manage strategy instances |
| `/strategies/:id` | StrategyDetail | Live chart with fill markers + order history |
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
│   │   │   ├── instruments/      # InstrumentCatalog interface, registry, seed, conform_order
│   │   │   ├── market_data/      # Yahoo Finance provider
│   │   │   ├── risk/             # RiskManager
│   │   │   ├── strategies/       # PLANNED — one module per strategy family (grid, arbitrage, …)
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
│   │   ├── i18n/locales/         # i18n strings (en, es)
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
ANTHROPIC_API_KEY=...        # Builder "generate" button only — deferred to Phase 3, not needed yet
#ANTHROPIC_MODEL=...         # optional — pin/upgrade the model. Defaults in config.py.
                             # Leave commented: an empty value overrides the default with "".
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

Take the instrument catalog by injection and resolve symbols through it — never parse the symbol
string yourself:

```python
def __init__(self, ..., instruments: InstrumentCatalog = INSTRUMENTS):
    self._instruments = instruments
```

---

## Adding Instruments

Add the symbol to `backend/app/domain/instruments/seed.py` — **one place, nowhere else**. Every
adapter, and eventually the order path, picks it up automatically:

```python
_CRYPTO_SPOT = {
    "TIA": (0.001, 0.01),   # base → (tick_size, lot_step)
}
```

Specs are conservative seed values in the shape each venue publishes (Binance `exchangeInfo`,
Bybit `instruments-info`, Alpaca `assets`). Crypto pairs default to **spot**; perpetuals are
separate instruments with an explicit `.P` suffix, because `BTCUSDT` spot and `BTCUSDT` perp are
two different things to own even though every venue spells them the same.

An unseeded symbol makes adapters log a warning and fall back rather than raise — an unknown
symbol must not break an in-flight order — so watch for `*.symbol.unresolved` /
`*.category.unresolved` in the logs. On the order path proper, unknown symbols fail loud by
design: guessing a tick size is how orders get routed to the wrong product.

---

## Roadmap

### Phase 1 — Local (current)

- [x] FastAPI backend with layered architecture
- [x] Strategy engine with built-in strategies + user-defined auto-loading
- [x] Backtesting — equity curve, trade chart, performance metrics
- [x] Monte Carlo robustness — resample a backtest's trade sequence (bootstrap + shuffle) into a distribution of outcomes; separates edge from luck
- [x] DCA vs halving-cycle-grid comparison — 7 arms (dca_flat, dca_dip_weighted_cycle, cycle_buydip_selltop, cycle_ath_trim_rebuy, dip_deploy_trim, cycle_selltop_redeploy_manual, cycle_selltop_redeploy_auto) over the same BTC history; per-strategy params tunable via the request body; OHLCV cached in the DB (incremental tail fetch); reports final value, drawdown/Sharpe/Calmar, avg cost basis side by side (research tool; not live-deployable yet). Finding: cycle_selltop_redeploy_manual (sell high / buy the lower half of the drop) beats DCA on coins+value in-sample, but the honest auto-derived arm shows the durable edge is small/uncertain + realized income
- [x] Yahoo Finance + Bybit data providers with OHLCV caching
- [x] Canonical instrument registry behind an `InstrumentCatalog` interface — per-broker symbol/category translation, tick/lot/min-notional specs, spot vs perp; Alpaca + Bybit wired
- [x] Order conformance on the live path — `ExecutionEngine` rounds to tick/lot and rejects sub-minimum opens before `RiskManager`/the broker; closes are quantized but never blocked
- [ ] Wire `BinanceAdapter` to the instrument catalog; refresh `seed.py` from each broker's live instruments endpoint
- [ ] Strategy-family modules (`grid`, `arbitrage`, `scalping`, `swing`) behind shared contracts — grid designed in full, none built
- [x] Strategy Builder — Monaco editor + subprocess sandbox execution (write-by-hand, no AI)
- [x] Live/paper strategy executor with WebSocket signals
- [x] Full trade pipeline: sizing → RiskManager → broker → fill → persistence (paper via built-in simulator); paper models the same commission + slippage as the backtest and is verified end-to-end
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

### Phase 3 — user-facing AI generation _(later still — not scoped)_

- [ ] **Builder "generate from plain English" via Claude** _(deferred 2026-08-18)_ — any
  Claude usage reachable from the frontend is explicitly out of scope before this: not Phase
  1, not Phase 1.5, not Phase 2. The sandbox editor above already covers hand-written
  strategies without it. When it's picked back up: prompt caching, structured tool-use output
  instead of regex-scraping JSON from the response, and moving the logic out of the router
  into a service + `LLMEnrichmentAdapter` (see `TODO.md` → *Do Last*).

---

## Future Ideas

- **Strategy families** — one self-contained module per family (`grid`, `arbitrage`, `scalping`,
  `swing`, …) behind shared abstractions, so adding a family edits no existing family, router, or
  page. The grid bot is fully designed and is the first one queued. See the architecture note above
  and `TODO.md` for the contracts and the two open design decisions.
- **Internal MCP server** — expose `run_backtest` / `dca_compare` / `monte_carlo` as Model Context
  Protocol tools so sweeps can be driven by an agent instead of by hand-written scripts in
  `scratchpad/`. Under discussion, not decided — a conversational sweep also makes it trivially easy
  to fish for a flattering parameter set, so any such tool should report walk-forward results by
  default rather than in-sample bests.
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
