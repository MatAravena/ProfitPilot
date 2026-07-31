"""Only-past realized-drawdown statistics for the auto rotation arm.

A "completed episode" is a running-ATH peak, the minimum price before a later bar exceeds that peak
(recovery). Its drop is (peak - trough) / peak. Because an episode is only recorded once price has
recovered above the prior peak, filtering by ``recovery_idx < i`` yields a strictly look-ahead-free
estimate at bar ``i`` — the auto arm knows only about drawdowns that already fully played out.
"""
from __future__ import annotations

from typing import Callable, List, Optional


def drawdown_episodes(prices: List[float]) -> List[dict]:
    n = len(prices)
    episodes: List[dict] = []
    if n == 0:
        return episodes
    run_peak = prices[0]
    run_peak_idx = 0
    trough = prices[0]
    trough_idx = 0
    in_dd = False
    for i in range(1, n):
        p = prices[i]
        if p >= run_peak:
            if in_dd:
                episodes.append({
                    "peak_idx": run_peak_idx, "peak": run_peak,
                    "trough_idx": trough_idx, "trough": trough,
                    "recovery_idx": i, "drop": (run_peak - trough) / run_peak if run_peak > 0 else 0.0,
                })
                in_dd = False
            run_peak = p
            run_peak_idx = i
            trough = p
            trough_idx = i
        else:
            in_dd = True
            if p < trough:
                trough = p
                trough_idx = i
    return episodes


def shallowest_drop_before(episodes: List[dict], i: int) -> Optional[float]:
    """Smallest completed drop whose recovery is strictly before bar ``i`` (None if none yet)."""
    past = [e["drop"] for e in episodes if e["recovery_idx"] < i]
    return min(past) if past else None


def ath_gain_multiples(episodes: List[dict]) -> List[float]:
    """peak / previous-peak across completed episodes (BTC's diminishing cycle-over-cycle gains)."""
    peaks = [e["peak"] for e in episodes]
    return [peaks[k] / peaks[k - 1] for k in range(1, len(peaks)) if peaks[k - 1] > 0]


def auto_drop_estimator(
    prices: List[float], caution_margin: float = 0.05, floor: float = 0.05
) -> Callable[[int], Optional[float]]:
    """Build the auto arm's only-past expected-drop function: shallowest realized drop before bar
    ``i``, made ``caution_margin`` shallower so a fill is ~guaranteed but still cheap. Returns None
    until the first drawdown has fully recovered (early history just DCAs)."""
    episodes = drawdown_episodes(prices)

    def estimate(i: int) -> Optional[float]:
        drop = shallowest_drop_before(episodes, i)
        if drop is None:
            return None
        return max(floor, drop - caution_margin)

    return estimate
