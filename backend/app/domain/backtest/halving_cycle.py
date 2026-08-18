"""Deterministic Bitcoin halving-cycle model — the master clock for the cycle-weighted
accumulation strategy.

Halvings occur every 210,000 blocks (~1458 days). "Days since the most recent halving" is
computable for any date with ZERO look-ahead. Cycle position is translated into behavior by a
`CycleTiming`: buy intensity peaks around the predicted cycle bottom, sell intensity around the
predicted top. All offsets are tunable parameters (CycleParams) — no magic constants.

Two timings ship, selected by `CycleParams.timing_mode` via `build_timing` (the ONE place that
switches on the mode — everything else depends on the `CycleTiming` abstraction):

- ``gaussian`` (default) — smooth bell curves; intensity fades in and out around the predicted
  top/bottom, so the strategy is always doing a little of everything.
- ``windows`` — discrete calendar windows: nothing before day A, full intensity from day A
  through day B, nothing after. This is the literal "start selling N days after the halving,
  start buying M days after the halving" reading of the cycle thesis.

NOTE: only ~3 completed cycles exist, so these offsets are fit to past tops/bottoms; treat
results as one live out-of-sample cycle, not proof.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Tuple

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

    # --- discrete-window timing (timing_mode="windows") ---
    # Day offsets are "days since the most recent halving". Leaving one None derives it from the
    # Gaussian params above (top/bottom +/- sigma), so the two modes stay in the same ballpark
    # and there is one source of truth for "where the cycle turns".
    timing_mode: str = "gaussian"          # "gaussian" | "windows"
    sell_start_day: Optional[int] = None   # start distributing this many days after the halving
    sell_end_day: Optional[int] = None     # stop distributing
    buy_start_day: Optional[int] = None    # start the heavy accumulation
    buy_end_day: Optional[int] = None      # stop it (back to the base_buy floor)
    ramp_days: int = 0                     # 0 = hard on/off; >0 eases in/out over N days

    @property
    def days_to_bottom(self) -> int:
        return self.days_to_top + self.top_to_bottom


class CycleTiming(ABC):
    """Maps a calendar date to buy/sell intensity in [0, 1]. Pure and look-ahead-free: the only
    input is how many days have passed since the most recent halving."""

    @abstractmethod
    def buy(self, d: date) -> float:
        ...

    @abstractmethod
    def sell(self, d: date) -> float:
        ...


class GaussianTiming(CycleTiming):
    """Smooth bell curves peaking at the predicted bottom (buy) and top (sell)."""

    def __init__(self, params: CycleParams = CycleParams()) -> None:
        self.params = params

    def buy(self, d: date) -> float:
        p = self.params
        bump = _gaussian(days_since_halving(d), p.days_to_bottom, p.sigma_bottom)
        return p.base_buy + (1.0 - p.base_buy) * bump

    def sell(self, d: date) -> float:
        p = self.params
        return _gaussian(days_since_halving(d), p.days_to_top, p.sigma_top)


class WindowTiming(CycleTiming):
    """Discrete windows — full intensity strictly between two day-offsets, nothing outside.

    Windows may wrap past the halving boundary (start > end), e.g. "buy from day 1400 of one
    cycle through day 60 of the next". `ramp_days` eases the edges *inside* the window, so the
    guarantee "zero before the start day" always holds exactly.
    """

    def __init__(self, params: CycleParams = CycleParams()) -> None:
        p = params
        self.params = p
        self.sell_start = p.sell_start_day if p.sell_start_day is not None \
            else p.days_to_top - int(p.sigma_top)
        self.sell_end = p.sell_end_day if p.sell_end_day is not None \
            else p.days_to_top + int(p.sigma_top)
        self.buy_start = p.buy_start_day if p.buy_start_day is not None \
            else p.days_to_bottom - int(p.sigma_bottom)
        self.buy_end = p.buy_end_day if p.buy_end_day is not None \
            else p.days_to_bottom + int(p.sigma_bottom)

    def buy(self, d: date) -> float:
        base = self.params.base_buy
        strength = self._strength(days_since_halving(d), self.buy_start, self.buy_end)
        return base + (1.0 - base) * strength

    def sell(self, d: date) -> float:
        return self._strength(days_since_halving(d), self.sell_start, self.sell_end)

    def _strength(self, day: int, start: int, end: int) -> float:
        """1.0 inside [start, end] (inclusive), 0.0 outside, linearly ramped at the edges."""
        elapsed = _days_into_window(day, start, end)
        if elapsed is None:
            return 0.0
        ramp = self.params.ramp_days
        if ramp <= 0:
            return 1.0
        span = _window_length(start, end)
        remaining = span - elapsed
        return max(0.0, min(1.0, min(elapsed, remaining) / ramp))


def build_timing(params: CycleParams = CycleParams()) -> CycleTiming:
    """The single switch point on `timing_mode`. Callers depend on `CycleTiming`, not on this."""
    if params.timing_mode == "windows":
        return WindowTiming(params)
    return GaussianTiming(params)


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


def _window_length(start: int, end: int) -> int:
    """Window width in days, handling a window that wraps past the halving boundary."""
    return end - start if start <= end else (CYCLE_LENGTH_DAYS - start) + end


def _days_into_window(day: int, start: int, end: int) -> Optional[int]:
    """Days elapsed since the window opened, or None when `day` is outside it."""
    if start <= end:
        return day - start if start <= day <= end else None
    if day >= start:
        return day - start
    if day <= end:
        return (CYCLE_LENGTH_DAYS - start) + day
    return None


def buy_intensity(d: date, params: CycleParams = CycleParams()) -> float:
    """Convenience wrapper — prefer holding a `CycleTiming` when calling this per bar."""
    return build_timing(params).buy(d)


def sell_intensity(d: date, params: CycleParams = CycleParams()) -> float:
    """Convenience wrapper — prefer holding a `CycleTiming` when calling this per bar."""
    return build_timing(params).sell(d)


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
