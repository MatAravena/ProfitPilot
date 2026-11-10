import pytest
from pydantic import ValidationError

from app.models.schemas.grid_schemas import GridArmResultResponse, GridParamsSchema, GridRequest


def test_grid_params_schema_defaults_match_domain_defaults():
    p = GridParamsSchema()
    assert p.min_edge == 3.0
    assert p.spacing_mode == "geometric"


def test_grid_request_defaults_are_valid():
    req = GridRequest()
    assert req.symbol == "BTCUSDT"
    assert req.grid.min_edge == 3.0
    assert req.regime.ema_fast == 9


def test_grid_params_schema_rejects_out_of_range_min_edge():
    with pytest.raises(ValidationError):
        GridParamsSchema(min_edge=-1.0)


def test_grid_arm_result_response_carries_the_forced_exit_pnl_split():
    """The mandatory realized-vs-mark-to-market split must be visible through the API, not just
    computed and discarded in the domain layer -- otherwise the reconciliation problem still
    exists from where anyone actually looks."""
    resp = GridArmResultResponse(
        equity_curve=[], final_equity=10_000.0, total_return_pct=0.0, max_drawdown_pct=0.0,
        sharpe_ratio=0.0, grid_trades=0, grid_realized_pnl=0.0, forced_exit_pnl=-5.0,
        force_close_count=1, mark_to_market_pnl=0.0, avg_profit_per_grid_pct=0.0,
        fill_rate=0.0, time_in_grid_pct=0.0, max_inventory_notional=0.0,
        worst_unrealized_pct=0.0, time_underwater_pct=0.0,
    )
    assert resp.forced_exit_pnl == -5.0
    assert resp.force_close_count == 1


def test_rejects_min_rungs_above_max_rungs():
    with pytest.raises(ValidationError):
        GridParamsSchema(min_rungs=50, max_rungs=10)


def test_rejects_inverted_vol_band_and_ema_order():
    from app.models.schemas.grid_schemas import RegimeParamsSchema
    with pytest.raises(ValidationError):
        RegimeParamsSchema(atr_vol_low=0.9, atr_vol_high=0.35)
    with pytest.raises(ValidationError):
        RegimeParamsSchema(ema_fast=30, ema_mid=20)
