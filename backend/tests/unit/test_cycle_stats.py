from __future__ import annotations

import pytest

from app.domain.backtest.cycle_stats import (
    ath_gain_multiples, drawdown_episodes, shallowest_drop_before,
)


def _two_peak():
    # rise 20->100, crash 100->40, recover to 120 (new peak) -> one completed episode drop=0.60,
    # then fall 120->60 (not yet recovered -> open, no episode).
    up1 = [20 + (100 - 20) * j / 9 for j in range(10)]        # ...100 at idx 9
    down1 = [100 - (100 - 40) * j / 5 for j in range(1, 6)]   # ->40
    rec = [40 + (120 - 40) * j / 8 for j in range(1, 9)]      # ->120 (exceeds 100 somewhere)
    down2 = [120 - (120 - 60) * j / 4 for j in range(1, 5)]   # ->60, open
    return up1 + down1 + rec + down2


def test_drawdown_episodes_finds_completed_drop():
    eps = drawdown_episodes(_two_peak())
    assert len(eps) == 1
    assert eps[0]["drop"] == pytest.approx(0.60, abs=1e-6)
    assert eps[0]["peak"] == pytest.approx(100.0)
    assert eps[0]["trough"] == pytest.approx(40.0)


def test_shallowest_drop_before_is_only_past():
    prices = _two_peak()
    eps = drawdown_episodes(prices)
    rec_idx = eps[0]["recovery_idx"]
    # Before the episode recovers, there is no completed drop to lean on.
    assert shallowest_drop_before(eps, rec_idx - 1) is None
    # After recovery it is available.
    assert shallowest_drop_before(eps, rec_idx + 1) == pytest.approx(0.60, abs=1e-6)


def test_shallowest_takes_the_minimum_drop():
    eps = [
        {"drop": 0.80, "recovery_idx": 5},
        {"drop": 0.55, "recovery_idx": 8},
        {"drop": 0.70, "recovery_idx": 12},
    ]
    assert shallowest_drop_before(eps, 100) == pytest.approx(0.55)
    assert shallowest_drop_before(eps, 9) == pytest.approx(0.55)
    assert shallowest_drop_before(eps, 6) == pytest.approx(0.80)


def test_ath_gain_multiples_are_peak_over_prev_peak():
    eps = [{"peak": 100.0}, {"peak": 300.0}, {"peak": 450.0}]
    assert ath_gain_multiples(eps) == pytest.approx([3.0, 1.5])
