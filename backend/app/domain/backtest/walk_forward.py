"""Walk-forward validation — optimize on a past window, judge on the next unseen one.

A single backtest over all history picks parameters with hindsight: the "best" settings
were chosen on the very data that scores them. Walk-forward removes that. For each fold:

    [ train window ][ test window ]        ← pick the best params on train only,
              [ train window ][ test window ]   then trade them on test, unseen
                        ...

Only the test windows count. They tile the data without overlapping, so the stitched
out-of-sample curve is what you would have experienced re-optimizing on that schedule.

Pure domain: every run goes through `BacktestEngine` (one execution path — costs,
sizing, fills identical to a normal backtest). No I/O, no registry.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from app.core.types import OHLCV
from app.domain.backtest.engine import BacktestEngine, BacktestResult
from app.domain.backtest.metrics import (
    BacktestMetrics, EquityPoint, TradeRecord, annualized_sharpe, max_drawdown_pct,
)
from app.domain.strategy.base import StrategyBase

StrategyFactory = Callable[[Dict[str, Any]], StrategyBase]


@dataclass
class WalkForwardFold:
    train_start: int            # bar indices into the input, [start, end)
    train_end: int
    test_start: int
    test_end: int
    params: Dict[str, Any]      # chosen on the train window only
    is_score: float             # objective of `params` on the train window
    is_return_pct: float
    oos_return_pct: float       # the number that counts
    oos_sharpe: float
    oos_max_drawdown_pct: float
    oos_trades: int
    buy_hold_return_pct: float  # same test window, just holding
    trades: List[TradeRecord] = field(repr=False, default_factory=list)
    equity_curve: List[EquityPoint] = field(repr=False, default_factory=list)


@dataclass
class WalkForwardResult:
    initial_capital: float
    objective: str
    combinations: int
    folds: List[WalkForwardFold]
    oos_total_return_pct: float
    oos_max_drawdown_pct: float
    oos_sharpe: float
    buy_hold_total_return_pct: float
    buy_hold_max_drawdown_pct: float
    pct_folds_profitable: float
    avg_is_score: float
    avg_oos_sharpe: float
    distinct_param_sets: int     # 1 = the same params won every fold (stable)
    equity_curve: List[EquityPoint]
    buy_hold_curve: List[EquityPoint]


def expand_grid(param_grid: Dict[str, Sequence[Any]]) -> List[Dict[str, Any]]:
    if not param_grid or any(len(v) == 0 for v in param_grid.values()):
        raise ValueError("param_grid needs at least one parameter with at least one value")
    keys = list(param_grid)
    return [dict(zip(keys, combo)) for combo in itertools.product(*(param_grid[k] for k in keys))]


async def walk_forward(
    bars: List[OHLCV],
    make_strategy: StrategyFactory,
    param_grid: Dict[str, Sequence[Any]],
    *,
    train_bars: int,
    test_bars: int,
    objective: str = "sharpe_ratio",
    initial_capital: float = 10_000.0,
    lookback_bars: Optional[int] = None,
    bars_per_year: int = 365,
    **engine_kwargs: Any,
) -> WalkForwardResult:
    """`engine_kwargs` go to every BacktestEngine run (costs, sizing, stops, allow_short)."""
    if objective not in BacktestMetrics._fields:
        raise ValueError(f"objective must be one of {BacktestMetrics._fields}")
    if train_bars < 2 or test_bars < 1:
        raise ValueError("train_bars must be >= 2 and test_bars >= 1")
    if len(bars) < train_bars + test_bars:
        raise ValueError(
            f"Need at least train_bars + test_bars = {train_bars + test_bars} bars, got {len(bars)}"
        )
    combos = expand_grid(param_grid)

    async def backtest(params, window, warmup=None) -> BacktestResult:
        kw = dict(engine_kwargs, initial_capital=initial_capital, lookback_bars=lookback_bars)
        if warmup is not None:
            kw["warmup_bars"] = warmup
        return await BacktestEngine(make_strategy(params), window, **kw).run()

    folds: List[WalkForwardFold] = []
    start = 0
    while start + train_bars + test_bars <= len(bars):
        train_end = start + train_bars
        test_end = train_end + test_bars

        # 1) Choose on the train window ONLY. Ties keep the earliest combo (deterministic).
        best_params, best_score, best_is = None, float("-inf"), None
        for params in combos:
            res = await backtest(params, bars[start:train_end])
            score = getattr(res.metrics, objective)
            score = float("-inf") if score is None else score
            if score > best_score:
                best_params, best_score, best_is = params, score, res

        # 2) Trade them on the unseen test window. The engine gets prior bars as context
        #    (indicators need history) but makes its first decision at test_start.
        context = train_end if lookback_bars is None else min(train_end, lookback_bars)
        oos = await backtest(best_params, bars[train_end - context:test_end], warmup=context)

        first, last = bars[train_end], bars[test_end - 1]
        folds.append(WalkForwardFold(
            train_start=start, train_end=train_end, test_start=train_end, test_end=test_end,
            params=best_params, is_score=best_score, is_return_pct=best_is.metrics.total_return_pct,
            oos_return_pct=_return_pct(oos), oos_sharpe=oos.metrics.sharpe_ratio,
            oos_max_drawdown_pct=oos.metrics.max_drawdown_pct, oos_trades=len(oos.trades),
            buy_hold_return_pct=(last.close / first.close - 1) * 100,
            trades=oos.trades, equity_curve=oos.equity_curve,
        ))
        start += test_bars

    return _aggregate(folds, bars, initial_capital, objective, len(combos), bars_per_year)


def _return_pct(res: BacktestResult) -> float:
    """Unrounded return from the equity curve (metrics round to 2 decimals)."""
    if not res.equity_curve:
        return 0.0
    return (res.metrics.final_equity / res.initial_capital - 1) * 100


def _aggregate(folds, bars, initial_capital, objective, combos, bars_per_year) -> WalkForwardResult:
    # Stitch: each fold's curve rescaled to start where the previous one ended.
    curve: List[EquityPoint] = []
    bh_curve: List[EquityPoint] = []
    equity = bh_equity = initial_capital
    for f in folds:
        scale = equity / initial_capital
        curve += [EquityPoint(timestamp=p.timestamp, value=p.value * scale) for p in f.equity_curve]
        equity *= 1 + f.oos_return_pct / 100

        base = bars[f.test_start].close
        bh_curve += [EquityPoint(timestamp=int(b.timestamp.timestamp() * 1000),
                                 value=bh_equity * b.close / base)
                     for b in bars[f.test_start:f.test_end]]
        bh_equity *= 1 + f.buy_hold_return_pct / 100
    if curve:   # pin the end exactly to the compounded fold returns
        curve[-1] = EquityPoint(timestamp=curve[-1].timestamp, value=equity)

    values = [p.value for p in curve]
    n = len(folds)
    return WalkForwardResult(
        initial_capital=initial_capital,
        objective=objective,
        combinations=combos,
        folds=folds,
        oos_total_return_pct=(equity / initial_capital - 1) * 100,
        oos_max_drawdown_pct=max_drawdown_pct(values, initial_capital),
        oos_sharpe=annualized_sharpe([initial_capital] + values, bars_per_year),
        buy_hold_total_return_pct=(bh_equity / initial_capital - 1) * 100,
        buy_hold_max_drawdown_pct=max_drawdown_pct([p.value for p in bh_curve], initial_capital),
        pct_folds_profitable=100.0 * sum(f.oos_return_pct > 0 for f in folds) / n,
        avg_is_score=sum(f.is_score for f in folds) / n,
        avg_oos_sharpe=sum(f.oos_sharpe for f in folds) / n,
        distinct_param_sets=len({tuple(sorted(f.params.items())) for f in folds}),
        equity_curve=curve,
        buy_hold_curve=bh_curve,
    )
