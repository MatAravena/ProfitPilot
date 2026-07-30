"""Deterministic Bitcoin halving-cycle model — the master clock for the cycle-weighted
accumulation strategy.

Halvings occur every 210,000 blocks (~1458 days). "Days since the most recent halving" is
computable for any date with ZERO look-ahead. Two intensity curves translate cycle position
into behavior: buy_intensity peaks at the predicted cycle bottom, sell_intensity at the
predicted top. All offsets are tunable parameters (CycleParams) — no magic constants.

NOTE: only ~3 completed cycles exist, so these offsets are fit to past tops/bottoms; treat
results as one live out-of-sample cycle, not proof.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Tuple

# Known Bitcoin halving dates (UTC).
HALVING_DATES: Tuple[date, ...] = (
    date(2012, 11, 28),
    date(2016, 7, 9),
    date(2020, 5, 11),
    date(2024, 4, 20),
)
CYCLE_LENGTH_DAYS = 1458  # ~4 years; used to extrapolate halvings beyond the known ones


@dataclass(frozen=True)
class CycleParams:
    days_to_top: int = 535        # halving -> predicted cycle top
    top_to_bottom: int = 380      # top -> predicted cycle bottom
    sigma_top: float = 90.0       # width (days) of the distribute (sell) bump
    sigma_bottom: float = 120.0   # width (days) of the accumulate (buy) bump
    base_buy: float = 0.25        # floor buy intensity — it's still DCA, always buys something

    @property
    def days_to_bottom(self) -> int:
        return self.days_to_top + self.top_to_bottom


def most_recent_halving(d: date) -> date:
    """The most recent halving on or before ``d`` (extrapolating past the last known one)."""
    last = HALVING_DATES[0]
    for h in HALVING_DATES:
        if h <= d:
            last = h
    nxt = last + timedelta(days=CYCLE_LENGTH_DAYS)
    while nxt <= d:
        last = nxt
        nxt = last + timedelta(days=CYCLE_LENGTH_DAYS)
    return last


def days_since_halving(d: date) -> int:
    return (d - most_recent_halving(d)).days


def _gaussian(x: float, mu: float, sigma: float) -> float:
    return math.exp(-0.5 * ((x - mu) / sigma) ** 2)


def buy_intensity(d: date, params: CycleParams = CycleParams()) -> float:
    days = days_since_halving(d)
    bump = _gaussian(days, params.days_to_bottom, params.sigma_bottom)
    return params.base_buy + (1.0 - params.base_buy) * bump


def sell_intensity(d: date, params: CycleParams = CycleParams()) -> float:
    days = days_since_halving(d)
    return _gaussian(days, params.days_to_top, params.sigma_top)


def _reference_halvings(end: date) -> List[date]:
    halvings = list(HALVING_DATES)
    cur = HALVING_DATES[-1] + timedelta(days=CYCLE_LENGTH_DAYS)
    while cur <= end + timedelta(days=CYCLE_LENGTH_DAYS):
        halvings.append(cur)
        cur = cur + timedelta(days=CYCLE_LENGTH_DAYS)
    return halvings


def cycle_markers(
    start: date, end: date, params: CycleParams = CycleParams()
) -> List[Tuple[date, str]]:
    """Predicted top/bottom dates inside [start, end], for chart reference lines."""
    markers: List[Tuple[date, str]] = []
    for h in _reference_halvings(end):
        top = h + timedelta(days=params.days_to_top)
        bottom = h + timedelta(days=params.days_to_bottom)
        if start <= top <= end:
            markers.append((top, "top"))
        if start <= bottom <= end:
            markers.append((bottom, "bottom"))
    return sorted(markers)
