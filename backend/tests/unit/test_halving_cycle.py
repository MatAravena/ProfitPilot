from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain.backtest.halving_cycle import (
    CycleParams, HALVING_DATES, buy_intensity, cycle_markers, days_since_halving, sell_intensity,
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


def test_cycle_markers_land_in_window():
    markers = cycle_markers(date(2024, 1, 1), date(2026, 12, 31))
    kinds = {k for _, k in markers}
    assert "top" in kinds and "bottom" in kinds
    # 2024 cycle top ~ 2024-04-20 + 535 days
    assert any(k == "top" and abs((d - (date(2024, 4, 20) + timedelta(days=535))).days) <= 1
               for d, k in markers)
