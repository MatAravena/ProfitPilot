"""The paper lineup script sets up exactly the agreed strategies, once."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.api.routes import strategies as strategies_route

_spec = importlib.util.spec_from_file_location(
    "paper_lineup", Path(__file__).resolve().parents[2] / "scripts" / "paper_lineup.py")
lineup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lineup)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def no_live_loops(monkeypatch):
    """Starting a strategy in paper launches its executor loop; keep the test hermetic."""
    monkeypatch.setattr("app.services.strategy_executor.executor.notify_status_change",
                        lambda *a, **k: None)


async def _labels(client):
    return {s["label"]: s for s in (await client.get("/api/v1/strategies")).json()}


async def test_creates_every_strategy_in_paper_with_its_agreed_config(client):
    report = await lineup.apply_lineup(client)
    assert len(report["created"]) == len(lineup.LINEUP) == 7

    got = await _labels(client)
    for spec in lineup.LINEUP:
        s = got[spec["label"]]
        assert s["status"] == "paper"
        assert s["class_name"] == spec["class_name"] and s["symbol"] == spec["symbol"]
        for key, value in spec["execution"].items():
            assert s["execution"][key] == value, (spec["label"], key)
    # Every symbol must be seeded, or the first live open would be rejected.
    from app.domain.instruments import INSTRUMENTS
    for spec in lineup.LINEUP:
        assert INSTRUMENTS.get(spec["symbol"]) is not None, spec["symbol"]


async def test_rerunning_never_duplicates_or_overrides(client):
    await lineup.apply_lineup(client)
    first = await _labels(client)
    sid = first[lineup.LINEUP[0]["label"]]["id"]
    await client.patch(f"/api/v1/strategies/{sid}/status", json={"status": "paused"})   # user's change

    report = await lineup.apply_lineup(client)
    assert report["created"] == []
    after = await _labels(client)
    assert len(after) == len(first)
    assert after[lineup.LINEUP[0]["label"]]["status"] == "paused"


async def test_dry_run_changes_nothing(client):
    before = await _labels(client)
    report = await lineup.apply_lineup(client, dry_run=True)
    # Every lineup entry is accounted for (would-create or already there), and nothing changed.
    assert sorted(report["created"] + report["skipped_existing"]) == sorted(s["label"] for s in lineup.LINEUP)
    assert await _labels(client) == before


def test_lineup_only_uses_strategies_that_passed_walk_forward():
    assert {s["class_name"] for s in lineup.LINEUP} <= {"TrendFilter", "MacdCrossover"}
    assert all(s["execution"]["allow_short"] is False for s in lineup.LINEUP)
    assert not any(s["symbol"] == "ETHUSDT" for s in lineup.LINEUP)   # nothing passed on ETH
