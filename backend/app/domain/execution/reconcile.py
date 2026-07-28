"""Pure position-reconciliation policy: given a strategy's directional intent and the
current position, decide the sequence of actions (close / open) to reach the intent.

This is the SINGLE SOURCE OF TRUTH for that decision, shared by the live ExecutionEngine
and the BacktestEngine so a strategy trades identically in backtest and live — in
particular, a direction flip (long→short or short→long) is a full reversal (close then
open the opposite), never a dropped half-trade.
"""
from __future__ import annotations

from typing import List, Optional

from app.core.enums import Direction

# Action tokens returned by plan_actions.
CLOSE = "close"
OPEN_LONG = "open_long"
OPEN_SHORT = "open_short"


def plan_actions(
    intent: Direction,
    current_side: Optional[str],   # "long" | "short" | None (flat)
    allow_short: bool = True,
) -> List[str]:
    """Return the ordered actions to move from ``current_side`` to ``intent``.

    - CLOSE / NEUTRAL → flatten if holding, else nothing (NEUTRAL == go flat, by design).
    - LONG / SHORT → no-op if already in that direction; otherwise close any opposite
      position first, then open the intended one (a reversal yields [CLOSE, OPEN_*]).
    - Opening a short when ``allow_short`` is False is suppressed (an opposite close still
      happens), matching the live engine.
    """
    held = current_side is not None

    if intent in (Direction.CLOSE, Direction.NEUTRAL):
        return [CLOSE] if held else []

    want_long = intent == Direction.LONG

    # Already in the intended direction → nothing to do.
    if held and (current_side == "long") == want_long:
        return []

    actions: List[str] = []
    if held:
        actions.append(CLOSE)   # reverse: close the opposite side first

    if not want_long and not allow_short:
        return actions          # shorting disabled — keep only the close (if any)

    actions.append(OPEN_LONG if want_long else OPEN_SHORT)
    return actions
