from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter

from app.core.errors import AppError, BacktestError, ErrorCode
from app.domain.backtest.engine import BacktestResult
from app.domain.backtest.walk_forward import passes_bar
from app.models.schemas.backtest_schemas import (
    ArmResultResponse,
    AvailableStrategiesResponse,
    BacktestMetricsResponse,
    BacktestRequest,
    BacktestResponse,
    CAVEAT_TEXT,
    CycleMarker,
    DcaCompareRequest,
    DcaCompareResponse,
    EquityPointResponse,
    MonteCarloMethodResponse,
    MonteCarloRequest,
    MonteCarloResponse,
    PricePointResponse,
    TradeRecordResponse,
)
from app.models.schemas.grid_schemas import (
    FUNDING_CAVEAT_TEXT,
    GridArmResultResponse,
    GridRequest,
    GridResponse,
)
from app.services.accumulation_compare_service import AccumulationCompareService
from app.services.backtest_service import BacktestService
from app.services.grid_service import GridService
from app.models.schemas.walk_forward_schemas import (
    WalkForwardFoldResponse,
    WalkForwardRequest,
    WalkForwardResponse,
)
from app.services.monte_carlo_service import MonteCarloService
from app.services.walk_forward_service import WalkForwardService

router = APIRouter(prefix="/backtests", tags=["backtests"])

logger = structlog.get_logger(__name__)

_svc = BacktestService()
_mc_svc = MonteCarloService(_svc)
_dca_svc = AccumulationCompareService(_svc)
_grid_svc = GridService(_svc)
_wf_svc = WalkForwardService(_svc)


@router.get("/strategies", response_model=AvailableStrategiesResponse)
async def list_strategies():
    """List all available built-in strategies with descriptions."""
    return _svc.list_strategies()


@router.post("/run", response_model=BacktestResponse)
async def run_backtest(req: BacktestRequest):
    """
    Run a backtest against Bybit public historical data.
    No broker credentials required.

    Example body:
    ```json
    {
      "strategy_name": "SmaCrossover",
      "symbol": "BTCUSDT",
      "timeframe": "1d",
      "initial_capital": 10000,
      "parameters": { "fast_period": 20, "slow_period": 50 }
    }
    ```
    """
    try:
        result: BacktestResult = await _svc.run(req)
    except ValueError as exc:
        # Expected: bad params / not enough data. Client-fixable → 400.
        raise AppError(str(exc), code=ErrorCode.BAD_REQUEST) from exc
    except AppError:
        raise
    except Exception as exc:
        # Unexpected failure inside the backtest pipeline. Log the full stack
        # trace so we can trace where it originated; return a structured 502.
        logger.error(
            "backtest.failed",
            strategy=req.strategy_name,
            symbol=req.symbol,
            timeframe=req.timeframe,
            error=str(exc),
            exc_info=exc,
        )
        raise BacktestError(f"Backtest failed: {exc}") from exc

    return BacktestResponse(
        strategy_name=result.strategy_name,
        symbol=result.symbol,
        timeframe=result.timeframe,
        initial_capital=result.initial_capital,
        metrics=BacktestMetricsResponse(**result.metrics._asdict()),
        equity_curve=[EquityPointResponse(timestamp=p.timestamp, value=p.value) for p in result.equity_curve],
        trades=[TradeRecordResponse(**t._asdict()) for t in result.trades],
        prices=[PricePointResponse(timestamp=p.timestamp, close=p.close) for p in result.prices],
    )


@router.post("/montecarlo", response_model=MonteCarloResponse)
async def run_montecarlo(req: MonteCarloRequest):
    """Run the backtest, then resample its trade sequence to turn one path into a
    distribution (bootstrap = sampling risk, shuffle = ordering risk). Opt-in: this
    re-runs the backtest server-side, so it isn't folded into every ordinary /run.

    `< 2` trades → 400 (a distribution needs at least two samples).
    """
    try:
        result, mc = await _mc_svc.run(req)
    except ValueError as exc:
        # Bad params / not enough data / < 2 trades. Client-fixable → 400.
        raise AppError(str(exc), code=ErrorCode.BAD_REQUEST) from exc
    except AppError:
        raise
    except Exception as exc:
        logger.error(
            "montecarlo.failed",
            strategy=req.strategy_name,
            symbol=req.symbol,
            timeframe=req.timeframe,
            error=str(exc),
            exc_info=exc,
        )
        raise BacktestError(f"Monte Carlo failed: {exc}") from exc

    return MonteCarloResponse(
        strategy_name=result.strategy_name,
        symbol=result.symbol,
        timeframe=result.timeframe,
        initial_capital=result.initial_capital,
        n_simulations=mc.n_simulations,
        n_trades=mc.n_trades,
        realized_total_return_pct=mc.realized_total_return_pct,
        drawdown_threshold_pct=mc.drawdown_threshold_pct,
        # Domain dataclass field names match the response schema → build straight from asdict.
        methods={name: MonteCarloMethodResponse(**asdict(m)) for name, m in mc.methods.items()},
    )


@router.post("/walk-forward", response_model=WalkForwardResponse)
async def run_walk_forward(req: WalkForwardRequest):
    """Optimize `param_grid` on each training window, trade the winner on the next unseen
    window, and report only those out-of-sample results — the honest version of a
    parameter sweep. Bad input / not enough data for one fold → 400."""
    try:
        run = await _wf_svc.run(req)
    except ValueError as exc:
        raise AppError(str(exc), code=ErrorCode.BAD_REQUEST) from exc
    except AppError:
        raise
    except Exception as exc:
        logger.error("walk_forward.failed", strategy=req.strategy_name, symbol=req.symbol,
                     timeframe=req.timeframe, error=str(exc), exc_info=exc)
        raise BacktestError(f"Walk-forward failed: {exc}") from exc

    r, ts = run.result, run.bar_timestamps_ms
    return WalkForwardResponse(
        strategy_name=run.strategy_name, symbol=run.symbol, timeframe=run.timeframe,
        objective=r.objective, initial_capital=r.initial_capital,
        train_bars=run.train_bars, test_bars=run.test_bars,
        combinations=r.combinations, skipped_combinations=run.skipped_combinations,
        oos_total_return_pct=r.oos_total_return_pct, oos_max_drawdown_pct=r.oos_max_drawdown_pct,
        oos_sharpe=r.oos_sharpe, buy_hold_total_return_pct=r.buy_hold_total_return_pct,
        buy_hold_max_drawdown_pct=r.buy_hold_max_drawdown_pct,
        pct_folds_profitable=r.pct_folds_profitable, avg_is_score=r.avg_is_score,
        avg_oos_sharpe=r.avg_oos_sharpe, distinct_param_sets=r.distinct_param_sets,
        passes_bar=passes_bar(r),
        folds=[
            WalkForwardFoldResponse(
                train_start=ts[f.train_start], train_end=ts[f.train_end - 1],
                test_start=ts[f.test_start], test_end=ts[f.test_end - 1],
                params=f.params, is_score=f.is_score, is_return_pct=f.is_return_pct,
                oos_return_pct=f.oos_return_pct, oos_sharpe=f.oos_sharpe,
                oos_max_drawdown_pct=f.oos_max_drawdown_pct, oos_trades=f.oos_trades,
                buy_hold_return_pct=f.buy_hold_return_pct,
            )
            for f in r.folds
        ],
        equity_curve=[EquityPointResponse(timestamp=p.timestamp, value=p.value) for p in r.equity_curve],
        buy_hold_curve=[EquityPointResponse(timestamp=p.timestamp, value=p.value) for p in r.buy_hold_curve],
    )


@router.post("/dca-compare", response_model=DcaCompareResponse)
async def run_dca_compare(req: DcaCompareRequest):
    """Compare flat DCA vs cycle-weighted accumulation vs full rotation over the same BTC data.

    Opt-in research tool. `< MIN_BACKTEST_BARS` bars or bad capital params → 400.
    The response carries an overfitting caveat — read it as one live cycle, not proof.
    """
    try:
        bundle = await _dca_svc.run(req)
    except ValueError as exc:
        raise AppError(str(exc), code=ErrorCode.BAD_REQUEST) from exc
    except AppError:
        raise
    except Exception as exc:
        logger.error("dca_compare.failed", symbol=req.symbol, error=str(exc), exc_info=exc)
        raise BacktestError(f"DCA comparison failed: {exc}") from exc

    def _arm(a) -> ArmResultResponse:
        return ArmResultResponse(
            equity_curve=[EquityPointResponse(timestamp=p.timestamp, value=p.value) for p in a.equity_curve],
            final_value=a.final_value, total_contributed=a.total_contributed,
            total_return_pct=a.total_return_pct, units_accumulated=a.units_accumulated,
            avg_cost_basis=a.avg_cost_basis, max_drawdown_pct=a.max_drawdown_pct,
            sharpe_ratio=a.sharpe_ratio, dry_powder=a.dry_powder, realized_pnl=a.realized_pnl,
        )

    def _marker_ts(d) -> int:
        return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)

    return DcaCompareResponse(
        symbol=bundle.symbol,
        timeframe=bundle.timeframe,
        capital_model=bundle.capital_model,
        caveat=CAVEAT_TEXT,
        cycle_markers=[CycleMarker(timestamp=_marker_ts(d), kind=kind) for d, kind in bundle.cycle_markers],
        arms={name: _arm(a) for name, a in bundle.arms.items()},
    )


@router.post("/grid", response_model=GridResponse)
async def run_grid(req: GridRequest):
    """Backtest-only grid family: two arms (bounded-loss grid_guarded_reanchor vs. unbounded
    grid_accumulate_nostop) over identical data, with a symmetric long/short regime.

    `< MIN_BACKTEST_BARS` bars or an unknown timeframe -> 400. SHORT_BIASED legs carry a
    disclosed funding-rate caveat (see FUNDING_CAVEAT_TEXT) — not modeled for v1.
    """
    try:
        bundle = await _grid_svc.run(req)
    except ValueError as exc:
        raise AppError(str(exc), code=ErrorCode.BAD_REQUEST) from exc
    except AppError:
        raise
    except Exception as exc:
        logger.error("grid.failed", symbol=req.symbol, error=str(exc), exc_info=exc)
        raise BacktestError(f"Grid backtest failed: {exc}") from exc

    def _arm(a) -> GridArmResultResponse:
        return GridArmResultResponse(
            equity_curve=[EquityPointResponse(timestamp=p.timestamp, value=p.value) for p in a.equity_curve],
            final_equity=a.final_equity, total_return_pct=a.total_return_pct,
            max_drawdown_pct=a.max_drawdown_pct, sharpe_ratio=a.sharpe_ratio,
            grid_trades=a.grid_trades, grid_realized_pnl=a.grid_realized_pnl,
            forced_exit_pnl=a.forced_exit_pnl, force_close_count=a.force_close_count,
            mark_to_market_pnl=a.mark_to_market_pnl, avg_profit_per_grid_pct=a.avg_profit_per_grid_pct,
            fill_rate=a.fill_rate, time_in_grid_pct=a.time_in_grid_pct,
            max_inventory_notional=a.max_inventory_notional, worst_unrealized_pct=a.worst_unrealized_pct,
            time_underwater_pct=a.time_underwater_pct,
        )

    return GridResponse(
        symbol=bundle.symbol, timeframe=bundle.timeframe,
        allow_intrabar_roundtrip=bundle.allow_intrabar_roundtrip,
        funding_rate_caveat=FUNDING_CAVEAT_TEXT,
        arms={name: _arm(a) for name, a in bundle.arms.items()},
    )
