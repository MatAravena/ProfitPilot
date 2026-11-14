from __future__ import annotations

from typing import Any, Dict, List, Literal, Union

from pydantic import BaseModel, Field, field_validator

from app.models.schemas.backtest_schemas import BacktestRequest, EquityPointResponse

MAX_COMBINATIONS = 300   # every combo is a backtest per fold; keep requests bounded

WF_CAVEAT_TEXT = (
    "Only the out-of-sample columns count: each test window is traded with parameters "
    "chosen on the window before it, never on itself. A strategy that beats buy-and-hold "
    "in-sample but not out-of-sample has no demonstrated edge. Folds are flat at their "
    "boundaries (any open position is closed at the end of each test window)."
)

ParamValue = Union[bool, int, float, str]


class WalkForwardRequest(BacktestRequest):
    """A normal backtest request (strategy, symbol, dates, costs, sizing, stops) plus the
    search space and window sizes. `parameters` holds fixed params; `param_grid` the ones
    searched — a key may not appear in both."""

    param_grid: Dict[str, List[ParamValue]] = Field(
        ..., description='e.g. {"fast_period": [8, 12, 16], "slow_period": [21, 26]}',
    )
    train_days: int = Field(730, ge=30, le=3650, description="In-sample window (calendar days)")
    test_days: int = Field(180, ge=7, le=1825, description="Out-of-sample window (calendar days)")
    objective: Literal["sharpe_ratio", "total_return_pct", "profit_factor", "win_rate"] = "sharpe_ratio"

    @field_validator("param_grid")
    @classmethod
    def _bounded_grid(cls, grid: Dict[str, List[Any]]) -> Dict[str, List[Any]]:
        if not grid or any(len(v) == 0 for v in grid.values()):
            raise ValueError("param_grid needs at least one parameter with at least one value")
        n = 1
        for values in grid.values():
            n *= len(values)
        if n > MAX_COMBINATIONS:
            raise ValueError(f"param_grid has {n} combinations; the limit is {MAX_COMBINATIONS}")
        return grid


class WalkForwardFoldResponse(BaseModel):
    train_start: int   # Unix ms of the first / last bar of each window
    train_end: int
    test_start: int
    test_end: int
    params: Dict[str, Any]
    is_score: float
    is_return_pct: float
    oos_return_pct: float
    oos_sharpe: float
    oos_max_drawdown_pct: float
    oos_trades: int
    buy_hold_return_pct: float


class WalkForwardResponse(BaseModel):
    strategy_name: str
    symbol: str
    timeframe: str
    objective: str
    initial_capital: float
    train_bars: int
    test_bars: int
    combinations: int
    skipped_combinations: int   # rejected by the strategy's own validation (e.g. fast >= slow)
    oos_total_return_pct: float
    oos_max_drawdown_pct: float
    oos_sharpe: float
    buy_hold_total_return_pct: float
    buy_hold_max_drawdown_pct: float
    pct_folds_profitable: float
    avg_is_score: float
    avg_oos_sharpe: float
    distinct_param_sets: int
    folds: List[WalkForwardFoldResponse]
    equity_curve: List[EquityPointResponse]
    buy_hold_curve: List[EquityPointResponse]
    caveat: str = WF_CAVEAT_TEXT
