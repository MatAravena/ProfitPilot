"""Multi-buy accumulation simulator for DCA-vs-cycle-grid comparison.

Separate from BacktestEngine on purpose: grid/DCA accumulate a position across many buys,
whereas the engine is single-position/flip-based (and underpins backtest<->live parity). A
ledger tracks units/cash/cost-basis; injected deployment policies decide how much to buy/sell
each bar (open/closed — new arms = new policies). Costs mirror the paper adapter's model:
a BUY pays price*(1+slip)*(1+comm), a SELL receives price*(1-slip)*(1-comm).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol, Tuple

from app.core.types import OHLCV
from app.domain.backtest.halving_cycle import CycleParams, buy_intensity, sell_intensity
from app.domain.backtest.metrics import EquityPoint, annualized_sharpe, max_drawdown_pct


@dataclass
class AccumulationLedger:
    commission_pct: float
    slippage_pct: float
    units: float = 0.0
    cash: float = 0.0
    contributed: float = 0.0
    buy_notional: float = 0.0     # gross cash spent acquiring units (for avg cost basis)
    units_bought: float = 0.0
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
        self.buy_notional += cash_amount
        self.units_bought += units

    def sell(self, unit_amount: float, price: float) -> None:
        unit_amount = min(unit_amount, self.units)
        if unit_amount <= 0 or price <= 0:
            return
        eff = price * (1 - self.slippage_pct) * (1 - self.commission_pct)
        proceeds = unit_amount * eff
        self.realized_pnl += proceeds - unit_amount * self.avg_cost_basis
        self.units -= unit_amount
        self.cash += proceeds

    def equity(self, price: float) -> float:
        return self.cash + self.units * price

    @property
    def avg_cost_basis(self) -> float:
        return self.buy_notional / self.units_bought if self.units_bought > 0 else 0.0


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
