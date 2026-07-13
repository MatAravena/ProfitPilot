"""
Strategy sandbox — run user-supplied Python strategy code in an isolated subprocess.

The code runs inside an asyncio subprocess (a fresh Python interpreter) with:
  - A hard 30-second wall-clock timeout (kills runaway / infinite-loop code)
  - Restricted builtins + ``__import__`` disabled, so the obvious ways to reach
    os / subprocess / socket / open() are removed
  - Communication only via stdin/stdout (JSON) — the harness never opens files

THREAT MODEL — READ BEFORE EXPOSING THIS TO UNTRUSTED USERS
-----------------------------------------------------------
This is **not** a hardened security boundary. Restricting ``__builtins__`` is a
guardrail against *accidental* unsafe operations, not a defense against
*deliberately malicious* code: CPython sandboxes built this way are escapable
(e.g. ``().__class__.__bases__[0].__subclasses__()`` can reach arbitrary
classes without any import). There is also no OS-level network isolation and no
memory cap — a hostile or buggy strategy can still exhaust RAM.

Why that's acceptable in **Phase 1**: the app is local and single-user, so the
person writing the strategy already owns the machine — an escape grants nothing
they don't already have. The subprocess + timeout still buy us crash isolation
and runaway-loop protection.

Before **Phase 2** (multi-tenant / internet-exposed), this MUST be replaced with
real OS-level isolation: a container / gVisor / Firecracker with no network
egress, cgroup CPU+memory limits, seccomp, and a read-only filesystem. Tracked
in TODO.md → Security (Phase 2).

API
---
    result = await sandbox_run(code, symbol, timeframe, limit, parameters)

Returns a BacktestResult or raises ValueError / TimeoutError.
"""
from __future__ import annotations

import asyncio
import json
import sys
import textwrap
from pathlib import Path
from typing import Any

import structlog

from app.core.enums import Timeframe
from app.domain.backtest.data_provider import fetch_ohlcv
from app.domain.backtest.engine import BacktestEngine, BacktestResult
from app.domain.strategy.base import StrategyBase, StrategyRegistry
from app.core.enums import Direction, MarketType, SignalSource
from app.core.types import Fill, MarketData, RiskConfig, Signal, Tick

logger = structlog.get_logger(__name__)

_TIMEOUT_SECONDS = 30

# Python code injected into every sandbox run as the harness
_HARNESS_TEMPLATE = textwrap.dedent("""
import json, sys, math, statistics

# ── Allowed stdlib subset ──────────────────────────────────────────────────
# Guardrail (NOT a security boundary — see the module docstring's threat model):
# narrow __builtins__ to a safe subset so accidental unsafe calls fail loudly.
_SAFE_BUILTINS = {{
    k: v for k, v in vars(__builtins__ if isinstance(__builtins__, dict) else __builtins__).items()
    if k in (
        'abs', 'all', 'any', 'bool', 'dict', 'enumerate', 'filter', 'float',
        'frozenset', 'getattr', 'hasattr', 'int', 'isinstance', 'issubclass',
        'iter', 'len', 'list', 'map', 'max', 'min', 'next', 'object',
        'print', 'range', 'repr', 'reversed', 'round', 'set', 'slice',
        'sorted', 'str', 'sum', 'tuple', 'type', 'zip', 'None', 'True', 'False',
        'ValueError', 'TypeError', 'RuntimeError', 'StopIteration',
    )
}}
_SAFE_BUILTINS['__import__'] = None   # block all imports inside user code

# ── Minimal types the user's generate_signals() receives ──────────────────

class Bar:
    __slots__ = ('time', 'open', 'high', 'low', 'close', 'volume')
    def __init__(self, time, open, high, low, close, volume):
        self.time   = time
        self.open   = open
        self.high   = high
        self.low    = low
        self.close  = close
        self.volume = volume

class MarketData:
    __slots__ = ('symbol', 'timeframe', 'bars')
    def __init__(self, symbol, timeframe, bars):
        self.symbol    = symbol
        self.timeframe = timeframe
        self.bars      = bars

    @property
    def latest(self):
        return self.bars[-1] if self.bars else None

# ── Signal return helpers ─────────────────────────────────────────────────

LONG    = 'long'
SHORT   = 'short'
CLOSE   = 'close'
NEUTRAL = 'neutral'

def signal(direction, confidence=0.65):
    return {{'direction': direction, 'confidence': float(confidence)}}

# ── Strategy base the user subclasses ─────────────────────────────────────

class StrategyBase:
    parameters: dict

    def __init__(self, parameters: dict):
        self.parameters = parameters

    def get_param(self, key, default=None):
        return self.parameters.get(key, default)

    def generate_signals(self, data) -> list:
        return []

# ── Inject user code ──────────────────────────────────────────────────────

_USER_NS = {{'StrategyBase': StrategyBase, 'signal': signal,
             'LONG': LONG, 'SHORT': SHORT, 'CLOSE': CLOSE, 'NEUTRAL': NEUTRAL,
             'math': math, 'statistics': statistics,
             '__builtins__': _SAFE_BUILTINS}}

exec(compile({user_code!r}, '<strategy>', 'exec'), _USER_NS)

# Find user strategy class
_StratClass = None
for _v in _USER_NS.values():
    if isinstance(_v, type) and issubclass(_v, StrategyBase) and _v is not StrategyBase:
        _StratClass = _v
        break

if _StratClass is None:
    print(json.dumps({{'error': 'No class found that subclasses StrategyBase'}}))
    sys.exit(1)

# ── Read bars from stdin ───────────────────────────────────────────────────

_payload = json.loads(sys.stdin.read())
_bars_raw = _payload['bars']
_symbol   = _payload['symbol']
_timeframe = _payload['timeframe']
_params   = _payload.get('parameters', {{}})
_warmup   = _payload.get('warmup', 50)

_bars = [Bar(**b) for b in _bars_raw]

# ── Run strategy bar-by-bar ───────────────────────────────────────────────

_strat = _StratClass(parameters={{**_params, 'symbol': _symbol}})

_signals = []
for _i in range(_warmup, len(_bars)):
    _md = MarketData(_symbol, _timeframe, _bars[:_i+1])
    try:
        _sigs = _strat.generate_signals(_md)
        for _s in (_sigs or []):
            _signals.append({{
                'bar_index': _i,
                'direction': _s.get('direction', 'neutral') if isinstance(_s, dict) else NEUTRAL,
                'confidence': _s.get('confidence', 0.65) if isinstance(_s, dict) else 0.65,
            }})
    except Exception as _e:
        pass  # skip errored bars

print(json.dumps({{'signals': _signals}}))
""")

_TIMEFRAME_MAP = {
    "1m": Timeframe.M1, "5m": Timeframe.M5, "15m": Timeframe.M15,
    "30m": Timeframe.M30, "1h": Timeframe.H1, "4h": Timeframe.H4,
    "1d": Timeframe.D1, "1w": Timeframe.W1,
}


async def sandbox_run(
    code: str,
    symbol: str,
    timeframe_str: str,
    limit: int = 500,
    parameters: dict[str, Any] | None = None,
    initial_capital: float = 10_000.0,
    commission_pct: float = 0.001,
) -> BacktestResult:
    """Execute user code in a subprocess sandbox and return BacktestResult."""

    tf = _TIMEFRAME_MAP.get(timeframe_str)
    if tf is None:
        raise ValueError(f"Unknown timeframe '{timeframe_str}'")

    # Fetch OHLCV data (uses yfinance/Bybit like the normal backtest)
    bars = await fetch_ohlcv(symbol=symbol, timeframe=tf, limit=limit)
    if len(bars) < 60:
        raise ValueError(f"Not enough data ({len(bars)} bars). Try a longer timeframe.")

    # Build the harness script with user code embedded
    script = _HARNESS_TEMPLATE.format(user_code=code)

    # Serialize bars for stdin
    bars_payload = json.dumps({
        "symbol": symbol,
        "timeframe": timeframe_str,
        "parameters": parameters or {},
        "warmup": 50,
        "bars": [
            {
                "time": int(b.timestamp.timestamp()),
                "open": b.open, "high": b.high,
                "low": b.low,  "close": b.close, "volume": b.volume,
            }
            for b in bars
        ],
    })

    # Run in subprocess
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", script,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=bars_payload.encode()),
            timeout=_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise TimeoutError(f"Strategy timed out after {_TIMEOUT_SECONDS}s")

    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        raise ValueError(f"Strategy error: {err[:500]}")

    try:
        output = json.loads(stdout.decode())
    except Exception:
        raise ValueError("Strategy produced invalid output (not JSON)")

    if "error" in output:
        raise ValueError(output["error"])

    sandbox_signals = output.get("signals", [])
    logger.info("sandbox.run.complete", symbol=symbol, signals=len(sandbox_signals))

    # Wrap in a StrategyBase-compatible class so BacktestEngine can use it
    strategy = _SandboxStrategy(
        sandbox_signals=sandbox_signals,
        symbol=symbol,
        timeframe=tf,
        parameters=parameters or {},
    )

    engine = BacktestEngine(
        strategy=strategy,
        bars=bars,
        initial_capital=initial_capital,
        commission_pct=commission_pct,
    )
    return await engine.run()


# ── Thin StrategyBase wrapper that replays pre-computed signals ────────────────

from uuid import uuid4
from datetime import datetime, timezone


class _SandboxStrategy(StrategyBase):
    """Replays the sandbox signals without any live market calls."""

    def __init__(
        self,
        sandbox_signals: list[dict],
        symbol: str,
        timeframe: Timeframe,
        parameters: dict,
    ):
        super().__init__(
            strategy_id=uuid4(),
            name="SandboxStrategy",
            version="sandbox",
            market_type=MarketType.CRYPTO,
            timeframe=timeframe,
            parameters={"symbol": symbol, **parameters},
            risk_config=RiskConfig(),
        )
        # Index signals by bar_index for O(1) lookup
        self._by_bar: dict[int, list[dict]] = {}
        for s in sandbox_signals:
            self._by_bar.setdefault(s["bar_index"], []).append(s)

    async def generate_signals(self, data: MarketData) -> list[Signal]:
        bar_index = len(data.bars) - 1
        raw = self._by_bar.get(bar_index, [])
        result = []
        for r in raw:
            try:
                direction = Direction(r["direction"])
            except ValueError:
                continue
            result.append(Signal(
                signal_id=uuid4(),
                strategy_id=self.strategy_id,
                symbol=data.symbol,
                market_type=self.market_type,
                timeframe=self.timeframe,
                direction=direction,
                confidence=float(r.get("confidence", 0.65)),
                source=SignalSource.QUANT,
                generated_at=datetime.now(timezone.utc),
            ))
        return result

    async def on_tick(self, tick: Tick) -> Signal | None:
        return None

    async def on_fill(self, fill: Fill) -> None:
        pass

    def get_required_symbols(self) -> list[str]:
        return [self.get_param("symbol", "BTCUSDT")]

    def validate_parameters(self) -> None:
        pass
