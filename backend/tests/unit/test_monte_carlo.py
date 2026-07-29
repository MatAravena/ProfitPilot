"""Unit tests for the pure Monte Carlo trade-sequence resampler.

MC turns a single backtest's realized trades into a *distribution* of outcomes:
- bootstrap (sampling risk) — draw returns with replacement
- shuffle   (ordering risk) — permute the same returns

The domain module is pure numpy: no DB, no FastAPI. It operates on the
fixed-fractional per-trade return series r_i = pnl_i / equity_before_trade_i.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.domain.backtest.monte_carlo import run_monte_carlo, trade_returns


# --------------------------------------------------------------------------- #
# trade_returns — the fixed-fractional per-trade return derivation
# --------------------------------------------------------------------------- #
def test_trade_returns_fixed_fractional_derivation():
    # equity_before_trade_0 = 100            -> r0 = 10 / 100  = 0.10
    # equity_before_trade_1 = 100 + 10 = 110 -> r1 = -5 / 110  = -0.045454...
    r = trade_returns([10.0, -5.0], initial_capital=100.0)
    assert r == pytest.approx([0.10, -5.0 / 110.0])


def test_trade_returns_compound_in_order_reproduces_realized_final_equity():
    pnls = [12.0, -7.0, 20.0, -3.0]
    initial = 1_000.0
    r = trade_returns(pnls, initial_capital=initial)
    compounded = initial * np.prod(1.0 + r)
    assert compounded == pytest.approx(initial + sum(pnls))


def test_trade_returns_requires_at_least_two_trades():
    with pytest.raises(ValueError):
        trade_returns([42.0], initial_capital=1_000.0)


# --------------------------------------------------------------------------- #
# run_monte_carlo — determinism & method selection
# --------------------------------------------------------------------------- #
def test_seed_makes_the_result_deterministic():
    returns = np.array([0.02, -0.01, 0.03, -0.015, 0.008])
    a = run_monte_carlo(returns, 10_000.0, n_simulations=2_000, seed=7)
    b = run_monte_carlo(returns, 10_000.0, n_simulations=2_000, seed=7)
    assert a == b


def test_only_requested_methods_are_computed():
    returns = np.array([0.02, -0.01, 0.03])
    res = run_monte_carlo(returns, 10_000.0, n_simulations=100, methods=["bootstrap"], seed=1)
    assert set(res.methods) == {"bootstrap"}


def test_shared_context_reports_trade_count_and_realized_return():
    returns = np.array([0.02, -0.01, 0.03])
    realized = (np.prod(1.0 + returns) - 1.0) * 100.0
    res = run_monte_carlo(returns, 10_000.0, n_simulations=500, seed=1)
    assert res.n_trades == 3
    assert res.n_simulations == 500
    assert res.initial_capital == 10_000.0
    assert res.realized_total_return_pct == pytest.approx(realized)


# --------------------------------------------------------------------------- #
# shuffle — a permutation of the same multiset has order-invariant final equity
# --------------------------------------------------------------------------- #
def test_shuffle_final_equity_is_order_invariant():
    # Compounding is commutative: Π(1 + r) is identical for every permutation,
    # so shuffle's final-equity distribution is a spike at the realized value.
    returns = np.array([0.10, -0.05, 0.03, -0.02])
    realized_final = 10_000.0 * float(np.prod(1.0 + returns))
    res = run_monte_carlo(returns, 10_000.0, n_simulations=1_000, methods=["shuffle"], seed=3)
    shuffle = res.methods["shuffle"]
    assert shuffle.final_equity.min == pytest.approx(realized_final)
    assert shuffle.final_equity.max == pytest.approx(realized_final)


def test_shuffle_max_drawdown_hand_computed():
    # returns [-0.10, +0.05]: both permutations peak-to-trough to exactly 10%.
    #   order A: 1 -> 0.90 -> 0.945     dd = (1 - 0.90)/1       = 10%
    #   order B: 1 -> 1.05 -> 0.945     dd = (1.05 - 0.945)/1.05 = 10%
    returns = np.array([-0.10, 0.05])
    res = run_monte_carlo(returns, 1_000.0, n_simulations=200, methods=["shuffle"], seed=5)
    dd = res.methods["shuffle"].max_drawdown_pct
    assert dd.p50 == pytest.approx(10.0)
    assert dd.min == pytest.approx(10.0)
    assert dd.max == pytest.approx(10.0)


def test_risk_of_exceeding_drawdown_threshold():
    returns = np.array([-0.10, 0.05])  # every path draws down exactly 10%
    res = run_monte_carlo(
        returns, 1_000.0, n_simulations=200, methods=["shuffle"], seed=5,
        drawdown_threshold_pct=5.0,
    )
    assert res.methods["shuffle"].risk_of_exceeding_drawdown == pytest.approx(1.0)

    res2 = run_monte_carlo(
        returns, 1_000.0, n_simulations=200, methods=["shuffle"], seed=5,
        drawdown_threshold_pct=20.0,
    )
    assert res2.methods["shuffle"].risk_of_exceeding_drawdown == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# bootstrap — all-positive returns can never lose
# --------------------------------------------------------------------------- #
def test_all_positive_returns_always_profit_never_ruin():
    returns = np.array([0.01, 0.02, 0.03])
    res = run_monte_carlo(returns, 10_000.0, n_simulations=1_000, seed=2)
    for m in res.methods.values():
        assert m.prob_profit == pytest.approx(1.0)
        assert m.risk_of_ruin == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# ruin guard — a -100% return zeroes the account and counts as ruin
# --------------------------------------------------------------------------- #
def test_ruin_guard_clamps_equity_to_zero_and_counts_ruin():
    # Every shuffle permutation of [-1.0, x] contains the -1.0 (total loss), so
    # Π(1 + r) = 0 for every path: guaranteed ruin, zero final equity.
    returns = np.array([-1.0, 0.05])
    res = run_monte_carlo(returns, 10_000.0, n_simulations=200, methods=["shuffle"], seed=9)
    shuffle = res.methods["shuffle"]
    assert shuffle.risk_of_ruin == pytest.approx(1.0)
    assert shuffle.prob_profit == pytest.approx(0.0)
    assert shuffle.final_equity.max == pytest.approx(0.0)
    assert shuffle.total_return_pct.p50 == pytest.approx(-100.0)


# --------------------------------------------------------------------------- #
# histogram — well-formed bins for the frontend chart
# --------------------------------------------------------------------------- #
def test_histogram_edges_and_counts_are_consistent():
    returns = np.array([0.02, -0.01, 0.03, -0.02, 0.015])
    res = run_monte_carlo(returns, 10_000.0, n_simulations=1_000, seed=4)
    hist = res.methods["bootstrap"].histogram
    assert len(hist.edges) == len(hist.counts) + 1
    assert sum(hist.counts) == 1_000
