from __future__ import annotations
import math
from typing import List, NamedTuple, Optional


class PricePoint(NamedTuple):
    timestamp: int  # Unix ms
    close: float


class EquityPoint(NamedTuple):
    timestamp: int   # Unix ms
    value: float


class TradeRecord(NamedTuple):
    symbol: str
    side: str            # "long" | "short"
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    entry_time: int      # Unix ms
    exit_time: int       # Unix ms


class BacktestMetrics(NamedTuple):
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate: float
    profit_factor: Optional[float]   # None = no losing trades (undefined / "infinite")
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    final_equity: float


def max_drawdown_pct(values: List[float], starting_peak: float) -> float:
    """Max peak-to-trough drawdown (%) of an equity series, measured from ``starting_peak``.

    Pure — shared by the backtest engine (peak = initial capital) and the accumulation
    simulator (peak = the series' first value)."""
    peak = starting_peak
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100
            if dd > max_dd:
                max_dd = dd
    return max_dd


def annualized_sharpe(values: List[float], bars_per_year: int) -> float:
    """Annualized Sharpe of an equity series (0 if fewer than 2 usable returns / no variance)."""
    returns = []
    for i in range(1, len(values)):
        prev, curr = values[i - 1], values[i]
        if prev > 0:
            returns.append((curr - prev) / prev)
    if len(returns) <= 1:
        return 0.0
    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
    std_r = math.sqrt(variance) if variance > 0 else 0
    return (mean_r / std_r) * math.sqrt(bars_per_year) if std_r > 0 else 0.0


def compute_metrics(
    equity_curve: List[EquityPoint],
    trades: List[TradeRecord],
    initial_capital: float,
    bars_per_year: int = 252,
) -> BacktestMetrics:
    if not equity_curve:
        return _empty_metrics(initial_capital)

    final_equity = equity_curve[-1].value
    total_return_pct = (final_equity - initial_capital) / initial_capital * 100

    values = [pt.value for pt in equity_curve]
    max_dd = max_drawdown_pct(values, initial_capital)
    sharpe = annualized_sharpe(values, bars_per_year)

    # Trade stats
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0.0
    avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0.0
    avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0.0

    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    # None (not inf) when there are no losses: inf is not JSON-compliant and would 500 the
    # response (Starlette serializes with allow_nan=False). The frontend renders None as "∞".
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else None

    return BacktestMetrics(
        total_return_pct=round(total_return_pct, 2),
        sharpe_ratio=round(sharpe, 3),
        max_drawdown_pct=round(max_dd, 2),
        win_rate=round(win_rate, 1),
        profit_factor=profit_factor,   # already rounded above; None when no losses
        total_trades=len(trades),
        winning_trades=len(wins),
        losing_trades=len(losses),
        avg_win=round(avg_win, 2),
        avg_loss=round(avg_loss, 2),
        final_equity=round(final_equity, 2),
    )


def _empty_metrics(initial_capital: float) -> BacktestMetrics:
    return BacktestMetrics(
        total_return_pct=0, sharpe_ratio=0, max_drawdown_pct=0,
        win_rate=0, profit_factor=0, total_trades=0,
        winning_trades=0, losing_trades=0, avg_win=0, avg_loss=0,
        final_equity=initial_capital,
    )
