"""Multi-buy accumulation simulator for DCA-vs-cycle-grid comparison.

Separate from BacktestEngine on purpose: grid/DCA accumulate a position across many buys,
whereas the engine is single-position/flip-based (and underpins backtest<->live parity). A
ledger tracks units/cash/cost-basis; injected deployment policies decide how much to buy/sell
each bar (open/closed — new arms = new policies). Costs mirror the paper adapter's model:
a BUY pays price*(1+slip)*(1+comm), a SELL receives price*(1-slip)*(1-comm).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, List, Optional, Protocol, Tuple

from app.core.types import OHLCV
from app.domain.backtest.halving_cycle import CycleParams, buy_intensity, sell_intensity
from app.domain.backtest.indicators import atr, ema, rolling_percentile, sma, supertrend
from app.domain.backtest.metrics import EquityPoint, annualized_sharpe, max_drawdown_pct


def bars_per_day(bars: List[OHLCV]) -> float:
    """Bars per calendar day, from the median gap between bars (1.0 for daily, 6.0 for 4h, ~1/7 for
    weekly). Used to normalize per-bar ``*_daily`` rates so a strategy behaves the same per *day*
    regardless of timeframe — otherwise a 0.15/bar rate fires 6× as often on 4h as on 1d."""
    if len(bars) < 2:
        return 1.0
    deltas = sorted((bars[i + 1].timestamp - bars[i].timestamp).total_seconds()
                    for i in range(len(bars) - 1))
    median = deltas[len(deltas) // 2]
    return 86400.0 / median if median > 0 else 1.0


@dataclass
class AccumulationLedger:
    """Moving-average cost-basis ledger.

    ``cost_basis`` is the total cost of *currently-held* units — a buy adds the cash spent,
    a sell removes cost proportionally at the running average. This keeps ``realized_pnl``
    (gain on units actually sold) and ``avg_cost_basis`` (basis of remaining inventory)
    correct across repeated buy/sell rotation. An earlier lifetime-average version
    (buy_notional / units_bought) never reduced the cost pool on sells, which understated
    the basis and wildly inflated realized_pnl for any selling strategy.
    """
    commission_pct: float
    slippage_pct: float
    units: float = 0.0
    cash: float = 0.0
    contributed: float = 0.0
    cost_basis: float = 0.0       # total cost of currently-held units
    realized_pnl: float = 0.0

    def contribute(self, amount: float) -> None:
        self.cash += amount
        self.contributed += amount

    def buy(self, cash_amount: float, price: float) -> None:
        cash_amount = min(cash_amount, self.cash)
        if cash_amount <= 0 or price <= 0:
            return
        eff = price * (1 + self.slippage_pct) * (1 + self.commission_pct)
        units = cash_amount / eff
        self.cash -= cash_amount
        self.units += units
        self.cost_basis += cash_amount

    def sell(self, unit_amount: float, price: float) -> None:
        unit_amount = min(unit_amount, self.units)
        if unit_amount <= 0 or price <= 0:
            return
        eff = price * (1 - self.slippage_pct) * (1 - self.commission_pct)
        proceeds = unit_amount * eff
        cost_removed = self.avg_cost_basis * unit_amount
        self.realized_pnl += proceeds - cost_removed
        self.units -= unit_amount
        self.cost_basis -= cost_removed
        self.cash += proceeds

    def equity(self, price: float) -> float:
        return self.cash + self.units * price

    @property
    def avg_cost_basis(self) -> float:
        return self.cost_basis / self.units if self.units > 0 else 0.0


@dataclass
class RunContext:
    capital_model: str            # "contributions" | "lump_sum"
    contribution_amount: float
    lump_sum_budget: float
    n_bars: int


class DeploymentPolicy(Protocol):
    def prepare(self, bars: List[OHLCV]) -> None: ...
    def decide(
        self, i: int, bars: List[OHLCV], ledger: AccumulationLedger, ctx: RunContext
    ) -> Tuple[float, float]:  # (buy_cash, sell_units)
        ...


class FlatDcaPolicy:
    """Benchmark: deploy the fixed contribution each contribution bar (contributions mode),
    or an even slice of the budget every bar (lump-sum mode)."""

    def prepare(self, bars: List[OHLCV]) -> None:
        return None

    def decide(self, i, bars, ledger, ctx) -> Tuple[float, float]:
        if ctx.capital_model == "lump_sum":
            return (ctx.lump_sum_budget / ctx.n_bars, 0.0)
        # contributions mode: spend whatever cash the just-added contribution left.
        return (ledger.cash, 0.0)


class CycleWeightedPolicy:
    """Deploy scaled by cycle buy-intensity x price confirmation; optionally distribute into
    the predicted-top window. Precomputes running expanding-high and rolling-window high/low
    (only-past) in prepare(), so decide() is O(1) and look-ahead-free."""

    def __init__(
        self,
        params: CycleParams = CycleParams(),
        *,
        distribute: bool = False,
        k_buy: float = 0.5,
        k_sell: float = 0.35,
        conf_floor: float = 0.2,
        rolling_window: int = 90,
        dd_ref: float = 0.5,
    ) -> None:
        self.params = params
        self.distribute = distribute
        self.k_buy = k_buy
        self.k_sell = k_sell
        self.conf_floor = conf_floor
        self.rolling_window = rolling_window
        self.dd_ref = dd_ref

    def prepare(self, bars: List[OHLCV]) -> None:
        self._exp_high: List[float] = []
        self._roll_high: List[float] = []
        self._roll_low: List[float] = []
        run_high = float("-inf")
        for i, bar in enumerate(bars):
            run_high = max(run_high, bar.high)
            self._exp_high.append(run_high)
            lo = max(0, i - self.rolling_window + 1)
            window = bars[lo : i + 1]
            self._roll_high.append(max(b.high for b in window))
            self._roll_low.append(min(b.low for b in window))

    @staticmethod
    def _clamp(x: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, x))

    def decide(self, i, bars, ledger, ctx) -> Tuple[float, float]:
        d = bars[i].timestamp.date()
        price = bars[i].close

        # Buy confidence: deeper below the running all-time high => stronger (grid-like).
        exp_high = self._exp_high[i]
        drawdown = (exp_high - price) / exp_high if exp_high > 0 else 0.0
        buy_conf = self._clamp(self.conf_floor + (1 - self.conf_floor) * (drawdown / self.dd_ref),
                               self.conf_floor, 1.0)
        deploy_frac = self._clamp(self.k_buy * buy_intensity(d, self.params) * buy_conf, 0.0, 1.0)
        buy_cash = deploy_frac * ledger.cash

        sell_units = 0.0
        if self.distribute:
            hi, lo = self._roll_high[i], self._roll_low[i]
            pos_in_range = (price - lo) / (hi - lo) if hi > lo else 0.0   # near recent high => 1
            sell_conf = self._clamp(pos_in_range, 0.0, 1.0)
            sell_frac = self._clamp(self.k_sell * sell_intensity(d, self.params) * sell_conf, 0.0, 1.0)
            sell_units = sell_frac * ledger.units

        return (buy_cash, sell_units)


@dataclass(frozen=True)
class CycleHunterParams:
    """Tunable knobs for CycleHunterPolicy. Defaults documented in the design spec."""
    ema_fast: int = 50
    sma_slow: int = 200
    st_period: int = 10
    st_mult: float = 3.0
    atr_period: int = 14
    atr_pctile_window: int = 365
    ath_sell_trigger: float = 0.95      # price >= this fraction of ATH to consider distributing
    sell_intensity_hi: float = 0.30     # halving sell_intensity threshold for "near top window"
    atr_pctile_hi: float = 0.60         # volatility regime that confirms euphoria at the top
    sell_cap_frac: float = 0.30         # never sell more than this fraction of the stack (keep a core).
                                        # 0.30 is the full-history sweet spot: trimming less keeps more
                                        # of the secular uptrend, beating heavier rotation on both value
                                        # and drawdown (see 2026-07-30 sweep).
    k_sell_daily: float = 0.15          # per-bar sell rate while distributing
    cooldown_days: int = 90             # "wait 3 months on the ATH" before re-accumulating
    reentry_within: float = 0.15        # stop aggressive buying once price is within this of prior ATH
    dd_ref: float = 0.70                # drawdown that maps to full-depth deployment
    k_bear_daily: float = 0.05          # per-bar dry-powder deploy rate in the bear
    bear_floor: float = 0.02            # minimum per-bar deploy in the bear (always buys something)


class CycleHunterPolicy:
    """ATH-aware rotation state machine (see 2026-07-30-cycle-hunter-design.md).

    Halving windows are the master clock; EMA/SMA trend, Supertrend direction, and ATR
    percentile confirm. Four states: ACCUMULATE_BASE (DCA), DISTRIBUTE (trim into the top,
    keeping a core), COOLDOWN (~3 months of no buying after a confirmed top), BEAR_ACCUMULATE
    (deploy the dry powder into the decline until price recovers near the prior ATH).

    All indicators are precomputed only-from-past in prepare(); decide() is O(1) and the state
    machine transitions on past/current data only, so the run is look-ahead-free.
    """

    def __init__(self, cycle: CycleParams = CycleParams(), hp: CycleHunterParams = CycleHunterParams()) -> None:
        self.cycle = cycle
        self.hp = hp

    def prepare(self, bars: List[OHLCV]) -> None:
        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        self._close = closes
        self._rscale = 1.0 / bars_per_day(bars)   # normalize per-bar rates across timeframes
        hp = self.hp
        self._ema = ema(closes, hp.ema_fast)
        self._sma = sma(closes, hp.sma_slow)
        self._st = supertrend(highs, lows, closes, hp.st_period, hp.st_mult)
        atrv = atr(highs, lows, closes, hp.atr_period)
        self._atr_pctile = rolling_percentile(atrv, hp.atr_pctile_window)
        # Running all-time high (expanding), look-ahead-free.
        self._ath: List[float] = []
        run_high = float("-inf")
        for b in bars:
            run_high = max(run_high, b.high)
            self._ath.append(run_high)

        # State machine registers (mutable across the sequential decide() calls of one run).
        self._state = "ACCUMULATE_BASE"
        self._dist_start_units = 0.0
        self._sold_units_cycle = 0.0
        self._prior_ath = 0.0
        self._cooldown_until: date | None = None

    @staticmethod
    def _clamp(x: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, x))

    def _base_deploy(self, ledger: AccumulationLedger, ctx: RunContext) -> float:
        """DCA baseline: spend accumulated contributions, or an even slice of a lump sum."""
        if ctx.capital_model == "lump_sum":
            return ctx.lump_sum_budget / ctx.n_bars
        return ledger.cash

    def decide(self, i, bars, ledger, ctx) -> Tuple[float, float]:
        hp = self.hp
        d = bars[i].timestamp.date()
        price = bars[i].close
        ath = self._ath[i]
        st_bull = self._st[i] == 1
        ema_v, sma_v = self._ema[i], self._sma[i]
        bull_regime = ema_v is not None and sma_v is not None and ema_v > sma_v
        atr_pct = self._atr_pctile[i]
        self._prior_ath = max(self._prior_ath, ath)

        state = self._state

        if state == "ACCUMULATE_BASE":
            near_ath = ath > 0 and price >= hp.ath_sell_trigger * ath
            top_window = sell_intensity(d, self.cycle) >= hp.sell_intensity_hi
            euphoric = atr_pct >= hp.atr_pctile_hi
            if near_ath and top_window and euphoric and st_bull and bull_regime:
                self._state = "DISTRIBUTE"
                self._dist_start_units = ledger.units
                self._sold_units_cycle = 0.0
                return self._distribute(i, ledger)
            return (self._base_deploy(ledger, ctx), 0.0)

        if state == "DISTRIBUTE":
            # Trend break (Supertrend flips bearish) confirms the top -> cool down.
            if not st_bull:
                self._state = "COOLDOWN"
                self._cooldown_until = d + timedelta(days=hp.cooldown_days)
                return (0.0, 0.0)
            return self._distribute(i, ledger)

        if state == "COOLDOWN":
            if self._cooldown_until is not None and d >= self._cooldown_until:
                # Cooldown elapsed: accumulate if still well below the prior ATH, else resume DCA.
                if price < (1 - hp.reentry_within) * self._prior_ath:
                    self._state = "BEAR_ACCUMULATE"
                    return self._bear_deploy(i, ledger, d)
                self._state = "ACCUMULATE_BASE"
                return (self._base_deploy(ledger, ctx), 0.0)
            return (0.0, 0.0)   # still cooling down: hold, pile dry powder

        if state == "BEAR_ACCUMULATE":
            if price >= (1 - hp.reentry_within) * self._prior_ath:
                self._state = "ACCUMULATE_BASE"
                return (self._base_deploy(ledger, ctx), 0.0)
            return self._bear_deploy(i, ledger, d)

        return (self._base_deploy(ledger, ctx), 0.0)

    def _distribute(self, i, ledger: AccumulationLedger) -> Tuple[float, float]:
        hp = self.hp
        cap_remaining = max(0.0, hp.sell_cap_frac * self._dist_start_units - self._sold_units_cycle)
        sell_units = min(hp.k_sell_daily * self._rscale * self._dist_start_units, cap_remaining, ledger.units)
        self._sold_units_cycle += sell_units
        return (0.0, sell_units)   # no buying while distributing — contributions become dry powder

    def _bear_deploy(self, i, ledger: AccumulationLedger, d: date) -> Tuple[float, float]:
        hp = self.hp
        price = self._close[i]
        dd = (self._prior_ath - price) / self._prior_ath if self._prior_ath > 0 else 0.0
        depth = self._clamp(dd / hp.dd_ref, 0.0, 1.0)
        trend_boost = 1.25 if self._st[i] == 1 else 1.0     # accelerate once trend turns back up
        deploy_frac = self._clamp(
            (hp.bear_floor + hp.k_bear_daily * depth * buy_intensity(d, self.cycle))
            * trend_boost * self._rscale,
            0.0, 1.0,
        )
        return (deploy_frac * ledger.cash, 0.0)


@dataclass(frozen=True)
class CycleRotationParams:
    """Tunable knobs for CycleRotationPolicy (sell-high / buy-the-lower-half)."""
    sell_fraction_at_ath: float = 0.70   # target fraction of the stack to sell near the top (0..1)
    ath_band: float = 0.08               # "near ATH" = price >= (1 - ath_band) * running ATH
    sell_intensity_hi: float = 0.85      # halving top-window gate — tight, so selling stays near the top
    k_sell_daily: float = 0.10           # base per-bar sell rate (× intensity^sell_sharpness, on the pool)
    sell_sharpness: float = 4.0          # steep intensity weighting so selling clusters at the very top
    expected_bear_drop: float = 0.70     # manual arm: assumed ATH->bottom drop (auto arm derives it)
    buy_zone_top_frac: float = 0.50      # start deploying at half the expected drop (lower-half buying)
    k_deploy_daily: float = 0.10         # per-bar deploy rate of the war chest
    deploy_floor: float = 0.30           # minimum deploy weight once inside the buy zone
    reentry_gain: float = 0.30           # exit DEPLOY once price recovers this far above the trough
    st_period: int = 10
    st_mult: float = 3.0


class CycleRotationPolicy:
    """Sell most of the stack near a confirmed ATH, then redeploy the war chest across the LOWER
    HALF of the drawdown (see 2026-07-30-cycle-rotation-redesign.md).

    States HOLD_CORE -> DISTRIBUTE -> DEPLOY -> HOLD_CORE. The only difference between the manual
    (`cycle_rotation_v2`) and derived (`cycle_rotation_auto`) arms is ``drop_estimator``: a callable
    (bar index -> expected drop, or None). Look-ahead-free: indicators precomputed only-from-past and
    the estimator itself only uses past drawdowns.
    """

    def __init__(
        self,
        cycle: CycleParams = CycleParams(),
        rp: CycleRotationParams = CycleRotationParams(),
        drop_estimator: Optional[Callable[[int], Optional[float]]] = None,
    ) -> None:
        self.cycle = cycle
        self.rp = rp
        # Default (manual) estimator returns the fixed expected_bear_drop.
        self._drop_est = drop_estimator or (lambda i: rp.expected_bear_drop)

    def prepare(self, bars: List[OHLCV]) -> None:
        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        self._close = closes
        self._rscale = 1.0 / bars_per_day(bars)   # normalize per-bar rates across timeframes
        self._st = supertrend(highs, lows, closes, self.rp.st_period, self.rp.st_mult)
        self._ath: List[float] = []
        run_high = float("-inf")
        for b in bars:
            run_high = max(run_high, b.high)
            self._ath.append(run_high)
        self._state = "HOLD_CORE"
        self._dist_start_units = 0.0
        self._sold_units = 0.0
        self._cycle_ath = 0.0
        self._buy_target = 0.0
        self._zone_top = 0.0
        self._trough = float("inf")

    @staticmethod
    def _clamp(x: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, x))

    def _base_deploy(self, ledger: AccumulationLedger, ctx: RunContext) -> float:
        if ctx.capital_model == "lump_sum":
            return ctx.lump_sum_budget / ctx.n_bars
        return ledger.cash

    def decide(self, i, bars, ledger, ctx) -> Tuple[float, float]:
        rp = self.rp
        d = bars[i].timestamp.date()
        price = self._close[i]
        ath = self._ath[i]
        st_bull = self._st[i] == 1

        if self._state == "HOLD_CORE":
            near_ath = ath > 0 and price >= (1 - rp.ath_band) * ath
            top_window = sell_intensity(d, self.cycle) >= rp.sell_intensity_hi
            if near_ath and top_window and st_bull:
                self._state = "DISTRIBUTE"
                self._dist_start_units = ledger.units
                return self._distribute(ledger, d)
            return (self._base_deploy(ledger, ctx), 0.0)

        if self._state == "DISTRIBUTE":
            if not st_bull:                     # Supertrend flip confirms the top
                drop = self._drop_est(i)
                if drop is None or drop <= 0:
                    self._state = "HOLD_CORE"
                    return (self._base_deploy(ledger, ctx), 0.0)
                self._cycle_ath = ath
                self._buy_target = self._cycle_ath * (1 - drop)
                self._zone_top = self._cycle_ath * (1 - drop * rp.buy_zone_top_frac)
                self._trough = price
                self._state = "DEPLOY"
                return self._deploy(ledger, price)
            return self._distribute(ledger, d)

        if self._state == "DEPLOY":
            self._trough = min(self._trough, price)
            recovered = price >= self._trough * (1 + rp.reentry_gain)
            if recovered or price >= self._cycle_ath or ledger.cash < 1e-6:
                self._state = "HOLD_CORE"
                return (self._base_deploy(ledger, ctx), 0.0)
            return self._deploy(ledger, price)

        return (self._base_deploy(ledger, ctx), 0.0)

    def _distribute(self, ledger: AccumulationLedger, d: date) -> Tuple[float, float]:
        """Sell a slice of the *sellable pool* (units above the kept core), weighted by halving
        sell-intensity so the selling concentrates at the predicted top rather than dumping early."""
        rp = self.rp
        core = (1 - rp.sell_fraction_at_ath) * self._dist_start_units
        sellable = max(0.0, ledger.units - core)
        rate = rp.k_sell_daily * self._rscale * (sell_intensity(d, self.cycle) ** rp.sell_sharpness)
        sell_units = self._clamp(rate, 0.0, 1.0) * sellable
        return (0.0, sell_units)

    def _deploy(self, ledger: AccumulationLedger, price: float) -> Tuple[float, float]:
        rp = self.rp
        if price > self._zone_top:              # not into the lower-half buy zone yet
            return (0.0, 0.0)
        span = self._zone_top - self._buy_target
        depth = self._clamp((self._zone_top - price) / span, 0.0, 1.0) if span > 0 else 1.0
        deploy_frac = self._clamp(rp.k_deploy_daily * self._rscale * (rp.deploy_floor + depth), 0.0, 1.0)
        return (deploy_frac * ledger.cash, 0.0)


@dataclass(frozen=True)
class AccumulatorGridParams:
    """Tunable knobs for AccumulatorGridPolicy."""
    base_deploy: float = 0.35       # per-bar fraction of cash deployed even at the ATH (stay invested).
                                    # Higher = smaller idle-cash reserve = less drag; the full-history
                                    # sweep showed a large reserve doesn't pay for itself on BTC.
    dip_gain: float = 1.30          # extra deploy per unit of drawdown-from-ATH
    dd_ref: float = 0.60            # drawdown that maps to full deployment
    st_boost: float = 1.25          # multiply dip-buying when Supertrend is bullish (confirmed dip)
    profit_step: float = 0.50       # only trim once price is this far above avg cost
    trim_frac: float = 0.05         # base per-bar fraction of the above-core stack to trim
    trim_pos_hi: float = 0.85       # only trim near the top of the recent range
    core_frac: float = 0.75         # ratcheting floor: keep >= this fraction of max-units-ever
    rolling_window: int = 90
    use_trend_filter: bool = True   # only harvest income while price > SMA (uptrend). Turn OFF for
                                    # ranging assets, which have no trend to respect (harvest both ways).
    sma_slow: int = 200             # SMA period for the trend filter (ignored when use_trend_filter=False)
    st_period: int = 10
    st_mult: float = 3.0
    atr_period: int = 14
    atr_pctile_window: int = 365


class AccumulatorGridPolicy:
    """Buy-the-dip accumulation grid with light, trend-gated profit trims and a ratcheting core.

    Design intent (see the 2026-07-30 grid discussion): the edge is on the BUY side, not on
    timing tops. Hold a cash reserve and deploy it *disproportionately into drawdowns* (deeper
    dip -> larger fraction of cash spent -> more coins per dollar than flat DCA). Never fully
    exit: a core floor ratchets up with the largest position ever held. Take only small profit
    trims near local highs while the trend is up (price > SMA), banking realized income that is
    recycled into the next dip. Look-ahead-free: indicators precomputed only-from-past.
    """

    def __init__(self, gp: AccumulatorGridParams = AccumulatorGridParams()) -> None:
        self.gp = gp

    def prepare(self, bars: List[OHLCV]) -> None:
        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        gp = self.gp
        self._close = closes
        self._rscale = 1.0 / bars_per_day(bars)   # normalize per-bar rates across timeframes
        self._sma = sma(closes, gp.sma_slow)
        self._st = supertrend(highs, lows, closes, gp.st_period, gp.st_mult)
        atrv = atr(highs, lows, closes, gp.atr_period)
        self._atr_pctile = rolling_percentile(atrv, gp.atr_pctile_window)
        # Running ATH and rolling range (only-past).
        self._ath: List[float] = []
        self._roll_high: List[float] = []
        self._roll_low: List[float] = []
        run_high = float("-inf")
        for i, b in enumerate(bars):
            run_high = max(run_high, b.high)
            self._ath.append(run_high)
            lo = max(0, i - gp.rolling_window + 1)
            window = bars[lo : i + 1]
            self._roll_high.append(max(x.high for x in window))
            self._roll_low.append(min(x.low for x in window))
        self._max_units = 0.0     # ratchet for the core floor

    @staticmethod
    def _clamp(x: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, x))

    def decide(self, i, bars, ledger, ctx) -> Tuple[float, float]:
        gp = self.gp
        price = self._close[i]
        ath = self._ath[i]
        self._max_units = max(self._max_units, ledger.units)
        core_floor = gp.core_frac * self._max_units

        # ---- income trim: light, trend-gated, keep the core -------------------------------- #
        sell_units = 0.0
        sma_v = self._sma[i]
        uptrend = (not gp.use_trend_filter) or (sma_v is not None and price > sma_v)
        hi, lo = self._roll_high[i], self._roll_low[i]
        pos_in_range = (price - lo) / (hi - lo) if hi > lo else 0.0
        sellable = max(0.0, ledger.units - core_floor)
        above_cost = ledger.avg_cost_basis > 0 and price >= ledger.avg_cost_basis * (1 + gp.profit_step)
        if sellable > 0 and above_cost and uptrend and pos_in_range >= gp.trim_pos_hi:
            trim = gp.trim_frac * self._rscale * (1 + self._atr_pctile[i])   # more in high-vol euphoria
            sell_units = min(trim * sellable, sellable)

        # ---- dip buy: deploy more of the cash reserve the deeper the drawdown --------------- #
        dd = (ath - price) / ath if ath > 0 else 0.0
        deploy = gp.base_deploy + gp.dip_gain * (dd / gp.dd_ref)
        if self._st[i] == 1:
            deploy *= gp.st_boost                              # confirmed-uptrend dip -> lean in
        deploy_frac = self._clamp(deploy * self._rscale, 0.0, 1.0)
        # Cash freed by a trim this bar is available to redeploy immediately (harvest recycling).
        avail_cash = ledger.cash + sell_units * price * (1 - ledger.slippage_pct) * (1 - ledger.commission_pct)
        buy_cash = deploy_frac * avail_cash

        return (buy_cash, sell_units)


@dataclass
class ArmResult:
    equity_curve: List[EquityPoint]
    final_value: float
    total_contributed: float
    total_return_pct: float
    units_accumulated: float
    avg_cost_basis: float
    max_drawdown_pct: float
    sharpe_ratio: float
    dry_powder: float
    realized_pnl: float


def run_accumulation(
    bars: List[OHLCV],
    policy: DeploymentPolicy,
    *,
    capital_model: str,
    contribution_amount: float,
    contribution_interval_days: int,
    lump_sum_budget: float,
    commission_pct: float,
    slippage_pct: float,
    bars_per_year: int,
) -> ArmResult:
    if not bars:
        raise ValueError("No bars to run accumulation on")

    ledger = AccumulationLedger(commission_pct=commission_pct, slippage_pct=slippage_pct)
    ctx = RunContext(
        capital_model=capital_model,
        contribution_amount=contribution_amount,
        lump_sum_budget=lump_sum_budget,
        n_bars=len(bars),
    )
    policy.prepare(bars)
    if capital_model == "lump_sum":
        ledger.contribute(lump_sum_budget)

    equity_curve: List[EquityPoint] = []
    last_contribution_day = None

    for i, bar in enumerate(bars):
        d = bar.timestamp.date()
        if capital_model == "contributions":
            if last_contribution_day is None or (d - last_contribution_day).days >= contribution_interval_days:
                ledger.contribute(contribution_amount)
                last_contribution_day = d

        buy_cash, sell_units = policy.decide(i, bars, ledger, ctx)
        if sell_units > 0:
            ledger.sell(sell_units, bar.close)
        if buy_cash > 0:
            ledger.buy(buy_cash, bar.close)

        ts_ms = int(bar.timestamp.timestamp() * 1000)
        equity_curve.append(EquityPoint(timestamp=ts_ms, value=ledger.equity(bar.close)))

    final_price = bars[-1].close
    final_value = ledger.equity(final_price)
    contributed = ledger.contributed
    total_return_pct = (final_value - contributed) / contributed * 100 if contributed > 0 else 0.0
    values = [pt.value for pt in equity_curve]
    starting_peak = values[0] if values else 0.0

    return ArmResult(
        equity_curve=equity_curve,
        final_value=round(final_value, 2),
        total_contributed=round(contributed, 2),
        total_return_pct=round(total_return_pct, 2),
        units_accumulated=round(ledger.units, 8),
        avg_cost_basis=round(ledger.avg_cost_basis, 2),
        max_drawdown_pct=round(max_drawdown_pct(values, starting_peak), 2),
        sharpe_ratio=round(annualized_sharpe(values, bars_per_year), 3),
        dry_powder=round(ledger.cash, 2),
        realized_pnl=round(ledger.realized_pnl, 2),
    )
