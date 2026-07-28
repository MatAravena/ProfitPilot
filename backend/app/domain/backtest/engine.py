from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

import structlog

from app.core.constants import DEFAULT_WARMUP_BARS
from app.core.enums import Timeframe
from app.core.types import MarketData, OHLCV
from app.domain.execution.reconcile import CLOSE, OPEN_LONG, OPEN_SHORT, plan_actions
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
        warmup_bars: int = DEFAULT_WARMUP_BARS,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
        position_size_pct: float = 1.0,   # fraction of equity per entry; 1.0 = all-in
        slippage_pct: float = 0.0,        # adverse fill slippage per side (spread + impact)
        allow_short: bool = True,         # include shorts the strategy asks for (matches live gate)
    ):
        self._strategy = strategy
        self._bars = bars
        self._initial_capital = initial_capital
        self._commission_pct = commission_pct
        self._warmup_bars = warmup_bars
        self._stop_loss_pct = stop_loss_pct
        self._take_profit_pct = take_profit_pct
        self._position_size_pct = position_size_pct
        self._slippage_pct = slippage_pct
        self._allow_short = allow_short

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

            # Intrabar stop-loss / take-profit: check the current bar's range against an open
            # position before acting on new signals. Fills at the trigger price.
            if position is not None:
                exit_price = self._exit_trigger(position, current)
                if exit_price is not None:
                    # Closing a long = sell (slip down); closing a short = buy back (slip up).
                    fill = self._apply_slippage(exit_price, is_buy=position.side == "short")
                    trade = self._close_position(position, fill, ts_ms)
                    capital = self._capital_after_close(capital, position, fill)
                    trades.append(trade)
                    position = None

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

            # Process the bar's intent — fill at next bar's open if available. The intent is the
            # last signal of the bar (matches the live executor), and the close→open action plan
            # comes from the shared reconcile policy so a flip is a full reversal, identical to live.
            fill_price = bars[i + 1].open if i + 1 < len(bars) else current.close

            if signals:
                intent = signals[-1].direction
                current_side = position.side if position is not None else None
                for action in plan_actions(intent, current_side, self._allow_short):
                    if action == CLOSE and position is not None:
                        # Long close = sell (slip down); short close = buy (slip up).
                        fill = self._apply_slippage(fill_price, is_buy=position.side == "short")
                        trades.append(self._close_position(position, fill, ts_ms))
                        capital = self._capital_after_close(capital, position, fill)
                        position = None
                    elif action == OPEN_LONG:
                        position, capital = self._open_position("long", fill_price, capital, ts_ms)
                    elif action == OPEN_SHORT:
                        position, capital = self._open_position("short", fill_price, capital, ts_ms)

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
            fill = self._apply_slippage(last.close, is_buy=position.side == "short")
            trade = self._close_position(position, fill, ts_ms)
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

    def _exit_trigger(self, pos: _Position, bar: OHLCV) -> Optional[float]:
        """Return the SL/TP exit price if the bar's range hit a level, else None.
        Stop is checked before target (conservative when both hit in one bar)."""
        sl, tp = self._stop_loss_pct, self._take_profit_pct
        if pos.side == "long":
            if sl is not None and bar.low <= pos.entry_price * (1 - sl):
                return pos.entry_price * (1 - sl)
            if tp is not None and bar.high >= pos.entry_price * (1 + tp):
                return pos.entry_price * (1 + tp)
        else:  # short
            if sl is not None and bar.high >= pos.entry_price * (1 + sl):
                return pos.entry_price * (1 + sl)
            if tp is not None and bar.low <= pos.entry_price * (1 - tp):
                return pos.entry_price * (1 - tp)
        return None

    def _open_position(self, side: str, fill_price: float, capital: float, ts_ms: int):
        """Open a long/short sized at equity × position_size_pct, with adverse slippage +
        commission baked into the entry price. Returns (position, new_capital)."""
        is_long = side == "long"
        entry = self._apply_slippage(fill_price, is_buy=is_long)   # buy slips up, sell slips down
        commission = entry * self._commission_pct
        notional = capital * self._position_size_pct
        size = notional / (entry + commission)
        position = _Position(side=side, entry_price=entry, size=size, entry_time=ts_ms)
        if is_long:
            capital -= size * (entry + commission)
        else:
            capital += size * (entry - commission)   # short receives proceeds on entry
        return position, capital

    def _apply_slippage(self, price: float, *, is_buy: bool) -> float:
        """Adverse slippage on a market fill: buys fill higher, sells fill lower — modeling the
        half-spread crossed plus market impact. Symmetric per side; 0.0 disables it."""
        if is_buy:
            return price * (1 + self._slippage_pct)
        return price * (1 - self._slippage_pct)

    def _capital_after_close(self, capital: float, pos: _Position, price: float) -> float:
        """Cash balance after flattening a position at ``price``.

        Long close = sell the units → receive proceeds net of commission.
        Short close = buy the units back → pay the buyback cost plus commission.
        (The mirror of the entry accounting; a short's proceeds were already added
        to cash on entry, so covering must subtract the buyback here.)
        """
        if pos.side == "long":
            return capital + pos.size * price * (1 - self._commission_pct)
        return capital - pos.size * price * (1 + self._commission_pct)

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
