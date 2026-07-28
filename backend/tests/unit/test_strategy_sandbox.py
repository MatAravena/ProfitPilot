"""Strategy sandbox end-to-end tests.

The sandbox (`sandbox_run`) is the engine behind the Builder page: it runs
user-supplied Python in a subprocess and backtests the resulting signals. These
tests monkeypatch the network fetch with synthetic bars so the whole pipeline —
subprocess harness → signal replay → BacktestEngine — runs hermetically.
"""
from __future__ import annotations

import math

import pytest

import app.services.strategy_sandbox as sandbox
from tests.conftest import make_bars

pytestmark = pytest.mark.asyncio


# A trending-then-oscillating series so an SMA crossover flips several times.
_CLOSES = [100 + 30 * math.sin(i / 12.0) + i * 0.2 for i in range(200)]


@pytest.fixture()
def patched_fetch(monkeypatch):
    """Replace the network OHLCV fetch with deterministic synthetic bars."""
    async def _fake_fetch(symbol, timeframe, limit, **kwargs):
        return make_bars(_CLOSES, symbol=symbol, timeframe=timeframe)

    monkeypatch.setattr(sandbox, "fetch_ohlcv", _fake_fetch)


async def test_sandbox_runs_a_valid_strategy_end_to_end(patched_fetch):
    """A textbook SMA-crossover strategy must run and produce a real backtest.

    Regression guard: the harness previously omitted ``__build_class__`` from the
    restricted builtins, so *any* strategy (which must define a class) failed with
    ``NameError: __build_class__ not found`` — the sandbox could not run at all.
    """
    code = (
        "class SmaCross(StrategyBase):\n"
        "    def generate_signals(self, data):\n"
        "        closes = [b.close for b in data.bars]\n"
        "        if len(closes) < 21:\n"
        "            return []\n"
        "        fast = sum(closes[-10:]) / 10\n"
        "        slow = sum(closes[-20:]) / 20\n"
        "        if fast > slow:\n"
        "            return [signal(LONG)]\n"
        "        return [signal(CLOSE)]\n"
    )
    result = await sandbox.sandbox_run(code=code, symbol="BTCUSDT", timeframe_str="1d", limit=200)

    assert result.strategy_name == "SandboxStrategy"
    assert result.symbol == "BTCUSDT"
    assert result.timeframe == "1d"
    assert len(result.equity_curve) > 0
    # The crossover flips over this series, so it must actually open/close trades.
    assert result.metrics.total_trades > 0
    assert len(result.trades) == result.metrics.total_trades


async def test_sandbox_can_use_injected_math_and_statistics(patched_fetch):
    """`math` and `statistics` are injected; strategies may use them without imports."""
    code = (
        "class VolBreak(StrategyBase):\n"
        "    def generate_signals(self, data):\n"
        "        closes = [b.close for b in data.bars]\n"
        "        if len(closes) < 21:\n"
        "            return []\n"
        "        sd = statistics.stdev(closes[-20:])\n"
        "        mean = statistics.mean(closes[-20:])\n"
        "        if closes[-1] > mean + math.sqrt(sd):\n"
        "            return [signal(LONG)]\n"
        "        return [signal(CLOSE)]\n"
    )
    result = await sandbox.sandbox_run(code=code, symbol="BTCUSDT", timeframe_str="1d", limit=200)
    assert len(result.equity_curve) > 0


async def test_sandbox_rejects_code_without_a_strategy_class(patched_fetch):
    with pytest.raises(ValueError, match="StrategyBase"):
        await sandbox.sandbox_run(code="x = 1 + 1", symbol="BTCUSDT", timeframe_str="1d")


async def test_sandbox_blocks_imports(patched_fetch):
    """`__import__` is disabled: importing anything must fail loudly, not silently run."""
    code = (
        "import os\n"
        "class S(StrategyBase):\n"
        "    def generate_signals(self, data):\n"
        "        return []\n"
    )
    with pytest.raises(ValueError, match="Strategy error"):
        await sandbox.sandbox_run(code=code, symbol="BTCUSDT", timeframe_str="1d")


async def test_sandbox_rejects_unknown_timeframe():
    with pytest.raises(ValueError, match="Unknown timeframe"):
        await sandbox.sandbox_run(code="class S(StrategyBase): pass", symbol="BTCUSDT", timeframe_str="7z")


async def test_sandbox_raises_on_insufficient_data(monkeypatch):
    async def _few_bars(symbol, timeframe, limit, **kwargs):
        return make_bars(_CLOSES[:10], symbol=symbol, timeframe=timeframe)

    monkeypatch.setattr(sandbox, "fetch_ohlcv", _few_bars)
    with pytest.raises(ValueError, match="Not enough data"):
        await sandbox.sandbox_run(
            code="class S(StrategyBase):\n    def generate_signals(self, d): return []",
            symbol="BTCUSDT", timeframe_str="1d",
        )
