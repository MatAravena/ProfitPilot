"""Per-rung lot ledger. Each rung fill opens a Lot targeting the adjacent rung; the Lot closes
when price later touches that target -- so "grid profit" is realized P&L on a matched pair, never
mark-to-market drift (see design doc, "Fill realism").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Literal, Optional, Protocol

from app.domain.strategies.base.ledger import Ledger
from app.domain.strategies.grid.levels import GridLevels
from app.domain.strategies.grid.regime import GridDirection


@dataclass
class RungLot:
    root_index: int
    side: Literal["long", "short"]
    entry_price: float
    target_price: float
    units: float
    opened_at: int


class _Bar(Protocol):
    low: float
    high: float


@dataclass
class GridLedger(Ledger):
    fee_pct: float
    slippage_pct: float
    notional_per_rung: float
    cash: float = 0.0
    # Keyed by an internal, auto-incrementing lot id -- NEVER by a rung array index. The ladder is
    # rebuilt from fresh bb_mid/atr every bar (see planner.py), so consecutive bars' ladders share
    # essentially zero exact price levels; an index-keyed dict would let a stale lot permanently
    # "occupy" a slot number that later refers to a completely different, unrelated price (measured:
    # this capped concurrent lots at max_rungs by accident, and could zero the no-stop arm's income
    # for the entire length of a sustained drawdown -- see the domain-engine review).
    open_lots: Dict[int, RungLot] = field(default_factory=dict)
    realized_pnl: float = 0.0
    grid_trades: int = 0
    grid_realized_pnl: float = 0.0
    forced_pnl: float = 0.0
    force_close_count: int = 0
    # Safety valve, not the primary economic brake: with index-keying removed, nothing else stops
    # short lots (which ADD cash on open, so a cash check can't bound them) from opening every bar
    # forever. Longs are bounded by the cash check below; this covers shorts and acts as a backstop
    # for longs too. Deliberately generous (2x the old accidental 30-lot cap) and not yet a public
    # GridParams/API knob -- this is a correctness fix, not new user-facing configurability.
    max_open_lots: int = 60
    _next_lot_id: int = field(default=0, repr=False)

    def has_lot_near(self, price: float, tol_pct: float) -> bool:
        """Is a price level already covered by an open lot? Tolerance is a fraction of price
        (typically half a rung's spacing) -- this is the price-identity check that replaces the
        old (buggy) array-index occupancy check."""
        tol = abs(price) * tol_pct
        return any(abs(lot.entry_price - price) <= tol for lot in self.open_lots.values())

    def open_long_lot(self, root_index: int, price: float, ts_ms: int, target: float) -> int:
        lot_id = self._next_lot_id
        self._next_lot_id += 1
        units = self.notional_per_rung / (price * (1 + self.fee_pct))
        self.cash -= units * price * (1 + self.fee_pct)
        self.open_lots[lot_id] = RungLot(
            root_index=root_index, side="long", entry_price=price,
            target_price=target, units=units, opened_at=ts_ms,
        )
        return lot_id

    def close_long_lot(self, lot_id: int, price: float) -> float:
        lot = self.open_lots.pop(lot_id)
        proceeds = lot.units * price * (1 - self.fee_pct)
        cost = lot.units * lot.entry_price * (1 + self.fee_pct)
        pnl = proceeds - cost
        self.cash += proceeds
        self._record_grid_pnl(pnl)
        return pnl

    def open_short_lot(self, root_index: int, price: float, ts_ms: int, target: float) -> int:
        """Mirrors BacktestEngine._open_position(side="short"): short entry RECEIVES proceeds."""
        lot_id = self._next_lot_id
        self._next_lot_id += 1
        units = self.notional_per_rung / price
        self.cash += units * price * (1 - self.fee_pct)
        self.open_lots[lot_id] = RungLot(
            root_index=root_index, side="short", entry_price=price,
            target_price=target, units=units, opened_at=ts_ms,
        )
        return lot_id

    def close_short_lot(self, lot_id: int, price: float) -> float:
        """Mirrors BacktestEngine._capital_after_close(short): closing PAYS the buyback."""
        lot = self.open_lots.pop(lot_id)
        buyback = lot.units * price * (1 + self.fee_pct)
        proceeds_received = lot.units * lot.entry_price * (1 - self.fee_pct)
        pnl = proceeds_received - buyback
        self.cash -= buyback
        self._record_grid_pnl(pnl)
        return pnl

    def force_close_all(self, price: float, ts_ms: int) -> float:
        """Taker + slippage forced exit (arm-triggered) -- NOT a rung fill. Closes every open lot
        at one adverse price, per the fill-realism rule."""
        total = 0.0
        had_lots = bool(self.open_lots)
        for lot_id, lot in list(self.open_lots.items()):
            if lot.side == "long":
                exit_price = price * (1 - self.slippage_pct)
                proceeds = lot.units * exit_price * (1 - self.fee_pct)
                cost = lot.units * lot.entry_price * (1 + self.fee_pct)
                pnl = proceeds - cost
                self.cash += proceeds
            else:
                exit_price = price * (1 + self.slippage_pct)
                buyback = lot.units * exit_price * (1 + self.fee_pct)
                proceeds_received = lot.units * lot.entry_price * (1 - self.fee_pct)
                pnl = proceeds_received - buyback
                self.cash -= buyback
            self.realized_pnl += pnl
            self.forced_pnl += pnl
            total += pnl
            del self.open_lots[lot_id]
        if had_lots:
            self.force_close_count += 1
        return total

    def equity(self, price: float) -> float:
        value = self.cash
        for lot in self.open_lots.values():
            value += lot.units * price if lot.side == "long" else -lot.units * price
        return value

    def inventory_notional(self, price: float) -> float:
        return sum(lot.units * price for lot in self.open_lots.values())

    def _record_grid_pnl(self, pnl: float) -> None:
        self.realized_pnl += pnl
        self.grid_realized_pnl += pnl
        self.grid_trades += 1


def process_bar_fills(
    ledger: GridLedger, levels: Optional[GridLevels], direction: GridDirection, bar: _Bar,
    ts_ms: int, allow_intrabar_roundtrip: bool,
) -> None:
    # 1. Close any open lot whose target price traded this bar.
    #
    #    The target is a RESTING limit order at a price fixed when the lot opened, so whether it
    #    fills depends only on this bar's range -- never on the CURRENT ladder's float values.
    #    Matching the target against `rungs` by equality (or index) cannot work: the ladder is
    #    recomputed every bar from a fresh bb_mid/atr, and consecutive ladders share literally
    #    zero exact float rungs, so a target recorded on an earlier bar would never be found and
    #    no lot would ever close (measured: lots open on 86% of bars, grid_trades stuck at 0).
    #
    #    This also runs BEFORE the `levels is None` guard on purpose: per the design, a FLAT
    #    regime stops opening NEW rungs but existing inventory still works its rungs. Returning
    #    early on FLAT would strand open inventory -- worst exactly for the no-stop arm.
    #    Fill test is DIRECTIONAL, the standard limit-order convention: a long lot's exit is a
    #    resting SELL above entry, so it fills once bar.high reaches it; a short lot's exit is a
    #    resting BUY below entry, filling once bar.low reaches it. Requiring the target to sit
    #    INSIDE the bar's range would silently skip every target the price gapped straight
    #    through -- and a real resting order fills on that gap rather than being passed over.
    for lot_id, lot in list(ledger.open_lots.items()):
        if lot.side == "long":
            filled = bar.high >= lot.target_price
        else:
            filled = bar.low <= lot.target_price
        if filled:
            if lot.side == "long":
                ledger.close_long_lot(lot_id, lot.target_price)
            else:
                ledger.close_short_lot(lot_id, lot.target_price)

    if levels is None:
        return
    rungs = levels.rungs
    crossed = {i for i, r in enumerate(rungs) if bar.low <= r <= bar.high}
    if not crossed:
        return

    is_long_side = direction in (GridDirection.LONG_BIASED, GridDirection.NEUTRAL)

    # 2. Open new lots on touched rungs not already covered by an open lot. "Already covered" is
    #    a PRICE check (has_lot_near), not an index check -- see the GridLedger.open_lots docstring
    #    for why an index-keyed occupancy check was wrong. Tolerance is half a rung's width, so a
    #    ladder that has merely shifted slightly bar-to-bar doesn't spuriously re-open a lot right
    #    on top of one already resting nearby.
    #    Skip a rung whose paired target was ALSO touched this bar when roundtrips are disallowed
    #    -- one bar can't fill both ends of the same pair, per the fill-realism rule.
    #    Capacity is bounded honestly: longs require enough cash to actually afford another lot
    #    (a real economic brake -- opening unconditionally on borrowed cash is how the old
    #    index-keying accidentally capped exposure at max_rungs); max_open_lots is a blanket safety
    #    valve, since shorts ADD cash on open and so aren't bounded by a cash check at all.
    last_index = len(rungs) - 1
    tol_pct = levels.step_pct / 2
    for i in sorted(crossed):
        if ledger.has_lot_near(rungs[i], tol_pct):
            continue
        if len(ledger.open_lots) >= ledger.max_open_lots:
            continue
        if is_long_side:
            if i == last_index:
                continue
            target_index = i + 1
        else:
            if i == 0:
                continue
            target_index = i - 1
        if not allow_intrabar_roundtrip and target_index in crossed:
            continue
        target_price = rungs[target_index]
        if is_long_side:
            if ledger.cash < ledger.notional_per_rung:
                continue
            ledger.open_long_lot(i, rungs[i], ts_ms, target_price)
        else:
            ledger.open_short_lot(i, rungs[i], ts_ms, target_price)
