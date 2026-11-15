"""The research CLI reports only out-of-sample results, with the project's verdict."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_bars

pytestmark = pytest.mark.asyncio

_spec = importlib.util.spec_from_file_location(
    "research_cli", Path(__file__).resolve().parents[2] / "scripts" / "research.py")
research = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(research)


def _bars(n=900):
    return make_bars([30_000 + 1_500 * math.sin(i / 9) + 800 * math.sin(i / 37) + i * 3 for i in range(n)])


async def _run(argv):
    from app.db.base import Base, engine
    import app.models.db  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    with patch("app.services.backtest_service.fetch_ohlcv", new=AsyncMock(return_value=_bars())):
        return await research.run(argv, migrate=False)


async def test_lists_every_built_in_with_its_parameters():
    out = await research.run(["strategies"], migrate=False)
    names = {s["name"]: s for s in out}
    assert {"MacdCrossover", "TrendFilter", "DonchianBreakout"} <= set(names)
    assert names["TrendFilter"]["parameters"] == {"period": 200}


async def test_walk_forward_reports_verdict_and_out_of_sample_only():
    out = await _run(["walk-forward", "SmaCrossover", "--grid", '{"fast_period": [5, 10], "slow_period": [30]}',
                      "--train-days", "300", "--test-days", "100"])
    assert isinstance(out["passes_bar"], bool)
    assert set(out["oos"]) == {"return_pct", "max_dd_pct", "sharpe", "folds_profitable_pct"}
    assert len(out["folds"]) == 6 and out["combinations"] == 2
    assert all(f["params"]["fast_period"] in (5, 10) for f in out["folds"])
    # Deliberately no in-sample best-of-sweep in the output — only the average for comparison.
    assert "best_in_sample" not in out and "in_sample_sharpe_avg" in out


async def test_without_a_grid_it_tests_the_strategy_defaults():
    out = await _run(["walk-forward", "TrendFilter", "--train-days", "300", "--test-days", "100"])
    assert {f["params"]["period"] for f in out["folds"]} == {200}


async def test_bad_input_is_a_value_error_the_cli_turns_into_json():
    with pytest.raises(ValueError):
        await _run(["walk-forward", "NoSuchStrategy", "--grid", '{"a": [1]}'])
