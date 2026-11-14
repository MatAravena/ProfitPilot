"""Pure position-sizing logic.

Converts a directional intent + account equity + price into an order quantity.
No I/O, no DB, no broker calls — trivially unit-testable.
"""
from __future__ import annotations

from typing import Optional

from app.core.types import RiskConfig


def entry_fraction(
    max_position_size_pct: float,
    risk_per_trade_pct: Optional[float],
    stop_loss_pct: Optional[float],
) -> float:
    """Fraction of equity to put into a new position — the ONE sizing rule, shared by the
    live sizer below and the backtest engine so the two can never drift apart.

    * Fixed mode (no risk_per_trade_pct): the position is max_position_size_pct of equity.
    * Risk mode: size so that hitting the stop loses exactly risk_per_trade_pct of equity —
      position = risk / stop distance — capped at max_position_size_pct (no leverage past it).
      A 2% position with a 1.5% stop only risks 0.03% of equity; risk mode makes the
      loss budget the input instead of an accident of two unrelated settings.
    """
    if risk_per_trade_pct is None:
        return max_position_size_pct
    if not stop_loss_pct or stop_loss_pct <= 0:
        raise ValueError("risk_per_trade_pct sizing needs a stop_loss_pct (the risk is measured to the stop)")
    return min(risk_per_trade_pct / stop_loss_pct, max_position_size_pct)


def size_entry(equity: float, price: float, risk_cfg: RiskConfig) -> float:
    """Quantity for a new entry: equity × entry_fraction(...) / price.

    Returns 0.0 for non-positive equity or price (caller treats 0 as "no order").
    """
    if equity <= 0 or price <= 0:
        return 0.0
    fraction = entry_fraction(risk_cfg.max_position_size_pct, risk_cfg.risk_per_trade_pct,
                              risk_cfg.stop_loss_pct)
    qty = equity * fraction / price
    return qty if qty > 0 else 0.0


def stop_loss_price(entry_price: float, is_long: bool, risk_cfg: RiskConfig) -> float:
    """Stop-loss trigger price for an open position."""
    pct = risk_cfg.stop_loss_pct
    return entry_price * (1 - pct) if is_long else entry_price * (1 + pct)


def take_profit_price(entry_price: float, is_long: bool, risk_cfg: RiskConfig) -> float | None:
    """Take-profit trigger price, or None if not configured."""
    if risk_cfg.take_profit_pct is None:
        return None
    pct = risk_cfg.take_profit_pct
    return entry_price * (1 + pct) if is_long else entry_price * (1 - pct)
