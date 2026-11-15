# ProfitPilot — Master TODO

> Algorithmic trading platform with ML forecasting, multi-broker execution, and LLM signal enrichment.
>
> - **Phase 1:** Local, single user — test strategies, possibly with real broker money.
> - **Phase 2:** Multi-tenant SaaS — let other people use the platform.

_Last updated: 2026-11-13_

**Legend:** `[ ]` todo · `[~]` partial / in progress · `[x]` done

---

# 🎯 Active / Next Up

The short list of what's actually actionable right now. Everything under
[**Done**](#-done) is finished; everything under [**Pro Ideas**](#-pro-ideas--discuss-later)
is a future discussion.

## 🚦 Roadmap to a first live track record — from the 2026-11-13 plan review

> **Do these in order. Everything else in this file waits behind step 4.** The engineering is
> ahead of the evidence: the three paper strategies deployed 2026-08-21 have **never produced a
> signal or an order** (`last_signal_at` null, `signals` empty, every sim account still at exactly
> 100,000) because the executor only runs while the app is open on the dev machine. No strategy
> here has an out-of-sample result yet. The goal of this roadmap is one thing: a **verified,
> continuously-running paper/testnet track record** of a strategy that survived walk-forward.
>
> **No real money in this roadmap** _(user call, 2026-11-13)_ — Bybit testnet + Alpaca paper only.

### Step 1 — Host it on the old PC (always-on)

> **Repo side built 2026-11-13** (uncommitted, branch `worktree-todo-roadmap-review`) — what is
> left in this step is on the physical box, plus Alembic. Setup instructions: README →
> "Run it always-on". **Not yet verified:** the Docker image has never been built and the
> workflow has never run — the first `docker compose … up --build` on the box is the real test.
>
> Two things the plan assumed that were not true, found while doing it: (1) there were **no
> Dockerfiles** and `docker/docker-compose.yml` only starts Postgres + Redis (its api/frontend
> services are commented out) — `CLAUDE.md`'s "docker-compose up starts the full stack" is
> wrong; (2) `.gitignore`'s `*.txt` rule meant **`backend/requirements.txt` was never in the
> repo**, so a fresh clone could not install the backend. Both fixed.

- [ ] **Prepare the box** _(yours — physical)_ — Ubuntu Server LTS (or keep Windows + Docker
  Desktop if simpler); BIOS "power on after AC loss"; wired ethernet; NTP on (bar timestamps and
  broker signatures both depend on the clock); disable sleep. Install Docker + Tailscale.
- [x] **Single-container host stack** _(2026-11-13)_ — root `Dockerfile` (multi-stage: builds the
  frontend, then the API serves it via the new `app/api/spa.py`, non-root) +
  `docker/docker-compose.host.yml` (`restart: unless-stopped`, SQLite on a named volume,
  published on **loopback by default**; `PROFITPILOT_BIND` = Tailscale IP for remote access).
  Deliberately **no Postgres/Redis/Celery** — nothing uses them yet.
- [x] **Deploy from GitHub** _(2026-11-13)_ — `.github/workflows/deploy.yml`: backend + frontend
  tests on GitHub's runners → rebuild/restart on the box's self-hosted runner (label
  `profitpilot`). No `pull_request` trigger on purpose.
  - [ ] _(yours)_ register the runner on the box; set repo variable `PROFITPILOT_ENV_FILE`.
  - ⚠️ Keep the repo **private**: the deploy job runs on the box that holds the broker keys.
- [ ] **Secrets live only on the box** _(yours)_ — env file outside any checkout (e.g.
  `/opt/profitpilot/.env`). Broker API keys created **without withdrawal permission**,
  IP-allowlisted where the venue supports it.
- [x] **Nightly DB backup** _(2026-11-13)_ — `app/db/backup.py` (SQLite backup API, keeps newest
  `BACKUP_KEEP`), run by the daily heartbeat so a failed backup shows up in Telegram.
  - [ ] _(yours)_ point `PROFITPILOT_BACKUP_DIR` at a second disk / cloud-synced folder —
    the default is a Docker volume on the same disk.
- [x] **Alembic migrations** _(2026-11-14)_ — `backend/migrations/` + `app/db/migrate.py`; the app
  upgrades to head on startup instead of `create_all`. A pre-Alembic database (the dev DB, an
  early box) is **adopted**: stamped at baseline `0001`, then upgraded — data untouched.
  `tests/unit/test_migrations.py` fails whenever a model changes without a migration.
  - Verified on a **copy of the real dev DB**: adopted, all rows intact (3 strategies, 74,680
    cached bars). It surfaced real drift: the DB was missing `ix_strategy_instances_user_id`
    (lost in the 2026-07-11 nullable-columns rebuild) → migration `0002` recreates it only
    where missing. Your dev DB gets it the next time you start the app.
  - Tests still build in-memory DBs with `create_all` (fast); the guard test proves parity.
  - **Step 1 code is now complete.** What remains in Step 1 is on the physical box (yours).
- [x] **Alerting (Telegram)** _(2026-11-13)_ — `services/alerts.py` (off unless
  `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` set; never raises; never logs the token) +
  `services/monitor.py` + hooks in `StrategyExecutor` (notifier injected). Sends `ERROR` (first
  failing cycle only, re-armed on recovery), `HALTED`, `STALE` (no completed cycle with market
  data for > 2 poll intervals), and a `Daily:` heartbeat with the backup result. Plain code, no
  LLM. 27 new tests; 403 backend tests pass.
  - **Independent review done same day, all MEDIUM findings fixed:** bot token could leak via
    httpx's own INFO logger (pinned to WARNING); a strategy whose `generate_signals` raises every
    bar was reported healthy (now alerts + doesn't count as progress); a restart after the daily
    hour re-ran heartbeat + backup, so a crash loop could rotate out every good backup (monitor
    is now seeded from the newest backup's date); the frontend catch-all route disabled API
    trailing-slash redirects in the container only (now a not-found fallback, not a route);
    backup pruning could delete unrelated files sharing the prefix (strict filename match,
    temp-file + rename); alert text is now the first line of an error, max 200 chars; deleting
    a strategy now stops its loop (pre-existing bug); `python-binance` was missing from
    `requirements.txt`.
  - **Known and left:** an error that flaps (fail → ok → fail) alerts each time, no rate limit;
    a bad deploy replaces the old container before health is known (job fails, no auto-rollback);
    GitHub Actions are pinned by tag, not commit SHA; with backups off, each restart after the
    daily hour re-sends the heartbeat (harmless — reads as a restart notice).
  - [ ] _(yours)_ create the bot with @BotFather and put the two values in the box's env file.
  - _Not done:_ equity in the heartbeat; a "process started" message; an external dead-man's
    switch (if the whole box dies nothing is sent — **the missing daily message is the signal**,
    or add a free uptime-ping service later).

### Step 2 — Touch a real broker API (testnet / paper)

- [ ] **Bybit testnet smoke test** — keys are free; runbook `docs/runbooks/testnet-smoke-test.md`.
  (Existing item under 🔌 Broker.)
- [ ] **Alpaca paper account** connected the same way.
- [ ] **Know what each environment proves:**
  - *Bybit testnet* = **plumbing only** (auth, order routing, tick/lot conformance, fill
    reconciliation). Testnet books are thin and prices drift from mainnet — its P&L means nothing.
  - *Alpaca paper* and the internal `SimulatedBrokerAdapter` use **real market prices** — these
    are the ones whose P&L counts as the track record.
- [ ] **Before any live key ever exists:** position reconciliation loop, deterministic
  `client_order_id` (idempotent retry), persisted **global** kill switch. (All three already
  listed under Pro Ideas — they are prerequisites, not ideas.)

### Step 3 — Make the backtest numbers believable

- [x] **Walk-forward / out-of-sample validation** _(2026-11-14)_ — pure
  `domain/backtest/walk_forward.py` (every run goes through `BacktestEngine`: one execution
  path) + `WalkForwardService` + `POST /api/v1/backtests/walk-forward` (`param_grid`,
  `train_days`, `test_days`, `objective`; ≤ 300 combos; combos the strategy rejects, e.g.
  fast ≥ slow, are skipped not fatal). Folds tile the data; the test run gets prior bars as
  indicator context but decides only inside its window. Reports per-fold chosen params,
  in-sample score vs out-of-sample return/Sharpe/DD, buy-and-hold per fold, stitched OOS and
  B&H curves. Causality golden test (truncating future bars can't change an earlier fold's
  choice) + an overfit case where the in-sample winner loses out-of-sample. 20 new tests.
  - **Results on real cached data** (BTC 1d 2015→2026-08, ETH 1d 2020→, BTC 4h 2020→;
    train 730 d / test 180 d; 0.1% fee + 5 bps slippage; **100% position size** so the signal
    is comparable to buy-and-hold — at the live 2% every return is ~50× smaller, see Step 4):

    | strategy | OOS return / maxDD / Sharpe | B&H return / maxDD | folds + | verdict |
    |---|---|---|---|---|
    | MACD BTC 1d | +8,266% / 59% / 1.29 | +8,029% / 86% | 68% | **survives** — same return, far less drawdown |
    | MACD ETH 1d | −42% / 64% / −0.06 | −52% / 74% | 33% | **fails** — no edge |
    | SMA BTC 1d | +1,687% / 64% / 0.93 | +8,029% / 86% | 47% | **fails** — IS Sharpe 1.67 → OOS 0.42 |
    | MACD BTC 4h | −51% / 57% / −0.35 | +57% / 68% | 50% | **fails badly** |

    MACD BTC 1d caveats: the 2016–17 folds dominate the compounded total; from 2022 on it
    roughly tracks buy-and-hold with smaller drawdowns. Chosen params moved around (10 distinct
    sets in 19 folds) but mostly `fast=16`, a plateau rather than one lucky cell.
  - [ ] **Your decision:** pause the two paper strategies that failed (MACD ETHUSDT 1d,
    SMA BTCUSDT 1d). Not done for you — they are your running instances.
  - [x] **Backtests-page panel** _(2026-11-15)_ — after any backtest, **Run walk-forward**
    re-runs that exact request (costs, sizing, stop) searching ½×, 1× and 1.5× each current
    parameter (`lib/walkForwardGrid.ts`; combos the strategy rejects are skipped server-side),
    with editable train/test days. `WalkForwardPanel` shows the verdict against the project's
    bar (`passesBar`: return/DD beats buy & hold, > 50% folds profitable, Sharpe ≥ 0.5), OOS vs
    B&H stats, a log-scale OOS vs B&H curve, and the fold table. en/es. 11 new frontend tests.
    A 4h run with a 4-parameter strategy (81 combos) can take a few minutes — no progress bar.
  - [ ] **Not built:** a parameter-plateau check in the panel (neighbours of the winner also
    profitable?) — done by hand for TrendFilter in the Step 5b log.
  - [ ] Grid-bot sweep through walk-forward — after the 3 open 2026-11-13 grid findings below.
- [x] **Backtest engine no longer quadratic** _(2026-11-14)_ — the cost was not indicators but
  the engine handing the strategy the **whole history** every bar. It now passes the last
  `STRATEGY_LOOKBACK_BARS` (500, `core/constants.py`) — the **same window the live executor now
  fetches** (was 200), so this is also a parity fix. Measured on 14,062 real BTC 4h bars:
  MACD 21.9 s → 1.6 s, RSI 11.6 → 0.8, SMA/BB 4.0 → 0.4 — **every trade identical** to the
  full-history run for all four built-ins. The Builder sandbox keeps full history (it indexes
  signals by bar count). A strategy whose params need > 500 bars can never signal, live or
  backtest — raise the constant first.
- [ ] **Always report against buy-and-hold on the same capital**, and report return **on capital
  actually deployed**, not just on the account.

### Step 4 — Fix sizing: position size ≠ risk

- [x] **Risk-based position sizing — built 2026-11-14.** New optional per-strategy
  `risk_per_trade_pct` (and on `/backtests/run` + `/walk-forward`): size = risk ÷ stop
  distance, capped at `size_pct`, which then acts as the **maximum** position size (the UI
  relabels it). Blank = fixed sizing, unchanged. ONE pure rule,
  `position_sizer.entry_fraction`, used by both the live sizer and `BacktestEngine` (parity).
  Migration `0003` adds the column (first real use of Alembic). Frontend: config form, strategy
  card, backtest form, en/es. 12 backend + 1 frontend test; 438 backend + 134 frontend pass.
  - **Finding that matters more than the sizing:** the live **1.5% stop** wrecks the one
    strategy that survived walk-forward. MACD BTC 1d out-of-sample: no stop +8,266% / Sharpe
    1.29 · **1.5% stop +315% / 0.77** · 5% stop +1,759% / 1.09 · 10% stop +10,130% / 1.38. Daily
    BTC moves > 1.5% routinely, so the stop ejects it from good trades. The stop must suit the
    strategy's timeframe — and risk sizing makes that explicit (size = risk ÷ stop).
  - **What each config earns** (MACD BTC 1d, out-of-sample 2016→2026, costs on): today's paper
    (2% size, 1.5% stop) **0.6%/yr**, max DD 1.0% — below cash. Risk 1% / 10% stop: 6.3%/yr,
    DD 7.4%. Risk 2% / 10% stop: 12.5%/yr, DD 14.3%. Risk 5% / 10% stop: 30.1%/yr, DD 32.7%.
    Sharpe ≈ 1.2 in every risk row: **sizing creates no edge**, it only trades return for
    drawdown. Past drawdowns are a floor, not a ceiling — expect worse live.
  - [ ] **Your decision — reconfigure the MACD BTC 1d paper strategy:** stop-loss override 10%,
    risk per trade 1–2%, max position size 100%. Not done for you (it's your running instance).
  - _Not done:_ volatility-scaled stops (stop = k × ATR instead of a fixed %) — the natural
    next refinement, since a fixed % suits one volatility regime only.
- [ ] ~~Risk-based position sizing~~ _(original item, kept for the reasoning)_ Today `max_position_size_pct = 2%` *and*
  `stop_loss_pct = 1.5%`, so a stopped-out trade loses `2% × 1.5% = 0.03%` of equity. That is why
  the MACD backtest shows a 1.5% max drawdown and only ~18% total return over the whole daily
  history — the account is ~98% idle cash. The professional convention is the other way round:
  **decide the risk per trade, derive the size**:
  `position_notional = equity × risk_per_trade_pct / stop_distance_pct`
  (e.g. 0.5% risk ÷ 1.5% stop → 33% of equity in the position), still capped by a max-exposure
  limit. Or volatility targeting: size so the position's expected daily vol hits a target.
  - Belongs in `domain/execution/position_sizer.py` as a second sizing policy (keep the current
    fixed-% one); `RiskManager` keeps the hard cap. Backtest must use the same sizer (parity rule).
  - Add `risk_per_trade_pct` to `RiskConfig` / `ExecutionConfig` (one column + one field).
- [ ] **Portfolio-level cap** — three BTC/ETH trend bots are one correlated bet; cap aggregate
  exposure, not just per-strategy. (Existing Pro Idea "Portfolio-level risk".)

### Step 5 — Strategy research, in order of realism

- [ ] **Trend + volatility targeting on a small basket** (BTC, ETH, a few liquid ETFs via
  Alpaca) — low-frequency, fits the poll-at-bar-close architecture, and is what the MACD result
  already is. Most plausible edge for this setup.
- [ ] **Funding-rate carry (long spot / short perp, delta-neutral)** — the realistic version of
  "arbitrage". **Start with data only:** collect + store funding-rate history (Bybit/Binance
  public endpoints), backtest the carry including fees and the periods when funding goes
  negative. Needs later: two-leg position model, margin/liquidation monitor on the short leg.
  Cannot be validated on testnet (testnet funding is meaningless) → stays research until real
  money is on the table. Check the account can trade perps at all in your jurisdiction.
- [ ] **DEX spread scanner — read-only experiment, not a strategy** _(user idea 2026-11-13:
  PancakeSwap/Uniswap price gaps, executed only if a contract guarantees profit)_. The
  "contract reverts unless profitable" mechanism is real (atomic arbitrage / flash loans), but
  it is the MEV-searcher game: competitors run their own nodes and private order flow, and bid
  nearly all of the profit away in priority fees, usually within one block. It is also a
  separate stack (Solidity, node RPC, mempool) that reuses none of ProfitPilot's execution path.
  **Cheap honest test before spending any effort:** a script that polls pool quotes + a CEX
  price and logs every gap **net of** swap fees, gas, and price impact at a realistic size, for
  a month. Decide from that log. No contracts, no keys, no money.
- [ ] ❌ **Dropped: cross-exchange spot arbitrage, triangular arbitrage, scalping.** Spreads on
  liquid pairs are ~1–2 bps against ~10 bps taker fee per side, and this system polls REST at
  bar close. Not a fit for the architecture — removed from "Families planned" below.

### Step 5b — Strategy candidates and how each one gets developed _(added 2026-11-13)_

> **None of these is known to work here.** Each has a documented reason to pay and fits this
> system (bar-close polling, daily/4h, spot + paper). Whether it survives costs out-of-sample on
> our data is exactly what the pipeline below decides. Expect most to be killed — that is the
> pipeline working, not failing.

**The pipeline every candidate goes through (same gates, no exceptions):**

1. **Hypothesis first, in writing, before any backtest** — one paragraph in this file: why
   should it pay, who is on the other side, what would prove it wrong. Parameters and the test
   period are fixed here too. This is the only real defence against fitting by eye.
2. **Implement** as a `StrategyBase` subclass under `domain/strategy/examples/` (+ `_BUILTIN_META`),
   stateless, unit-tested on a synthetic series with hand-computable signals.
3. **Walk-forward** (Step 3) with live costs and live sizing (Step 4), on ≥ 2 symbols.
   **Pass =** positive out-of-sample return after costs in most windows, a parameter *plateau*
   (neighbours also work — not one lucky cell), and a better return-to-drawdown than
   buy-and-hold on the same capital. Raw return above buy-and-hold is not required; lower
   drawdown for similar return is a valid edge.
4. **Monte Carlo** on the out-of-sample trades — the 5th-percentile drawdown must be one you
   would actually sit through.
5. **Paper, minimum 8 weeks and ≥ 20 trades** (daily strategies will need longer) on the old PC.
   **Pass =** realized results inside the backtest's expected band; fills and signals match a
   backtest re-run over the same dates.
6. **Only then** is it a candidate for real money — outside this roadmap, user decision.
   **Kill rule:** failing gate 3 twice (after one honest revision of the hypothesis, not the
   parameters) drops the candidate. Record the result here either way — a documented dead idea
   is worth keeping.

**Tier A — fit today's single-position engine; build these first**

- [ ] **A1 · Trend-following with volatility targeting (BTC, ETH; 1d).** Long when price is
  above a long moving average / on a Donchian breakout, flat otherwise; size by volatility
  target. *Why it might pay:* time-series momentum is one of the most replicated effects across
  asset classes, and crypto trends hard. *Other side:* late sellers and mean-reversion traders in
  a trend. *Known weakness:* bleeds in sideways chop — many small losses. The existing
  `MacdCrossover`/`SmaCrossover` are already members of this family: **re-validate them through
  the pipeline rather than writing new ones**, and add a Donchian variant as a third opinion.
  Needs: Step 3 + Step 4. No new machinery.
- [ ] **A2 · ETF trend timing (Alpaca paper; 1d bars, monthly decision).** One instance per ETF
  (broad US equity, international equity, bonds, gold, commodities — all already in
  `instruments/seed.py` or one line to add): hold while price is above its ~10-month average,
  otherwise cash. Equal capital per instance. *Why it might pay:* it has historically cut the
  deep drawdowns of buy-and-hold for similar long-run return; it is a drawdown-control strategy
  more than a return booster. *Known weakness:* whipsaws around the average, lags V-shaped
  recoveries. Runs as N independent single-symbol strategies — **no portfolio engine needed.**
  Needs: a monthly-evaluation option (only act on the last bar of the month), Alpaca paper wired.
- [ ] **A3 · Short-term mean reversion on index ETFs (Alpaca paper; 1d, long-only).** Buy a
  sharp multi-day pullback (e.g. 2-period RSI oversold) **only while the long-term trend is up**,
  exit on the bounce. *Why it might pay:* index ETFs have shown short-horizon reversal;
  liquidity providers get paid for absorbing panic selling. *Known weakness:* the edge has
  decayed since it was published, and it catches falling knives in a real bear — hence the
  trend filter and a hard stop. Small expected edge per trade: **costs decide this one**, so
  test with pessimistic slippage. Reuses `RsiMeanReversion` + one trend filter.
- [ ] **A4 · Baseline: plain scheduled DCA (BTC and/or a broad ETF).** Not alpha — the honest
  "passive" option and the **benchmark every other candidate must beat on risk-adjusted terms.**
  `dca_flat` already exists in the comparison backtester; making it runnable in paper needs a
  scheduled-buy path (staged buys, no flips), which is also the first brick of the multi-buy
  execution the halving-cycle and grid families need. If nothing in Tier A beats A4, the
  platform's best product *is* A4 with good reporting — worth knowing early.

**Tier B — need a small portfolio engine (several symbols, ranked, rebalanced)**

> Build the engine **once**, when the first Tier B candidate is actually next: inputs = a symbol
> universe + a ranking function + a rebalance schedule; output = target weights; execution goes
> through the existing `ExecutionEngine`/`RiskManager` per symbol. Not before.

- [ ] **B1 · Dual momentum on ETFs (monthly).** Each month hold the strongest of a small ETF set
  over the past ~12 months, but only if it also beat cash; otherwise bonds/cash. *Why:* combines
  relative strength with the A2 trend filter. *Weakness:* concentrated in one asset at a time;
  results are sensitive to the lookback and the rebalance day — test several of each and require
  a plateau.
- [ ] **B2 · Cross-sectional crypto momentum (weekly, top-N of ~15 liquid coins, long-only).**
  *Why:* winners have tended to keep winning over 1–4 weeks. *Weakness:* **survivorship bias is
  the trap** — a universe built from today's top coins already excludes the ones that died, which
  inflates any backtest. The universe must be defined point-in-time (by volume/market cap *as of*
  each rebalance date). If that data cannot be sourced honestly, do not build this.

**Tier C — need multi-leg or resting-order execution; research/data only for now**

- [ ] **C1 · Funding-rate carry** — see Step 5. Start collecting funding history now; it costs
  nothing and the data is needed whatever is decided later.
- [ ] **C2 · Grid bot live** — backtest exists; needs the validation sweep through walk-forward
  first, then resting limit orders + partial fills in the execution layer.
- [ ] **C3 · Halving-cycle accumulation live** — exists as a comparison backtester; same
  execution gap as C2, and only ~3 cycles of evidence. Stays gated on evidence (see 🔭 Backlog).

**Overlay, not a strategy**

- [ ] **Volatility/regime stand-down** — a shared filter (e.g. ATR percentile outside a band →
  no new entries) that any Tier A strategy can opt into. `grid/regime.py` already computes the
  pieces; lift them to a shared module when the second consumer appears. Validate as "strategy
  with overlay vs without" in the same walk-forward — it must earn its place.

**Suggested build order:** Step 3 + Step 4 → **A1** (re-validate MACD/SMA; cheapest, paper instances
already exist) → **A4** (benchmark + first staged-buy execution) → **A2** (brings Alpaca
paper and ETFs online) → **A3** → decide from the results whether Tier B's engine is worth
building. One candidate in the pipeline at a time.

#### Pipeline log — built-ins re-validated + new candidates _(2026-11-14)_

**Built-ins, walk-forward verdicts** (BTC/ETH 1d; train 730 / test 180 days; 0.1% fee + 5 bps;
100% size, no stop — signal quality vs buy-and-hold):

| strategy | BTC 1d OOS (Sharpe, IS→OOS) | ETH 1d OOS | verdict |
|---|---|---|---|
| MacdCrossover | +8,266%, DD 59% (1.73→1.29) | −42% (1.10→0.01) | **BTC only survives** |
| SmaCrossover | +1,687%, DD 64% (1.67→0.42) | — | fails |
| RsiMeanReversion | −4%, DD 80% (1.26→0.19) | −57% (1.21→−0.19) | **fails** |
| BollingerBandsMeanReversion | −44%, DD 77% (0.81→0.03) | −60% (0.66→−0.27) | **fails** |

**Gate-1 hypotheses — written BEFORE any backtest of these. Do not edit after results.**
Fixed test for all three: BTCUSDT + ETHUSDT 1d, full cached history, train 730 / test 180 days,
objective Sharpe, 0.1% fee + 5 bps slippage, 100% size, no stop, long-only.
**Pass (all three required, on at least one symbol):** out-of-sample return/max-DD better than
buy-and-hold over the same windows · > 50% of folds profitable · OOS Sharpe ≥ 0.5.

- **A1b · `DonchianBreakout`** — long when the close breaks above the highest high of the
  previous `entry_bars`; flat when it breaks below the lowest low of the previous `exit_bars`.
  *Why it might pay:* time-series momentum; breakouts to new highs in crypto tend to extend.
  *Other side:* traders selling into strength / mean-reverters. *Wrong if:* breakouts mostly
  fail (chop) so whipsaw costs eat the trend gains. Grid: `entry_bars` {20, 55, 100},
  `exit_bars` {10, 20, 50}.
- **A2c · `TrendFilter`** — long while the close is above its `period`-day SMA, flat below.
  *Why:* the simplest trend filter; mainly avoids the deep bear legs (−75–85% on BTC/ETH).
  *Other side:* buyers of falling prices. *Wrong if:* whipsaws around the average cost more
  than the drawdowns it avoids. Grid: `period` {50, 100, 150, 200}.
- **A3 · `RsiPullbackInTrend`** — buy when RSI(`rsi_period`) drops below `entry_rsi` while the
  close is above its `trend_period` SMA; exit when the close rises above its `exit_period` SMA.
  *Why:* short-term reversal inside an uptrend — buying panic from weak hands, only when the
  bigger trend says the dip is likely bought. *Wrong if:* dips in uptrends keep falling (the
  plain RSI result above already says unfiltered dip-buying has no edge here). Grid:
  `rsi_period` {2, 3}, `entry_rsi` {5, 10, 20}, `trend_period` {100, 200}, `exit_period` {5, 10}.

**Gate-3 results (run after the hypotheses above were written; built in
`domain/strategy/examples/trend.py`, registered via the new `loader._BUILTIN_MODULES`):**

| strategy | BTC 1d OOS | ETH 1d OOS | verdict |
|---|---|---|---|
| **TrendFilter** | +13,884%, DD 68%, Sharpe 1.28 (IS 1.63), 68% folds +, ret/DD **203 vs B&H 94** | +34%, Sharpe 0.37 | **PASSES on BTC** |
| DonchianBreakout | +2,419%, DD 71%, Sharpe 1.00; ret/DD 34 vs 94 | +15%, Sharpe 0.26 | fails |
| RsiPullbackInTrend | +140%, DD 50%, Sharpe 0.47; ret/DD 2.8 vs 94 | −22%, Sharpe 0.00 | fails |

- **TrendFilter BTC is a plateau, not a lucky cell:** every fixed period walked out-of-sample
  works — 50: Sharpe 1.31 · 75: 1.16 · 100: 1.26 · 125: 1.45 · 150: 1.30 · 200: 1.05 · 250: 1.06.
  The fold-by-fold choice jumps (50…200), which matters little when all neighbours work.
  1–8 trades per 6-month fold: very low turnover, costs barely matter.
- **Caveats, stated plainly:** one asset (fails on ETH); the decade is dominated by BTC's huge
  trends and the 2016–17 folds dominate the compounded total; a 65–70% drawdown at full size
  is still brutal — size it down (Step 4). It and MACD BTC are both BTC trend-following:
  running both is close to one bet twice, not diversification.
- **Stops barely matter for it** (period 100, OOS): none Sharpe 1.26 / 74% folds + · 1.5%
  1.31 / 53% · 10% 1.25 / 74% · 20% 1.24 / 74% · 25% 1.27 / 74%. Unlike MACD (crossover
  *events*), TrendFilter re-signals LONG every bar it is above the average, so a stop-out simply
  re-enters next day. A wide stop keeps more folds profitable and trades less.
**Gate-1 hypothesis — A2 · ETF trend timing — written BEFORE any ETF backtest. Do not edit.**
`TrendFilter` (already built) on each of five asset-class ETFs: SPY (US stocks), EFA
(international stocks), IEF (US 7–10y Treasuries), VNQ (US real estate), DBC (commodities).
Equal capital per ETF, each its own independent strategy instance, long-only, daily bars.
*Why it might pay:* it is a drawdown-control rule — asset classes spend long stretches in
deep bear markets (2008 stocks −55%, 2022 bonds −20%), and being in cash below the average
skips most of the deepest legs. Five weakly correlated assets smooth each other out — and
none of them is BTC. *Other side:* buy-and-hold investors who sit through the bear legs.
*Wrong if:* whipsaws around the average cost as much as the drawdowns avoided (likely in
choppy assets like DBC), or the cash periods miss the V-shaped recoveries (2020).
Fixed test: common history of all five (from DBC's 2006 start), walk-forward train 730 /
test 180 **calendar days**, `period` grid {100, 150, 200} trading days, 5 bps slippage +
0.1% fee (pessimistic for ETFs), 100% size per instance, no stop.
**Pass (basket, equal-weight, both required):** out-of-sample max drawdown at most two-thirds
of equal-weight buy-and-hold's over the same windows, **and** return/max-DD better than it.
Per-ETF results reported but not required to pass individually.

**A2 result** (Yahoo daily, common history 2006-02 → 2026-11, folds from 2008; 503/124-bar
windows = 730/180 calendar days):

| | per year | max DD | ret/DD | Sharpe |
|---|---|---|---|---|
| **Trend basket** (equal weight) | 3.7% | **15.0%** | 6.56 | 0.50 |
| Buy-and-hold basket | 7.0% | 43.9% | 5.75 | 0.54 |

Per ETF (OOS vs B&H): SPY +408% / DD 22% vs +742% / 50% (Sharpe 0.80, the best) · EFA +57% /
30% vs +165% / 58% · IEF +5% / 18% vs +64% / 24% · VNQ **−20%** / 52% vs +254% / 66% · DBC +43%
/ 50% vs +37% / 74%.
- **Verdict: passes the pre-registered bar** (DD 15.0% ≤ ⅔ × 43.9%; ret/DD 6.56 > 5.75) — **but
  only as drawdown control, not as an edge**: it gives up half the return for a third of the
  drawdown, and Sharpe is no better (0.50 vs 0.54). Honest reading: a calmer way to hold a
  diversified ETF basket, not a money-maker. Cash earns 0% in the backtest; real cash earns
  T-bill interest while out of the market, which would lift it somewhat (not modelled).
- **Still the first non-BTC result** — it diversifies the BTC trend bet. Candidates for paper:
  the basket on Alpaca paper (5 instances, equal size), or SPY alone (its strongest leg).
- Found + fixed while doing it: walk-forward windows were converted with a **median bar gap**
  (1 day for stocks *and* crypto), so "730 days" meant ~2.9 years on stocks. Now bars per
  **calendar** day over the whole history (`walk_forward_service._bars_per_calendar_day`),
  with a regression test. Crypto results above are unaffected (it trades every day).
- Seeded EFA, IEF, VNQ, DBC in `instruments/seed.py` (an unseeded symbol's open is rejected live).

- [ ] **Your decision — gate 5 (paper):** add `TrendFilter` BTCUSDT 1d, period 100–125, in paper,
  stop override ~20%, sized with risk per trade (e.g. 1–2% risk ÷ 20% stop = 5–10% position) or
  a fixed 25–50% max position.

### Step 6 — Agent layers (Claude) — what goes where

> **Rule: the LLM never places an order and never holds a key that can.** Anthropic's agents
> are LLM loops with tools — they do **not** ship a risk manager. Ours (`RiskManager`) stays the
> only gate; agents sit *around* the pipeline, never inside the order path. An agent may only
> take **risk-reducing** actions (pause a strategy, trip the kill switch) — never open or resize.

- [x] **Layer 1 — Research agent (dev machine)** _(2026-11-15)_ — built as a **CLI, not an MCP
  server**: Claude Code already runs commands, so `backend/scripts/research.py` (`strategies`,
  `walk-forward`) gives an agent the same capability with no new dependency and no server.
  Same `WalkForwardService` as the API and the Backtests page, so numbers match the UI. JSON
  out, `passes_bar` first; **only** out-of-sample results — there is deliberately no command that
  prints an in-sample best. No trading tools at all. `CLAUDE.md` tells agents to use it.
  - The pass/fail bar moved to ONE place, `domain/backtest/walk_forward.passes_bar`; the API
    returns `passes_bar` and the UI panel reads it (was computed in the frontend only).
  - Verified live: TrendFilter BTC 1d, grid {50,100,150}, data to 2026-11-07 → **passes**
    (OOS +7,447% / DD 68% / Sharpe 1.14 vs B&H +7,548% / 86%, 65% folds profitable).
  - Upgrade to MCP only if a non-Claude-Code client needs it (e.g. the box's Layer-2 ops agent).
  - `scripts/grid_search_strategies.py` (in-sample sweep with `--deploy`) is superseded — your
    call whether to delete it; `CLAUDE.md` already tells agents not to use it.
- [ ] **Layer 1b — Paper-to-strategy intake** _(user request 2026-11-13; builds on Layer 1)_.
  Feed a research paper (PDF / arXiv q-fin / SSRN link) to Claude and get a candidate for the
  Step 5b pipeline, not a trade:
  1. **Extract a "strategy card"** (structured output, stored): hypothesis, universe, signal
     rule, rebalance frequency, holding period, data required, costs assumed, claimed results
     and sample period. The paper *is* gate 1 (hypothesis written before our backtest).
  2. **Feasibility filter — most papers stop here.** Reject if it needs data we don't have
     (tick/order book, options, fundamentals, a point-in-time stock universe), a frequency this
     system can't trade (intraday/HFT), or shorting single stocks. Record the reason.
  3. **Generate the `StrategyBase` code** through the Builder's generate + sandbox path (so this
     is the feature that finally justifies wiring it), human-reviewed against the card.
  4. **Run the normal pipeline** (walk-forward, costs, Monte Carlo, paper) and store **our
     result next to the paper's claim.**
  - ⚠️ **Expect less than the paper reports.** Published strategies are a filtered sample (only
    the ones that worked got published), many ignore realistic costs, and returns typically
    shrink after publication as others trade them. A paper is a good source of *hypotheses*, not
    of results — our own out-of-sample numbers are the only ones that count.
  - Replication mismatch is a signal too: if we can't reproduce the paper's in-sample number on
    its own period, either our implementation or the paper is wrong — find out which before
    going further.
  - Keep a `papers/` log (card + verdict) so a rejected paper is never re-evaluated from scratch.
- [ ] **Layer 2 — Ops agent (old PC, scheduled daily).** Read-only tools over the API/DB: did
  every strategy process its bar, do broker positions match ours, is paper P&L inside the
  backtest's expected band, anything odd in the logs. Output = a short Telegram report. Its only
  write tool is "pause strategy". Needs Step 1 (hosting + alerts) first; the deterministic
  alerts stay — this is the layer that *explains*, not the one that *detects*.
- [ ] **Layer 3 — Event veto (`LLMEnrichmentAdapter`, first real implementation).** Classify
  news/events (exchange hack, delisting, major macro print) into a risk-off flag that makes
  strategies stand down or halve size. Can only reduce exposure. **Evaluate forward-only:** log
  every output with a timestamp and judge it on live data — an LLM "backtested" on history
  already knows what happened, so any historical result is contaminated.
- [ ] **Layer 4 — ML forecasting (later, still wanted).** XGBoost/LightGBM first, through
  `ForecastingModelAdapter`, on a point-in-time feature pipeline, validated with the Step 3
  walk-forward. Gate: it must beat the plain trend baseline out-of-sample before it sizes a
  trade. PyTorch/Darts/NeuralProphet after that, same gate. LLM + ML combined via the existing
  `StrategyOrchestrator` design — the architecture already has the right seams for this.
- [ ] Move the Builder's direct `AsyncAnthropic` call behind an adapter when Layer 3 lands
  (already tracked under ⏸️ Do Last) — one LLM integration path, not two.

### Housekeeping from the same review

- [ ] **Dev DB cleanup (`backend/profitpilot.db`)** — leftovers from the pre-fix test-isolation
  bug. Stop the API, **copy the file as a backup first**, then:
  ```sql
  -- 2 synthetic orders (BTCUSDT @ 30000/31000, dated 2024-01-01/02) for a strategy that no longer exists
  DELETE FROM order_records
   WHERE strategy_instance_id NOT IN (SELECT id FROM strategy_instances);
  -- 1 orphan sim account (created 2026-07-11) for a deleted strategy
  DELETE FROM sim_accounts
   WHERE strategy_instance_id NOT IN (SELECT id FROM strategy_instances);
  ```
  Expected: 2 rows + 1 row deleted. Optional: `DELETE FROM ohlcv;` — it is only a cache
  (BTCUSDT 15m/1h/4h/1d, ETHUSDT 4h/1d) and refetches on the next backtest; do it if you want
  to be sure no synthetic test bars from that session remain mixed in. Nothing else needs
  cleaning (`signals`, `portfolio_snapshots`, `broker_connections`, `sim_positions` are empty).
  Simplest alternative when moving to the old PC: start that box with a **fresh DB** and
  recreate the three strategies there.
- [ ] **`PROFITPILOT_PROJECT_INSTRUCTIONS.md` is the original vision doc, not current state** —
  its §12 status tracker is entirely unchecked although most of it is built, and §9 lists pages
  that don't exist yet (`/models`, `/models/:id`, `/signals`, `/brokers`, `/admin`,
  `/backtests/:id`) while missing ones that do (`/trade`, `/builder`). The future pages are fine
  to keep as a target. Fix: add a one-line banner "vision / target architecture — current status
  lives in `TODO.md`" and delete §12, so status has one owner.
- [ ] **Rust (`rust_math/`) — keep as is, add nothing** _(user call, 2026-11-13)_. Do not delete
  or discard what exists. New hot paths are written in Python/numpy first; Rust is revisited only
  if a measured bottleneck survives that.
- [ ] **Frozen until Step 4 is done:** Celery migration, TimescaleDB, SaaS/billing/auth,
  marketplace, strategy-family framework. Not discarded — just not next.

## 🧱 Strategy-family architecture — the long-run shape of both stacks

> **Superseded (2026-08-28) — see `docs/superpowers/specs/2026-08-28-grid-bot-design.md`.**
> The full pre-built contract layer below (`StrategyFamily`, `SimulationEngine`,
> `FamilyRegistry`, registry-driven frontend, migrating `BacktestEngine`/`accumulation.py`
> onto it) was **deliberately deferred** rather than built before grid. Reasoning: it touches
> the two most heavily-tested, parity-critical modules in the app for no behaviour change and
> no new capability, in service of an abstraction with only one real consumer either way.
> **What ships with grid instead:** one real shared contract, `domain/strategies/
> base/ledger.py::Ledger(ABC)` (`equity(price) -> float`) — genuinely shared between
> `AccumulationLedger`-shaped and per-rung-lot accounting, provable without retrofitting either
> existing simulator. Grid ships behind **one dedicated route**, exactly like `dca-compare`,
> not through a registry. Everything below stays as the plan **if/when a second new family**
> (arbitrage/swing) lands — promoting the identity dataclass into a registry, or extracting
> `SimulationEngine` from two real driver functions, is a small refactor done with two real
> shapes in hand instead of a guessed third. Today every new strategy idea lands wherever it
> fits: the halving-cycle work went into `domain/backtest/accumulation.py` because
> `BacktestEngine` is single-position and flip-based and couldn't express it — that's the
> second purpose-built simulator in the codebase, and grid is intentionally the third rather
> than forcing a shared framework nothing has stress-tested yet.

- [ ] **Define the shared family contracts** *(deferred — build when a 2nd new family needs
  it, not before)* — new `backend/app/domain/strategies/base/`. Nothing here knows what a
  grid or a swing is:
  - `StrategyFamily` — identity, param schema, and a factory. The **single source of truth**
    for a family's knobs, the way `ExecutionConfig.model_fields` already is for per-strategy
    config. The FE form and the BE validator both derive from it; neither hand-maintains a list.
  - `Ledger` (ABC) — **partially done, see grid** — `equity(price) -> float` shipped with
    grid. Position/inventory accounting beyond that stays per-family (single-position
    `BacktestEngine`, blended cost basis `accumulation.py`, per-rung lots `grid`); a family
    still writes its own P&L maths, it just reports equity through one shape.
  - `SimulationEngine` (ABC) — what execution semantics a family needs (flip-based,
    multi-level accumulation, multi-leg). Families declare, the driver supplies.
  - `CostModel` — already effectively shared between engine/accumulation/paper adapter;
    lift it into one place so a fourth consumer can't quietly diverge.
  - `FamilyMetrics` — standard metrics come from `metrics.py`; a family adds its own
    (grid: `grid_trades`, `fill_rate`; arbitrage: spread capture) without forking it.
- [ ] **`FamilyRegistry`** *(deferred)* — `@FamilyRegistry.register`, mirroring
  `StrategyRegistry` and `BrokerRegistry`. One endpoint lists families + their param schemas;
  routers never switch on family name.
- [ ] **Frontend: registry-driven, not page-driven** *(deferred — grid ships a dedicated
  `GridControls`/`GridPanel` pair instead, mirroring `DcaCompareControls`/`DcaComparePanel`)*
  — the Backtests page currently hardcodes a panel per feature. Generalise to:
  - `lib/strategyFamilies/` — schema-derived param forms, extending the pattern
    `dcaCompareParams.ts` already proves (field defs + defaults + presets + localStorage in one
    place). A new family ships a schema, not a new form component.
  - A results-panel contract so each family renders its own chart/table behind one interface.
  - Families fetched from the BE registry, so FE and BE can't drift on what exists.
- [ ] **Migrate the two existing families onto the contracts** *(deferred, not a grid
  prerequisite)* — retrofit `accumulation.py` (DCA/halving) and `BacktestEngine` (flip-based).
  **Non-negotiable: no behaviour change** — the existing test suites are the proof.

**Families planned** (each a module under `domain/strategies/`, each backtest-only first):
`grid` (designed — see below, spec written) · `carry` (funding-rate, long spot / short perp —
see 🚦 Step 5; cross-exchange / triangular arbitrage and `scalping` were **dropped 2026-11-13**
as a poor fit for a poll-at-bar-close system) · `swing` (multi-day holds; closest to today's `BacktestEngine`) ·
`accumulation` (exists) · `trend` / `mean-reversion` (exist as built-in strategies, would be
re-homed).

## 🔲 Grid bot — **backend + UI implemented 2026-08-29/30**, no sweep yet

> **Backend implemented 2026-08-29** via subagent-driven execution of
> `docs/superpowers/plans/2026-08-28-grid-bot.md` (Tasks 1–12, the full plan as written).
> **UI implemented 2026-08-30** via `docs/superpowers/plans/2026-08-29-grid-bot-ui.md` (Tasks 1–4:
> types/API/i18n, `GridControls`, `GridPanel`, Backtests-page wiring). **357 backend tests pass**
> (unit + integration), **133 frontend** (`tsc -b` clean). Everything is **uncommitted
> working-tree changes** — the user commits.
>
> **Found and fixed while wiring the UI:** the locale-parity guard added in Task 1
> (`frontend/src/i18n/localeParity.test.ts`) caught a **pre-existing, unrelated bug** — Spanish
> pagination labels for the Backtests trade table (`backtests.pagination.*`) were misfiled under
> `builder.pagination` in `es.json` instead of `backtests.pagination`, so the live key was silently
> missing translation and Spanish-locale users saw raw key names or English fallback on that table.
> Fixed by moving the block to the correct namespace.
>
> **⚠️ Still not delivered:**
> 1. **No validation sweep run → no performance numbers.** Nothing is known yet about whether this
>    grid has an edge. Planned scope: BTCUSDT + ETHUSDT, 1h, 2019→now, bear slice
>    Nov-2021→Nov-2022 broken out separately (per the original design doc).
> 2. **Review debt on the backend, unchanged.** Only Tasks 1–2 of the *backend* plan got
>    independent code review (both approved). Tasks 3–12 were implemented and self-reviewed only —
>    the reviewer subagents were killed mid-run by an account spend limit. **Re-review before
>    trusting any of it**, starting with `process_bar_fills` in `domain/strategies/grid/ledger.py`
>    (largest deviation from the plan, load-bearing for every reported number). Ledger + ready-made
>    review packages: `.superpowers/sdd/2026-08-28-grid-bot/`.
>    The UI implementation (2026-08-30) was done inline, TDD-first, with every plan assumption
>    checked against real code before use — not yet independently reviewed either.
>
> **Four plan defects found and fixed during execution** (all recorded with rationale in that
> ledger): (1) a cost-floor test asserting exact float equality against an unreachable value;
> (2) both regime trending tests unpassable — proportional bar spreads make ATR monotonic, pinning
> its percentile outside the vol band so every bar gated FLAT; (3) the same defect in the planner's
> active-ladder test; (4) **critical** — `process_bar_fills` matched a lot's exit target against
> the *current* bar's rung ladder by exact float, but the ladder is recomputed every bar and
> consecutive ladders share **zero** exact rung floats, so no lot could ever close and grid income
> was structurally always zero. Also fixed a non-terminating geometric-rung loop on a non-positive
> range low (the plan's own test would have hung the suite, not failed it).
>
> Backtest-only for v1 (not live-deployable — `ExecutionEngine` is single-position/flip-based,
> grid needs multi-level resting orders). Ships as its own module,
> `backend/app/domain/strategies/grid/`, behind one dedicated `POST /api/v1/backtests/grid`
> route — **not** on the full family-contracts framework above (see that section's
> "Superseded" note); the only shared piece pulled forward is a minimal `Ledger(ABC)`.
>
> The commits named *"grid things"* / *"extra grid strategies"* are halving-cycle
> **accumulation** arms, a different feature that shares the word.

### 🔎 Code review findings — 2026-11-10 — ✅ all 9 fixed (same day)

> From `/code-review` of the grid work. **🔐 Security: none found.** Each fix has a regression
> test that fails on the old code (8 new tests; backend 312 pass). Line refs in the original
> review were stale, the substance held.

- [x] 🔴 **Look-ahead in range extension** — extension now decided on `bars[i-1]` (the bar the
  plan came from), never the bar being filled.
- [x] 🔴 **Arithmetic rungs ≤ 0** — `_clamp_rung_count` stops growing downward at the
  `center*1e-3` floor and grows upward instead.
- [x] 🟠 **Extension was a no-op** — extended ladder no longer re-clamped to the swing pivot; one
  `max_extensions` slot now buys a whole break episode (held while price stays outside, released
  when it comes back).
- [x] 🟠 **`cooldown_bars` ignored** — simulator stays flat for `cooldown_bars` after a forced close.
- [x] 🟠 **`allow_intrabar_roundtrip` did nothing** — a lot whose target is also touched that bar
  now opens and closes in the same bar when the flag is on.
- [x] 🟠 **No cross-field validation** — `model_validator`s: `min_rungs <= max_rungs`,
  `atr_vol_low < atr_vol_high`, `ema_fast < ema_mid < ema_slow` (422 instead of silent 0 trades).
- [x] 🟠 **Swing pivot on wrong side of center** — ignored instead of clamping the ladder to one side.
- [x] 🟡 **Mislabeled metrics** — `fill_rate` = % of active-ladder bars where something filled;
  `worst_unrealized_pct` = open inventory only (realized losses excluded).
- [x] ⚪ **Duplicate `bars_per_day`** — removed from `indicators.py`; single copy in `accumulation.py`.
- [ ] **Follow-up:** `GridControls` doesn't prevent the invalid combos above client-side — the
  user just gets the API 422. Add inline hints if it bites.

### 🔎 Code review findings — 2026-11-13 — ❌ 3 open, fix BEFORE the validation sweep

> From the second `/code-review` of the grid commits (`02b55c7..a9274c2`). All three were confirmed
> by reading the code at HEAD; #1 and #3 also by a numeric probe. CLAUDE.md compliance, ledger
> accounting, fee sides, and schema ↔ route ↔ TS field names were checked and are clean — don't
> re-audit those. **#1 and #2 bias every reported number, so the sweep is blocked on them.**
>
> **Instructions for whoever implements this (written for Opus 5.5):**
> - Do them in order, one at a time, TDD: write the regression test first, watch it fail on the
>   current code, then fix. Each test must fail on the old code for the reason described here.
> - Touch only `backend/app/domain/strategies/grid/` and its tests in `backend/tests/unit/`. No
>   schema, route, service or frontend change is needed — none of the fixes adds a user-facing knob.
> - If an existing test's expected numbers change, re-derive them by hand in the test's comment.
>   Don't paste the new output in as the expectation.
> - Run `pytest tests/unit -k grid -v` after each fix and the full `pytest tests/unit` at the end.
> - Then update the README grid section (see the last item), run `graphify update .`, and tick the
>   boxes here. **Never commit or stage** — the user does that.

- [ ] 🔴 **#1 — Entries open on the wrong side of the market** · `ledger.py::process_bar_fills`
  (the `crossed = {… if bar.low <= r <= bar.high}` line and the open loop below it)
  - **What's wrong:** every rung the bar's range touches becomes an entry. Nothing checks where
    price was *before* the bar, so a long opens on a rung that was above the market when the order
    would have been placed (a real buy limit only rests below the market; shorts mirror).
  - **Repro:** rungs `100, 101, … 110`, `LONG_BIASED`, previous close `103`, bar `low=103.5
    high=106.5`. Today: one long opens at `106`. Correct: nothing opens (no buy rung below 103 was
    touched).
  - **Fix:** add a required keyword argument `ref_price: float` to `process_bar_fills`. In the
    open loop, skip a rung unless it is on the resting side: long/neutral requires
    `rungs[i] < ref_price`, short requires `rungs[i] > ref_price`. Step 1 (closing open lots at
    their target) is untouched.
  - **Caller:** `simulator.py` passes `ref_price=bars[i - 1].close`. `i > 0` is already guaranteed
    there because `plan` is `None` on bar 0.
  - **Tests:** add the repro above (asserts zero lots) plus its short mirror (previous close `107`,
    bar `low=103.5 high=106.5`, `SHORT_BIASED` → no short opens at `104`). Every existing
    `process_bar_fills(...)` call in `test_grid_ledger.py` needs a `ref_price`; pick one that keeps
    each test's intent (above the touched rung for long tests, below for short).
  - **Out of scope, leave a `ponytail:` comment:** a rung the bar gaps straight through
    (previous close 103, bar opens at 99) is still missed by the `bar.low <= r <= bar.high` test.
    Don't fix it here.

- [ ] 🔴 **#2 — The stop-out bar skips its own fills** · `simulator.py::run_grid_backtest`
  (the `elif policy.should_force_close(...)` branch)
  - **What's wrong:** `should_force_close` decides on bar `i`'s close, and because it sits in an
    `if/elif` chain ahead of `process_bar_fills`, that bar's resting orders never fill. Buys the
    price traded through on the way down are never opened, so they are never closed at a loss.
    This is same-bar look-ahead, the class already fixed for the extension decision.
  - **Repro:** long ladder with rungs `96, 98, 100, …`, Supertrend bearish, `reanchor_buffer_pct`
    1%. Bar `i-1` closes at `99`. Bar `i`: `open=99 low=93.5 high=99 close=94`. Today: zero lots
    opened on bar `i`. Correct: longs open at `98` and `96`, then both are force-closed at `94`.
  - **Fix:** split the chain into two independent steps, in this order:
    1. if there is a plan and `i > cooldown_until`: run the extension + `process_bar_fills` block
       exactly as now;
    2. if there is a plan and `policy.should_force_close(i, bar, plan, ledger)`:
       `ledger.force_close_all(bar.close, ts_ms)` and set `cooldown_until`.
    Step 2 must still be evaluated during cooldown, as it is today, so cooldown behaviour and
    `force_close_count` don't change.
  - **Tests:** add the repro to `test_grid_simulator.py`; assert `forced_exit_pnl` is more
    negative than with the old code (two extra lots closed at a loss) and that
    `max_inventory_notional` includes them. Expect
    `test_pnl_buckets_reconcile_to_total_return_including_forced_exits` and
    `test_cooldown_keeps_the_grid_flat_after_a_forced_close` to need re-derived numbers; the
    reconciliation identity itself (`grid + forced + mark-to-market == total`) must still hold.

- [ ] 🟠 **#3 — `max_extensions` above 1 does nothing when ATR spacing sets the step** ·
  `simulator.py` (where `extended_params` is built) + `levels.py::_clamp_rung_count`
  - **What's wrong:** the extended ladder is rebuilt through `compute_levels`, which always ends in
    `_clamp_rung_count`. Once the natural rung count exceeds `max_rungs`, the clamp cuts
    symmetrically around center, so a bigger `range_atr_mult` yields the same ~`max_rungs` window.
  - **Repro (probe):** `compute_levels(center=100, atr=4, params=GridParams())`, varying only
    `range_atr_mult`: lowest rung is `88.0` at 3, `83.61` at 6, `83.21` at 9, `83.80` at 12. The
    third extension reaches *less* far than the first.
  - **Fix (recommended, one line, no change to `levels.py`):** when building `extended_params`,
    scale the rung cap by the same factor as the range:
    `max_rungs=round(grid_params.max_rungs * ext_mult / grid_params.range_atr_mult)`. Exposure
    stays bounded by cash and `max_open_lots`, which is where the ledger already bounds it;
    `max_rungs` was never the exposure cap.
  - **Tests:** in `test_grid_simulator.py` or `test_grid_levels.py`, with the probe inputs above
    and the scaled cap, assert the lowest rung strictly decreases across extensions 1 → 2 → 3, and
    that every adjacent gap still clears `cost_floor_step_pct`.
  - **If the recommended fix turns out wrong** (e.g. the scaled ladder makes a sweep too slow),
    stop and write the finding here instead of inventing a different clamp.

- [ ] ⚪ **README is stale about grid status** — the grid section says it's built, but three other
  lines still say it isn't: the `strategies/  # PLANNED` line in the directory tree, "grid
  designed in full, none built" in the roadmap checklist, and "is the first one queued" in the
  strategy-families note. Fix those, and add the #1/#2 behaviour to the "Fill realism" paragraph
  (entries only on the resting side of the previous close; the stop-out bar fills before it stops).

- [ ] **`backend/app/domain/strategies/grid/`** — pure domain, one file per responsibility:
  `params.py` (frozen dataclasses, every knob) · `levels.py` (rung geometry, spacing, cost
  floor) · `regime.py` (indicators → regime + gates) · `planner.py` (`(bars, i) → GridPlan`) ·
  `simulator.py` (`GridLedger` implementing `domain/strategies/base/ledger.py::Ledger`, per-rung
  lot accounting, intrabar fill sweep, equity curve) · `policies.py` (the two arms as
  subclasses, **not** if-branches).
- [ ] **Geometry** — range half-width `H = 3.0 × ATR` centred on the **Bollinger mid, not
  spot** (anchoring at spot puts half the ladder instantly underwater), clipped to the last
  confirmed swing high/low so the grid never extends past structure. Spacing
  `step = max(0.30 × ATR, min_edge × 2 × (fee + slip))` — **that second term is the cost floor,
  and omitting it is the #1 reason retail grid bots bleed**. Geometric spacing by default
  (constant % per rung → constant % profit per rung; crypto returns are lognormal, arithmetic
  rungs pay unevenly), arithmetic as a param. ~20 rungs falls out naturally, clamped 8–30.
  Equal notional per buy rung → max inventory known upfront.
- [x] **Regime gates — decided: symmetric long/short, not long-only** _(2026-08-28)_.
  `trend_up = EMA9 > EMA20 and close > EMA50`; `trend_down = EMA9 < EMA20 and close < EMA50`
  (new — mirrors `trend_up`, added so grid can lean into a downtrend instead of only falling
  back to a neutral ladder in one); `vol_ok = 0.35 <= atr_percentile <= 0.90` (**a band, not a
  floor** — too quiet starves the grid, too wild breaks the range); `squeeze =
  bb_bandwidth_percentile < 0.20`. → `LONG_BIASED` (`trend_up` + `vol_ok`: buy rungs primary,
  sells trail up) · `SHORT_BIASED` (`trend_down` + `vol_ok`: sell/short rungs primary, buys
  trail down — new) · `NEUTRAL` (sideways + `vol_ok`: full symmetric ladder) · `FLAT`
  (`!vol_ok`: no new rungs; existing inventory still works its rungs). Regime (direction) and
  arm (risk posture) stay orthogonal — the planner carries a `direction` field rather than
  forking the two arms into four policy classes; the guarded-reanchor exit mirrors under
  `direction` (short: exit above `range_high × (1 + buffer)` + Supertrend bullish).
  **Ledger consequence:** `SHORT_BIASED` needs real short inventory (negative rung positions,
  perp-style), reusing `BacktestEngine._capital_after_close`'s short-accounting formula rather
  than re-deriving it. **Caveat to ship in the API response + UI banner:** funding rates aren't
  modeled, so short-biased grid realism has a disclosed gap vs. a real perp position.
  Note: Supertrend-red means **stop opening new buy rungs** for a long-biased grid (not "sell
  opportunity" — the usual reading is backwards here); symmetrically, Supertrend-green means
  stop opening new short rungs for a short-biased grid.
- [ ] **Two arms, named by mechanics** (existing convention):
  - `grid_guarded_reanchor` — exits only when the range breaks against the active bias **and**
    Supertrend confirms (long: `close < range_low × (1 − buffer)` + bearish flip; short:
    `close > range_high × (1 + buffer)` + bullish flip), so wicks don't stop you; then FLAT +
    cooldown until the vol gate reopens. Breaks the other way → trail and re-anchor, rate-limited
    against thrash. Bounded loss — **this is the deployable one.**
  - `grid_accumulate_nostop` — no stop; extends the ladder another `H` further from remaining
    budget, capped at `max_extensions = 3` so cash stays finite. **Unbounded exposure by
    construction** (downside long, upside-cost short), so it must report
    `max_inventory_notional`, `worst_unrealized_pct`, `time_underwater_pct`, and the sweep runs
    a bear slice (Nov-2021 → Nov-2022) so the failure mode shows rather than hiding behind a
    bull sample — this slice now also doubles as the primary proof case for `SHORT_BIASED`.
- [ ] **Fill realism — where grid backtests usually lie:** rungs are limit orders (fill at rung
  price, no slippage, maker fee); forced exits are taker + slippage — mixing these up is a ~2×
  error on net edge per rung. `allow_intrabar_roundtrip=False` by default: letting one bar fill
  a buy on the low and its paired sell on the high is the classic way a grid backtest prints
  money that doesn't exist (available as a flag, documented as optimistic). Per-rung `Lot`
  pairing so "grid profit" is realised, not average-cost drift. Indicator periods specified in
  **days**, converted via `bars_per_day()`, so you plan on daily logic while executing on 1h/4h.
- [ ] **Scoreboard** — standard metrics plus `grid_trades`, `avg_profit_per_grid_pct`,
  `fill_rate`, `time_in_grid_pct`, and the honest one: **return attribution splitting grid
  income from inventory mark-to-market** (most grid-bot "profit" is just beta on the bag).
  Always benchmarked against buy-and-hold on the same capital.
- [ ] **Tests** — sawtooth synthetic with hand-computable P&L; a **causality golden test**
  asserting the planner is unchanged when future bars are truncated (the swing-pivot
  confirmation lag is a live look-ahead trap); cost-floor and geometry invariants; a breakdown
  series asserting the two arms diverge in the documented direction; regime gates. Target ≥80%.
- [x] **`min_edge` — decided: default `3`, user-tunable per family, not a global constant**
  _(2026-08-18)_. Rungs must clear N× round-trip costs before the bot places them (see
  `params.py`'s cost floor above). `3` is the grid family's shipped default; it lives in
  grid's own `GridParams` dataclass (not a `StrategyFamily` schema — that layer is deferred,
  see 🧱 above), exposed in the FE tuning panel the same way `DcaCompareControls` already
  exposes `cycle` / `hunter` / `rotation` — bounded by param min/max/step, no separate plumbing
  needed. A future HFT/scalping family still declares its *own* `min_edge` (or doesn't have the
  concept at all) in its own params, independently of grid's — no shared "trading knobs" file
  to keep in sync, contracts or no contracts. Tightening grid's default toward 1.5–2 roughly
  doubles trade count but the edge-over-cost gets thin fast — leave 3 as shipped default,
  adjust per-run from the UI.
- [x] **Validation sweep symbols/period — decided: BTCUSDT + ETHUSDT, 1h, 2019→now**
  _(2026-08-28)_, bear slice (Nov-2021→Nov-2022) broken out separately. Two symbols is enough
  to show the grid isn't curve-fit to one coin without blowing up sweep runtime — check grid's
  own simulator complexity before running it at 1h across the full 6-year window, given
  `BacktestEngine` sweeps are already O(n²)/bar (see `project_strategy_grid_search_paper_deploy`
  memory).

## 📐 Indicators needed by the grid family

- [ ] **`bollinger`, `bandwidth`, causal `swing_pivots`** in `domain/backtest/indicators.py` —
  the grid geometry and regime gates need all three (`bollinger` mid for the range anchor,
  `bandwidth` percentile for the squeeze gate, `swing_pivots` for structure clipping).
  Already present and reusable: `sma`, `ema`, `atr`, `true_ranges`, `supertrend`,
  `rolling_percentile`.
  - **`swing_pivots` must be causal** — a pivot is only confirmed N bars after the fact.
    Returning it at its own timestamp is look-ahead, and it is the single most likely way this
    family reports a fake edge. Hence the causality golden test above.
  - Also move `bars_per_day` here from `accumulation.py`, so a family module never has to
    import upward into a sibling.
  - Longer term these belong behind the family `base/` contracts, not in `domain/backtest/` —
    indicators are shared infrastructure, not backtest-specific.

## 🎛️ DCA-compare — front-end to tune the accumulation strategies

The 7 accumulation arms (`dca_flat`, `dca_dip_weighted_cycle`, `cycle_buydip_selltop`,
`cycle_ath_trim_rebuy`, `dip_deploy_trim`, `cycle_selltop_redeploy_manual`,
`cycle_selltop_redeploy_auto`) are tunable via the `/api/v1/backtests/dca-compare` request body
(`cycle`, `hunter`, `rotation` blocks). The UI to drive them is now **done** (front-end only).

- [x] **Param-tuning form on the Backtests page (`DcaCompareControls`)** — collapsible **Tune
  parameters** panel that edits the `cycle` / `hunter` / `rotation` blocks and re-runs the comparison.
  Kept separate from `DcaComparePanel` (input vs results = clean SoC).
  - [x] All three schema blocks exposed as collapsible groups; number inputs bounded by the schema's
    min/max/step. Field defs + defaults live once in `frontend/src/lib/dcaCompareParams.ts` (mirrors
    the backend `Field(...)`); TS request types extended in `types/backtest.ts`.
  - [x] **Reset to defaults**; **presets** (Default / Keep core / Sell everything at top / Aggressive
    dip buyer) — one click loads a set; the selector shows "Custom" when params match no preset.
  - [x] **localStorage persistence** (`profitpilot.dcaCompareParams`) — tuning survives a refresh;
    `mergeDcaParams` tolerates corrupt/partial stored JSON by falling back to defaults.
  - [x] i18n en + es for every label. Tests: `dcaCompareParams.test.ts` (10) + `DcaCompareControls.test.tsx` (5).
  - [ ] (remaining nice-to-have) Per-arm **show/hide** toggles on the chart/table (7 lines is a lot);
    show which exact param set produced the current run.
- [x] **Discrete halving windows — precise "start buying / start selling" day offsets** _(2026-08-04)_ —
  the cycle clock was Gaussian-only (intensity always partially on); now `cycle.timing_mode` picks
  between `gaussian` (unchanged default) and `windows` (hard on/off between two day-offsets since the
  halving, optional `ramp_days` easing the edges *inside* the window so "zero before day A" holds
  exactly; windows may wrap past the halving boundary; blank bounds derive from top/bottom ± sigma).
  New `CycleTiming` ABC + `GaussianTiming` / `WindowTiming` in `domain/backtest/halving_cycle.py`;
  `build_timing()` is the **only** switch on the mode and all three cycle policies now hold the
  abstraction (constructed once, so `decide()` stays O(1)). Schema + service pass the fields through;
  the tuning form renders a **Timing mode** select and reveals the day fields only in windows mode,
  plus a **Halving windows** preset. 9 new backend tests (7 timing + 2 policy-behavior) + 2 integration
  + 6 frontend. **261 backend + 109 FE tests pass, `tsc --noEmit` clean.**
  Measured (`scratchpad/run_window_timing_compare.py`, full BTC history): tight windows beat Gaussian
  (+42% / +13% coins on the two cycle arms) but the broad window is *worse* on one — i.e. the ranking
  is unstable, which is the overfitting tell. Documented as such in the README; **not** evidence of edge.
- [ ] **(stretch) Timeframe + symbol selector** for the compare tool (1d/4h, BTC/ETH/…), reusing the
  existing OHLCV DB cache. Surface the halving cycle markers per selection.

## 📈 Live Strategy Visualization (CRITICAL)

- [x] **Live strategy graph with past positions and future signals** _(2026-07-12)_ — new
  `/strategies/:id` detail page: `TradingChart` with fill markers (buy ▲ / sell ▼ from
  `order_records`) + optional faint signal-history toggle + projected latest-signal marker on the
  current bar. New backend `GET /strategies/{id}/orders` endpoint; markers built by a pure
  `buildStrategyMarkers()` (unit-tested); live updates via the executor's existing
  `strategy.signal` / `strategy.order` WebSocket broadcasts (candles poll every 20s — no Phase-1
  tick stream). Card gets a "View" link; header reuses the extracted `StatusBadge` + start/pause/
  go-live controls; scrollable order-history table below the chart. Spec + plan in
  `docs/superpowers/{specs,plans}/2026-07-12-live-strategy-visualization*`. **131 backend + 69
  frontend tests pass; `tsc -b` clean.**
  - _Not done (deferred):_ compact Dashboard version of the chart.

## 🔌 Broker — real smoke test (blocked on API keys)

- [ ] **Real Bybit testnet / Alpaca paper smoke run** — code path is covered by integration tests
  with a fake adapter; needs actual keys to run end-to-end.
  Runbook: `docs/runbooks/testnet-smoke-test.md`
  - Set `BYBIT_API_KEY` + `BYBIT_SECRET_KEY` + `BYBIT_TESTNET=true` in `backend/.env`
  - Connect via `POST /api/v1/brokers`, then `GET /api/v1/brokers/{id}/account`
- [ ] Test Binance and Alpaca adapters
- [x] **`conform_order` is on the strategy-driven order path** _(2026-08-18 — see ✅ Done)_ —
  every order a strategy generates is rounded to tick/lot at the `ExecutionEngine` chokepoint
  before it reaches `RiskManager` or a broker; opens can be rejected below the exchange
  minimum or on an unknown symbol, closes always execute (quantity unconformed on purpose,
  price rounded — see the code-review fix in Done).
- [x] **Conform the manual Trade-page order path, sized by quantity, fiat amount, or
  % of position** _(caught by code review 2026-08-19, shipped 2026-08-21)_ —
  `BrokerService.place_order` now resolves `PlaceOrderRequest.amount_type`
  (`quantity` | `notional` | `percent`) into a base quantity — notional divides by the
  current price (limit price if given, else the last 1m close via `adapter.get_market_data`);
  percent multiplies the held position size from `adapter.get_positions()` — then runs it
  through `conform_order` (round to tick/lot, reject unseeded symbols or below-min-notional)
  before it reaches `adapter.place_order`. **Deliberately skips `RiskManager`** — a manual
  order is the user overriding position-size/drawdown limits on purpose, not a bug. Only the
  `percent` mode fetches positions; `quantity`/`notional` place immediately. Route maps
  `InstrumentError` → 400 (was falling into the generic 502 "broker error"). Frontend:
  Portfolio.tsx order form has a quantity/$/% toggle. Test:
  `tests/unit/test_broker_service_order_sizing.py`.
  Binance/Alpaca route through the same `PlaceOrderRequest`, untested against a real fill yet.
- [ ] **Wire `BinanceAdapter` to the instrument catalog** — Alpaca and Bybit now take an
  injected `InstrumentCatalog`; Binance still does its own thing.
- [ ] **Refresh instrument specs from the brokers** — `seed.py` is hand-written and
  conservative. Each venue publishes the real values (Binance `exchangeInfo`, Bybit
  `instruments-info`, Alpaca `assets`); a periodic refresh into an alternate `InstrumentCatalog`
  needs no caller change, which is exactly what the interface was for.
- [ ] Implement `stream_ticks()` on all 3 broker adapters (WebSocket price feeds for live strategies)
- [ ] Live broker fill-confirmation (Bybit returns `submitted`; reconciled next poll)

## 🏗️ Infrastructure

- [ ] **Set up Alembic migrations** — tables are currently created via `create_all` on startup
  (dev only). Wire Alembic before any production use.
  - `alembic revision --autogenerate -m "description" && alembic upgrade head`
- [x] **OHLCV caching** _(2026-07-13)_ — end-to-end cache-aside test through `BacktestService`
  (`test_ohlcv_cache.py`): first run over a 200-bar range is a cache **miss** (fetch + chunked
  write), a second identical run is a **hit** served from the DB (provider awaited exactly once);
  asserts all 200 bars persisted. **Also fixed a test-isolation bug found while writing it** —
  integration tests were running against the real dev DB (`profitpilot.db`) because `.env`'s
  file-backed `DATABASE_URL` was cached before the fixture's `setdefault`; `conftest.py` now forces
  in-memory SQLite at import time. ⚠️ _Earlier test runs this session (pre-fix) executed
  `test_orders`' `DELETE order_records` and wrote synthetic bars against `profitpilot.db` — see
  session note._

## 📊 Backtesting

- [x] **DCA vs halving-cycle-grid comparison backtester** _(2026-07-29)_ — a purpose-built
  accumulation simulator (separate from the single-position `BacktestEngine`, protecting its
  live-parity guarantees) that runs three arms over the same BTC data and reports final value,
  drawdown/Sharpe, and avg cost basis side by side: **flat_dca** (benchmark), **smart_accumulate**
  (deploy scaled by Bitcoin halving-cycle intensity × price confirmation, saving dry powder for dips),
  and **full_rotation** (also distributes into the predicted top). Cycle model
  (`domain/backtest/halving_cycle.py`): deterministic halving dates → only-past "days since halving";
  Gaussian buy-intensity peaking at the predicted bottom (~535+380 days post-halving), sell-intensity
  at the predicted top; **all offsets are tunable params, not magic constants**. Ledger + policies +
  driver in `domain/backtest/accumulation.py` (DRY'd `max_drawdown_pct`/`annualized_sharpe` out of
  `metrics.py` without changing its output); costs mirror the paper adapter's model. Both capital
  models (periodic contributions + dry powder, and lump sum). `POST /api/v1/backtests/dca-compare`;
  `DcaComparePanel` (overlaid curves + metrics table + cycle markers) on the Backtests page, i18n
  en/es. **Overfitting caveat is first-class** — surfaced in the API response and UI banner, with an
  explicit no-look-ahead test — because only ~3 completed cycles means the offsets are fit to past
  tops/bottoms (a 2016–2024 backtest beats DCA almost by construction; read as one out-of-sample
  cycle, not proof). 5 halving + 8 accumulation unit + 4 integration tests; **212 backend + 86 FE
  tests pass, `tsc --noEmit` clean.** Spec + plan in
  `docs/superpowers/{specs,plans}/2026-07-29-halving-cycle-dca-comparison*`.
- [x] **Monte Carlo on the trade sequence (step 3 of 3)** _(2026-07-29)_ — turns a single backtest
  (one lucky path) into a *distribution* of outcomes. New pure `domain/backtest/monte_carlo.py`
  (vectorized numpy) resamples the **fixed-fractional per-trade return series**
  (`r_i = pnl_i / equity_before_trade_i`, so compounding in order reproduces realized final equity)
  two ways: **bootstrap** (with replacement → sampling risk, "were the results luck?") and **shuffle**
  (permutation → ordering risk, "was my drawdown a lucky order?"; final equity is order-invariant so it
  isolates drawdown-path risk). Reports percentiles of final equity / total return / max-drawdown,
  prob-of-profit, risk-of-exceeding-drawdown (threshold = the profile's total-DD limit), and a
  ruin-guarded risk-of-ruin, plus a return histogram. `MonteCarloService` runs the backtest through the
  existing `BacktestService` (single source of truth for trades — MC never re-implements execution);
  thin `POST /api/v1/backtests/montecarlo` router; `< 2` trades → 400. Frontend: opt-in **Run Monte
  Carlo** button on the Backtests page → `MonteCarloPanel` (method toggle, stats grid, Recharts return
  histogram with a realized reference line), i18n en/es. **12 domain unit + 4 integration tests; 195
  backend + 84 FE tests pass, `tsc --noEmit` clean.** Closes the backtest↔live parity work (steps 1–3).
  Spec: `docs/superpowers/specs/2026-07-29-monte-carlo-trade-sequence-design.md`.
- [x] **Full live/paper usage verified end-to-end (step 2 of 3)** _(2026-07-28)_ — new
  `test_live_paper_e2e.py` drives the REAL `StrategyExecutor` for a paper strategy across three poll
  cycles (long → reversal to short → close) against the shared in-memory DB, then asserts exactly what
  the strategy-detail page consumes: `GET /strategies/{id}/orders` (multiset opened_long/opened_short/
  closed×2, reversal close with reason "reversal" and realized_pnl>0, opened_short carries a real fill),
  `GET /signals?strategy_id=` (long/short/close), and the `strategy.signal`×3 / `strategy.order`
  WebSocket broadcasts (chronological action stream opened_long→closed→opened_short→closed). Exercises
  create-via-API → executor → RiskManager → simulated fill (with the new costs) → persist → broadcast →
  read-back-via-API, i.e. the whole chain the frontend depends on. 179 backend tests pass. Next: (3)
  Monte Carlo on trades.
- [x] **Closed the backtest↔live gap (step 1 of 3)** _(2026-07-27)_ — two divergences that made a
  backtest an unfaithful preview of paper/live:
  - **Paper trading had zero costs.** `SimulatedBrokerAdapter` filled at the exact mark (no
    commission, no slippage) while the backtest modeled both — so paper looked better than the
    backtest and real live would be worse than paper. Added a cost model **identical to the engine's**
    (slippage + commission baked into an effective fill price: BUY pays `base·(1+slip)·(1+comm)`, SELL
    receives `base·(1-slip)·(1-comm)`) — needs no new DB column, all cash/P&L accounting unchanged.
    Adapter defaults costs to 0 (pure mechanism); the executor injects `SIM_COMMISSION_PCT` (0.1%) /
    `SIM_SLIPPAGE_PCT` (5 bps) from settings (policy). 4 new tests (`test_paper_costs.py`).
  - **Backtest dropped flip trades.** A long→short signal only closed the long (never opened the
    short); a short→long was ignored entirely — so a reversing strategy traded differently in backtest
    vs live. Extracted a shared pure `domain/execution/reconcile.py::plan_actions` (the single source
    of truth for intent→action) and wired **both** the backtest engine and the live `ExecutionEngine`
    to it — a flip is now a full close→open reversal in both. Backtest gained `allow_short` (default
    True). Live engine refactor preserved every outcome/reason string. 13 + 4 new tests
    (`test_reconcile.py`, `test_backtest_reversal.py`).
  - **Fill timing left as-is** (backtest next-open, live last-close) — negligible for crypto, honest
    for daily bars; documented, not changed.
  - **178 backend tests pass**, `tsc -b` clean. Next: (2) full live-usage test in the FE, then (3)
    Monte Carlo on trades.
- [x] **Fixed two FE console errors on the Backtests page** _(2026-07-26)_
  - **`BacktestChart` crashed on duplicate timestamps** — Lightweight Charts' `setData` requires
    strictly-ascending **unique** times, but an intraday run produced two consecutive price points at
    the same second (`time=1743296400, prev=1743296400`, index 8380 — 1743296400 = 2025-03-30 01:00 UTC,
    EU DST start), throwing `data must be asc ordered by time` and unmounting the chart. Extracted a pure
    `lib/chartSeries.ts::toSeriesData` (ms→s, sort ascending, collapse duplicate timestamps keeping the
    last) used by `BacktestChart` before `setData`; **5 unit tests** cover dupes/ordering/empty.
    - **ROOT CAUSE was a BE bug, not Yahoo data** _(fixed 2026-07-27)_ — `yfinance_provider.py`
      stripped tz with `.to_pydatetime().replace(tzinfo=None)`, keeping **local wall-clock** time
      instead of UTC. yfinance returns tz-aware intraday bars localized to a market tz; around a DST
      boundary two instants collapse onto the same naive hour → duplicate/non-monotonic bars (and all
      yfinance "UTC" bars were silently off from real UTC, unlike the Bybit path). Fixed to use the
      existing `to_naive_utc()` (convert→UTC then strip). Added defense-in-depth: pure
      `domain/market_data/normalize.py::dedupe_sort_bars` applied at the `fetch_ohlcv` chokepoint so
      **no** provider can emit dup/unsorted bars; also DRY'd Bybit's inline dedup onto it. 4 unit
      tests. **Provider stays Yahoo — switching wouldn't have fixed our own tz handling.**
  - **`Received NaN for the value attribute`** — the **Initial capital** number input in `Backtests.tsx`
    ran `parseFloat(e.target.value)` with no guard, so clearing it set `initial_capital = NaN`. Now
    guards `NaN → 0` (state) and renders `''` when NaN. (Not caused by the new slippage/position-size
    fields — those were already guarded.)
  - 81 frontend tests pass, `tsc -b` clean.
- [x] **Realistic cost model — adverse slippage on every fill** _(2026-07-26)_ — the engine charged
  only a flat commission; real fills also cross the spread + market impact. `BacktestEngine` now
  applies `slippage_pct` adversely to **every** fill via `_apply_slippage` (buys fill higher, sells
  lower) — entries, signal-closes, SL/TP exits, and the end-of-data flatten, for both long and short.
  `BacktestRequest.slippage_pct` defaults to a conservative **5 bps** so backtests aren't optimistically
  frictionless; Backtests form has a **Slippage** input (i18n en/es). Engine default is `0.0`
  (back-compat for direct-engine tests). Verified end-to-end (all-in: 45.03% → 38.13% at 5% slippage).
  New `test_backtest_costs.py` (3). 153 backend + 76 FE tests pass, `tsc -b` clean.
  - _Next slippage refinement (not done):_ volatility-scaled slippage (× bar range / ATR) instead of a
    flat bps, per the "realistic cost model" Pro Idea — flat is the v1 foundation.
- [x] **Backtest position sizing now matches the live risk model** _(2026-07-25)_ — the engine went
  **all-in** (100% of capital/trade) while the live executor risks `max_position_size_pct` (2%
  default), so backtest returns overstated live by **~50×** and couldn't be trusted as a live
  predictor. `BacktestEngine` now sizes entries as `capital × position_size_pct` (long & short);
  `BacktestRequest` gained `position_size_pct` (`Optional`, `None` → service applies the live default
  `RiskConfig.max_position_size_pct`, single source of truth); Backtests form has a **Position size %**
  input defaulting to 2% (i18n en/es). Engine default stays `1.0` (all-in) so direct-engine unit tests
  remain valid. Verified end-to-end: same strategy/data gives an exact 50× ratio between all-in and 2%.
  New `test_backtest_sizing.py` (3). 150 backend + 76 FE tests pass, `tsc -b` clean.
- [x] **Bug hunt — 3 correctness bugs found & fixed** _(2026-07-25)_ — (1) **Short cash accounting
  was inverted**: closing a short *added* the buyback notional to cash (correct only for a long), so
  a flat short reported +200% return / 3× equity while the trade's own pnl was correctly 0. Added
  `BacktestEngine._capital_after_close` (long = receive proceeds; short = pay buyback + commission),
  used by both the signal-close and SL/TP-exit paths. (2) **`profit_factor = float("inf")` for
  all-winning backtests 500'd the endpoint** — Starlette serializes with `allow_nan=False`, so `inf`
  raised; the frontend's `=== Infinity` branch was dead (JSON can't carry Infinity). Now returns
  `None` (schema `Optional[float]`), frontend maps `null → ∞`. (3) covered by the sandbox fix below.
  New: `test_backtest_short_accounting.py` (3), updated `test_metrics.py` (+JSON-serializable guard).
  147 backend + 10 FE (Backtests/Builder) tests pass, `tsc -b` clean.
- [x] **Fix the strategy sandbox — it could not run *any* strategy** _(2026-07-24)_ — the Builder
  page's `sandbox_run` was completely broken: the restricted-builtins whitelist omitted
  `__build_class__` and the exec namespace had no `__name__`, so every user strategy (all of which
  *must* define a class subclassing `StrategyBase`) died at exec time with `NameError: __build_class__
  not found` / `name '__name__' is not defined`. Added both to the harness. Also fixed a swallowed
  error: the "no StrategyBase subclass" path printed a structured JSON error to stdout then
  `sys.exit(1)`, but the parent treats any non-zero exit as an opaque stderr crash — changed it to
  `exit(0)` so the helpful message reaches the user. Added **6 tests** (`test_strategy_sandbox.py`,
  the sandbox's first coverage): full SMA-crossover run producing real trades, injected
  `math`/`statistics`, no-class rejection, import blocking, unknown timeframe, insufficient data.
  144 backend tests pass.
- [x] Verify backtest uses the full requested date range _(2026-07-12)_ — now covered by an
  automated test (`test_run_backtest_forwards_requested_date_range`): asserts the requested
  `[start, end]` reaches `fetch_ohlcv` intact (hermetic via a unique symbol → forces the cache-miss
  path). No longer a manual smoke.
- [~] Confirm equity curve + buy/sell signals render correctly on the Backtests page — marker/data
  layers are unit-tested (`buildTradeMarkers`, `EquityChart` data), but the actual canvas render
  can't be asserted in jsdom. **Remaining: one manual browser smoke** (run a backtest, eyeball the
  equity curve + ▲/▼ markers).
- [x] Add pagination to backtest results if the trade list is very long _(2026-07-12)_ —
  client-side pagination in `TradeTable` (default 50/page); Prev/Next + "from–to of total" appear
  only when trades exceed the page size; page clamps if a new backtest returns fewer trades. i18n
  (en/es) + 3 tests.

## 🖥️ Frontend Pages

- [x] Dashboard — wire real portfolio data (positions, P&L, equity curve) _(2026-07-13)_ — KPIs,
  positions table, and live signals were already wired to real endpoints (`portfolio.summary`,
  `signals`); added the missing **portfolio equity curve** card (`portfolio.history` →
  `EquityChart`, empty-state when no snapshots yet). i18n (en/es) + a render test. Degrades to
  zeros/empty with no broker connected.
- [x] Portfolio — real positions from broker adapters, paginated order history _(2026-07-13)_ —
  positions/KPIs/equity-curve/place-order were already wired; added the missing **order history**:
  new user-wide `GET /api/v1/orders?limit=&offset=` endpoint (from `order_records`, newest first,
  returns `{items, total}`) + a paginated table on the Portfolio page (25/page, Prev/Next). Extracted
  `OrderRecordResponse` into shared `order_schemas.py` (used by both the per-strategy and user-wide
  endpoints); replaced the frontend `api.orders.list` placeholder with the real call. i18n (en/es) +
  2 backend + 2 frontend tests.
- [x] Replace backtest `TradeChart` (Recharts) with a Lightweight Charts version + trade markers
  _(2026-07-12)_ — new `components/backtest/BacktestChart.tsx`: Lightweight Charts **area series** of
  close prices (backtest data is close-only, no OHLC) + buy/sell markers via a pure
  `lib/tradeMarkers.ts` (`buildTradeMarkers`, unit-tested). Native scroll/drag zoom replaces the
  Recharts `Brush`. Old `TradeChart.tsx` + test removed; `EquityChart` stays Recharts per the
  chart-library split. **70 frontend tests pass; `tsc -b` clean.**
- [ ] **Request TradingView Advanced Charts access** (DEFERRED — gated on launch; needs company email)
- [ ] **Claude.ai artifact portability — gaps found while adapting the Dashboard summary**
  _(2026-08-19)_ — the real frontend stack (React 18 + TS + Vite + Tailwind + Radix) already
  matches the `web-artifacts-builder` skill's stack, so page/component code ports cleanly once
  given static data instead of live fetches. Gaps found while doing a first Dashboard-summary
  artifact (KPIs + equity curve + positions + signal feed, sample data, no backend):
  - TanStack Query hooks call live `/api/v1/...` endpoints — an artifact has no backend, so any
    ported component needs a props/sample-data variant instead of an embedded `useQuery` fetch.
  - `lightweight-charts` (TradingView, used by `PriceChart`/`TradingChart`) and
    `@monaco-editor/react` (Builder) both load assets at runtime; the artifact CSP blocks
    external hosts, so neither works unbundled — needs a Recharts-only substitute or a fully
    self-hosted/inlined bundle. Left out of the first artifact for this reason.
  - `react-router-dom` multi-page flows (Dashboard → `/strategies/:id`, etc.) don't translate to
    a single-view artifact; would need flattening to local component state.
  - Zustand stores tied to WebSocket (`/ws`) push updates assume a running app/server; fine to
    reuse for pure UI state, not for live sync.
  - `react-i18next` + locale JSON works but is unnecessary weight for a one-off artifact — inline
    just the needed strings instead of porting the i18n setup.
- [ ] **`Trade.tsx` has zero test coverage** _(surfaced 2026-08-22 during the FE UI-component
  audit)_ — the manual-trading page (symbol/timeframe toolbar, chart, indicator controls, metrics
  panel) is the one page with no render test. Chart-heavy components being untested is more
  defensible than a whole untested page.

## 🧹 Code-quality follow-ups (lower priority)

- [x] **PATCH `/strategies/{id}/config` is now a partial update** _(2026-07-13)_ —
  `StrategyService.update_config` applies only fields present in the body (`model_dump(exclude_unset=True)`);
  omitted fields keep their current value, an explicit `null` clears a risk override. Sending the full
  config (the current UI) still replaces everything, so no frontend change. Also DRY'd `_config_columns`
  onto a single `_CONFIG_FIELDS` tuple. 2 new tests + updated the pipeline test that asserted the old
  full-replacement behavior.
- [x] **Config fields — single source of truth** _(2026-07-19)_ — the two pure 1:1 mirror layers
  now derive their field set from `ExecutionConfig.model_fields` instead of hand-listing it: schema
  `from_instance` uses `model_construct(**{f: getattr(inst, f) for f in cls.model_fields})`, and the
  service's `_CONFIG_FIELDS` is `tuple(ExecutionConfig.model_fields)`. New guard test
  `test_execution_config_fields_map_to_orm_columns` fails if the schema and `StrategyInstance` ORM
  columns drift. Left `_merge_risk_config` explicit **on purpose** — it renames
  `size_pct`→`max_position_size_pct`, covers only the risk subset, and carries profile-inheritance
  (`pick`) logic; a data-driven version would be less readable. ORM columns are the irreducible 4th
  layer. Net: adding a config field = 1 column + 1 Pydantic field (was 4 hand-edits). 138 tests pass.
- [x] **Magic-number cleanup** _(2026-07-13)_ — extracted duplicated literals into
  `app/core/constants.py`: `MIN_BACKTEST_BARS` (60, was inlined in `backtest_service` + sandbox),
  `DEFAULT_WARMUP_BARS` (50, was in the engine + sandbox payload); named `_FETCH_LIMIT` (1000) in
  `backtest_service`. Left intentional per-strategy confidences (0.7/0.65/0.68/0.66) and the
  self-documenting `_infer_bars_per_year` annualization table alone. 137 tests still pass.
- [x] **Flaky `frontend/src/lib/websocket.test.ts`** _(2026-07-12)_ — no longer reproduces: ran the
  full `vitest run` 3× (70 tests) + the file in isolation, all green every time. Added defensive
  `vi.clearAllTimers()` in `afterEach` (before `vi.useRealTimers()`) to drop any pending
  reconnect/heartbeat fake timers so nothing can leak into the next file — cheap insurance against
  the documented fake-timer pollution.

## 🔭 Backlog (designed, not started)

- [ ] **Promote the halving-cycle grid to a live-deployable strategy** _(future — gated on evidence)_ —
  today the cycle-grid exists only as a *comparison backtester* (`dca-compare`). Making it run live
  through the executor needs new execution machinery the platform lacks: multi-level accumulation
  (resting limit orders / staged buys), partial-fill handling, and multi-buy position management — the
  current `ExecutionEngine` is single-position/flip-based. **Only worth building if the comparison shows
  a robust edge that survives parameter perturbation and (ideally) the next live cycle** — not just the
  overfit 2016–2024 backtest. Would inherit the existing RiskManager gate + cost model.
- [ ] **Hand-calibrated personal cycle strategy — my own measured cycle map, not a fitted one**
  _(requested 2026-08-29 — needs a design pass; blocked on my own measurements first)_
  A strategy whose cycle model **I author by hand** instead of letting the code infer it: I measure,
  from the charts myself, how many **days** each phase of the BTC cycle lasted and how far it moved
  in **percent** — bear length + depth, bull length + height, the intermediate up/down legs — and
  anchor all of it to the **halving dates**. The strategy then trades that map (accumulate through
  my measured bear window, distribute through my measured top window, sized by how far price sits
  into my measured range).
  - **What's genuinely new vs. what already exists.** `domain/backtest/halving_cycle.py` already has
    a tunable halving clock (`GaussianTiming` / `WindowTiming`, `days_to_top` ≈ 535,
    `top_to_bottom` ≈ 380, and the `windows` mode's explicit day offsets), so *timing* is partly
    covered. **Magnitude is not:** there is no per-phase "how far up / how far down in %" model
    anywhere — the closest thing is `rotation.expected_bear_drop`, a single number on one arm.
    So the new pieces are: (a) **full phase segmentation** (bear/bull/chop durations, not just
    top-day and bottom-day offsets), and (b) **a magnitude per phase**, both supplied by me.
  - **Shape it should probably take** (to decide in the design pass): a `CycleTemplate` — an ordered
    list of `(phase, start_day_since_halving, end_day, expected_move_pct)` rows I fill in — consumed
    as a third `CycleTiming` implementation alongside Gaussian/Window, so `build_timing()` stays the
    single switch and the existing arms pick it up without change. Tunable from the DCA-compare
    panel the same way the other blocks already are.
  - ⚠️ **The trap to design around, stated plainly:** measuring these numbers off the same ~3
    completed cycles I then backtest on is **still overfitting — just done by hand instead of by
    optimizer**, and it will look *more* convincing precisely because I chose the numbers myself.
    The only honest versions are: write the template down **before** running the backtest and never
    revise it to improve the result; and/or fit it on cycles 1–2 and test on cycle 3 only. Whatever
    ships must carry the same first-class overfitting caveat the `dca-compare` response and UI
    banner already carry — that caveat exists for exactly this failure mode.
  - **Open, to pin down with me** ("and so on" in the original request): whether phases are absolute
    day-offsets or fractions of the cycle; whether magnitudes are measured from the halving price,
    the prior ATH, or the prior bottom; whether ETH/other assets get their own template or inherit
    BTC's; and what happens when live price leaves the template's envelope.
- [ ] **Builder "Save to project" — promote a sandbox strategy into `user_strategies/`** _(future)_ —
  today the Builder sandbox only *backtests* pasted code against historical data using a **simplified
  harness API** (sync `generate_signals` returning `signal(LONG)` dicts, minimal `Bar`); it cannot
  save the strategy into the project. A future step should scaffold that logic into a real
  `StrategyBase` subclass (async `generate_signals` → `Signal` objects, the `on_tick` / `on_fill` /
  `get_required_symbols` / `validate_parameters` boilerplate, `@StrategyRegistry.register`) dropped in
  `backend/user_strategies/` so it can then run live/paper. **Current sandbox scope is intentionally
  minimal: fetch data → backtest → show results, nothing more.** The simplified authoring API is kept
  on purpose for fast idea iteration; the contract translation belongs in this promote step (not in
  the sandbox harness).
- [ ] **Resize open positions on size-% change** (live) — future: prompt the user
  *"restart all positions / update current positions / apply to future only?"* before re-trading.
  For now a size change only affects future entries; stops/targets adjust immediately.
- [ ] **Maintenance mode** — manual pause-all + resume AND scheduled maintenance windows,
  configurable **per broker** (brokers have different maintenance times). Pauses order placement,
  preserves positions/state, auto-resumes. Needs its own design.

---

# 🔐 Security

> **Guiding principle (2026-07-11):** Security is the **foundation for launching ProfitPilot as an
> internet SaaS (Phase 2)** — these needs are *tracked, never discarded*. In the current
> **local-only Phase 1** we implement only the security a single-user machine genuinely needs;
> everything internet-facing is deferred to Phase 2 but kept here so it's ready the day we go public.
> Rule of thumb: **anything reachable from the web belongs to Phase 2**; Phase 1 stays minimal.

## Phase 1 — local only (minimal, appropriate for a single-user machine)

- [x] **Secrets via env only** — `core/config.py` (Pydantic Settings); no hardcoded keys; `.env`
  gitignored (`**/.env`); `.env.example` holds only placeholders. _(verified 2026-07-11)_
- [x] **`DEBUG=false` by default** — `config.py` default is `False`; tracebacks/raw error messages
  are gated behind `DEBUG` in `core/errors.py`. Added a warning in `.env.example` that `DEBUG=true`
  must never run on a network-reachable host. _(2026-07-11)_
- [x] **Bind to `127.0.0.1` for local-only use** — both `be` scripts (root + `frontend/package.json`)
  and the README dev command now bind loopback; README notes the no-auth / non-hardened-sandbox
  reason and when `0.0.0.0` is acceptable. _(2026-07-11)_
- [~] **Strategy sandbox threat model documented** _(2026-07-11)_ — corrected the sandbox docstring
  + comments: restricted-builtins/`__import__=None` is a guardrail against *accidents*, **not** a
  security boundary (CPython escapes exist), and there's no network/memory isolation. Acceptable in
  Phase 1 (local single-user = code author owns the box); subprocess + 30s timeout give crash /
  runaway protection. **Real OS-level isolation (container/gVisor, no egress, cgroup limits, seccomp,
  read-only FS) is a Phase 2 item** — see Security → Phase 2.
- [x] **Dependency scanning — frontend** _(2026-07-11)_ — `npm audit fix` applied: `react-router`
  open-redirect resolved within the lockfile (patched 6.x, no breaking bump). **Verified: 61 tests
  pass (14 files), `tsc -b` clean, `vite build` succeeds.** _Accepted risk (Phase 1):_ 2 remaining
  moderates are the DOMPurify `ALLOWED_ATTR` chain via `monaco-editor` — only exploitable when
  sanitizing untrusted HTML; the Builder edits the user's *own* code on a local single-user box, so
  no attack surface. Fixing needs `--force` (pulls a monaco dev build) → deferred. Dev-only
  esbuild/vite advisories need vite@8 (breaking) → deferred (dev server, not shipped).
- [~] **Dependency scanning — backend** _(scanned 2026-07-11; `pip-audit` installed)_ — **33 known
  vulns in 10 packages.** Categorized:
  - _Web-facing (belongs to Phase 2 hardening per the phasing rule; low risk while loopback +
    single-user):_ `starlette 1.0.0` (6 — ASGI request path; fix ≥1.3.1), `aiohttp 3.13.5` (11,
    transitive; fix 3.14.1), `urllib3 2.6.3` (3; fix 2.7.0).
  - _Safe patch bumps (do soon):_ `pydantic-settings 2.14.0→2.14.2`, `cryptography 47.0.0→48.0.1`,
    `idna 3.13→3.15`, `soupsieve 2.8.3→2.8.4`, `msgpack 1.1.2→1.2.1`.
  - _Dev-only (not shipped):_ `pip 25.3` (5), `pytest 8.3.3` (1). Upgrade pip; pytest bump optional.
- [x] **`requirements.txt` reconciled to the installed `.venv`** _(2026-07-11)_ — the pins had
  drifted badly (declared `fastapi 0.115` / `numpy 1.26` / `pandas 2.2`; venv actually runs
  `fastapi 0.136.1` / `numpy 2.4.4` / `pandas 3.0.2`). Rewrote into **Active** (installed & running,
  pinned to reality) vs **Deferred** (ML / Phase-2 infra, commented so a clean install reproduces
  the working Phase-1 app). Also caught **undeclared-but-imported runtime deps** (`aiosqlite`,
  `yfinance`) that were missing from the manifest, and flagged that `anthropic` (AI Builder) isn't
  installed. Documented the **numpy 2.x / pandas 3.x vs ML-stack numpy<2 conflict**. Verified: 92
  backend unit tests pass.
- [x] **Apply backend dep fixes** _(patch bumps + pins + scan done 2026-07-12)_ — _safe patch bumps_
  applied & pinned in `requirements.txt`: `pydantic-settings→2.14.2`, `cryptography→48.0.1`, plus
  transitive `idna→3.15`, `soupsieve→2.8.4`, `msgpack→1.2.1` (pinned as security-floor with
  `Required-by` verified); also upgraded dev-only `pip 25.3→26.1.2`.
  **Re-ran `pip-audit`: 33 vulns/10 pkgs → 26 vulns/5 pkgs** (all 5 bumped packages now clean; `pip
  check` clean; 92 unit tests still pass). **Code-level scan** (injection/SQLi/deserialization/CORS/
  secrets) found no active Phase-1 flaws — one latent Phase-2 finding logged (pickle.load, below).
  _Remaining pip-audit vulns deferred per the phasing rule:_ _web-facing_ →Phase 2 (`aiohttp
  3.13.5`→3.14.1 · 11, `starlette 1.0.0`→1.3.1 · 6, `urllib3 2.6.3`→2.7.0 · 3); _dev-only_ `pytest
  8.3.3`→9.0.3 (1, optional — major bump, left as-is).
- [ ] **Keep secrets out of logs/screenshots** — standing review: no API keys in structured logs or
  error payloads (spot-checked; not exhaustively audited).

## Phase 2 — internet / web SaaS (the foundation; design before ANY public launch)

- [ ] **Authentication** — JWT register/login, password hashing (argon2id/bcrypt), refresh-token
  handling, login throttling / lockout, email verification, password reset, optional MFA.
- [ ] **Authorization / multi-tenant isolation** — every query scoped by `user_id` (row-level);
  never trust a client-supplied id. Add tests proving user A cannot read or act on user B's
  strategies / orders / brokers.
- [ ] **Encrypt broker API keys + secrets at rest** — per-user broker credentials must be encrypted
  (envelope encryption / KMS / Vault), not plaintext columns. **Single biggest data-breach risk in
  a trading SaaS.**
- [ ] **Secrets manager** — move secrets out of `.env` into Vault / cloud KMS.
- [ ] **TLS everywhere + HSTS**, plus security headers (CSP, X-Frame-Options, X-Content-Type-Options).
- [ ] **Rate limiting** (per user + per IP) and DoS protection (WAF at the edge).
- [ ] **CORS** — replace `allow_origin_regex` with an explicit production origin allowlist.
- [ ] **CSRF protection** if using cookie auth (else Bearer tokens + SameSite).
- [ ] **Sandbox hardening for untrusted multi-tenant code** — subprocess import-blocking is not
  enough when strangers run code. Move to container / gVisor / Firecracker isolation: no network
  egress, cgroup CPU/memory limits, seccomp, read-only FS.
- [ ] **Audit logging** — the `audit_log` table exists; record auth events, order placement,
  config/risk changes, and broker connects.
- [ ] **Supply chain** — dependency + container-image scanning in CI; generate an SBOM.
- [ ] **Injection review** — ORM already parameterizes queries (SQLi low risk); keep it that way (no
  raw SQL string building). Output-encode any user-derived content (XSS).
- [ ] **Untrusted model-artifact deserialization** — `forecasting/adapters/xgboost_adapter.py::load`
  uses `pickle.load` on `artifact_path`. Safe in Phase 1 (ML stack not installed; paths are
  internal), but pickle = arbitrary-code-execution if a path/blob ever becomes user-influenced under
  multi-tenant. Before wiring ML SaaS: constrain `artifact_path` to an allowlisted dir and/or switch
  to a non-executable format (xgboost native `save_model`/`load_model`, safetensors, joblib w/ trust).
- [ ] **Broker webhook/callback signature verification** (if brokers push fills/events).

---

# 🔮 Future Phases

## 🤖 ML / Forecasting (Phase 1.5+)

- [ ] PyTorch / XGBoost / LightGBM / Darts adapters — stubs exist, not implemented
- [ ] NeuralProphet integration
- [ ] Rust math library (`rust_math/`) — PyO3 bindings for indicators and Monte Carlo
  (`cd rust_math && cargo build --release`). **Kept, not extended** — Python first; see 🚦
  Housekeeping.

## 🌐 Phase 2 — SaaS infrastructure

> Security for this phase lives in [🔐 Security](#-security) above; this section is
> infra / scaling only.

- [ ] Multi-tenant DB — `user_id` FKs already in place (isolation *enforcement* is a Security item)
- [ ] Billing integration
- [ ] Replace SQLite with TimescaleDB (PostgreSQL + hypertables) for production
- [ ] Docker Compose full stack (TimescaleDB, Redis, Celery worker/beat, API, frontend)
- [ ] User registration + login UI (backed by the auth work in Security)
- [ ] **Scale web server: Gunicorn + UvicornWorkers**
  - Current: single Uvicorn process with `--reload` (dev only, no supervision)
  - **BLOCKER:** `strategy_executor` and `portfolio_snapshot_loop` are module-level singletons —
    multiple workers would each run their own copy. Move both to Celery first.
- [ ] **Move background tasks to Celery** (prerequisite for multi-worker Uvicorn)
  - `strategy_executor` loop → Celery periodic task (beat scheduler)
  - `portfolio_snapshot_loop` → Celery periodic task
  - Redis is already in `docker-compose.yml` as the broker
- [ ] **WebSocket broadcasting with Redis pub/sub** — the in-memory WS manager only works
  single-process; with multiple workers a message in worker A won't reach clients on worker B

---

# 💡 Pro Ideas — discuss later

Higher-leverage directions worth a real design conversation. These separate a hobby backtester
from a platform you'd trust with money. Roughly ordered by value-for-effort.

### Backtest realism & robustness
- [ ] **Walk-forward / out-of-sample validation** — rolling in-sample optimize → out-of-sample test
  windows. Single-period backtests overfit; walk-forward is the honest way to report expected edge.
- [x] **Monte Carlo on the trade sequence** _(done 2026-07-29 — see 📊 Backtesting step 3)_ —
  resample/shuffle the realized trades thousands of times to get a *distribution* of drawdown and final
  equity, not one lucky path. Answers "how bad could a normal run get?" — directly feeds position sizing.
- [ ] **Event-driven backtester (kill look-ahead bias)** — audit the current engine for subtle
  future-peeking (indicator warm-up, same-bar fill at close, survivorship). A bar-by-bar
  event loop that only ever sees past data makes backtest≈live much tighter.
- [ ] **Realistic cost model** — slippage as a function of volatility/spread + partial fills +
  latency, not a flat commission %. A strategy that's profitable at 0 slippage and dead at 2bps
  is one you want to *know* is fragile before going live.

### Live safety & observability
- [ ] **Live-vs-backtest drift monitor** — run the same strategy in paper alongside live and alert
  when realized fills/P&L diverge from the backtest's expectation band. Early warning that the
  edge has decayed or something's mis-wired.
- [ ] **Portfolio-level risk (not just per-strategy)** — correlation-aware sizing + "portfolio heat"
  (total risk across all open positions). Today each bot risks 2% independently; five correlated
  longs is really one 10% bet. A portfolio RiskManager caps aggregate exposure.
- [ ] **Alerting** — Telegram / Discord / email on signal fired, drawdown limit hit, kill switch
  tripped, or broker disconnect. Cheap to add, huge for trust when running real money.
- [ ] **Reconciliation loop** — periodically diff our believed positions against the broker's truth
  and auto-correct / alert on mismatch (missed fills, manual trades, partial fills).

### Capital allocation & meta-strategy
- [ ] **Strategy ensembling / dynamic allocation** — allocate capital across running strategies by
  live risk-adjusted return (Sharpe, or Kelly-capped). Turn a portfolio of bots into one managed
  book instead of N independent gamblers.
- [ ] **Market-regime detection** — classify trend/chop/high-vol regimes and enable/size strategies
  per regime (a mean-reversion bot should stand down in a strong trend). Even a crude vol/ADX
  gate meaningfully lifts a multi-strategy book.

### ML / forecasting (Phase 1.5 done right)
- [ ] **Feature store + leakage guards** — a single pipeline computing features with strict
  point-in-time correctness, shared by backtest and live. Most ML-trading failures are silent
  train/serve skew; a shared store is the fix.
- [ ] **Probabilistic forecasts, not point predictions** — have `ForecastingModelAdapter` return a
  distribution/confidence, and let sizing scale with conviction. A 51% and a 90% signal should not
  be the same trade.

### 🧭 Borrowed from a competing trading app (added 2026-08-14)

> A feature list copied from another trading app the user liked. Captured verbatim-ish as a wishlist —
> **not yet designed or scoped**. Several items overlap with things already listed above; those are
> cross-referenced so we don't build them twice.

**Correctness / safety**
- [ ] **Position reconciler** — periodic diff of broker-reported positions/orders vs expected state,
  per adapter; log drift, correct behind a flag.
  _(Same idea as **Reconciliation loop** under Live safety & observability — merge when designing.)_
- [ ] **Deterministic `client_order_id`** = `hash(strategy, signal_id, destination, intent)`;
  idempotent submit on retry.
- [ ] **Adapter state machine** Online / Degraded / Offline via heartbeat + staleness threshold;
  Degraded blocks entries, allows exits.
- [ ] **Global kill switch** — halts all submission, persisted across restart, flatten-or-hold choice,
  visible in the UI header. _(Today the kill switch is per-strategy inside `RiskManager`.)_
- [ ] **RiskManager check per destination** with its own equity basis, not per signal.

**Instruments & costs**
- [x] **Canonical instrument registry** _(2026-08-15, wired live 2026-08-18 — see ✅ Done)_ —
  internal symbol → per-broker symbol, tick size, lot step, min notional, multiplier, spot/perp;
  fails loud on unknown. `conform_order` is on the live `ExecutionEngine` order path.
- [ ] **Funding rates + commission tiers + slippage in the backtest cost model.**
  _(Extends the flat-bps model shipped 2026-07-26; see **Realistic cost model** above.)_
- [ ] **Single `Trade` record** with net P&L incl. fees/funding, used by all consumers;
  break-even epsilon.

**Analytics**
- [ ] **Shared stats library** across backtest / walk-forward / paper / live, computed on **returns,
  not currency**: expectancy, profit factor, SQN, Kelly, Sharpe, Sortino, Calmar, max DD + DD
  duration, streak Z-score, hold-time buckets.
  _(`domain/backtest/metrics.py` is the natural seed — it already owns `max_drawdown_pct` /
  `annualized_sharpe` for both the engine and the accumulation simulator.)_
- [ ] **Pivot view over the trade journal** — rows × columns × metric
  (symbol, side, hour, weekday, duration, strategy, regime).
- [ ] **Correlation ID** signal → order → fill → trade; downloadable log bundle.

### 🔌 Internal MCP server — drive ProfitPilot from an agent _(discuss later)_

> **Explicitly a discussion item, not a decision.** Captured because the workflow it would
> replace is one we already do by hand.

- [ ] **Expose the backtest surface as MCP tools** — `run_backtest`, `dca_compare`,
  `monte_carlo`, `list_strategies`, `fetch_ohlcv` over the Model Context Protocol, so a
  backtest can be run and iterated conversationally instead of through the UI. There is no
  `mcp` dependency today. The honest case for it: the `scratchpad/run_*.py` spikes exist
  precisely because driving a parameter sweep through the UI is slow — that is the loop this
  would close. The services already exist; MCP would be a thin adapter over them, and
  `MonteCarloService`'s "never re-implement execution, always go through `BacktestService`"
  rule is the model to copy so the MCP layer can't become a second execution path.
- [ ] **Parallel agents / skills over the family modules** — once families are registry-driven
  (see 🧱 Strategy-family architecture), independent families can be developed, swept, and
  reviewed in parallel by separate agents without shared state. Depends on the contracts
  landing first; without them, agents would collide in the same files.
- [ ] **Open questions before committing to any of this** — is the value real or is it a
  faster path to overfitting? A conversational sweep makes it trivially easy to fish for a
  flattering parameter set, which is the exact failure mode the README's overfitting caveat
  already warns about. Any MCP sweep tool should report walk-forward / out-of-sample results
  by default, not in-sample bests.

### Product / platform
- [ ] **Strategy marketplace** — share/discover community strategies ranked by *live* (not
  backtested) Sharpe. The trust anchor is verified live track record.
- [ ] **Paper-trading tournament** — run many strategies in parallel, leaderboard by risk-adjusted
  return in real time. Natural funnel for the marketplace and for the user's own selection.
- [ ] **Automated parameter tuning** — Optuna / Bayesian search over strategy params, but always
  reported through walk-forward so it doesn't just overfit prettier.

---

# ⏸️ Do Last (explicitly deprioritized)

> Parked here on purpose — **not needed for Phase 1**. In the current local test phase strategies
> are written **manually** (built-ins + `user_strategies/*.py`), so the AI code-generation feature
> is the very last thing to wire up. **Any user-facing Claude usage — the Builder's "generate"
> button — is Phase 3 material** _(user call, 2026-08-18)_: not this phase, not the next, revisit
> once the platform has users beyond the one local one. Nothing below is active work.

- [ ] **Builder — AI generation end-to-end** _(deprioritized 2026-07-12; pushed to Phase 3
  2026-08-18)_ — test `/api/v1/builder/generate` (plain-English → strategy code via Claude,
  model id in `ANTHROPIC_MODEL`). Needs `pip install anthropic` (currently a deferred dep)
  **and** `ANTHROPIC_API_KEY` in `backend/.env` (billable per call). The Builder page's Monaco
  editor + subprocess sandbox backtest already work without it; only the generate button
  depends on this.
  - [ ] **Prompt caching** — the ~50-line sandbox-contract system prompt is byte-identical on
    every call and would be re-sent (and re-billed) in full each time. A `cache_control`
    breakpoint on the system block is a near one-line change once the endpoint is live.
  - [ ] **Structured output instead of regex-scraping JSON** — the handler does
    `re.search(r'\{[\s\S]*\}', raw)` over the model's prose. Any prose containing a stray
    brace, any truncation at `max_tokens`, and it 500s with "AI returned unexpected format".
    Tool use / a JSON schema would make `code` + `explanation` come back shape-guaranteed.
  - [ ] **The endpoint violates our own layering** — `api/routes/builder.py` holds the system
    prompt, the SDK client construction, the API call, and the response parsing; `CLAUDE.md`
    says routers hold no business logic and every model call goes through an adapter, and
    this bypasses `LLMEnrichmentAdapter` to hit `AsyncAnthropic` directly. Extract to
    `services/strategy_generation_service.py` + an adapter under `domain/llm/` — do this
    together with the two items above, same code, one pass. Also reads
    `os.getenv("ANTHROPIC_API_KEY")` directly instead of `settings`, a second source of truth.

---

# ✅ Done

Completed work, most recent first. Kept in detail because it records design decisions.

## 🧭 Canonical instrument registry — built, wired, and two symbol bugs killed (2026-08-15)

The registry existed as three uncommitted modules but had **no `__init__.py`**, so
`from app.domain.instruments import INSTRUMENTS` failed and **the entire backend unit suite
could not collect** — all 199 tests, not just the new ones. Fixed, then wired.

- **`domain/instruments/`** — `base.py` (new `InstrumentCatalog` ABC), `instrument.py`
  (model + `conform_order`), `registry.py` (`InstrumentRegistry`, now implements the ABC),
  `seed.py` (25 crypto spot + 3 perps + 23 equities/ETFs), `__init__.py` (public surface +
  the `INSTRUMENTS` singleton).
- **Callers depend on the abstraction, never the implementation.** Adapters take
  `instruments: InstrumentCatalog = INSTRUMENTS` by constructor injection — so a
  broker-refreshed or DB-backed catalog drops in with no adapter change, and tests inject a
  three-symbol catalog instead of the full seed. `register()` is deliberately **not** on the
  interface: consumers read, they do not mutate.
- **Two real bugs found and fixed while wiring:**
  - `BybitAdapter._resolve_category` ignored its `symbol` argument entirely and
    **always returned `"linear"`** — every spot order was submitted against the perpetual
    product. Bybit spells spot and perp identically (`BTCUSDT`), so the string genuinely
    cannot answer this; the catalog can, because they are separate instruments
    (`BTCUSDT` vs `BTCUSDT.P`).
  - `AlpacaAdapter` decided market type with `"/" in symbol`, which calls the canonical
    `BTCUSDT` a stock and routes it to the equities data client. Now reads `market_type`
    from the catalog, with the old shape heuristic kept only as an unseeded-symbol fallback.
  - Both adapters translate to venue notation via `symbol_for` (`BTCUSDT` → `BTC/USD` at
    Alpaca), and Alpaca now keys the bars response by the symbol it actually asked for.
  - Unknown symbols **warn and fall back** rather than raise — an unseeded symbol must not
    break an in-flight order; the log line is the signal to seed it.
- **Also de-versioned the docs** — `CLAUDE.md` pinned `claude-sonnet-4-6`, which had gone
  stale. Model id now lives only in `ANTHROPIC_MODEL` (`core/config.py`), read by
  `builder.py`; `CLAUDE.md` gained a standing rule against pinning anything that ages faster
  than the architecture (model ids, dep versions, test/page counts). Fixed three other stale
  claims: locales are at `src/i18n/locales/` not `src/locales/`, and the route table was
  missing `/trade` and `/strategies/:id`. `.env.example` documents `ANTHROPIC_MODEL`
  commented out on purpose — an empty value there would override the default with `""`.
- **26 registry + 11 adapter-wiring tests; 236 backend unit tests pass** (was 199 blocked).

_Not done at the time:_ `conform_order` wasn't yet on the live order path, and Binance wasn't
wired — both tracked below; the order-path half is now done (2026-08-18).

## 🎯 `conform_order` on the live order path — the registry actually gates orders now (2026-08-18)

`ExecutionEngine._submit` (the single chokepoint every open/close order passes through) now
conforms to the instrument's tick/lot grid **before** `RiskManager.approve_order` and before
`BrokerAdapter.place_order` — not after, as originally planned: `RiskManager` must size-check
the exact quantity that will be submitted, not a pre-rounding one, so conform has to come first.

- **Opens are validated and can be rejected** — `conform_order` runs in full; an
  `InstrumentViolation` (below `min_qty`, below `min_notional`, or not listed on the broker)
  returns `ACTION_REJECTED` with the violation's message, same shape as a `RiskVeto` rejection,
  and never reaches the broker. An order too small to clear the exchange's minimum must never
  open a position in the first place.
- **Closes conform the price only, never the quantity** — round to tick, but pass the held
  quantity through **unchanged**. This is a correction from code review (see below): the
  original version also `floor_to_step`'d the close quantity, which zeros out a held amount
  smaller than one lot step (dust from a partial fill, or a legacy pre-registry position) —
  submitting a nonsensical **0-quantity order** instead of exiting the position, while
  `realized_pnl` (computed by the caller from the raw held quantity) would still get booked
  as if the close had happened. A close exits exactly what's held; it never opens a new
  increment, so it was never a "lot-step" question in the first place.
- **An unseeded symbol rejects an open, but never blocks a close** — this took a correction
  mid-session: the first pass let an unseeded symbol pass through unconformed on *both* opens
  and closes, which contradicts `UnknownInstrument`'s own documented contract ("deliberately
  fatal … guessing a tick size is how orders get routed to the wrong product"). Fixed so an
  **open** on an unseeded symbol is rejected outright (nothing to validate against — the
  original bug this whole effort was meant to prevent), while a **close** on an unseeded
  symbol still passes through unconformed, because a position already held must always be
  closable regardless of catalog coverage.
- `ExecutionEngine` takes `instruments: InstrumentCatalog = INSTRUMENTS` by constructor
  injection, same pattern as the broker adapters.
- The `Fill` record now carries the conformed quantity/price (`order.quantity` /
  `order.limit_price`), not the pre-conform sizer output, so persisted fills match what was
  actually submitted.
- **8 new tests** (`test_execution_engine_instruments.py`): injection, lot-step flooring
  (opens), tick rounding, min-notional rejection, close-never-blocked, close-quantity-never-
  floored-even-below-one-lot-step (locks in the code-review fix above), unseeded-open-
  rejected, unseeded-close-still-allowed. **306 backend unit + integration tests pass**
  (was 298).

**Caught by `superpowers:requesting-code-review` the same day, fixed same session** — the
close-quantity-flooring bug above (Important #1) and one still-open gap it surfaced
(Important #2, tracked separately below: `BrokerService.place_order`, the **manual**
Trade-page order path, calls `adapter.place_order` directly and never goes through
`ExecutionEngine._submit` — so manual orders get correct symbol/category routing from the
adapters, but skip tick/lot/min-notional conformance entirely). Both were independently
re-verified by reading the code before being accepted, not applied on the review's say-so.

⚠️ **Operational note:** any strategy instance configured on a symbol **not** in
`domain/instruments/seed.py` will have its next open rejected (`ACTION_REJECTED`,
"Unknown instrument"). Existing open positions on an unseeded symbol are unaffected — they
still close normally. Before relying on this in paper/live, check `seed.py` covers every
symbol currently configured on an active strategy instance; add any gap there.

_Still open:_ Binance isn't wired to the catalog. The registry seed is hand-written; refreshing
it from each broker's live instruments endpoint is the natural follow-up. **The manual
Trade-page order path is not conformed** — see the Active section below.

## 🔎 Risk-profile redesign — per-user defaults + per-strategy overrides (2026-07-11)

**Decision:** SL/TP + account-level risk limits belong to a **per-user risk profile**; strategies
carry behavior (symbol, timeframe, params, `size_pct`, `allow_short`, `poll_seconds`) plus
**optional** risk overrides (blank = inherit the profile). Backtests get their own arrangeable SL/TP.

- [x] **Phase 1 — per-user `RiskProfile`**: `risk_profiles` table (SL, TP, max positions,
  daily/total drawdown, orders/min, kill switch) + repo + `RiskProfileService` (get-or-create
  seeded from global defaults) + `GET`/`PUT /api/v1/settings/risk`. New table auto-created by
  `create_all`. 4 tests.
- [x] **Phase 2 — profile + per-strategy overrides**: risk columns on `StrategyInstance` are now
  **nullable overrides** (null ⇒ inherit); `_merge_risk_config(profile, instance)` merges
  profile + non-null overrides + `size_pct`. `ExecutionConfig` risk fields optional. Dev DB
  rebuilt (nullable) preserving data + FK children.
- [x] **Phase 3 — backtest SL/TP**: `BacktestEngine` applies intrabar stop-loss / take-profit exits
  (fills at the trigger price, stop checked first); `stop_loss_pct`/`take_profit_pct` added to
  `BacktestRequest`. 3 engine tests.
- [x] **Phase 4 — frontend**: Settings **Risk defaults** form; Strategies config = behavior +
  optional risk overrides (blank = inherit, card shows "Profile" when inherited); Backtest
  **SL/TP inputs** pre-filled from the profile. Types + api client + i18n (en/es).
- [x] **Correction applied**: changing the user default risk does **not** restart running bots — it
  only refreshes form pre-fills. Only a strategy's own edit makes its live bot adapt.
- **Final counts:** backend 129 tests, frontend 59 tests (13 files), tsc clean.

## 🔎 Code review — live-trading pipeline (2026-07-10 → 07-11)

Multi-agent review of the live-trading pipeline; all confirmed bugs fixed + tested.

- [x] RiskManager float-safe position-size check (relative tolerance) — sizer targets exactly the
  cap; `qty*price` could float above it and spuriously veto an entry
- [x] RiskManager checks evaluated lazily — a veto no longer lets `_check_order_rate` consume the
  per-minute budget for orders that never reached the broker
- [x] `_rehydrate_risk_state` counts only the strategy's symbol — an account-wide `get_positions()`
  was inflating `open_position_count` and could veto the first order after restart
- [x] Reactivating a halted strategy clears the kill-switch (`release_halt`) — was silently vetoing
  every order forever
- [x] Live adapter errors record an error outcome + advance `error_count`/halt instead of
  propagating and retrying forever
- [x] `_last_bar_ts` cleared on `_stop` + halt path — fixes a leak and lets a config reload
  re-evaluate the current bar immediately
- [x] `stop_loss_pct`/`take_profit_pct` must be `> 0` — a 0% stop/target = trigger price at entry
- [x] `_trade_on_signals` now `session.rollback()`s before recording an error outcome — a DB-origin
  failure had left the session poisoned (`PendingRollbackError`), so `error_count` never advanced
- [x] `ExecutionConfig.from_instance` uses `model_construct` — reading a persisted row no longer
  re-runs input validators (a legacy out-of-range value would have 500'd the list endpoint)
- [x] Frontend config fields switched to `type=text inputMode` + on-blur resync — decimal typing
  isn't wiped and a blanked required field can't silently submit a stale value
- [x] `load_user_strategies()` no longer globs the filesystem every poll (only when a class is
  unregistered); removed a dead import

**Design decisions — resolved:**
- [x] **NEUTRAL treated as CLOSE** — NEUTRAL = "go flat" (synonym for CLOSE). A strategy that wants
  to hold should return no signal. Documented in the engine.
- [x] **`peak_equity` persisted across restarts** — new `strategy_instances.peak_equity` column;
  `RiskManager.observe_equity()` tracks the high-water mark every cycle, persisted in
  `_update_instance`, and `seed_state(peak_equity=…)` seeds it on boot so the total-drawdown kill
  switch keeps its true baseline while underwater.

## 🧠 Strategy System — live/paper trade pipeline

- [x] **Full trade pipeline wired into the executor** (2026-07-05) — signal → sizing → RiskManager
  → BrokerAdapter → fill handling. `domain/execution/position_sizer.py` (pure sizing + stop/TP
  levels) and `domain/execution/execution_engine.py` (`ExecutionEngine`: loop-managed exits →
  idempotent position state machine → risk gate → placement → `ExecutionOutcome`).
  `SimulatedBrokerAdapter` for `paper` (fills at latest close, DB-persisted virtual ledger);
  `live` resolves a real broker connection. New `order_records` table + repo (one row per attempt).
  Exits bypass the risk veto; only opens are gated. 33 new tests, 96% coverage on new modules.
- [x] **Per-strategy execution/risk config** (2026-07-06) — real columns on `strategy_instances`;
  `ExecutionConfig` schema wired into create + response; `PATCH /strategies/{id}/config`; executor
  builds each strategy's `RiskConfig` + `allow_short` + poll cadence from its own row.
  **Live reload** (2026-07-07): `notify_config_change()` restarts a running strategy's loop on a
  config `PATCH`.
- [x] **New-bar gating** (2026-07-07) — regenerate signals only once per closed bar; exit/stop
  checks still run every poll.
- [x] **Rehydrate RiskManager state on restart** (2026-07-09) — `boot()` seeds each strategy's risk
  state from persisted broker/ledger truth via `seed_state()` (peak equity + open-position count).
- [x] **Daily-P&L continuity across restarts** (2026-07-10) — each close persists its realized P&L
  on the `OrderRecord`; `boot()` sums today's (UTC) closes back into `daily_pnl`.
- [~] **Live-path testing** (2026-07-10) — `live` path covered by integration tests with a fake
  adapter. Real smoke run still pending (see Active / Broker).
- [x] **User-defined strategies auto-load** from `backend/user_strategies/*.py` (2026-07-10) —
  executor loads user classes on demand; added `user_strategies/always_long.py` (`AlwaysLong`)
  deterministic test strategy for the smoke run.

## 🖥️ Frontend — manual-trading chart with indicators (Lightweight Charts)

> **Decision:** Recharts stays for portfolio/equity/value charts; TradingView Lightweight Charts
> (free, npm) for ALL price/trading charts. Indicators computed client-side, all adjustable.

- [x] Install `lightweight-charts` (v4)
- [x] `lib/indicators.ts` — pure indicator math (overlays: SMA, EMA, WMA, Bollinger, VWAP, PSAR;
  sub-panels: Volume, RSI, MACD, Stochastic, ATR)
- [x] `components/charts/TradingChart.tsx` — candlesticks + volume + overlays + indicator sub-panes
- [x] `components/charts/IndicatorControls.tsx` — toggle + edit params
- [x] `components/charts/ChartMetricsPanel.tsx` — live price/%/OHLC/period-high-low/volume readout +
  open position + unrealized P&L for the symbol
- [x] New dedicated `/trade` page (Markets); wired route, sidebar, i18n (en/es)
- [x] Migrate Dashboard `PriceChart` → lightweight candlestick chart

## 🔴 Early fixes (2026-07-02)

- [x] **BE error visibility** — `app/core/errors.py` (`AppError` hierarchy + stable `ErrorCode`s);
  `register_exception_handlers(app)`; consistent `{"error": {...}}` shape; tracebacks only when
  `DEBUG=true`; 422s name failing fields.
- [x] **FE error messages** — `lib/errors.ts` (typed `ApiError` + `friendlyError()`); `request()`
  parses the structured envelope; toast system; wired into Backtests + Builder; i18n en/es.
- [x] **Fix naive/aware datetime comparison in `/backtests/run`** — `to_naive_utc()` util +
  `@field_validator` on `BacktestRequest.start`/`.end`.
- [x] **Fix backend 500 on startup** — was stale; app imports cleanly, `create_all` runs, endpoints
  return 200.
- [x] **Fix `npm run start` from root** — `be` script now `python -m uvicorn …` (resolves uvicorn via
  the Python interpreter on PATH).
- [x] **Backend test suite green** — installed missing test deps; fixed stale
  `test_market.py` patch target. Full suite passing.
