from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain.backtest.halving_cycle import (
    CycleParams, GaussianTiming, HALVING_DATES, WindowTiming, build_timing, buy_intensity,
    cycle_markers, days_since_halving, sell_intensity,
)


def test_days_since_halving_on_known_boundaries():
    assert days_since_halving(date(2024, 4, 20)) == 0            # halving day
    assert days_since_halving(date(2024, 4, 30)) == 10
    # day before the 2024 halving belongs to the 2020 cycle
    assert days_since_halving(date(2024, 4, 19)) == (date(2024, 4, 19) - date(2020, 5, 11)).days


def test_days_since_halving_extrapolates_future_cycles():
    # A date well past the last known halving still resolves to a positive, bounded day count.
    d = date(2029, 1, 1)
    days = days_since_halving(d)
    assert 0 <= days < 1500


def test_buy_intensity_peaks_at_predicted_bottom_and_floors_at_base():
    p = CycleParams()
    # bottom = 535 + 380 = 915 days after a halving
    bottom_day = date(2024, 4, 20)
    at_bottom = buy_intensity(bottom_day + timedelta(days=p.days_to_bottom), p)
    at_top = buy_intensity(bottom_day + timedelta(days=p.days_to_top), p)
    assert at_bottom == pytest.approx(1.0, abs=1e-6)   # bump peak
    assert at_bottom > at_top
    assert at_top >= p.base_buy


def test_sell_intensity_peaks_at_predicted_top():
    p = CycleParams()
    h = date(2024, 4, 20)
    at_top = sell_intensity(h + timedelta(days=p.days_to_top), p)
    at_bottom = sell_intensity(h + timedelta(days=p.days_to_bottom), p)
    assert at_top == pytest.approx(1.0, abs=1e-6)
    assert at_top > at_bottom


# --- discrete halving windows ("start buying on day A, start selling on day C") ---

_H = date(2024, 4, 20)   # a known halving, so day-offsets are exact


def _windows(**kw) -> CycleParams:
    """CycleParams in windows mode; explicit day offsets unless overridden."""
    base = dict(timing_mode="windows",
                sell_start_day=500, sell_end_day=560,
                buy_start_day=880, buy_end_day=950)
    base.update(kw)
    return CycleParams(**base)


def test_build_timing_defaults_to_gaussian_and_reproduces_the_curve_functions():
    p = CycleParams()
    timing = build_timing(p)
    assert isinstance(timing, GaussianTiming)
    d = _H + timedelta(days=300)
    assert timing.buy(d) == pytest.approx(buy_intensity(d, p))
    assert timing.sell(d) == pytest.approx(sell_intensity(d, p))


def test_build_timing_selects_window_mode():
    assert isinstance(build_timing(_windows()), WindowTiming)


def test_sell_is_off_before_the_window_full_inside_and_off_after():
    t = build_timing(_windows())
    assert t.sell(_H + timedelta(days=499)) == 0.0        # nothing before day A
    assert t.sell(_H + timedelta(days=500)) == pytest.approx(1.0)   # switches on exactly at A
    assert t.sell(_H + timedelta(days=530)) == pytest.approx(1.0)
    assert t.sell(_H + timedelta(days=560)) == pytest.approx(1.0)   # inclusive end
    assert t.sell(_H + timedelta(days=561)) == 0.0


def test_buy_holds_the_base_floor_outside_its_window_and_peaks_inside():
    p = _windows()
    t = build_timing(p)
    assert t.buy(_H + timedelta(days=879)) == pytest.approx(p.base_buy)   # still DCA outside
    assert t.buy(_H + timedelta(days=880)) == pytest.approx(1.0)
    assert t.buy(_H + timedelta(days=950)) == pytest.approx(1.0)
    assert t.buy(_H + timedelta(days=951)) == pytest.approx(p.base_buy)


def test_window_wraps_around_the_halving_boundary():
    # A window that opens late in one cycle and closes early in the next.
    t = build_timing(_windows(buy_start_day=1400, buy_end_day=60))
    assert t.buy(_H + timedelta(days=1400)) == pytest.approx(1.0)
    assert t.buy(_H + timedelta(days=1450)) == pytest.approx(1.0)   # before the next halving
    assert t.buy(_H + timedelta(days=1500)) == pytest.approx(1.0)   # ~day 42 of the next cycle
    assert t.buy(_H + timedelta(days=1000)) == pytest.approx(CycleParams().base_buy)


def test_ramp_days_eases_in_without_ever_firing_before_the_start_day():
    t = build_timing(_windows(ramp_days=10))
    assert t.sell(_H + timedelta(days=499)) == 0.0              # hard zero still holds
    assert t.sell(_H + timedelta(days=500)) == pytest.approx(0.0, abs=1e-9)
    assert t.sell(_H + timedelta(days=505)) == pytest.approx(0.5, abs=1e-6)
    assert t.sell(_H + timedelta(days=510)) == pytest.approx(1.0)
    assert t.sell(_H + timedelta(days=555)) == pytest.approx(0.5, abs=1e-6)   # ramps back down
    assert t.sell(_H + timedelta(days=561)) == 0.0


def test_window_day_offsets_default_to_the_gaussian_mass():
    """Omitted window bounds derive from the Gaussian params (single source of truth) —
    top +/- sigma_top, bottom +/- sigma_bottom."""
    p = CycleParams(timing_mode="windows")
    t = build_timing(p)
    assert t.sell(_H + timedelta(days=p.days_to_top)) == pytest.approx(1.0)
    assert t.sell(_H + timedelta(days=p.days_to_top - int(p.sigma_top) - 1)) == 0.0
    assert t.buy(_H + timedelta(days=p.days_to_bottom)) == pytest.approx(1.0)
    assert t.buy(_H + timedelta(days=p.days_to_bottom + int(p.sigma_bottom) + 1)) \
        == pytest.approx(p.base_buy)


def test_windows_are_look_ahead_free_and_identical_across_cycles():
    """Intensity depends only on days since the most recent halving, so the same offset in an
    older cycle gives the same answer — no future information can leak in."""
    t = build_timing(_windows())
    prev_h = date(2020, 5, 11)
    for offset in (499, 500, 530, 561, 900):
        assert t.sell(prev_h + timedelta(days=offset)) == t.sell(_H + timedelta(days=offset))
        assert t.buy(prev_h + timedelta(days=offset)) == t.buy(_H + timedelta(days=offset))


def test_cycle_markers_land_in_window():
    markers = cycle_markers(date(2024, 1, 1), date(2026, 12, 31))
    kinds = {k for _, k in markers}
    assert "top" in kinds and "bottom" in kinds
    # 2024 cycle top ~ 2024-04-20 + 535 days
    assert any(k == "top" and abs((d - (date(2024, 4, 20) + timedelta(days=535))).days) <= 1
               for d, k in markers)
