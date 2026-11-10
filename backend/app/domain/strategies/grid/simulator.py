"""The bar-loop driver: wires planner + policy + ledger together, applies fill realism, and
reports the honest scoreboard (grid income vs. mark-to-market, unbounded-exposure disclosure).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List

from app.core.types import OHLCV
from app.domain.backtest.metrics import EquityPoint, annualized_sharpe, max_drawdown_pct
from app.domain.strategies.grid.ledger import GridLedger, process_bar_fills
from app.domain.strategies.grid.levels import compute_levels
from app.domain.strategies.grid.params import GridParams
from app.domain.strategies.grid.planner import GridPlanSeries
from app.domain.strategies.grid.policies import GridPolicy


@dataclass
class GridArmResult:
    equity_curve: List[EquityPoint]
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    grid_trades: int
    grid_realized_pnl: float
    forced_exit_pnl: float
    force_close_count: int
    mark_to_market_pnl: float
    avg_profit_per_grid_pct: float
    fill_rate: float
    time_in_grid_pct: float
    max_inventory_notional: float
    worst_unrealized_pct: float
    time_underwater_pct: float


def run_grid_backtest(
    bars: List[OHLCV],
    plan_series: GridPlanSeries,
    policy: GridPolicy,
    grid_params: GridParams,
    *,
    initial_capital: float,
    notional_per_rung: float,
    allow_intrabar_roundtrip: bool = False,
    bars_per_year: int = 8_760,
) -> GridArmResult:
    if not bars:
        raise ValueError("No bars to run the grid backtest on")

    ledger = GridLedger(
        fee_pct=grid_params.fee_pct, slippage_pct=grid_params.slippage_pct,
        notional_per_rung=notional_per_rung, cash=initial_capital,
    )
    policy.prepare(bars, plan_series)

    equity_curve: List[EquityPoint] = []
    max_inventory = 0.0
    worst_unrealized_pct = 0.0
    bars_with_open_lots = 0
    bars_underwater = 0
    bars_with_active_plan = 0

    for i, bar in enumerate(bars):
        ts_ms = int(bar.timestamp.timestamp() * 1000)
        # A resting order can only be priced from information known BEFORE the bar it fills in --
        # bar i trades against plans[i-1], never plans[i] (which is itself built from bar i's own
        # high/low). Bar 0 has no prior plan, so nothing rests yet on the first bar.
        plan = plan_series.plans[i - 1] if i > 0 else None
        if plan is not None and plan.levels is not None:
            bars_with_active_plan += 1

        if plan is None:
            pass
        elif policy.should_force_close(i, bar, plan, ledger):
            ledger.force_close_all(bar.close, ts_ms)
        else:
            ext_mult = policy.extend_range_mult(i, bar, plan, ledger)
            levels = plan.levels
            if ext_mult is not None and levels is not None:
                extended_params = replace(grid_params, range_atr_mult=ext_mult)
                levels = compute_levels(
                    center=levels.center, atr=plan_series.regime.atr[i - 1], params=extended_params,
                    swing_high=plan.swing_high, swing_low=plan.swing_low,
                )
            process_bar_fills(ledger, levels, plan.direction, bar, ts_ms, allow_intrabar_roundtrip)

        equity = ledger.equity(bar.close)
        equity_curve.append(EquityPoint(timestamp=ts_ms, value=equity))

        inv = ledger.inventory_notional(bar.close)
        max_inventory = max(max_inventory, inv)
        if initial_capital > 0:
            underwater_pct = max(0.0, (initial_capital - equity) / initial_capital * 100)
            worst_unrealized_pct = max(worst_unrealized_pct, underwater_pct)
            if equity < initial_capital:
                bars_underwater += 1
        if ledger.open_lots:
            bars_with_open_lots += 1

    final_equity = ledger.equity(bars[-1].close)
    total_return_pct = (final_equity - initial_capital) / initial_capital * 100 if initial_capital else 0.0
    values = [p.value for p in equity_curve]
    mark_to_market_pnl = (final_equity - initial_capital) - ledger.realized_pnl
    n = len(bars)

    return GridArmResult(
        equity_curve=equity_curve,
        final_equity=round(final_equity, 2),
        total_return_pct=round(total_return_pct, 2),
        max_drawdown_pct=round(max_drawdown_pct(values, initial_capital), 2),
        sharpe_ratio=round(annualized_sharpe(values, bars_per_year), 3),
        grid_trades=ledger.grid_trades,
        grid_realized_pnl=round(ledger.grid_realized_pnl, 2),
        forced_exit_pnl=round(ledger.forced_pnl, 2),
        force_close_count=ledger.force_close_count,
        mark_to_market_pnl=round(mark_to_market_pnl, 2),
        avg_profit_per_grid_pct=round(
            (ledger.grid_realized_pnl / ledger.grid_trades / notional_per_rung * 100)
            if ledger.grid_trades else 0.0, 3,
        ),
        fill_rate=round(bars_with_active_plan / n * 100, 2),
        time_in_grid_pct=round(bars_with_open_lots / n * 100, 2),
        max_inventory_notional=round(max_inventory, 2),
        worst_unrealized_pct=round(worst_unrealized_pct, 2),
        time_underwater_pct=round(bars_underwater / n * 100, 2),
    )
