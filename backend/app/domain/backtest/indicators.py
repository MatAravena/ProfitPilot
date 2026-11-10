"""Pure-Python technical indicators for the accumulation backtester.

Every function is causal (look-ahead-free): the value at index ``i`` depends only on inputs
at indices ``<= i``. Returned lists are the same length as the input, with ``None`` where
there is not yet enough history. Kept dependency-free (no numpy/rust) so the domain layer
stays importable everywhere the accumulation policies run.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple


def sma(values: List[float], period: int) -> List[Optional[float]]:
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if period <= 0:
        return out
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            out[i] = running / period
    return out


def ema(values: List[float], period: int) -> List[Optional[float]]:
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if period <= 0 or n < period:
        return out
    seed = sum(values[:period]) / period          # seed with SMA of first `period`
    out[period - 1] = seed
    k = 2.0 / (period + 1)
    prev = seed
    for i in range(period, n):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def true_ranges(highs: List[float], lows: List[float], closes: List[float]) -> List[float]:
    n = len(highs)
    tr: List[float] = [0.0] * n
    for i in range(n):
        if i == 0:
            tr[i] = highs[i] - lows[i]
        else:
            pc = closes[i - 1]
            tr[i] = max(highs[i] - lows[i], abs(highs[i] - pc), abs(lows[i] - pc))
    return tr


def atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> List[Optional[float]]:
    """Wilder's ATR (RMA of true range)."""
    n = len(highs)
    out: List[Optional[float]] = [None] * n
    if period <= 0 or n < period:
        return out
    tr = true_ranges(highs, lows, closes)
    prev = sum(tr[:period]) / period
    out[period - 1] = prev
    for i in range(period, n):
        prev = (prev * (period - 1) + tr[i]) / period
        out[i] = prev
    return out


def supertrend(
    highs: List[float], lows: List[float], closes: List[float],
    period: int = 10, multiplier: float = 3.0,
) -> List[int]:
    """Supertrend direction: +1 (bullish) / -1 (bearish). Bars before ATR is ready default +1."""
    n = len(closes)
    direction: List[int] = [1] * n
    if n == 0:
        return direction
    atrv = atr(highs, lows, closes, period)
    final_upper = [0.0] * n
    final_lower = [0.0] * n
    prev_dir = 1
    started = False
    for i in range(n):
        a = atrv[i]
        if a is None:
            direction[i] = 1
            continue
        hl2 = (highs[i] + lows[i]) / 2.0
        basic_upper = hl2 + multiplier * a
        basic_lower = hl2 - multiplier * a
        if not started:
            final_upper[i] = basic_upper
            final_lower[i] = basic_lower
            prev_dir = 1 if closes[i] >= hl2 else -1
            direction[i] = prev_dir
            started = True
            continue
        final_upper[i] = (basic_upper
                          if (basic_upper < final_upper[i - 1] or closes[i - 1] > final_upper[i - 1])
                          else final_upper[i - 1])
        final_lower[i] = (basic_lower
                          if (basic_lower > final_lower[i - 1] or closes[i - 1] < final_lower[i - 1])
                          else final_lower[i - 1])
        if closes[i] > final_upper[i - 1]:
            d = 1
        elif closes[i] < final_lower[i - 1]:
            d = -1
        else:
            d = prev_dir
        direction[i] = d
        prev_dir = d
    return direction


def rolling_percentile(values: List[Optional[float]], window: int) -> List[float]:
    """Percentile rank (0..1) of ``values[i]`` within its trailing ``window`` (only-past).

    ``None`` entries are ignored (both as the current value -> 0.0, and inside the window).
    """
    n = len(values)
    out: List[float] = [0.0] * n
    if window <= 0:
        return out
    for i in range(n):
        v = values[i]
        if v is None:
            out[i] = 0.0
            continue
        lo = max(0, i - window + 1)
        win = [x for x in values[lo : i + 1] if x is not None]
        if not win:
            out[i] = 0.0
            continue
        leq = sum(1 for x in win if x <= v)
        out[i] = leq / len(win)
    return out


def bollinger(
    values: List[float], period: int = 20, num_std: float = 2.0,
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    mid = sma(values, period)
    n = len(values)
    upper: List[Optional[float]] = [None] * n
    lower: List[Optional[float]] = [None] * n
    for i in range(n):
        m = mid[i]
        if m is None:
            continue
        window = values[i - period + 1 : i + 1]
        variance = sum((x - m) ** 2 for x in window) / period
        std = math.sqrt(variance)
        upper[i] = m + num_std * std
        lower[i] = m - num_std * std
    return mid, upper, lower


def bandwidth(
    mid: List[Optional[float]], upper: List[Optional[float]], lower: List[Optional[float]],
) -> List[Optional[float]]:
    n = len(mid)
    out: List[Optional[float]] = [None] * n
    for i in range(n):
        m, u, l = mid[i], upper[i], lower[i]
        if m is None or u is None or l is None or m == 0:
            continue
        out[i] = (u - l) / m
    return out


def swing_pivots(
    highs: List[float], lows: List[float], *, confirm_bars: int = 3,
) -> Tuple[List[Optional[float]], List[Optional[float]]]:
    """Causal running swing high/low. Index i holds the most recently CONFIRMED pivot price as of
    bar i (or None before any pivot is confirmed). A candidate pivot at index k is only confirmed
    at k + confirm_bars, once confirm_bars bars on both sides are known — never at its own
    timestamp k, which would be look-ahead.

    A candidate is confirmed only if it is the *strict, unique* extremum of its window: on a flat
    run every bar ties for the max/min, and confirming ties would report a "pivot" on every bar of
    a plateau (and could even overwrite a real peak with a later tied plateau value) — the opposite
    of a swing point.
    """
    n = len(highs)
    swing_high: List[Optional[float]] = [None] * n
    swing_low: List[Optional[float]] = [None] * n
    last_high: Optional[float] = None
    last_low: Optional[float] = None
    for i in range(n):
        k = i - confirm_bars
        if confirm_bars <= k < n - confirm_bars:
            window_hi = highs[k - confirm_bars : k + confirm_bars + 1]
            window_lo = lows[k - confirm_bars : k + confirm_bars + 1]
            if highs[k] == max(window_hi) and window_hi.count(highs[k]) == 1:
                last_high = highs[k]
            if lows[k] == min(window_lo) and window_lo.count(lows[k]) == 1:
                last_low = lows[k]
        swing_high[i] = last_high
        swing_low[i] = last_low
    return swing_high, swing_low

