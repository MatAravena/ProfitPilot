from __future__ import annotations
from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_broker_service, get_current_user
from app.models.db.user import User
from app.models.schemas.broker_schemas import (
    AccountResponse,
    BrokerConnectionResponse,
    ConnectBrokerRequest,
    OrderResultResponse,
    PlaceOrderRequest,
    PositionResponse,
)
from app.services.broker_service import BrokerService

router = APIRouter(prefix="/brokers", tags=["brokers"])

CurrentUser = Annotated[User, Depends(get_current_user)]
BrokerSvc = Annotated[BrokerService, Depends(get_broker_service)]


@router.get("", response_model=List[BrokerConnectionResponse])
async def list_brokers(user: CurrentUser, svc: BrokerSvc):
    """List all active broker connections for the current user."""
    return await svc.list_connections(user.id)


@router.post("", response_model=BrokerConnectionResponse, status_code=status.HTTP_201_CREATED)
async def connect_broker(req: ConnectBrokerRequest, user: CurrentUser, svc: BrokerSvc):
    """Connect a broker (Bybit, Binance, or Alpaca) with API credentials."""
    return await svc.connect_broker(user.id, req)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_broker(connection_id: UUID, user: CurrentUser, svc: BrokerSvc):
    """Disconnect (deactivate) a broker connection."""
    try:
        await svc.disconnect_broker(user.id, connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/{broker_id}/account", response_model=AccountResponse)
async def get_broker_account(broker_id: str, user: CurrentUser, svc: BrokerSvc):
    """Fetch live account info from a specific broker."""
    try:
        account = await svc.get_account(user.id, broker_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Broker error: {exc}")
    return AccountResponse(
        broker_id=account.broker_id,
        account_id=account.account_id,
        equity=account.equity,
        cash=account.cash,
        buying_power=account.buying_power,
        paper_mode=account.paper_mode,
        currency=account.currency,
        updated_at=account.updated_at,
    )


@router.get("/{broker_id}/positions", response_model=List[PositionResponse])
async def get_broker_positions(broker_id: str, user: CurrentUser, svc: BrokerSvc):
    """Fetch open positions from a specific broker."""
    try:
        positions = await svc.get_positions(user.id, broker_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Broker error: {exc}")
    return [
        PositionResponse(
            symbol=p.symbol,
            market_type=p.market_type.value,
            broker_id=p.broker_id,
            quantity=p.quantity,
            avg_entry_price=p.avg_entry_price,
            current_price=p.current_price,
            unrealized_pnl=p.unrealized_pnl,
            unrealized_pnl_pct=p.unrealized_pnl_pct,
            opened_at=p.opened_at,
        )
        for p in positions
    ]


@router.post("/{broker_id}/orders", response_model=OrderResultResponse, status_code=status.HTTP_201_CREATED)
async def place_order(broker_id: str, req: PlaceOrderRequest, user: CurrentUser, svc: BrokerSvc):
    """Place a market or limit order on a connected broker."""
    try:
        result = await svc.place_order(user.id, broker_id, req)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Broker error: {exc}")
    return OrderResultResponse(
        order_id=str(result.order_id),
        broker_order_id=result.broker_order_id,
        status=result.status.value,
        submitted_at=result.submitted_at,
    )
