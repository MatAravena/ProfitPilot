"""Pure position-sizing logic.

Converts a directional intent + account equity + price into an order quantity.
No I/O, no DB, no broker calls — trivially unit-testable.
"""
from __future__ import annotations

from app.core.types import RiskConfig


def size_entry(equity: float, price: float, risk_cfg: RiskConfig) -> float:
    """Quantity for a new entry.

    notional = equity * max_position_size_pct
    qty      = notional / price

    Returns 0.0 for non-positive equity or price (caller treats 0 as "no order").
    """
    if equity <= 0 or price <= 0:
        return 0.0
    notional = equity * risk_cfg.max_position_size_pct
    qty = notional / price
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
