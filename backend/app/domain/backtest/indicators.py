"""Pure-Python technical indicators for the accumulation backtester.

Every function is causal (look-ahead-free): the value at index ``i`` depends only on inputs
at indices ``<= i``. Returned lists are the same length as the input, with ``None`` where
there is not yet enough history. Kept dependency-free (no numpy/rust) so the domain layer
stays importable everywhere the accumulation policies run.
"""
from __future__ import annotations

from typing import List, Optional


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
