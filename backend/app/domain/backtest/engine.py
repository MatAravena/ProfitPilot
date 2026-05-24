from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

import structlog

from app.core.enums import Direction, Timeframe
from app.core.types import MarketData, OHLCV
from app.domain.backtest.metrics import (
    BacktestMetrics, EquityPoint, PricePoint, TradeRecord, compute_metrics,
)
from app.domain.strategy.base import StrategyBase

logger = structlog.get_logger(__name__)


@dataclass
class BacktestResult:
    strategy_name: str
    symbol: str
    timeframe: str
    initial_capital: float
    metrics: BacktestMetrics
    equity_curve: List[EquityPoint]
    trades: List[TradeRecord]
    prices: List[PricePoint]


@dataclass
class _Position:
    side: str           # "long" | "short"
    entry_price: float
    size: float         # number of units
    entry_time: int     # Unix ms


class BacktestEngine:
    """
    Simple bar-by-bar backtesting engine.

    Runs a strategy against historical OHLCV data, simulating market-order fills
    at the open of the next bar (realistic: signal on close, fill on next open).
    One position at a time. Long and short supported.
    """

    def __init__(
        self,
        strategy: StrategyBase,
        bars: List[OHLCV],
        initial_capital: float = 10_000.0,
        commission_pct: float = 0.001,   # 0.1% per trade side
        warmup_bars: int = 50,
    ):
        self._strategy = strategy
        self._bars = bars
        self._initial_capital = initial_capital
        self._commission_pct = commission_pct
        self._warmup_bars = warmup_bars

    async def run(self) -> BacktestResult:
        bars = self._bars
        capital = self._initial_capital
        position: Optional[_Position] = None
        equity_curve: List[EquityPoint] = []
        trades: List[TradeRecord] = []
        prices: List[PricePoint] = []

        logger.info(
            "backtest.run.start",
            strategy=self._strategy.name,
            bars=len(bars),
            capital=capital,
        )

        for i in range(self._warmup_bars, len(bars)):
            current = bars[i]
            ts_ms = int(current.timestamp.timestamp() * 1000)

            # Build MarketData up to (and including) current bar
            market_data = MarketData(
                symbol=current.symbol,
                timeframe=current.timeframe,
                bars=bars[: i + 1],
            )

            # Generate signals from strategy
            try:
                signals = await self._strategy.generate_signals(market_data)
            except Exception as exc:
                logger.error("backtest.signal.error", bar=i, error=str(exc))
                signals = []

            # Process signals — fill at next bar's open if available
            fill_price = bars[i + 1].open if i + 1 < len(bars) else current.close

            for signal in signals:
                if signal.direction == Direction.LONG and position is None:
                    # Enter long
                    commission = fill_price * self._commission_pct
                    size = capital / (fill_price + commission)
                    position = _Position(
                        side="long",
                        entry_price=fill_price,
                        size=size,
                        entry_time=ts_ms,
                    )
                    capital -= size * (fill_price + commission)

                elif signal.direction in (Direction.SHORT, Direction.CLOSE) and position is not None:
                    # Close existing position
                    trade = self._close_position(position, fill_price, ts_ms)
                    pnl = trade.pnl
                    capital += position.size * fill_price * (1 - self._commission_pct)
                    trades.append(trade)
                    position = None

                elif signal.direction == Direction.SHORT and position is None:
                    # Enter short (sell first, buy back later)
                    commission = fill_price * self._commission_pct
                    size = capital / (fill_price + commission)
                    position = _Position(
                        side="short",
                        entry_price=fill_price,
                        size=size,
                        entry_time=ts_ms,
                    )
                    capital += size * (fill_price - commission)

            # Mark-to-market equity (cash + current market value of any open position)
            if position is None:
                equity = capital
            elif position.side == "long":
                equity = capital + position.size * current.close
            else:
                equity = capital - position.size * current.close
            equity_curve.append(EquityPoint(timestamp=ts_ms, value=equity))
            prices.append(PricePoint(timestamp=ts_ms, close=current.close))

        # Close any open position at end of data
        if position is not None:
            last = bars[-1]
            ts_ms = int(last.timestamp.timestamp() * 1000)
            trade = self._close_position(position, last.close, ts_ms)
            trades.append(trade)

        bars_per_year = self._infer_bars_per_year(self._strategy.timeframe)
        metrics = compute_metrics(equity_curve, trades, self._initial_capital, bars_per_year)

        logger.info(
            "backtest.run.complete",
            trades=metrics.total_trades,
            total_return=metrics.total_return_pct,
            sharpe=metrics.sharpe_ratio,
            max_dd=metrics.max_drawdown_pct,
        )

        return BacktestResult(
            strategy_name=self._strategy.name,
            symbol=self._bars[0].symbol if self._bars else "",
            timeframe=self._strategy.timeframe.value,
            initial_capital=self._initial_capital,
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades,
            prices=prices,
        )

    def _close_position(self, pos: _Position, price: float, ts_ms: int) -> TradeRecord:
        entry_commission = pos.entry_price * self._commission_pct
        exit_commission = price * self._commission_pct
        if pos.side == "long":
            proceeds = pos.size * (price - exit_commission)
            cost = pos.size * (pos.entry_price + entry_commission)
            pnl = proceeds - cost
        else:
            proceeds = pos.size * (pos.entry_price - entry_commission)
            cost = pos.size * (price + exit_commission)
            pnl = proceeds - cost

        pnl_pct = pnl / (pos.size * pos.entry_price) * 100

        return TradeRecord(
            symbol=self._bars[0].symbol if self._bars else "",
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=price,
            size=pos.size,
            pnl=round(pnl, 2),
            pnl_pct=round(pnl_pct, 2),
            entry_time=pos.entry_time,
            exit_time=ts_ms,
        )

    @staticmethod
    def _infer_bars_per_year(timeframe: Timeframe) -> int:
        mapping = {
            Timeframe.M1: 525_600,
            Timeframe.M5: 105_120,
            Timeframe.M15: 35_040,
            Timeframe.M30: 17_520,
            Timeframe.H1: 8_760,
            Timeframe.H4: 2_190,
            Timeframe.D1: 365,
            Timeframe.W1: 52,
        }
        return mapping.get(timeframe, 252)
