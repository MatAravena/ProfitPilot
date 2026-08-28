"""Manual orders can be sized by base quantity, fiat notional, or % of the held
position — and always get rounded to the instrument's grid, but never see
RiskManager (a manual order is an intentional user override, not a strategy)."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.enums import BrokerID, MarketType, OrderStatus
from app.core.types import OrderResult, Position
from app.domain.instruments import UnknownInstrument
from app.models.schemas.broker_schemas import PlaceOrderRequest
from app.services.broker_service import BrokerService

pytestmark = pytest.mark.asyncio


class _FakeAdapter:
    broker_id = BrokerID.BYBIT

    def __init__(self, last_price: float = 50_000.0, held_qty: float = 0.2):
        self._last_price = last_price
        self._held_qty = held_qty
        self.placed = None

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...

    async def get_market_data(self, symbol, timeframe, limit=200):
        return [{"close": self._last_price}]

    async def get_positions(self):
        return [Position(
            symbol="BTCUSDT", market_type=MarketType.CRYPTO, broker_id="bybit",
            quantity=self._held_qty, avg_entry_price=self._last_price,
            current_price=self._last_price, unrealized_pnl=0.0, unrealized_pnl_pct=0.0,
            opened_at=datetime.now(timezone.utc),
        )]

    async def place_order(self, order):
        self.placed = order
        return OrderResult(
            order_id=order.order_id, broker_order_id="x1",
            status=OrderStatus.SUBMITTED, submitted_at=datetime.now(timezone.utc),
        )


def _svc(adapter: _FakeAdapter) -> BrokerService:
    svc = BrokerService(repo=None)  # place_order never touches the repo once resolved
    svc.get_adapter_by_connection = lambda user_id, connection_id: _resolved(adapter)
    return svc


async def _resolved(adapter):
    return adapter


def _req(**overrides) -> PlaceOrderRequest:
    base = dict(symbol="BTCUSDT", side="buy", order_type="market", quantity=0.123456)
    base.update(overrides)
    return PlaceOrderRequest(**base)


async def test_quantity_mode_rounds_to_lot_step():
    adapter = _FakeAdapter()
    result = await _svc(adapter).place_order(uuid4(), uuid4(), _req(amount_type="quantity"))
    assert result.status == OrderStatus.SUBMITTED
    assert adapter.placed.quantity < 0.123456  # floored to BTCUSDT's lot step


async def test_notional_mode_converts_fiat_to_quantity():
    adapter = _FakeAdapter(last_price=50_000.0)
    req = _req(amount_type="notional", quantity=1_000.0)  # $1,000 of BTC @ $50k = 0.02
    await _svc(adapter).place_order(uuid4(), uuid4(), req)
    assert adapter.placed.quantity == pytest.approx(0.02, rel=1e-6)


async def test_percent_mode_reads_current_holding():
    adapter = _FakeAdapter(held_qty=0.2)
    req = _req(amount_type="percent", side="sell", quantity=50.0)  # sell 50% of 0.2 BTC
    await _svc(adapter).place_order(uuid4(), uuid4(), req)
    assert adapter.placed.quantity == pytest.approx(0.1, rel=1e-6)


async def test_unseeded_symbol_is_rejected():
    adapter = _FakeAdapter()
    with pytest.raises(UnknownInstrument):
        await _svc(adapter).place_order(uuid4(), uuid4(), _req(symbol="NOTASYMBOL"))
