"""The agreed paper-trading lineup (the 'common ground' to run on the always-on box).

Only strategies that passed out-of-sample testing (TODO.md 🚦 Step 5b), with stops and sizing
the tests support. Paper only (SimulatedBrokerAdapter, real prices) — no broker keys needed.

Run against the running app (default http://127.0.0.1:8000), from backend/:

    python scripts/paper_lineup.py                 # create missing strategies and start them in paper
    python scripts/paper_lineup.py --dry-run       # show what would be created

Idempotent: a strategy whose label already exists is left exactly as it is (status and config
included), so re-running never duplicates or overrides your own changes.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, Dict, List

import httpx

API = "/api/v1/strategies"

_BTC_TREND = {
    "label": "TrendFilter BTC 1d · p100",
    "class_name": "TrendFilter", "symbol": "BTCUSDT", "timeframe": "1d",
    "parameters": {"period": 100},
    # Exits on its own SMA cross; a stop-out just re-enters next bar, so the stop is wide.
    # 2% risk ÷ 20% stop = 10% of the account per position.
    "execution": {"size_pct": 1.0, "risk_per_trade_pct": 0.02, "stop_loss_pct": 0.20, "allow_short": False},
}
_BTC_MACD = {
    "label": "MACD BTC 1d · 16/34/9",
    "class_name": "MacdCrossover", "symbol": "BTCUSDT", "timeframe": "1d",
    "parameters": {"fast_period": 16, "slow_period": 34, "signal_period": 9},
    # A 1.5% stop wrecks MACD on daily BTC (OOS Sharpe 1.29 → 0.77); 10% keeps it.
    # 1% risk ÷ 10% stop = 10% of the account per position.
    "execution": {"size_pct": 1.0, "risk_per_trade_pct": 0.01, "stop_loss_pct": 0.10, "allow_short": False},
}


def _etf(symbol: str) -> Dict[str, Any]:
    # Drawdown control on a diversified basket — each its own paper account, fully invested above
    # the average, cash below.
    return {
        "label": f"TrendFilter {symbol} 1d · p150",
        "class_name": "TrendFilter", "symbol": symbol, "timeframe": "1d",
        "parameters": {"period": 150},
        "execution": {"size_pct": 1.0, "stop_loss_pct": 0.15, "allow_short": False},
    }


LINEUP: List[Dict[str, Any]] = [_BTC_TREND, _BTC_MACD] + [_etf(s) for s in ("SPY", "EFA", "IEF", "VNQ", "DBC")]


async def apply_lineup(client: httpx.AsyncClient, *, dry_run: bool = False) -> Dict[str, List[str]]:
    resp = await client.get(API)
    resp.raise_for_status()
    existing = {s["label"] for s in resp.json()}
    report: Dict[str, List[str]] = {"created": [], "skipped_existing": []}
    for spec in LINEUP:
        if spec["label"] in existing:
            report["skipped_existing"].append(spec["label"])
            continue
        if not dry_run:
            created = await client.post(API, json=spec)
            created.raise_for_status()
            sid = created.json()["id"]
            started = await client.patch(f"{API}/{sid}/status", json={"status": "paper"})
            started.raise_for_status()
        report["created"].append(spec["label"])
    return report


async def _main(base_url: str, dry_run: bool) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        print(json.dumps(await apply_lineup(client, dry_run=dry_run), indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    try:
        asyncio.run(_main(a.base_url, a.dry_run))
    except httpx.HTTPError as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        sys.exit(1)
