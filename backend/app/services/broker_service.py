from __future__ import annotations
from datetime import datetime
from typing import List
from uuid import UUID, uuid4

import structlog

from app.core.enums import BrokerID, OrderSide, OrderType
from app.core.types import Account, Order, OrderResult, Position
from app.domain.broker.base import BrokerAdapter
from app.models.db.broker_connection import BrokerConnection
from app.models.schemas.broker_schemas import ConnectBrokerRequest, BrokerConnectionResponse, PlaceOrderRequest
from app.repositories.broker_connection_repository import BrokerConnectionRepository
from app.services.crypto_service import decrypt, encrypt

_MANUAL_STRATEGY_ID = UUID("00000000-0000-0000-0000-000000000001")

logger = structlog.get_logger(__name__)

# Priority order for broker resolution
_BROKER_PRIORITY = [BrokerID.BYBIT, BrokerID.BINANCE, BrokerID.ALPACA]


class BrokerService:
    def __init__(self, repo: BrokerConnectionRepository):
        self._repo = repo

    # ── Connections ────────────────────────────────────────────────────────────

    async def connect_broker(self, user_id: UUID, req: ConnectBrokerRequest) -> BrokerConnectionResponse:
        # Deactivate any existing connection for same broker+user
        existing = await self._repo.get_by_user_and_broker(user_id, req.broker_id)
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

    async def get_adapter(self, user_id: UUID, broker_id: str) -> BrokerAdapter:
        conn = await self._repo.get_by_user_and_broker(user_id, broker_id)
        if conn is None:
            raise ValueError(f"No active {broker_id} connection for this user")
        return _build_adapter(conn)

    async def get_all_adapters(self, user_id: UUID) -> List[BrokerAdapter]:
        conns = await self._repo.get_by_user(user_id)
        # Return in priority order
        by_id = {c.broker_id: c for c in conns}
        return [
            _build_adapter(by_id[b.value])
            for b in _BROKER_PRIORITY
            if b.value in by_id
        ]

    # ── Account data ──────────────────────────────────────────────────────────

    async def get_account(self, user_id: UUID, broker_id: str) -> Account:
        adapter = await self.get_adapter(user_id, broker_id)
        await adapter.connect()
        try:
            return await adapter.get_account()
        finally:
            await adapter.disconnect()

    async def get_positions(self, user_id: UUID, broker_id: str) -> List[Position]:
        adapter = await self.get_adapter(user_id, broker_id)
        await adapter.connect()
        try:
            return await adapter.get_positions()
        finally:
            await adapter.disconnect()

    async def place_order(self, user_id: UUID, broker_id: str, req: PlaceOrderRequest) -> OrderResult:
        adapter = await self.get_adapter(user_id, broker_id)
        await adapter.connect()
        try:
            order = Order(
                order_id=uuid4(),
                strategy_id=_MANUAL_STRATEGY_ID,
                broker_id=broker_id,
                symbol=req.symbol.upper(),
                side=OrderSide(req.side),
                order_type=OrderType(req.order_type),
                quantity=req.quantity,
                limit_price=req.limit_price,
                time_in_force=req.time_in_force,
                created_at=datetime.utcnow(),
            )
            result = await adapter.place_order(order)
            logger.info(
                "order.placed",
                broker=broker_id,
                symbol=order.symbol,
                side=order.side.value,
                qty=order.quantity,
                status=result.status.value,
            )
            return result
        finally:
            await adapter.disconnect()


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
