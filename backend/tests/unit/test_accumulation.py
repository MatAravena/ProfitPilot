from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.enums import Timeframe
from app.core.types import OHLCV
from app.domain.backtest.accumulation import FlatDcaPolicy, run_accumulation


def _bars(closes: list[float]) -> list[OHLCV]:
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    return [
        OHLCV(timestamp=start + timedelta(days=i), symbol="BTCUSDT",
              open=c, high=c, low=c, close=c, volume=1.0, timeframe=Timeframe.D1)
        for i, c in enumerate(closes)
    ]


def _run_flat(closes, **kw):
    defaults = dict(
        capital_model="contributions", contribution_amount=100.0,
        contribution_interval_days=1, lump_sum_budget=0.0,
        commission_pct=0.0, slippage_pct=0.0, bars_per_year=365,
    )
    defaults.update(kw)
    return run_accumulation(_bars(closes), FlatDcaPolicy(), **defaults)


def test_flat_dca_on_constant_price_units_and_cost_basis():
    # Buy $100 for 10 days at price 100, no fees -> 10 units, avg cost 100.
    res = _run_flat([100.0] * 10)
    assert res.units_accumulated == pytest.approx(10.0)
    assert res.avg_cost_basis == pytest.approx(100.0)
    assert res.total_contributed == pytest.approx(1000.0)


def test_flat_dca_avg_cost_between_min_and_max_on_rising_price():
    res = _run_flat([100.0, 150.0, 200.0], contribution_interval_days=1)
    assert 100.0 < res.avg_cost_basis < 200.0


def test_accounting_identity_accumulate_only_no_fees():
    # contributions must equal ending cash + gross cash spent on units (no sells, no fees).
    # Reconstructed from ArmResult, whose avg_cost_basis is cent-rounded, so tolerate cents.
    res = _run_flat([100.0, 120.0, 90.0, 110.0])
    spent = res.avg_cost_basis * res.units_accumulated
    assert res.total_contributed == pytest.approx(spent + res.dry_powder, abs=0.05)


def test_commission_and_slippage_raise_cost_basis():
    clean = _run_flat([100.0] * 5, commission_pct=0.0, slippage_pct=0.0)
    costly = _run_flat([100.0] * 5, commission_pct=0.001, slippage_pct=0.0005)
    assert costly.avg_cost_basis > clean.avg_cost_basis
    assert costly.units_accumulated < clean.units_accumulated


def test_lump_sum_flat_dca_spreads_budget_over_all_bars():
    res = _run_flat([100.0] * 4, capital_model="lump_sum", lump_sum_budget=400.0,
                    contribution_amount=0.0)
    assert res.total_contributed == pytest.approx(400.0)
    assert res.units_accumulated == pytest.approx(4.0)   # 100/bar at price 100


# --------------------------------------------------------------------------- #
# CycleWeightedPolicy — cycle timing + price confirmation
# --------------------------------------------------------------------------- #
from datetime import date

from app.domain.backtest.accumulation import (
    AccumulationLedger, CycleWeightedPolicy, RunContext,
)
from app.domain.backtest.halving_cycle import CycleParams


def _bars_from(start_date, closes):
    base = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
    return [
        OHLCV(timestamp=base + timedelta(days=i), symbol="BTCUSDT",
              open=c, high=c, low=c, close=c, volume=1.0, timeframe=Timeframe.D1)
        for i, c in enumerate(closes)
    ]


def test_cycle_policy_buys_more_near_predicted_bottom_than_top():
    # Flat price so only the cycle clock differs. Compare units bought in a top window vs a
    # bottom window of equal length, each fed the same contributions.
    p = CycleParams()
    halving = date(2024, 4, 20)
    top_start = halving + timedelta(days=p.days_to_top - 15)
    bottom_start = halving + timedelta(days=p.days_to_bottom - 15)

    common = dict(capital_model="contributions", contribution_amount=100.0,
                  contribution_interval_days=1, lump_sum_budget=0.0,
                  commission_pct=0.0, slippage_pct=0.0, bars_per_year=365)

    top_res = run_accumulation(_bars_from(top_start, [100.0] * 30), CycleWeightedPolicy(p), **common)
    bottom_res = run_accumulation(_bars_from(bottom_start, [100.0] * 30), CycleWeightedPolicy(p), **common)
    assert bottom_res.units_accumulated > top_res.units_accumulated


def test_full_rotation_sells_into_top_and_realizes_pnl():
    # Accumulate cheap, then a rising price into the predicted-top window should trigger sells.
    p = CycleParams()
    halving = date(2024, 4, 20)
    start = halving + timedelta(days=p.days_to_top - 60)
    closes = [100.0] * 30 + [200.0] * 30   # price doubles heading into the top window
    res = run_accumulation(_bars_from(start, closes),
                           CycleWeightedPolicy(p, distribute=True),
                           capital_model="contributions", contribution_amount=100.0,
                           contribution_interval_days=1, lump_sum_budget=0.0,
                           commission_pct=0.0, slippage_pct=0.0, bars_per_year=365)
    assert res.realized_pnl > 0
    assert res.dry_powder > 0   # sold some units back to cash


def test_no_look_ahead_decision_depends_only_on_past_bars():
    # The decision at bar i must be identical whether or not future bars exist.
    p = CycleParams()
    bars = _bars_from(date(2024, 10, 1), [100, 110, 90, 120, 80, 130, 95, 105])
    policy_full = CycleWeightedPolicy(p)
    policy_trunc = CycleWeightedPolicy(p)
    policy_full.prepare(bars)
    policy_trunc.prepare(bars[:5])
    ctx = RunContext("contributions", 100.0, 0.0, len(bars))
    led_a, led_b = AccumulationLedger(0, 0), AccumulationLedger(0, 0)
    led_a.contribute(1000)
    led_b.contribute(1000)
    dec_full = policy_full.decide(4, bars, led_a, ctx)
    dec_trunc = policy_trunc.decide(4, bars[:5], led_b, ctx)
    assert dec_full == pytest.approx(dec_trunc)
