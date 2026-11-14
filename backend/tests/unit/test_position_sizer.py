from __future__ import annotations

import pytest

from app.core.types import RiskConfig
from app.domain.execution.position_sizer import (
    entry_fraction,
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


def test_risk_based_size_loses_exactly_the_risk_budget_at_the_stop():
    """0.5% risk with a 10% stop → 5% of equity in the position; hitting the stop loses
    5% × 10% = 0.5% of equity, the budget."""
    cfg = RiskConfig(max_position_size_pct=1.0, risk_per_trade_pct=0.005, stop_loss_pct=0.10)
    qty = size_entry(equity=100_000, price=100, risk_cfg=cfg)
    assert qty * 100 == pytest.approx(5_000)
    assert qty * 100 * 0.10 == pytest.approx(100_000 * 0.005)


def test_risk_based_size_is_capped_by_max_position_size():
    """1% risk with a 0.5% stop would be a 200% position — capped at the maximum (100%)."""
    cfg = RiskConfig(max_position_size_pct=1.0, risk_per_trade_pct=0.01, stop_loss_pct=0.005)
    assert size_entry(equity=10_000, price=50, risk_cfg=cfg) * 50 == pytest.approx(10_000)


@pytest.mark.parametrize("max_pct,risk,stop,expected", [
    (0.02, None, 0.015, 0.02),      # fixed mode: unchanged behaviour
    (1.0, 0.005, 0.10, 0.05),
    (0.30, 0.01, 0.02, 0.30),       # 50% wanted, capped at 30%
    (1.0, 0.01, None, 1.0),         # no stop → can't size by risk → the maximum is NOT used
])
def test_entry_fraction(max_pct, risk, stop, expected):
    if stop is None and risk is not None:
        with pytest.raises(ValueError):
            entry_fraction(max_pct, risk, stop)
        return
    assert entry_fraction(max_pct, risk, stop) == pytest.approx(expected)


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
