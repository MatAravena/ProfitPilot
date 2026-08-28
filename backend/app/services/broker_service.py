from __future__ import annotations
from datetime import datetime
from typing import List
from uuid import UUID, uuid4

import structlog

from app.core.enums import BrokerID, OrderSide, OrderType
from app.core.types import Account, Order, OrderResult, Position
from app.domain.broker.base import BrokerAdapter
from app.domain.instruments import INSTRUMENTS, InstrumentCatalog, conform_order
from app.models.db.broker_connection import BrokerConnection
from app.models.schemas.broker_schemas import ConnectBrokerRequest, BrokerConnectionResponse, PlaceOrderRequest
from app.repositories.broker_connection_repository import BrokerConnectionRepository
from app.services.crypto_service import decrypt, encrypt

_MANUAL_STRATEGY_ID = UUID("00000000-0000-0000-0000-000000000001")

logger = structlog.get_logger(__name__)

# Priority order for broker resolution
_BROKER_PRIORITY = [BrokerID.BYBIT, BrokerID.BINANCE, BrokerID.ALPACA]


class BrokerService:
    def __init__(self, repo: BrokerConnectionRepository, instruments: InstrumentCatalog = INSTRUMENTS):
        self._repo = repo
        self._instruments = instruments

    # ── Connections ────────────────────────────────────────────────────────────

    async def connect_broker(self, user_id: UUID, req: ConnectBrokerRequest) -> BrokerConnectionResponse:
        # Deactivate any existing connection for the same broker + mode (paper/live are
        # separate accounts, so connecting testnet keys doesn't kill a live connection).
        existing = await self._repo.get_by_user_broker_and_mode(user_id, req.broker_id, req.is_paper)
        if existing:
            await self._repo.deactivate(existing)

        conn = BrokerConnection(
            user_id=user_id,
            broker_id=req.broker_id,
            encrypted_api_key=encrypt(req.api_key),
            encrypted_secret_key=encrypt(req.secret_key),
            label=req.label or req.broker_id.capitalize(),
            is_paper=req.is_paper,
            is_active=True,
        )
        saved = await self._repo.add(conn)
        logger.info("broker.connected", user=str(user_id), broker=req.broker_id)
        return BrokerConnectionResponse.model_validate(saved)

    async def list_connections(self, user_id: UUID) -> List[BrokerConnectionResponse]:
        conns = await self._repo.get_by_user(user_id)
        return [BrokerConnectionResponse.model_validate(c) for c in conns]

    async def disconnect_broker(self, user_id: UUID, connection_id: UUID) -> None:
        conn = await self._repo.get(connection_id)
        if conn is None or conn.user_id != user_id:
            raise ValueError("Broker connection not found")
        await self._repo.deactivate(conn)

    # ── Adapter resolution ─────────────────────────────────────────────────────

    async def get_adapter_by_connection(self, user_id: UUID, connection_id: UUID) -> BrokerAdapter:
        conn = await self._repo.get(connection_id)
        if conn is None or conn.user_id != user_id or not conn.is_active:
            raise ValueError("No active broker connection for this user")
        return _build_adapter(conn)

    async def get_all_adapters(self, user_id: UUID) -> List[BrokerAdapter]:
        conns = await self._repo.get_by_user(user_id)
        # Paper and live connections for the same broker both count — priority only
        # orders the list, it doesn't dedupe.
        order = {b.value: i for i, b in enumerate(_BROKER_PRIORITY)}
        conns.sort(key=lambda c: order.get(c.broker_id, len(order)))
        return [_build_adapter(c) for c in conns]

    # ── Account data ──────────────────────────────────────────────────────────

    async def get_account(self, user_id: UUID, connection_id: UUID) -> Account:
        adapter = await self.get_adapter_by_connection(user_id, connection_id)
        await adapter.connect()
        try:
            return await adapter.get_account()
        finally:
            await adapter.disconnect()

    async def get_positions(self, user_id: UUID, connection_id: UUID) -> List[Position]:
        adapter = await self.get_adapter_by_connection(user_id, connection_id)
        await adapter.connect()
        try:
            return await adapter.get_positions()
        finally:
            await adapter.disconnect()

    async def place_order(self, user_id: UUID, connection_id: UUID, req: PlaceOrderRequest) -> OrderResult:
        adapter = await self.get_adapter_by_connection(user_id, connection_id)
        await adapter.connect()
        try:
            symbol = req.symbol.upper()
            qty = await self._resolve_quantity(adapter, symbol, req)

            # Round/validate against the instrument's own grid so the broker doesn't
            # bounce the request — deliberately no RiskManager veto here: a manual
            # order is the user overriding position-size/drawdown limits on purpose.
            instrument = self._instruments.require(symbol)
            qty, limit_price = conform_order(
                instrument, quantity=qty, price=req.limit_price, broker=adapter.broker_id,
            )

            order = Order(
                order_id=uuid4(),
                strategy_id=_MANUAL_STRATEGY_ID,
                broker_id=adapter.broker_id.value,
                symbol=symbol,
                side=OrderSide(req.side),
                order_type=OrderType(req.order_type),
                quantity=qty,
                limit_price=limit_price,
                time_in_force=req.time_in_force,
                created_at=datetime.utcnow(),
            )
            result = await adapter.place_order(order)
            logger.info(
                "order.placed",
                broker=order.broker_id,
                symbol=order.symbol,
                side=order.side.value,
                qty=order.quantity,
                amount_type=req.amount_type,
                status=result.status.value,
            )
            return result
        finally:
            await adapter.disconnect()

    async def _resolve_quantity(self, adapter: BrokerAdapter, symbol: str, req: PlaceOrderRequest) -> float:
        """Turn the user's amount — base quantity, fiat notional, or % of position — into
        a base-asset quantity. Only the percent mode needs a position lookup; quantity
        and notional sizing place the order immediately without one."""
        if req.amount_type == "quantity":
            return req.quantity
        if req.amount_type == "notional":
            price = req.limit_price or await self._last_price(adapter, symbol)
            return req.quantity / price
        positions = await adapter.get_positions()
        held = next((p.quantity for p in positions if p.symbol == symbol), 0.0)
        return abs(held) * (req.quantity / 100)

    async def _last_price(self, adapter: BrokerAdapter, symbol: str) -> float:
        bars = await adapter.get_market_data(symbol, "1m", limit=1)
        if not bars:
            raise ValueError(f"No market data available for {symbol}")
        return float(bars[-1]["close"])


# ── Private factory ────────────────────────────────────────────────────────────

def _build_adapter(conn: BrokerConnection) -> BrokerAdapter:
    api_key = decrypt(conn.encrypted_api_key)
    secret_key = decrypt(conn.encrypted_secret_key)

    if conn.broker_id == BrokerID.BYBIT.value:
        from app.domain.broker.adapters.bybit_adapter import BybitAdapter
        return BybitAdapter(api_key=api_key, secret_key=secret_key, paper_mode=conn.is_paper)

    if conn.broker_id == BrokerID.BINANCE.value:
        from app.domain.broker.adapters.binance_adapter import BinanceAdapter
        return BinanceAdapter(api_key=api_key, secret_key=secret_key, paper_mode=conn.is_paper)

    if conn.broker_id == BrokerID.ALPACA.value:
        from app.domain.broker.adapters.alpaca_adapter import AlpacaAdapter
        return AlpacaAdapter(api_key=api_key, secret_key=secret_key, paper_mode=conn.is_paper)

    raise ValueError(f"Unknown broker: {conn.broker_id}")
