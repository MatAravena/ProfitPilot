from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

from app.core.enums import Direction, MarketType, SignalSource, Timeframe
from app.core.types import Fill, MarketData, RiskConfig, Signal, Tick
from app.domain.strategy.base import StrategyBase, StrategyRegistry


@StrategyRegistry.register
class SmaCrossover(StrategyBase):
    """
    Classic SMA crossover strategy.

    Parameters:
        symbol      — trading symbol, e.g. "BTCUSDT"
        fast_period — fast SMA window  (default: 20)
        slow_period — slow SMA window  (default: 50)

    Logic:
        - BUY  signal when fast SMA crosses ABOVE slow SMA
        - CLOSE signal when fast SMA crosses BELOW slow SMA
    """

    def __init__(self, parameters: dict, **kwargs):
        super().__init__(
            strategy_id=kwargs.get("strategy_id", uuid4()),
            name="SmaCrossover",
            version="1.0.0",
            market_type=MarketType.CRYPTO,
            timeframe=kwargs.get("timeframe", Timeframe.D1),
            parameters=parameters,
            risk_config=kwargs.get("risk_config", RiskConfig()),
            forecasting_models=kwargs.get("forecasting_models"),
            broker=kwargs.get("broker"),
        )
        self.validate_parameters()
        self._prev_cross: Optional[str] = None  # "above" | "below"

    def validate_parameters(self) -> None:
        fast = self.get_param("fast_period", 20)
        slow = self.get_param("slow_period", 50)
        if not isinstance(fast, int) or fast < 2:
            raise ValueError("fast_period must be an integer >= 2")
        if not isinstance(slow, int) or slow <= fast:
            raise ValueError("slow_period must be an integer > fast_period")

    def get_required_symbols(self) -> List[str]:
        return [self.get_param("symbol", "BTCUSDT")]

    async def generate_signals(self, data: MarketData) -> List[Signal]:
        fast = self.get_param("fast_period", 20)
        slow = self.get_param("slow_period", 50)

        if len(data.bars) < slow + 1:
            return []

        closes = [b.close for b in data.bars]

        fast_now  = _sma(closes, fast)
        slow_now  = _sma(closes, slow)
        fast_prev = _sma(closes[:-1], fast)
        slow_prev = _sma(closes[:-1], slow)

        cross_now  = "above" if fast_now  > slow_now  else "below"
        cross_prev = "above" if fast_prev > slow_prev else "below"

        signals: List[Signal] = []

        if cross_prev == "below" and cross_now == "above":
            # Golden cross — go long
            signals.append(self._make_signal(data, Direction.LONG))
            self._prev_cross = "above"

        elif cross_prev == "above" and cross_now == "below":
            # Death cross — close / go short
            signals.append(self._make_signal(data, Direction.CLOSE))
            self._prev_cross = "below"

        return signals

    async def on_tick(self, tick: Tick) -> Optional[Signal]:
        return None  # SMA crossover is bar-based only

    async def on_fill(self, fill: Fill) -> None:
        self.last_signal_at = datetime.now(timezone.utc)

    # ── Private ─────────────────────────────────────────────────────────────────

    def _make_signal(self, data: MarketData, direction: Direction) -> Signal:
        self.last_signal_at = datetime.now(timezone.utc)
        return Signal(
            signal_id=uuid4(),
            strategy_id=self.strategy_id,
            symbol=data.symbol,
            market_type=self.market_type,
            timeframe=self.timeframe,
            direction=direction,
            confidence=0.7,
            source=SignalSource.QUANT,
            generated_at=datetime.now(timezone.utc),
        )


class RsiMeanReversion(StrategyBase):
    """
    RSI mean-reversion strategy.

    Parameters:
        symbol      — trading symbol
        rsi_period  — RSI window       (default: 14)
        oversold    — RSI buy level    (default: 30)
        overbought  — RSI sell level   (default: 70)

    Logic:
        - BUY  when RSI drops below oversold threshold
        - CLOSE when RSI rises above overbought threshold
    """

    def __init__(self, parameters: dict, **kwargs):
        super().__init__(
            strategy_id=kwargs.get("strategy_id", uuid4()),
            name="RsiMeanReversion",
            version="1.0.0",
            market_type=MarketType.CRYPTO,
            timeframe=kwargs.get("timeframe", Timeframe.H4),
            parameters=parameters,
            risk_config=kwargs.get("risk_config", RiskConfig()),
            forecasting_models=kwargs.get("forecasting_models"),
            broker=kwargs.get("broker"),
        )
        self.validate_parameters()

    def validate_parameters(self) -> None:
        period = self.get_param("rsi_period", 14)
        ob = self.get_param("overbought", 70)
        os_ = self.get_param("oversold", 30)
        if period < 2:
            raise ValueError("rsi_period must be >= 2")
        if not (0 < os_ < ob < 100):
            raise ValueError("Must satisfy: 0 < oversold < overbought < 100")

    def get_required_symbols(self) -> List[str]:
        return [self.get_param("symbol", "BTCUSDT")]

    async def generate_signals(self, data: MarketData) -> List[Signal]:
        period = self.get_param("rsi_period", 14)
        oversold = self.get_param("oversold", 30)
        overbought = self.get_param("overbought", 70)

        if len(data.bars) < period + 2:
            return []

        closes = [b.close for b in data.bars]
        rsi_now  = _rsi(closes, period)
        rsi_prev = _rsi(closes[:-1], period)

        signals: List[Signal] = []

        if rsi_prev >= oversold and rsi_now < oversold:
            signals.append(self._make_signal(data, Direction.LONG))

        elif rsi_prev <= overbought and rsi_now > overbought:
            signals.append(self._make_signal(data, Direction.CLOSE))

        return signals

    async def on_tick(self, tick: Tick) -> Optional[Signal]:
        return None

    async def on_fill(self, fill: Fill) -> None:
        self.last_signal_at = datetime.now(timezone.utc)

    def _make_signal(self, data: MarketData, direction: Direction) -> Signal:
        self.last_signal_at = datetime.now(timezone.utc)
        return Signal(
            signal_id=uuid4(),
            strategy_id=self.strategy_id,
            symbol=data.symbol,
            market_type=self.market_type,
            timeframe=self.timeframe,
            direction=direction,
            confidence=0.65,
            source=SignalSource.QUANT,
            generated_at=datetime.now(timezone.utc),
        )


# Register second strategy
StrategyRegistry.register(RsiMeanReversion)


@StrategyRegistry.register
class MacdCrossover(StrategyBase):
    """
    MACD crossover strategy.

    Parameters:
        symbol        — trading symbol
        fast_period   — fast EMA window   (default: 12)
        slow_period   — slow EMA window   (default: 26)
        signal_period — signal EMA window (default: 9)

    Logic:
        - BUY   when MACD line crosses above signal line
        - CLOSE when MACD line crosses below signal line
    """

    def __init__(self, parameters: dict, **kwargs):
        super().__init__(
            strategy_id=kwargs.get("strategy_id", uuid4()),
            name="MacdCrossover",
            version="1.0.0",
            market_type=MarketType.CRYPTO,
            timeframe=kwargs.get("timeframe", Timeframe.H4),
            parameters=parameters,
            risk_config=kwargs.get("risk_config", RiskConfig()),
            forecasting_models=kwargs.get("forecasting_models"),
            broker=kwargs.get("broker"),
        )
        self.validate_parameters()

    def validate_parameters(self) -> None:
        fast = self.get_param("fast_period", 12)
        slow = self.get_param("slow_period", 26)
        sig  = self.get_param("signal_period", 9)
        if fast < 2:
            raise ValueError("fast_period must be >= 2")
        if slow <= fast:
            raise ValueError("slow_period must be > fast_period")
        if sig < 2:
            raise ValueError("signal_period must be >= 2")

    def get_required_symbols(self) -> List[str]:
        return [self.get_param("symbol", "BTCUSDT")]

    async def generate_signals(self, data: MarketData) -> List[Signal]:
        fast   = self.get_param("fast_period", 12)
        slow   = self.get_param("slow_period", 26)
        sig_p  = self.get_param("signal_period", 9)
        min_bars = slow + sig_p + 2

        if len(data.bars) < min_bars:
            return []

        closes = [b.close for b in data.bars]
        macd_line  = _macd_line(closes, fast, slow)
        signal_line = _ema_series(macd_line, sig_p)

        if len(signal_line) < 2:
            return []

        prev_above = macd_line[-(len(signal_line))]   > signal_line[0] if len(macd_line) >= len(signal_line) else False
        now_macd   = macd_line[-1]
        now_sig    = signal_line[-1]
        prev_macd  = macd_line[-2] if len(macd_line) >= 2 else now_macd
        prev_sig   = signal_line[-2] if len(signal_line) >= 2 else now_sig

        _ = prev_above  # used implicitly via crossover check
        signals: List[Signal] = []
        if prev_macd <= prev_sig and now_macd > now_sig:
            signals.append(self._make_signal(data, Direction.LONG))
        elif prev_macd >= prev_sig and now_macd < now_sig:
            signals.append(self._make_signal(data, Direction.CLOSE))
        return signals

    async def on_tick(self, tick: Tick) -> Optional[Signal]:
        return None

    async def on_fill(self, fill: Fill) -> None:
        self.last_signal_at = datetime.now(timezone.utc)

    def _make_signal(self, data: MarketData, direction: Direction) -> Signal:
        self.last_signal_at = datetime.now(timezone.utc)
        return Signal(
            signal_id=uuid4(),
            strategy_id=self.strategy_id,
            symbol=data.symbol,
            market_type=self.market_type,
            timeframe=self.timeframe,
            direction=direction,
            confidence=0.68,
            source=SignalSource.QUANT,
            generated_at=datetime.now(timezone.utc),
        )


@StrategyRegistry.register
class BollingerBandsMeanReversion(StrategyBase):
    """
    Bollinger Bands mean-reversion strategy.

    Parameters:
        symbol   — trading symbol
        period   — SMA window and std dev lookback (default: 20)
        std_mult — band width multiplier            (default: 2.0)

    Logic:
        - BUY   when close drops below the lower band
        - CLOSE when close rises above the middle band (SMA)
    """

    def __init__(self, parameters: dict, **kwargs):
        super().__init__(
            strategy_id=kwargs.get("strategy_id", uuid4()),
            name="BollingerBandsMeanReversion",
            version="1.0.0",
            market_type=MarketType.CRYPTO,
            timeframe=kwargs.get("timeframe", Timeframe.H4),
            parameters=parameters,
            risk_config=kwargs.get("risk_config", RiskConfig()),
            forecasting_models=kwargs.get("forecasting_models"),
            broker=kwargs.get("broker"),
        )
        self.validate_parameters()

    def validate_parameters(self) -> None:
        period = self.get_param("period", 20)
        mult   = self.get_param("std_mult", 2.0)
        if period < 2:
            raise ValueError("period must be >= 2")
        if mult <= 0:
            raise ValueError("std_mult must be > 0")

    def get_required_symbols(self) -> List[str]:
        return [self.get_param("symbol", "BTCUSDT")]

    async def generate_signals(self, data: MarketData) -> List[Signal]:
        period = self.get_param("period", 20)
        mult   = self.get_param("std_mult", 2.0)

        if len(data.bars) < period + 1:
            return []

        closes = [b.close for b in data.bars]
        window = closes[-period:]
        mid    = sum(window) / period
        std    = _std(window)
        lower  = mid - mult * std

        prev_close = closes[-2]
        curr_close = closes[-1]

        signals: List[Signal] = []
        if prev_close >= lower and curr_close < lower:
            signals.append(self._make_signal(data, Direction.LONG))
        elif curr_close > mid and prev_close <= mid:
            signals.append(self._make_signal(data, Direction.CLOSE))
        return signals

    async def on_tick(self, tick: Tick) -> Optional[Signal]:
        return None

    async def on_fill(self, fill: Fill) -> None:
        self.last_signal_at = datetime.now(timezone.utc)

    def _make_signal(self, data: MarketData, direction: Direction) -> Signal:
        self.last_signal_at = datetime.now(timezone.utc)
        return Signal(
            signal_id=uuid4(),
            strategy_id=self.strategy_id,
            symbol=data.symbol,
            market_type=self.market_type,
            timeframe=self.timeframe,
            direction=direction,
            confidence=0.66,
            source=SignalSource.QUANT,
            generated_at=datetime.now(timezone.utc),
        )


# ── Math helpers ────────────────────────────────────────────────────────────────

def _sma(closes: List[float], period: int) -> float:
    return sum(closes[-period:]) / period


def _rsi(closes: List[float], period: int) -> float:
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    recent = deltas[-period:]
    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period if gains else 0.0
    avg_loss = sum(losses) / period if losses else 0.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _ema_series(values: List[float], period: int) -> List[float]:
    if len(values) < period:
        return []
    k = 2.0 / (period + 1)
    emas = [sum(values[:period]) / period]
    for v in values[period:]:
        emas.append(v * k + emas[-1] * (1 - k))
    return emas


def _macd_line(closes: List[float], fast: int, slow: int) -> List[float]:
    fast_emas = _ema_series(closes, fast)
    slow_emas = _ema_series(closes, slow)
    offset = slow - fast
    return [fast_emas[i + offset] - slow_emas[i] for i in range(len(slow_emas))]


def _std(values: List[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return (sum((v - mean) ** 2 for v in values) / n) ** 0.5
