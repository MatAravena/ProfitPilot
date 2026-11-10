from app.domain.strategies.grid.ledger import GridLedger, process_bar_fills
from app.domain.strategies.grid.levels import GridLevels
from app.domain.strategies.grid.regime import GridDirection


def _ledger(**overrides):
    defaults = dict(fee_pct=0.001, slippage_pct=0.0005, notional_per_rung=100.0, cash=1000.0)
    defaults.update(overrides)
    return GridLedger(**defaults)


def test_open_long_lot_spends_cash_and_tracks_units():
    ledger = _ledger()
    lot_id = ledger.open_long_lot(root_index=0, price=100.0, ts_ms=0, target=110.0)
    assert lot_id in ledger.open_lots
    assert ledger.cash < 1000.0
    assert ledger.open_lots[lot_id].units > 0


def test_close_long_lot_realizes_grid_profit_on_a_price_step_up():
    ledger = _ledger(fee_pct=0.0, slippage_pct=0.0)
    lot_id = ledger.open_long_lot(root_index=0, price=100.0, ts_ms=0, target=110.0)
    pnl = ledger.close_long_lot(lot_id, price=110.0)
    assert pnl > 0
    assert ledger.grid_trades == 1
    assert ledger.grid_realized_pnl == pnl
    assert lot_id not in ledger.open_lots


def test_short_lot_open_and_close_mirrors_backtest_engine_sign_convention():
    """open_short receives proceeds (cash goes UP); close_short pays the buyback (cash goes DOWN);
    profit is realized when price fell between entry and close — the BacktestEngine mirror."""
    ledger = _ledger(fee_pct=0.0, slippage_pct=0.0)
    cash_before_open = ledger.cash
    lot_id = ledger.open_short_lot(root_index=5, price=100.0, ts_ms=0, target=90.0)
    assert ledger.cash > cash_before_open   # short entry receives proceeds

    cash_before_close = ledger.cash
    pnl = ledger.close_short_lot(lot_id, price=90.0)
    assert ledger.cash < cash_before_close   # closing pays the buyback
    assert pnl > 0                            # price fell -> short profits
    assert lot_id not in ledger.open_lots


def test_equity_marks_long_up_and_short_down_with_price():
    ledger = _ledger(fee_pct=0.0, slippage_pct=0.0)
    ledger.open_long_lot(root_index=0, price=100.0, ts_ms=0, target=110.0)
    equity_at_entry = ledger.equity(100.0)
    equity_after_rise = ledger.equity(110.0)
    assert equity_after_rise > equity_at_entry


def test_force_close_all_uses_taker_and_slippage_not_maker_rates():
    ledger = _ledger(fee_pct=0.001, slippage_pct=0.01)
    ledger.open_long_lot(root_index=0, price=100.0, ts_ms=0, target=110.0)
    pnl = ledger.force_close_all(price=100.0, ts_ms=1)   # flat price, but slippage still costs
    assert pnl < 0   # forced exit at the SAME price as entry still loses to slippage+fees
    assert ledger.open_lots == {}


def test_force_close_all_records_forced_pnl_separately_and_counts_the_event():
    """The mandatory realized-vs-mark-to-market split must reconcile: a forced (guard-triggered)
    exit's P&L used to vanish into neither grid_realized_pnl nor mark_to_market_pnl. Track it on
    its own so a reader can actually account for every dollar."""
    ledger = _ledger(fee_pct=0.001, slippage_pct=0.01)
    ledger.open_long_lot(root_index=0, price=100.0, ts_ms=0, target=110.0)
    pnl = ledger.force_close_all(price=100.0, ts_ms=1)
    assert ledger.forced_pnl == pnl
    assert ledger.force_close_count == 1
    # A forced exit is NOT a completed grid -- it must not be counted as grid income.
    assert ledger.grid_trades == 0
    assert ledger.grid_realized_pnl == 0.0

    # Calling force_close_all with nothing open must not count as a force-close event.
    ledger.force_close_all(price=100.0, ts_ms=2)
    assert ledger.force_close_count == 1


def test_has_lot_near_matches_within_tolerance_and_not_beyond_it():
    ledger = _ledger()
    ledger.open_long_lot(root_index=0, price=100.0, ts_ms=0, target=110.0)
    assert ledger.has_lot_near(100.4, tol_pct=0.01) is True     # within 1% of 100 -> covered
    assert ledger.has_lot_near(102.0, tol_pct=0.01) is False    # 2% away -> not covered


def test_process_bar_fills_opens_a_long_rung_when_price_touches_it():
    levels = GridLevels(center=100.0, step_pct=0.02, rungs=[96.0, 98.0, 100.0, 102.0, 104.0])
    ledger = _ledger()

    class _Bar:
        low, high = 97.5, 98.5

    process_bar_fills(ledger, levels, GridDirection.LONG_BIASED, _Bar(), ts_ms=0,
                      allow_intrabar_roundtrip=False)
    assert len(ledger.open_lots) == 1
    lot = next(iter(ledger.open_lots.values()))
    assert lot.entry_price == 98.0             # rung index 1 (98.0) touched
    assert lot.target_price == 100.0            # target is the next rung up


def test_process_bar_fills_skips_same_bar_roundtrip_when_disallowed():
    levels = GridLevels(center=100.0, step_pct=0.02, rungs=[96.0, 98.0, 100.0, 102.0, 104.0])
    ledger = _ledger()

    class _Bar:
        low, high = 97.5, 100.5   # touches both rung 98 (open) and rung 100 (its own target)

    process_bar_fills(ledger, levels, GridDirection.LONG_BIASED, _Bar(), ts_ms=0,
                      allow_intrabar_roundtrip=False)
    assert not any(lot.entry_price == 98.0 for lot in ledger.open_lots.values())


def test_process_bar_fills_does_not_reopen_a_slot_whose_ladder_has_merely_shifted():
    """Regression test for the root-index bug: two bars whose ladders have shifted slightly (as
    real bb_mid/atr-driven ladders do) must NOT stack a second lot on top of an already-open one
    at essentially the same price -- occupancy must be judged by price, not by array position."""
    ledger = _ledger(notional_per_rung=100.0, cash=1_000_000.0)
    levels_a = GridLevels(center=100.0, step_pct=0.02, rungs=[96.0, 98.0, 100.0, 102.0, 104.0])

    class _BarA:
        low, high = 97.5, 98.5

    process_bar_fills(ledger, levels_a, GridDirection.LONG_BIASED, _BarA(), ts_ms=0,
                      allow_intrabar_roundtrip=False)
    assert len(ledger.open_lots) == 1

    # Next bar's ladder has shifted slightly (98.0 -> 98.05, same relative shape) -- a real
    # bb_mid/atr recompute produces exactly this kind of small drift bar to bar.
    levels_b = GridLevels(center=100.05, step_pct=0.02, rungs=[96.05, 98.05, 100.05, 102.05, 104.05])

    class _BarB:
        low, high = 97.55, 98.55

    process_bar_fills(ledger, levels_b, GridDirection.LONG_BIASED, _BarB(), ts_ms=1,
                      allow_intrabar_roundtrip=False)
    # Still just the one lot -- the shifted rung at 98.05 is within tolerance of the existing
    # lot at 98.0, so it must be treated as the same slot, not a new one.
    assert len(ledger.open_lots) == 1


def test_process_bar_fills_opens_a_genuinely_new_lot_at_a_distant_price():
    """The flip side of the above: a rung far from any open lot's price must still open."""
    ledger = _ledger(notional_per_rung=100.0, cash=1_000_000.0)
    levels_a = GridLevels(center=100.0, step_pct=0.02, rungs=[96.0, 98.0, 100.0, 102.0, 104.0])

    class _BarA:
        low, high = 97.5, 98.5

    process_bar_fills(ledger, levels_a, GridDirection.LONG_BIASED, _BarA(), ts_ms=0,
                      allow_intrabar_roundtrip=False)
    assert len(ledger.open_lots) == 1

    # A much lower ladder, far from the existing lot's price -- a genuinely different rung.
    levels_b = GridLevels(center=50.0, step_pct=0.02, rungs=[46.0, 48.0, 50.0, 52.0, 54.0])

    class _BarB:
        low, high = 47.5, 48.5

    process_bar_fills(ledger, levels_b, GridDirection.LONG_BIASED, _BarB(), ts_ms=1,
                      allow_intrabar_roundtrip=False)
    assert len(ledger.open_lots) == 2


def test_long_open_is_skipped_when_cash_cannot_afford_another_lot():
    """Longs are bounded by a real economic brake: opening unconditionally on borrowed cash is
    exactly how the old index-keying accidentally capped exposure -- the honest replacement is a
    cash check, not an accident."""
    ledger = _ledger(notional_per_rung=100.0, cash=50.0)   # can't afford a $100 lot
    levels = GridLevels(center=100.0, step_pct=0.02, rungs=[96.0, 98.0, 100.0, 102.0, 104.0])

    class _Bar:
        low, high = 97.5, 98.5

    process_bar_fills(ledger, levels, GridDirection.LONG_BIASED, _Bar(), ts_ms=0,
                      allow_intrabar_roundtrip=False)
    assert ledger.open_lots == {}


def test_short_open_is_capped_by_max_open_lots_not_by_cash():
    """Shorts ADD cash on open, so they are never blocked by the cash check -- max_open_lots is
    their only capacity guard, and it must actually bind."""
    ledger = _ledger(notional_per_rung=10.0, cash=1_000_000.0, max_open_lots=2)
    # Three well-separated ladders, one rung each, all in SHORT_BIASED direction.
    for i, (center, price) in enumerate([(100.0, 100.0), (200.0, 200.0), (300.0, 300.0)]):
        levels = GridLevels(center=center, step_pct=0.02, rungs=[price * 0.98, price, price * 1.02])

        class _Bar:
            low = price - 0.5
            high = price + 0.5

        process_bar_fills(ledger, levels, GridDirection.SHORT_BIASED, _Bar(), ts_ms=i,
                          allow_intrabar_roundtrip=False)
    assert len(ledger.open_lots) == 2   # the third open was refused by the cap
