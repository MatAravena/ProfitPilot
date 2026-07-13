from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.schemas.strategy_schemas import ExecutionConfig


def test_zero_stop_loss_rejected():
    # 0% stop resolves to a trigger price == entry, which liquidates next bar.
    with pytest.raises(ValidationError):
        ExecutionConfig(stop_loss_pct=0)


def test_zero_take_profit_rejected():
    with pytest.raises(ValidationError):
        ExecutionConfig(take_profit_pct=0)


def test_none_take_profit_allowed():
    assert ExecutionConfig(take_profit_pct=None).take_profit_pct is None


def test_defaults_inherit_risk_and_set_behavior():
    cfg = ExecutionConfig()
    assert cfg.size_pct > 0            # behavioral — always set
    assert cfg.stop_loss_pct is None   # risk override unset → inherit the user profile
    assert cfg.max_open_positions is None


def test_from_instance_does_not_revalidate_persisted_values():
    # Reading a row whose stored values predate the current (tighter) bounds must not raise.
    from types import SimpleNamespace

    legacy = SimpleNamespace(
        size_pct=0.0, stop_loss_pct=0.0, take_profit_pct=0.0, max_open_positions=0,
        max_daily_drawdown_pct=0.0, max_total_drawdown_pct=0.0, max_orders_per_minute=0,
        allow_short=True, kill_switch_enabled=True, poll_seconds=None,
    )
    cfg = ExecutionConfig.from_instance(legacy)   # would raise under input validation
    assert cfg.stop_loss_pct == 0.0
    assert cfg.max_open_positions == 0
