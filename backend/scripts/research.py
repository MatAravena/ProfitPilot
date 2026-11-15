"""Research CLI — the agent-facing way to evaluate strategies (roadmap Step 6, Layer 1).

Runs the same WalkForwardService the API and the Backtests page use, so every number here
matches the UI. It only reports OUT-OF-SAMPLE results with a pass/fail verdict: there is
deliberately no command that prints an in-sample best-of-sweep, because fishing for one is
the failure mode this project guards against.

No server needed. Run from backend/ with the project venv:

    python scripts/research.py strategies
    python scripts/research.py walk-forward TrendFilter --symbol BTCUSDT \\
        --grid '{"period": [50, 100, 150]}'
    python scripts/research.py walk-forward MacdCrossover --symbol ETHUSDT --size 1.0 --stop 0.10

Output is JSON on stdout (verdict first); progress logs go to stderr. Market data is read
through the normal OHLCV cache, so a first run on a new symbol fetches and caches history.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # make `app` importable


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("strategies", help="List strategies and their parameters")

    wf = sub.add_parser("walk-forward", help="Out-of-sample test with a pass/fail verdict")
    wf.add_argument("strategy")
    wf.add_argument("--symbol", default="BTCUSDT")
    wf.add_argument("--timeframe", default="1d")
    wf.add_argument("--grid", help='JSON, e.g. {"period": [50, 100]}. Default: the strategy defaults only')
    wf.add_argument("--train-days", type=int, default=730)
    wf.add_argument("--test-days", type=int, default=180)
    wf.add_argument("--start", help="YYYY-MM-DD (default: all cached/available history)")
    wf.add_argument("--end", help="YYYY-MM-DD")
    wf.add_argument("--size", type=float, default=1.0,
                    help="Position size (fraction of equity, or the cap with --risk). Default 1.0 = "
                         "compare the signal with buy-and-hold")
    wf.add_argument("--risk", type=float, help="Risk per trade (fraction), needs --stop")
    wf.add_argument("--stop", type=float, help="Stop-loss (fraction)")
    wf.add_argument("--fee", type=float, default=0.001)
    wf.add_argument("--slippage", type=float, default=0.0005)
    wf.add_argument("--objective", default="sharpe_ratio")
    return p


def _strategies() -> List[Dict[str, Any]]:
    from app.domain.strategy.loader import get_all_strategy_classes
    return [{"name": s["class_name"], "description": s["description"],
             "parameters": {p["key"]: p["default"] for p in s["parameters"]}}
            for s in get_all_strategy_classes()]


def _default_grid(strategy: str) -> Dict[str, List[Any]]:
    for s in _strategies():
        if s["name"] == strategy:
            grid = {k: [v] for k, v in s["parameters"].items()}
            if grid:
                return grid
            break
    raise ValueError(f"Strategy '{strategy}' has no parameters to default; pass --grid")


def _day(ms: int) -> str:
    return datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d")


async def _walk_forward(a: argparse.Namespace) -> Dict[str, Any]:
    from app.domain.backtest.walk_forward import passes_bar
    from app.models.schemas.walk_forward_schemas import WalkForwardRequest
    from app.services.walk_forward_service import WalkForwardService

    req = WalkForwardRequest(
        strategy_name=a.strategy, symbol=a.symbol, timeframe=a.timeframe,
        start=datetime.fromisoformat(a.start) if a.start else None,
        end=datetime.fromisoformat(a.end) if a.end else None,
        param_grid=json.loads(a.grid) if a.grid else _default_grid(a.strategy),
        train_days=a.train_days, test_days=a.test_days, objective=a.objective,
        position_size_pct=a.size, risk_per_trade_pct=a.risk, stop_loss_pct=a.stop,
        commission_pct=a.fee, slippage_pct=a.slippage,
    )
    run = await WalkForwardService().run(req)
    r, ts = run.result, run.bar_timestamps_ms
    first, last = r.folds[0], r.folds[-1]
    return {
        "passes_bar": passes_bar(r),
        "bar": "OOS return/maxDD beats buy-and-hold, > 50% folds profitable, OOS Sharpe >= 0.5",
        "strategy": run.strategy_name, "symbol": run.symbol, "timeframe": run.timeframe,
        "out_of_sample": f"{_day(ts[first.test_start])} .. {_day(ts[last.test_end - 1])}",
        "oos": {"return_pct": round(r.oos_total_return_pct, 1), "max_dd_pct": round(r.oos_max_drawdown_pct, 1),
                "sharpe": round(r.oos_sharpe, 2), "folds_profitable_pct": round(r.pct_folds_profitable, 1)},
        "buy_hold": {"return_pct": round(r.buy_hold_total_return_pct, 1),
                     "max_dd_pct": round(r.buy_hold_max_drawdown_pct, 1)},
        "in_sample_sharpe_avg": round(r.avg_is_score, 2),
        "param_sets_chosen": f"{r.distinct_param_sets}/{len(r.folds)}",
        "combinations": r.combinations, "skipped_combinations": run.skipped_combinations,
        "folds": [{"test": f"{_day(ts[f.test_start])}..{_day(ts[f.test_end - 1])}", "params": f.params,
                   "oos_pct": round(f.oos_return_pct, 1), "buy_hold_pct": round(f.buy_hold_return_pct, 1),
                   "trades": f.oos_trades} for f in r.folds],
    }


async def run(argv: Optional[List[str]] = None, *, migrate: bool = True) -> Any:
    args = _parser().parse_args(argv)
    if migrate:   # the OHLCV cache lives in the app DB; make sure its schema is current
        from app.db.base import engine
        from app.db.migrate import upgrade_to_head
        async with engine.begin() as conn:
            await conn.run_sync(upgrade_to_head)
    if args.command == "strategies":
        return _strategies()
    return await _walk_forward(args)


def main() -> None:
    import structlog
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
                        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))
    try:
        result = asyncio.run(run())
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stdout)
        sys.exit(2)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
