"""Tests for the shared position-reconciliation policy (plan_actions) — the single source
of truth that keeps backtest and live trading the same intent → action decision."""
from __future__ import annotations

import pytest

from app.core.enums import Direction
from app.domain.execution.reconcile import CLOSE, OPEN_LONG, OPEN_SHORT, plan_actions


@pytest.mark.parametrize("intent, side, expected", [
    # From flat.
    (Direction.LONG,  None, [OPEN_LONG]),
    (Direction.SHORT, None, [OPEN_SHORT]),
    (Direction.CLOSE, None, []),
    (Direction.NEUTRAL, None, []),
    # Already in the intended direction → no-op.
    (Direction.LONG,  "long",  []),
    (Direction.SHORT, "short", []),
    # Flatten.
    (Direction.CLOSE,   "long",  [CLOSE]),
    (Direction.CLOSE,   "short", [CLOSE]),
    (Direction.NEUTRAL, "long",  [CLOSE]),
    # Full reversals — the trades the backtest used to drop.
    (Direction.SHORT, "long",  [CLOSE, OPEN_SHORT]),   # was: close only
    (Direction.LONG,  "short", [CLOSE, OPEN_LONG]),    # was: ignored entirely
])
def test_plan_actions_matches_live_semantics(intent, side, expected):
    assert plan_actions(intent, side, allow_short=True) == expected


def test_shorting_disabled_suppresses_open_but_still_closes_on_reversal():
    # LONG held, SHORT intent, shorting disabled → close the long, do NOT open the short.
    assert plan_actions(Direction.SHORT, "long", allow_short=False) == [CLOSE]


def test_shorting_disabled_from_flat_is_noop():
    assert plan_actions(Direction.SHORT, None, allow_short=False) == []
