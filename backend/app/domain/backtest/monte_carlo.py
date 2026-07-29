"""Pure Monte Carlo resampler over a backtest's realized trade sequence.

Turns a single backtest (one lucky path) into a *distribution* of outcomes, so we
can separate genuine edge from luck. It answers two questions a single run cannot:

- **Sampling risk** ("were my results luck?") — bootstrap: draw trades *with
  replacement* and compound.
- **Ordering risk** ("was my drawdown just a lucky order?") — shuffle: permute the
  same trades and compound. Final equity is order-invariant (Π(1+r) is
  commutative), but the drawdown *path* is not — this isolates ordering risk.

Everything operates on the **fixed-fractional per-trade return series**

    equity_before_trade_i = initial_capital + Σ(pnl of trades before i)
    r_i                    = pnl_i / equity_before_trade_i

which is exactly right for this platform: sizing is a fixed % of equity, so each
trade *is* "this fraction of whatever equity I hold at the time," and compounding
r_i in the original order reproduces the realized final equity.

Pure math only — no DB, no FastAPI, numpy-vectorized. Orchestration (running the
backtest, reading config) lives in the service layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

import numpy as np

DEFAULT_METHODS = ("bootstrap", "shuffle")
DEFAULT_HISTOGRAM_BINS = 40


@dataclass(frozen=True)
class PercentileStats:
    """Distribution summary for one metric across all simulations."""
    p5: float
    p25: float
    p50: float
    p75: float
    p95: float
    min: float
    max: float
    mean: float


@dataclass(frozen=True)
class Histogram:
    """Binned total-return %: ``len(edges) == len(counts) + 1``."""
    edges: List[float]
    counts: List[int]


@dataclass(frozen=True)
class MethodResult:
    method: str  # "bootstrap" | "shuffle"
    final_equity: PercentileStats
    total_return_pct: PercentileStats
    max_drawdown_pct: PercentileStats
    prob_profit: float                    # fraction of sims ending above initial capital
    risk_of_exceeding_drawdown: float     # fraction whose max-drawdown exceeds the threshold
    risk_of_ruin: float                   # fraction that hit equity <= 0
    histogram: Histogram


@dataclass(frozen=True)
class MonteCarloResult:
    n_simulations: int
    n_trades: int
    initial_capital: float
    realized_total_return_pct: float      # the single-path backtest result, for reference lines
    drawdown_threshold_pct: float
    methods: Dict[str, MethodResult]


def trade_returns(pnls: Sequence[float], initial_capital: float) -> np.ndarray:
    """Derive the fixed-fractional per-trade return series from realized P&L.

    ``pnls`` is the ordered per-trade profit/loss (e.g. ``[t.pnl for t in trades]``).
    Raises ``ValueError`` on fewer than 2 trades (a distribution needs at least two
    samples) or if cumulative losses drove account equity to zero.
    """
    arr = np.asarray(list(pnls), dtype=float)
    if arr.size < 2:
        raise ValueError("Need at least 2 trades to build a Monte Carlo return distribution")

    equity_before = initial_capital + np.concatenate(([0.0], np.cumsum(arr)[:-1]))
    if np.any(equity_before <= 0):
        raise ValueError("Cumulative losses drove account equity to zero; cannot derive returns")

    return arr / equity_before


def run_monte_carlo(
    returns: np.ndarray,
    initial_capital: float,
    *,
    n_simulations: int,
    methods: Sequence[str] = DEFAULT_METHODS,
    seed: int | None = None,
    drawdown_threshold_pct: float = 10.0,
    histogram_bins: int = DEFAULT_HISTOGRAM_BINS,
) -> MonteCarloResult:
    """Resample ``returns`` ``n_simulations`` times per method and summarize.

    Deterministic when ``seed`` is provided. ``drawdown_threshold_pct`` is the level
    used for ``risk_of_exceeding_drawdown`` (default = the risk profile's total-DD limit).
    """
    returns = np.asarray(returns, dtype=float)
    n = returns.size
    if n < 2:
        raise ValueError("Need at least 2 trade returns to resample")

    rng = np.random.default_rng(seed)
    realized_total_return_pct = round((float(np.prod(1.0 + returns)) - 1.0) * 100.0, 4)

    results: Dict[str, MethodResult] = {}
    for method in methods:
        if method == "bootstrap":
            # (n_simulations × n) draw with replacement.
            sampled = returns[rng.integers(0, n, size=(n_simulations, n))]
        elif method == "shuffle":
            # Per-row permutation via argsort of random keys (vectorized).
            order = rng.random((n_simulations, n)).argsort(axis=1)
            sampled = returns[order]
        else:
            raise ValueError(f"Unknown Monte Carlo method: {method!r}")

        results[method] = _summarize(
            method, sampled, initial_capital, drawdown_threshold_pct, histogram_bins
        )

    return MonteCarloResult(
        n_simulations=n_simulations,
        n_trades=n,
        initial_capital=initial_capital,
        realized_total_return_pct=realized_total_return_pct,
        drawdown_threshold_pct=drawdown_threshold_pct,
        methods=results,
    )


def _summarize(
    method: str,
    sampled: np.ndarray,          # (S × n) resampled returns
    initial_capital: float,
    drawdown_threshold_pct: float,
    histogram_bins: int,
) -> MethodResult:
    n_sims = sampled.shape[0]

    # Compound each path. Ruin guard: enforce an absorbing barrier at zero — once a
    # path's equity hits <= 0, it stays 0 for the rest of the path (keeps the math
    # total even when a return is <= -100%).
    equity = initial_capital * np.cumprod(1.0 + sampled, axis=1)
    ever_ruined = equity <= 0
    absorbed = np.logical_or.accumulate(ever_ruined, axis=1)
    equity = np.where(absorbed, 0.0, equity)

    # Prepend the starting capital so drawdown is measured from bar 0.
    full = np.concatenate([np.full((n_sims, 1), initial_capital), equity], axis=1)

    final_equity = equity[:, -1]
    ruined = absorbed[:, -1]
    total_return = (final_equity / initial_capital - 1.0) * 100.0

    # Peaks are running maxima starting at initial_capital (> 0), so the division is safe.
    peaks = np.maximum.accumulate(full, axis=1)
    max_drawdown = ((peaks - full) / peaks).max(axis=1) * 100.0

    # Shuffle (and all-identical) runs collapse to a single total-return value, which
    # gives np.histogram a zero-width range it can't bin — widen it so we still return
    # well-formed edges/counts.
    lo, hi = float(total_return.min()), float(total_return.max())
    if hi - lo < 1e-9:   # exactly constant, or fp noise from reordered compounding
        mid = (lo + hi) / 2.0
        lo, hi = mid - 0.5, mid + 0.5
    counts, edges = np.histogram(total_return, bins=histogram_bins, range=(lo, hi))

    return MethodResult(
        method=method,
        final_equity=_pstats(final_equity),
        total_return_pct=_pstats(total_return),
        max_drawdown_pct=_pstats(max_drawdown),
        prob_profit=round(float(np.mean(final_equity > initial_capital)), 4),
        risk_of_exceeding_drawdown=round(float(np.mean(max_drawdown > drawdown_threshold_pct)), 4),
        risk_of_ruin=round(float(np.mean(ruined)), 4),
        histogram=Histogram(
            edges=[round(float(e), 4) for e in edges],
            counts=[int(c) for c in counts],
        ),
    )


def _pstats(a: np.ndarray) -> PercentileStats:
    p5, p25, p50, p75, p95 = np.percentile(a, [5, 25, 50, 75, 95])
    return PercentileStats(
        p5=round(float(p5), 4),
        p25=round(float(p25), 4),
        p50=round(float(p50), 4),
        p75=round(float(p75), 4),
        p95=round(float(p95), 4),
        min=round(float(a.min()), 4),
        max=round(float(a.max()), 4),
        mean=round(float(a.mean()), 4),
    )
