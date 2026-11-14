"""The backtest engine sizes risk-based entries with the same function as live."""
from __future__ import annotations

import pytest

from app.core.enums import Timeframe
from app.domain.backtest.engine import BacktestEngine
from app.domain.strategy.examples.sma_crossover import SmaCrossover
from tests.unit.test_backtest_sizing import _PRICES, _LongThenClose, _bar

pytestmark = pytest.mark.asyncio


def _bars():
    return [_bar(i, p) for i, p in enumerate(_PRICES)]


async def _entry_notional(**kw):
    engine = BacktestEngine(_LongThenClose(), _bars(), initial_capital=10_000, commission_pct=0.0,
                            warmup_bars=2, **kw)
    trade = (await engine.run()).trades[0]
    return trade.size * trade.entry_price


async def test_risk_sizing_puts_risk_over_stop_of_equity_in_the_trade():
    # 1% risk, 20% stop → 5% of equity per entry (the maximum, 100%, doesn't bind).
    notional = await _entry_notional(position_size_pct=1.0, risk_per_trade_pct=0.01, stop_loss_pct=0.20)
    assert notional == pytest.approx(500, rel=1e-9)


async def test_risk_sizing_is_capped_by_the_maximum_position_size():
    notional = await _entry_notional(position_size_pct=0.03, risk_per_trade_pct=0.01, stop_loss_pct=0.20)
    assert notional == pytest.approx(300, rel=1e-9)


async def test_without_risk_sizing_behaviour_is_unchanged():
    notional = await _entry_notional(position_size_pct=0.02, stop_loss_pct=0.20)
    assert notional == pytest.approx(200, rel=1e-9)


async def test_risk_sizing_without_a_stop_is_rejected():
    with pytest.raises(ValueError):
        BacktestEngine(SmaCrossover(parameters={}, timeframe=Timeframe.D1), _bars(),
                       position_size_pct=1.0, risk_per_trade_pct=0.01)
