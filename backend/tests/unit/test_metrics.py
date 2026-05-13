"""Unit tests for backtest metrics computation."""
from __future__ import annotations

import pytest

from app.domain.backtest.metrics import (
    BacktestMetrics,
    EquityPoint,
    TradeRecord,
    compute_metrics,
)


def _trade(pnl: float, symbol: str = "BTCUSDT") -> TradeRecord:
    return TradeRecord(
        symbol=symbol, side="long",
        entry_price=100.0, exit_price=100.0 + pnl,
        size=1.0, pnl=pnl, pnl_pct=pnl,
        entry_time=0, exit_time=1,
    )


def _equity(values: list[float]) -> list[EquityPoint]:
    return [EquityPoint(timestamp=i * 1000, value=v) for i, v in enumerate(values)]


class TestComputeMetrics:
    def test_empty_curve_returns_zero_metrics(self):
        m = compute_metrics([], [], initial_capital=10_000)
        assert m.total_return_pct == 0
        assert m.final_equity == 10_000

    def test_total_return_positive(self):
        m = compute_metrics(
            _equity([10_000, 11_000]),
            [_trade(1_000)],
            initial_capital=10_000,
        )
        assert m.total_return_pct == pytest.approx(10.0)
        assert m.final_equity == pytest.approx(11_000)

    def test_total_return_negative(self):
        m = compute_metrics(
            _equity([10_000, 9_000]),
            [_trade(-1_000)],
            initial_capital=10_000,
        )
        assert m.total_return_pct == pytest.approx(-10.0)

    def test_max_drawdown(self):
        # Peak 12k → drops to 9k = 25% drawdown
        curve = _equity([10_000, 12_000, 11_000, 9_000, 10_000])
        m = compute_metrics(curve, [], initial_capital=10_000)
        assert m.max_drawdown_pct == pytest.approx(25.0)

    def test_win_rate_all_winners(self):
        trades = [_trade(100), _trade(200), _trade(50)]
        m = compute_metrics(_equity([10_000, 10_350]), trades, initial_capital=10_000)
        assert m.win_rate == pytest.approx(100.0)
        assert m.winning_trades == 3
        assert m.losing_trades == 0

    def test_win_rate_mixed(self):
        trades = [_trade(100), _trade(-50)]
        m = compute_metrics(_equity([10_000, 10_050]), trades, initial_capital=10_000)
        assert m.win_rate == pytest.approx(50.0)

    def test_profit_factor(self):
        trades = [_trade(200), _trade(-100)]
        m = compute_metrics(_equity([10_000, 10_100]), trades, initial_capital=10_000)
        assert m.profit_factor == pytest.approx(2.0)

    def test_profit_factor_infinite_when_no_losses(self):
        trades = [_trade(100)]
        m = compute_metrics(_equity([10_000, 10_100]), trades, initial_capital=10_000)
        assert m.profit_factor == float("inf")

    def test_avg_win_and_avg_loss(self):
        trades = [_trade(100), _trade(200), _trade(-50), _trade(-150)]
        m = compute_metrics(_equity([10_000, 10_100]), trades, initial_capital=10_000)
        assert m.avg_win == pytest.approx(150.0)
        assert m.avg_loss == pytest.approx(-100.0)

    def test_sharpe_flat_equity_is_zero(self):
        # No variance in returns → Sharpe = 0
        curve = _equity([10_000] * 10)
        m = compute_metrics(curve, [], initial_capital=10_000)
        assert m.sharpe_ratio == 0.0
