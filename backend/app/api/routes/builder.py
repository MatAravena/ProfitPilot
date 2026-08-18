from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.domain.backtest.engine import BacktestResult
from app.models.schemas.backtest_schemas import (
    BacktestMetricsResponse,
    BacktestResponse,
    EquityPointResponse,
    TradeRecordResponse,
)
from app.services.strategy_sandbox import sandbox_run

router = APIRouter(prefix="/builder", tags=["builder"])


class SandboxRunRequest(BaseModel):
    code: str = Field(..., min_length=10, max_length=20_000)
    symbol: str = Field("BTCUSDT", max_length=32)
    timeframe: str = Field("1d")
    limit: int = Field(500, ge=60, le=1000)
    initial_capital: float = Field(10_000.0, gt=0)
    commission_pct: float = Field(0.001, ge=0)
    parameters: Dict[str, Any] = Field(default_factory=dict)


class GenerateRequest(BaseModel):
    description: str = Field(..., min_length=10, max_length=2000)
    symbol: str = Field("BTCUSDT", max_length=32)
    timeframe: str = Field("1d")


class GenerateResponse(BaseModel):
    code: str
    explanation: str


@router.post("/run", response_model=BacktestResponse)
async def run_sandbox(req: SandboxRunRequest):
    """
    Execute user-supplied Python strategy code in a sandboxed subprocess
    and return backtest results.

    The code must define a class that subclasses `StrategyBase` (provided by
    the sandbox harness) and implements `generate_signals(data) -> list`.

    No imports are needed — `math`, `statistics`, and the signal helpers
    (`signal()`, `LONG`, `SHORT`, `CLOSE`, `NEUTRAL`) are pre-injected.

    Example:
    ```python
    class MyStrategy(StrategyBase):
        def generate_signals(self, data):
            closes = [b.close for b in data.bars]
            if len(closes) < 21:
                return []
            fast = sum(closes[-10:]) / 10
            slow = sum(closes[-20:]) / 20
            if fast > slow:
                return [signal(LONG)]
            return []
    ```
    """
    try:
        result: BacktestResult = await sandbox_run(
            code=req.code,
            symbol=req.symbol,
            timeframe_str=req.timeframe,
            limit=req.limit,
            parameters=req.parameters,
            initial_capital=req.initial_capital,
            commission_pct=req.commission_pct,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_408_REQUEST_TIMEOUT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Sandbox error: {exc}")

    return BacktestResponse(
        strategy_name=result.strategy_name,
        symbol=result.symbol,
        timeframe=result.timeframe,
        initial_capital=result.initial_capital,
        metrics=BacktestMetricsResponse(**result.metrics._asdict()),
        equity_curve=[EquityPointResponse(timestamp=p.timestamp, value=p.value) for p in result.equity_curve],
        trades=[TradeRecordResponse(**t._asdict()) for t in result.trades],
    )


@router.post("/generate", response_model=GenerateResponse)
async def generate_strategy(req: GenerateRequest):
    """
    Use Claude to generate strategy code from a plain-English description.
    Requires ANTHROPIC_API_KEY in the environment.
    """
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="anthropic package not installed. Run: pip install anthropic",
        )

    import os
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ANTHROPIC_API_KEY not set in environment",
        )

    client = AsyncAnthropic(api_key=api_key)

    system = """You are an expert algorithmic trading strategy developer.
Generate a Python trading strategy class for the ProfitPilot sandbox.

SANDBOX RULES:
- The class must subclass `StrategyBase` (already available, no import needed)
- Implement `generate_signals(self, data) -> list`
- `data.bars` is a list of Bar objects with: .time, .open, .high, .low, .close, .volume
- `data.symbol` is the trading symbol string
- Return a list of signals using the `signal()` helper: signal(LONG), signal(SHORT), signal(CLOSE)
- Available constants: LONG, SHORT, CLOSE, NEUTRAL
- Available modules: math, statistics (already injected, no imports needed)
- NO other imports allowed
- Use `self.get_param(key, default)` to access strategy parameters

RESPONSE FORMAT:
Return ONLY a JSON object with two fields:
{
  "code": "<the Python class code as a string>",
  "explanation": "<1-2 sentence explanation of the strategy logic>"
}
"""

    user_msg = (
        f"Strategy description: {req.description}\n"
        f"Symbol: {req.symbol}\n"
        f"Timeframe: {req.timeframe}\n\n"
        "Generate the strategy class code and explanation."
    )

    message = await client.messages.create(
        model=get_settings().ANTHROPIC_MODEL,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = message.content[0].text.strip()

    # Extract JSON from the response
    import json, re
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if not json_match:
        raise HTTPException(status_code=500, detail="AI returned unexpected format")

    try:
        parsed = json.loads(json_match.group())
        return GenerateResponse(code=parsed["code"], explanation=parsed["explanation"])
    except (json.JSONDecodeError, KeyError):
        raise HTTPException(status_code=500, detail="AI returned malformed JSON")
