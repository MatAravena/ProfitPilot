"""Walk-forward validation: optimize on a past window, judge on the next unseen one.

The point of the tool is honesty, so most of these tests are about what it must NOT
do: use future data to pick parameters, or count trades outside the test window.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import List
from uuid import uuid4

import pytest

from app.core.enums import Direction, MarketType, SignalSource, Timeframe
from app.core.types import RiskConfig, Signal
from app.domain.backtest.walk_forward import walk_forward
from app.domain.strategy.base import StrategyBase
from tests.conftest import make_bars

pytestmark = pytest.mark.asyncio


class _HoldLong(StrategyBase):
    """go_long=True → always want to be long; False → never trade. Records what it saw."""

    seen_lengths: List[int] = []

    def __init__(self, parameters: dict):
        super().__init__(strategy_id=uuid4(), name="HoldLong", version="t", market_type=MarketType.CRYPTO,
                         timeframe=Timeframe.D1, parameters=parameters, risk_config=RiskConfig())

    def validate_parameters(self): ...
    def get_required_symbols(self): return ["BTCUSDT"]
    async def on_tick(self, tick): return None
    async def on_fill(self, fill): return None

    async def generate_signals(self, data):
        _HoldLong.seen_lengths.append(len(data.bars))
        if not self.parameters.get("go_long"):
            return []
        return [Signal(signal_id=uuid4(), strategy_id=self.strategy_id, symbol=data.symbol,
                       market_type=MarketType.CRYPTO, timeframe=Timeframe.D1, direction=Direction.LONG,
                       confidence=1.0, source=SignalSource.QUANT, generated_at=datetime.now(timezone.utc))]


GRID = {"go_long": [False, True]}


def _bars(closes):
    return make_bars(closes)


def _rising(n, start=100.0, step=0.002):
    return [start * (1 + step) ** i for i in range(n)]


async def _wf(bars, **kw):
    kw.setdefault("train_bars", 400)
    kw.setdefault("test_bars", 200)
    return await walk_forward(bars, lambda p: _HoldLong(p), GRID, **kw)


async def test_folds_tile_the_data_without_overlapping_test_windows():
    bars = _bars(_rising(1000))
    res = await _wf(bars)

    assert [(f.test_start, f.test_end) for f in res.folds] == [(400, 600), (600, 800), (800, 1000)]
    assert [(f.train_start, f.train_end) for f in res.folds] == [(0, 400), (200, 600), (400, 800)]


async def test_picks_the_best_in_sample_parameters():
    res = await _wf(_bars(_rising(1000)))
    assert all(f.params == {"go_long": True} for f in res.folds)
    assert all(f.oos_return_pct > 0 for f in res.folds)


async def test_overfit_winner_is_exposed_out_of_sample():
    """Long wins every training window (rising), then the market turns down in the test
    window: in-sample says great, out-of-sample says loss — the gap the tool exists to show."""
    closes = _rising(600) + [_rising(600)[-1] * (1 - 0.003) ** i for i in range(1, 201)]
    res = await _wf(_bars(closes), train_bars=400, test_bars=200)

    last = res.folds[-1]
    assert last.params == {"go_long": True}
    assert last.is_score > 0
    assert last.oos_return_pct < 0
    assert last.buy_hold_return_pct < 0


async def test_parameter_choice_never_depends_on_future_bars():
    """Causality golden test: truncating everything after a fold's training window must
    not change the parameters chosen for that fold."""
    closes = [100 + 15 * math.sin(i / 23) + i * 0.01 for i in range(1000)]
    full = await _wf(_bars(closes))
    truncated = await _wf(_bars(closes[:800]))

    assert [f.params for f in truncated.folds] == [f.params for f in full.folds[:len(truncated.folds)]]
    assert [round(f.is_score, 9) for f in truncated.folds] == \
           [round(f.is_score, 9) for f in full.folds[:len(truncated.folds)]]


async def test_oos_trades_happen_only_inside_the_test_window_but_with_history():
    bars = _bars(_rising(1000))
    _HoldLong.seen_lengths = []
    res = await _wf(bars, lookback_bars=150)

    for f in res.folds:
        start_ms = int(bars[f.test_start].timestamp.timestamp() * 1000)
        end_ms = int(bars[f.test_end - 1].timestamp.timestamp() * 1000)
        assert f.trades, "fixture must trade"
        assert all(start_ms <= t.entry_time <= end_ms for t in f.trades)
        assert all(start_ms <= p.timestamp <= end_ms for p in f.equity_curve)
    # The OOS strategy's first decision saw prior bars (context), capped at the window.
    assert max(_HoldLong.seen_lengths) == 150


async def test_aggregate_compounds_the_folds():
    res = await _wf(_bars(_rising(1000)))

    expected = 1.0
    for f in res.folds:
        expected *= 1 + f.oos_return_pct / 100
    assert res.oos_total_return_pct == pytest.approx((expected - 1) * 100, rel=1e-9)
    assert res.pct_folds_profitable == 100.0
    assert res.equity_curve[-1].value == pytest.approx(res.initial_capital * expected, rel=1e-9)


async def test_not_enough_data_is_an_error():
    with pytest.raises(ValueError):
        await _wf(_bars(_rising(500)), train_bars=400, test_bars=200)


async def test_bad_grid_or_objective_is_an_error():
    bars = _bars(_rising(1000))
    with pytest.raises(ValueError):
        await walk_forward(bars, lambda p: _HoldLong(p), {}, train_bars=400, test_bars=200)
    with pytest.raises(ValueError):
        await walk_forward(bars, lambda p: _HoldLong(p), GRID, train_bars=400, test_bars=200,
                           objective="not_a_metric")
