from __future__ import annotations

import pytest

from app.core.types import RiskConfig
from app.domain.execution.position_sizer import (
    size_entry,
    stop_loss_price,
    take_profit_price,
)


def test_size_entry_uses_max_position_size_pct():
    cfg = RiskConfig(max_position_size_pct=0.02)
    # 100_000 * 0.02 = 2_000 notional; at price 100 → 20 units
    assert size_entry(equity=100_000, price=100, risk_cfg=cfg) == pytest.approx(20.0)


def test_size_entry_scales_with_price():
    cfg = RiskConfig(max_position_size_pct=0.10)
    assert size_entry(equity=10_000, price=50, risk_cfg=cfg) == pytest.approx(20.0)


@pytest.mark.parametrize("equity,price", [(0, 100), (-1, 100), (100_000, 0), (100_000, -5)])
def test_size_entry_guards_invalid_inputs(equity, price):
    cfg = RiskConfig()
    assert size_entry(equity=equity, price=price, risk_cfg=cfg) == 0.0


def test_stop_loss_price_long_and_short():
    cfg = RiskConfig(stop_loss_pct=0.015)
    assert stop_loss_price(100, is_long=True, risk_cfg=cfg) == pytest.approx(98.5)
    assert stop_loss_price(100, is_long=False, risk_cfg=cfg) == pytest.approx(101.5)


def test_take_profit_price_none_when_unset():
    cfg = RiskConfig(take_profit_pct=None)
    assert take_profit_price(100, is_long=True, risk_cfg=cfg) is None


def test_take_profit_price_long_and_short():
    cfg = RiskConfig(take_profit_pct=0.05)
    assert take_profit_price(100, is_long=True, risk_cfg=cfg) == pytest.approx(105.0)
    assert take_profit_price(100, is_long=False, risk_cfg=cfg) == pytest.approx(95.0)
