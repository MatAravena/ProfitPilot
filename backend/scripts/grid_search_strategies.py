"""Grid search over every tradeable strategy's parameters, via the backtests API.

Requires the backend running locally (`uvicorn app.main:app --reload`) and the
`requests` package (not a project dependency - pip install it if missing).

Usage:
    python scripts/grid_search_strategies.py                  # sweep + rank, print report
    python scripts/grid_search_strategies.py --deploy 3        # also deploy the top N
                                                                 distinct strategy/symbol
                                                                 combos to live paper trading

Skips AlwaysLong (no params, execution smoke-test only) and the user-defined
BollingerBands strategy (duplicate logic of the built-in BollingerBandsMeanReversion).
"""
from __future__ import annotations

import argparse
import itertools
import json
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8000/api/v1"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
# 4h and finer are intentionally excluded: BacktestEngine recomputes indicators from
# scratch per bar, so cost scales ~O(n^2) with bar count. 14k 4h bars made a single
# backtest take ~40s (a full sweep there would take hours); 1d's ~4.2k bars are ~11x
# cheaper and cover just as much history. Revisit if the engine goes incremental.
TIMEFRAMES = ["1d"]
MIN_TRADES = 8  # drop combos with too few trades to be statistically meaningful

GRIDS: dict[str, dict[str, list]] = {
    "SmaCrossover": {
        "fast_period": [5, 10, 20, 30],
        "slow_period": [50, 100, 150, 200],
    },
    "RsiMeanReversion": {
        "rsi_period": [7, 14, 21],
        "oversold": [20, 25, 30],
        "overbought": [70, 75, 80],
    },
    "MacdCrossover": {
        "fast_period": [8, 12, 16],
        "slow_period": [21, 26, 34],
        "signal_period": [5, 9, 12],
    },
    "BollingerBandsMeanReversion": {
        "period": [10, 20, 30, 40],
        "std_mult": [1.5, 2.0, 2.5, 3.0],
    },
}


def param_combos(grid: dict):
    keys = list(grid)
    for values in itertools.product(*[grid[k] for k in keys]):
        combo = dict(zip(keys, values))
        if "fast_period" in combo and "slow_period" in combo:
            if combo["fast_period"] >= combo["slow_period"]:
                continue
        yield combo


def run_sweep() -> list[dict]:
    results = []
    total = errors = 0
    t0 = time.time()

    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:
            for strategy_name, grid in GRIDS.items():
                for params in param_combos(grid):
                    total += 1
                    body = {
                        "strategy_name": strategy_name,
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "initial_capital": 10000,
                        "parameters": params,
                    }
                    try:
                        r = requests.post(f"{BASE}/backtests/run", json=body, timeout=60)
                        if r.status_code != 200:
                            errors += 1
                            continue
                        m = r.json()["metrics"]
                        results.append({
                            "strategy_name": strategy_name,
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "parameters": params,
                            **m,
                        })
                    except Exception as exc:
                        errors += 1
                        print("ERR", strategy_name, symbol, timeframe, params, exc)

                    if total % 10 == 0:
                        print(f"progress: {total} runs, {errors} errors, {time.time()-t0:.1f}s", flush=True)

    print(f"done: {total} runs, {errors} errors, {len(results)} results, {time.time()-t0:.1f}s")
    return results


def rank(results: list[dict]) -> list[dict]:
    filtered = [r for r in results if r["total_trades"] >= MIN_TRADES]
    filtered.sort(key=lambda r: r["sharpe_ratio"], reverse=True)
    return filtered


def report(ranked: list[dict], top_n: int = 20) -> None:
    print(f"\n=== TOP {top_n} by Sharpe (>= {MIN_TRADES} trades) ===")
    for r in ranked[:top_n]:
        print(
            f"{r['strategy_name']:28s} {r['symbol']:8s} sharpe={r['sharpe_ratio']:6.3f} "
            f"ret={r['total_return_pct']:7.2f}% dd={r['max_drawdown_pct']:6.2f}% "
            f"trades={r['total_trades']:4d} wr={r['win_rate']:5.1f}% params={r['parameters']}"
        )

    print("\n=== BEST PER STRATEGY CLASS (any symbol) ===")
    by_class: dict[str, dict] = {}
    for r in ranked:
        k = r["strategy_name"]
        if k not in by_class:
            by_class[k] = r
    for k, r in by_class.items():
        print(
            f"{k:28s} {r['symbol']:8s} sharpe={r['sharpe_ratio']:6.3f} "
            f"ret={r['total_return_pct']:7.2f}% dd={r['max_drawdown_pct']:6.2f}% "
            f"trades={r['total_trades']:4d} params={r['parameters']}"
        )


def deploy_top(ranked: list[dict], n: int) -> None:
    """Create + activate (status=paper) the top N distinct strategy/symbol combos."""
    seen: set[tuple[str, str]] = set()
    picked = []
    for r in ranked:
        key = (r["strategy_name"], r["symbol"])
        if key in seen:
            continue
        seen.add(key)
        picked.append(r)
        if len(picked) == n:
            break

    for r in picked:
        body = {
            "class_name": r["strategy_name"],
            "label": f"{r['strategy_name']} {r['symbol']} (grid-search Sharpe {r['sharpe_ratio']:.2f})",
            "symbol": r["symbol"],
            "timeframe": r["timeframe"],
            "parameters": r["parameters"],
        }
        resp = requests.post(f"{BASE}/strategies", json=body, timeout=30)
        resp.raise_for_status()
        strategy_id = resp.json()["id"]
        resp2 = requests.patch(f"{BASE}/strategies/{strategy_id}/status", json={"status": "paper"}, timeout=30)
        resp2.raise_for_status()
        print(f"deployed: {strategy_id} {body['label']} -> {resp2.json()['status']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--deploy", type=int, default=0, help="deploy the top N distinct strategy/symbol combos to live paper trading")
    args = parser.parse_args()

    results = run_sweep()
    out_path = Path(__file__).parent / "grid_results.json"
    out_path.write_text(json.dumps(results, indent=2))

    ranked = rank(results)
    report(ranked)

    if args.deploy:
        deploy_top(ranked, args.deploy)
