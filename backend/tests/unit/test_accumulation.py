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


def test_cycle_buydip_selltop_sells_into_top_and_realizes_pnl():
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


# --------------------------------------------------------------------------- #
# Ledger cost-basis accounting (moving-average) — regression for the inflated
# realized_pnl / avg_cost_basis bug that made the selling arms nonsensical.
# --------------------------------------------------------------------------- #

def test_sell_realizes_pnl_at_moving_avg_cost():
    # Buy 1 unit @100 (no fees), price -> 200, sell 0.5: realized = 0.5*(200-100)=50.
    led = AccumulationLedger(commission_pct=0.0, slippage_pct=0.0)
    led.contribute(100.0)
    led.buy(100.0, 100.0)          # 1 unit @100
    led.sell(0.5, 200.0)           # sell half at 200
    assert led.realized_pnl == pytest.approx(50.0)
    assert led.avg_cost_basis == pytest.approx(100.0)   # remaining basis unchanged by a sell
    assert led.units == pytest.approx(0.5)


def test_avg_cost_reflects_remaining_after_sell():
    # Buy 1@100 then 1@300 -> avg 200. Sell half -> avg stays 200, cost pool halves.
    led = AccumulationLedger(commission_pct=0.0, slippage_pct=0.0)
    led.contribute(400.0)
    led.buy(100.0, 100.0)          # +1 unit, cost 100
    led.buy(300.0, 300.0)          # +1 unit, cost 300 -> 2 units, avg 200
    assert led.avg_cost_basis == pytest.approx(200.0)
    led.sell(1.0, 500.0)           # sell 1 unit
    assert led.avg_cost_basis == pytest.approx(200.0)   # remaining unit still cost 200
    assert led.realized_pnl == pytest.approx(300.0)     # 500 - 200


def test_realized_pnl_not_inflated_by_rebuys():
    # Round-trip buy/sell/buy: realized is the sum of per-sell (proceeds - avg_cost*units),
    # never a lifetime blend that under-states basis on later sells.
    led = AccumulationLedger(commission_pct=0.0, slippage_pct=0.0)
    led.contribute(1000.0)
    led.buy(100.0, 100.0)          # 1u @100
    led.sell(1.0, 200.0)           # realized +100 (200-100)
    led.buy(200.0, 200.0)          # 1u @200
    led.sell(1.0, 250.0)           # realized +50 (250-200)
    assert led.realized_pnl == pytest.approx(150.0)
    assert led.units == pytest.approx(0.0)
    assert led.avg_cost_basis == pytest.approx(0.0)


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


# --------------------------------------------------------------------------- #
# CycleHunterPolicy — ATH-aware rotation state machine
# --------------------------------------------------------------------------- #
from app.domain.backtest.accumulation import CycleHunterParams, CycleHunterPolicy


def _cycle_path_bars():
    """Daily bars whose peak lands on the predicted 2024-04-20 cycle top (~+535d = 2025-10-07),
    then crash, bottom, and recovery toward the prior ATH. Piecewise-linear with mild jitter
    so ATR/Supertrend behave. Returns bars starting well before the top."""
    top = date(2024, 4, 20) + timedelta(days=CycleParams().days_to_top)   # 2025-10-07
    start = top - timedelta(days=200)
    peak = 120_000.0
    legs = [
        (200, 45_000.0, peak),        # rise into the top (ends at `top`)
        (150, peak, 38_000.0),        # crash
        (120, 38_000.0, 42_000.0),    # grind near bottom
        (260, 42_000.0, 118_000.0),   # recovery back toward prior ATH
    ]
    closes: list[float] = []
    for length, a, b in legs:
        for j in range(length):
            frac = j / max(1, length - 1)
            px = a + (b - a) * frac
            jitter = 1.0 + (0.01 if j % 2 else -0.01)   # ±1% to give TR some width
            closes.append(px * jitter)
    base = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    bars = []
    for i, c in enumerate(closes):
        bars.append(OHLCV(timestamp=base + timedelta(days=i), symbol="BTCUSDT",
                          open=c, high=c * 1.01, low=c * 0.99, close=c,
                          volume=1.0, timeframe=Timeframe.D1))
    return bars


def _drive_hunter(bars, hp: CycleHunterParams | None = None):
    """Run CycleHunterPolicy bar-by-bar, capturing state + units + cash for white-box asserts."""
    policy = CycleHunterPolicy(CycleParams(), hp or CycleHunterParams())
    policy.prepare(bars)
    ledger = AccumulationLedger(commission_pct=0.0, slippage_pct=0.0)
    ctx = RunContext("contributions", 100.0, 0.0, len(bars))
    last = None
    rows = []
    for i, bar in enumerate(bars):
        d = bar.timestamp.date()
        if last is None or (d - last).days >= 1:
            ledger.contribute(100.0)
            last = d
        buy_cash, sell_units = policy.decide(i, bars, ledger, ctx)
        if sell_units > 0:
            ledger.sell(sell_units, bar.close)
        if buy_cash > 0:
            ledger.buy(buy_cash, bar.close)
        rows.append((policy._state, ledger.units, ledger.cash))
    return rows


def test_hunter_progresses_through_all_states():
    # Disable the ATR-percentile gate so the flow is driven by the (deterministic) cycle path.
    hp = CycleHunterParams(atr_pctile_hi=0.0)
    rows = _drive_hunter(_cycle_path_bars(), hp)
    seen = {r[0] for r in rows}
    assert {"DISTRIBUTE", "COOLDOWN", "BEAR_ACCUMULATE"}.issubset(seen)


def test_hunter_keeps_a_core_through_distribution():
    hp = CycleHunterParams(atr_pctile_hi=0.0)
    rows = _drive_hunter(_cycle_path_bars(), hp)
    states = [r[0] for r in rows]
    units = [r[1] for r in rows]
    dist_start = states.index("DISTRIBUTE")
    peak_units = units[dist_start - 1]
    # Through DISTRIBUTE + COOLDOWN (no buying) units only fall, but never below the kept core.
    trough = min(u for s, u in zip(states, units) if s in ("DISTRIBUTE", "COOLDOWN"))
    assert trough >= (1 - hp.sell_cap_frac) * peak_units - 1e-9


def test_hunter_cooldown_blocks_buying():
    hp = CycleHunterParams(atr_pctile_hi=0.0)
    rows = _drive_hunter(_cycle_path_bars(), hp)
    cooldown_units = [r[1] for r in rows if r[0] == "COOLDOWN"]
    # No buys during cooldown -> units are non-increasing across the whole cooldown span.
    assert all(b <= a + 1e-9 for a, b in zip(cooldown_units, cooldown_units[1:]))


def test_hunter_bear_deploys_dry_powder():
    hp = CycleHunterParams(atr_pctile_hi=0.0)
    rows = _drive_hunter(_cycle_path_bars(), hp)
    bear = [(u, cash) for s, u, cash in rows if s == "BEAR_ACCUMULATE"]
    assert bear, "expected a BEAR_ACCUMULATE phase"
    # Units rise and dry powder is spent from start to end of the bear phase.
    assert bear[-1][0] > bear[0][0]
    assert bear[-1][1] < bear[0][1]


def test_hunter_no_look_ahead_full_run():
    # Decisions for the first k bars must be identical whether or not later bars exist.
    bars = _cycle_path_bars()
    hp = CycleHunterParams(atr_pctile_hi=0.0)
    k = 400
    full = _drive_hunter(bars, hp)
    trunc = _drive_hunter(bars[:k], hp)
    assert [r[0] for r in full[:k]] == [r[0] for r in trunc]
    assert [round(r[1], 10) for r in full[:k]] == [round(r[1], 10) for r in trunc]


# --------------------------------------------------------------------------- #
# AccumulatorGridPolicy — buy-the-dip accumulation + light income trims, keep core
# --------------------------------------------------------------------------- #
from app.domain.backtest.accumulation import AccumulatorGridParams, AccumulatorGridPolicy


def _drive_grid(bars, gp: AccumulatorGridParams | None = None):
    """Run AccumulatorGridPolicy bar-by-bar, capturing (buy_cash, sell_units, units, cash, price)."""
    policy = AccumulatorGridPolicy(gp or AccumulatorGridParams())
    policy.prepare(bars)
    ledger = AccumulationLedger(commission_pct=0.0, slippage_pct=0.0)
    ctx = RunContext("contributions", 100.0, 0.0, len(bars))
    last = None
    rows = []
    for i, bar in enumerate(bars):
        d = bar.timestamp.date()
        if last is None or (d - last).days >= 1:
            ledger.contribute(100.0)
            last = d
        cash_before = ledger.cash
        buy_cash, sell_units = policy.decide(i, bars, ledger, ctx)
        if sell_units > 0:
            ledger.sell(sell_units, bar.close)
        if buy_cash > 0:
            ledger.buy(buy_cash, bar.close)
        frac = buy_cash / cash_before if cash_before > 0 else 0.0
        rows.append(dict(i=i, buy_cash=buy_cash, sell_units=sell_units, frac=frac,
                         units=ledger.units, cash=ledger.cash, price=bar.close))
    return rows


def _ramp_bars(closes):
    base = datetime(2020, 1, 1, tzinfo=timezone.utc)
    return [OHLCV(timestamp=base + timedelta(days=i), symbol="BTCUSDT",
                  open=c, high=c * 1.01, low=c * 0.99, close=c, volume=1.0, timeframe=Timeframe.D1)
            for i, c in enumerate(closes)]


def _rise_crash_recover():
    # rise 20k->100k, crash to 30k, recover to 95k — exercises dip-buy, trims, and core floor.
    up = [20_000 + (100_000 - 20_000) * j / 249 for j in range(250)]
    down = [100_000 + (30_000 - 100_000) * j / 149 for j in range(150)]
    rec = [30_000 + (95_000 - 30_000) * j / 199 for j in range(200)]
    return _ramp_bars(up + down + rec)


def test_grid_deploys_more_of_cash_on_deeper_drawdown():
    gp = AccumulatorGridParams()
    rows = _drive_grid(_rise_crash_recover(), gp)
    # Deploy fraction of available cash should be higher deep in the crash than near the ATH.
    near_ath = [r["frac"] for r in rows if r["i"] in range(230, 250)]     # just before the top
    deep_dip = [r["frac"] for r in rows if r["i"] in range(380, 400)]     # near the bottom
    assert sum(deep_dip) / len(deep_dip) > sum(near_ath) / len(near_ath)


def test_grid_never_sells_below_core_floor():
    gp = AccumulatorGridParams()
    rows = _drive_grid(_rise_crash_recover(), gp)
    max_units = 0.0
    for r in rows:
        max_units = max(max_units, r["units"])
        assert r["units"] >= gp.core_frac * max_units - 1e-6


def test_grid_does_not_trim_in_a_bear():
    # Monotonic decline below cost and below the trend filter -> no sells at all.
    gp = AccumulatorGridParams()
    closes = [100_000 * (0.995 ** i) for i in range(300)]
    rows = _drive_grid(_ramp_bars(closes), gp)
    assert all(r["sell_units"] == 0.0 for r in rows)


def test_grid_trend_filter_off_harvests_more():
    # On a choppy sideways path, turning the uptrend filter OFF lets the grid trim on rallies that
    # sit below the SMA too, so it harvests strictly more often (the ranging-asset mode).
    closes = []
    p = 1000.0
    for i in range(400):
        p *= 1.03 if i % 8 < 4 else 0.97
        closes.append(p)
    bars = _ramp_bars(closes)
    on = _drive_grid(bars, AccumulatorGridParams(use_trend_filter=True, profit_step=0.03,
                                                 trim_pos_hi=0.6, sma_slow=50))
    off = _drive_grid(bars, AccumulatorGridParams(use_trend_filter=False, profit_step=0.03,
                                                  trim_pos_hi=0.6))
    trims_on = sum(1 for r in on if r["sell_units"] > 0)
    trims_off = sum(1 for r in off if r["sell_units"] > 0)
    assert trims_off > trims_on


def test_grid_harvests_income_on_rips():
    # A choppy uptrend above cost should trigger some trims (realized income) while still holding.
    gp = AccumulatorGridParams()
    closes = []
    price = 20_000.0
    for i in range(500):
        price *= 1.004 * (1.06 if i % 10 < 5 else 0.95)   # net up with big oscillation
        closes.append(price)
    rows = _drive_grid(_ramp_bars(closes), gp)
    assert any(r["sell_units"] > 0 for r in rows)          # harvested at least once
    assert rows[-1]["units"] > 0                            # never fully exits


def test_grid_no_look_ahead():
    bars = _rise_crash_recover()
    k = 350
    full = _drive_grid(bars)
    trunc = _drive_grid(bars[:k])
    assert [round(r["units"], 10) for r in full[:k]] == [round(r["units"], 10) for r in trunc]


# --------------------------------------------------------------------------- #
# CycleRotationPolicy — sell most near a confirmed ATH, buy the lower half of the drop
# --------------------------------------------------------------------------- #
from app.domain.backtest.accumulation import CycleRotationParams, CycleRotationPolicy
from app.domain.backtest.cycle_stats import auto_drop_estimator


def _const_drop(drop: float):
    return lambda i: drop


def _sell_high_buy_low_bars():
    """Path anchored to the 2024 halving: blow-off rise into the predicted top (~2025-10-07), a
    SHARP crash (so Supertrend flips fast and selling stops near the top), then recovery — so
    DISTRIBUTE sells high and DEPLOY buys the lower half."""
    top = date(2024, 4, 20) + timedelta(days=CycleParams().days_to_top)   # 2025-10-07
    start = top - timedelta(days=220)
    closes = []
    for j in range(220):                          # blow-off: most of the gain in the last stretch
        closes.append(20_000.0 + 100_000.0 * (j / 219) ** 3)
    for j in range(70):                           # sharp crash 120k -> ~38k
        closes.append(120_000.0 + (38_000.0 - 120_000.0) * (j / 69))
    for j in range(220):                          # recovery toward the prior ATH
        closes.append(38_000.0 + (105_000.0 - 38_000.0) * (j / 219))
    base = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    return [OHLCV(timestamp=base + timedelta(days=i), symbol="BTCUSDT",
                  open=c, high=c * 1.01, low=c * 0.99, close=c, volume=1.0, timeframe=Timeframe.D1)
            for i, c in enumerate(closes)]


def _drive_rotation(bars, policy):
    policy.prepare(bars)
    ledger = AccumulationLedger(commission_pct=0.0, slippage_pct=0.0)
    ctx = RunContext("contributions", 100.0, 0.0, len(bars))
    last = None
    rows = []
    for i, bar in enumerate(bars):
        d = bar.timestamp.date()
        if last is None or (d - last).days >= 1:
            ledger.contribute(100.0)
            last = d
        buy_cash, sell_units = policy.decide(i, bars, ledger, ctx)
        if sell_units > 0:
            ledger.sell(sell_units, bar.close)
        if buy_cash > 0:
            ledger.buy(buy_cash, bar.close)
        rows.append(dict(i=i, state=policy._state, price=bar.close,
                         buy_cash=buy_cash, sell_units=sell_units, units=ledger.units))
    return rows


_ROT_COMMON = dict(capital_model="contributions", contribution_amount=100.0,
                   contribution_interval_days=1, lump_sum_budget=0.0,
                   commission_pct=0.0, slippage_pct=0.0, bars_per_year=365)


def test_rotation_net_accumulates_vs_hold_when_timing_is_right():
    bars = _sell_high_buy_low_bars()
    rp = CycleRotationParams(sell_fraction_at_ath=0.90)
    rot = run_accumulation(bars, CycleRotationPolicy(CycleParams(), rp, _const_drop(0.50)), **_ROT_COMMON)
    hold = run_accumulation(bars, FlatDcaPolicy(), **_ROT_COMMON)
    # Selling ~everything near 120k and rebuying in the 45-90k zone must net MORE coins than holding.
    assert rot.units_accumulated > hold.units_accumulated


def test_rotation_in_windows_mode_never_sells_before_the_sell_start_day():
    """Discrete-window timing: the arm must be completely inert before day A of the cycle, then
    distribute once the window opens — the literal 'start selling N days after the halving'."""
    bars = _sell_high_buy_low_bars()
    halving = date(2024, 4, 20)
    sell_start = 525   # inside the blow-off, 10 days before the gaussian top (535)
    rp = CycleRotationParams()

    def sold_split(policy):
        rows = _drive_rotation(bars, policy)
        before = sum(r["sell_units"] for r in rows
                     if (bars[r["i"]].timestamp.date() - halving).days < sell_start)
        after = sum(r["sell_units"] for r in rows
                    if (bars[r["i"]].timestamp.date() - halving).days >= sell_start)
        return before, after

    win_before, win_after = sold_split(CycleRotationPolicy(
        CycleParams(timing_mode="windows", sell_start_day=sell_start, sell_end_day=600),
        rp, _const_drop(0.50)))
    gauss_before, _ = sold_split(CycleRotationPolicy(CycleParams(), rp, _const_drop(0.50)))

    assert win_before == 0.0      # hard off before day A...
    assert win_after > 0.0        # ...and it does fire once the window opens
    assert gauss_before > 0.0     # the gaussian curve *does* sell early — the window is what stops it


def test_windows_and_gaussian_modes_produce_different_runs():
    """Guard against the mode being silently ignored anywhere in the wiring."""
    bars = _sell_high_buy_low_bars()
    rp = CycleRotationParams()
    gauss = run_accumulation(bars, CycleRotationPolicy(CycleParams(), rp, _const_drop(0.50)),
                             **_ROT_COMMON)
    win = run_accumulation(
        bars,
        CycleRotationPolicy(CycleParams(timing_mode="windows", sell_start_day=560,
                                        sell_end_day=640), rp, _const_drop(0.50)),
        **_ROT_COMMON,
    )
    assert win.units_accumulated != pytest.approx(gauss.units_accumulated)


def test_rotation_respects_sell_fraction_cap():
    bars = _sell_high_buy_low_bars()
    rp = CycleRotationParams(sell_fraction_at_ath=0.60)
    policy = CycleRotationPolicy(CycleParams(), rp, _const_drop(0.50))
    rows = _drive_rotation(bars, policy)
    sold = sum(r["sell_units"] for r in rows)
    assert sold <= rp.sell_fraction_at_ath * policy._dist_start_units + 1e-9
    assert policy._dist_start_units > 0    # it did distribute


def test_rotation_deploys_only_inside_buy_zone():
    bars = _sell_high_buy_low_bars()
    policy = CycleRotationPolicy(CycleParams(), CycleRotationParams(), _const_drop(0.50))
    rows = _drive_rotation(bars, policy)
    for r in rows:
        if r["state"] == "DEPLOY" and r["buy_cash"] > 0:
            assert r["price"] <= policy._zone_top + 1e-6


def test_rotation_auto_holds_until_a_drawdown_exists():
    # A monotonic rise never completes a drawdown -> auto estimator is None -> never leaves HOLD_CORE.
    closes = [1000 * (1.002 ** i) for i in range(400)]
    bars = _ramp_bars(closes)
    est = auto_drop_estimator([b.close for b in bars], caution_margin=0.05)
    policy = CycleRotationPolicy(CycleParams(), CycleRotationParams(), est)
    rows = _drive_rotation(bars, policy)
    assert all(r["state"] in ("HOLD_CORE", "DISTRIBUTE") for r in rows)
    assert all(r["state"] != "DEPLOY" for r in rows)


def test_rotation_no_look_ahead():
    bars = _sell_high_buy_low_bars()
    k = 300
    p_full = CycleRotationPolicy(CycleParams(), CycleRotationParams(), _const_drop(0.50))
    p_trunc = CycleRotationPolicy(CycleParams(), CycleRotationParams(), _const_drop(0.50))
    full = _drive_rotation(bars, p_full)
    trunc = _drive_rotation(bars[:k], p_trunc)
    assert [r["state"] for r in full[:k]] == [r["state"] for r in trunc]
    assert [round(r["units"], 10) for r in full[:k]] == [round(r["units"], 10) for r in trunc]


# --------------------------------------------------------------------------- #
# Timeframe normalization — per-bar `*_daily` rates scaled by bars-per-day
# --------------------------------------------------------------------------- #
from app.domain.backtest.accumulation import bars_per_day


def _daily_and_4h(closes):
    """Same price path as daily bars and as 4h bars (6 identical bars per day)."""
    top = date(2024, 4, 20) + timedelta(days=CycleParams().days_to_top)
    start = top - timedelta(days=len(closes) - 90)
    base = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    daily = [OHLCV(timestamp=base + timedelta(days=i), symbol="BTCUSDT",
                   open=c, high=c * 1.01, low=c * 0.99, close=c, volume=1.0, timeframe=Timeframe.D1)
             for i, c in enumerate(closes)]
    h4 = []
    for i, c in enumerate(closes):
        for k in range(6):
            h4.append(OHLCV(timestamp=base + timedelta(days=i, hours=4 * k), symbol="BTCUSDT",
                            open=c, high=c * 1.01, low=c * 0.99, close=c, volume=1.0,
                            timeframe=Timeframe.H4))
    return daily, h4


def test_bars_per_day_by_timeframe():
    daily, h4 = _daily_and_4h([100.0] * 30)
    assert bars_per_day(daily) == pytest.approx(1.0)
    assert bars_per_day(h4) == pytest.approx(6.0)


def test_rotation_rates_normalized_across_timeframes():
    # Identical price path on 1d vs 4h should accumulate ~the same — the per-bar rates are scaled
    # by bars-per-day, so the 4h run isn't 6x more aggressive.
    closes = ([20_000 + 100_000 * (j / 219) ** 3 for j in range(220)]
              + [120_000 + (38_000 - 120_000) * (j / 69) for j in range(70)]
              + [38_000 + (105_000 - 38_000) * (j / 219) for j in range(220)])
    daily, h4 = _daily_and_4h(closes)
    rp = CycleRotationParams()
    common_d = dict(capital_model="contributions", contribution_amount=100.0,
                    contribution_interval_days=1, lump_sum_budget=0.0,
                    commission_pct=0.0, slippage_pct=0.0, bars_per_year=365)
    common_h = dict(common_d, bars_per_year=365 * 6)
    rd = run_accumulation(daily, CycleRotationPolicy(CycleParams(), rp, _const_drop(0.5)), **common_d)
    rh = run_accumulation(h4, CycleRotationPolicy(CycleParams(), rp, _const_drop(0.5)), **common_h)
    assert rh.units_accumulated == pytest.approx(rd.units_accumulated, rel=0.12)
