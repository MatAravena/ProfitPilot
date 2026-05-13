from __future__ import annotations
import asyncio
from datetime import datetime
from typing import AsyncGenerator, List, Optional

import structlog

from app.core.enums import BrokerID, MarketType, OrderSide, OrderStatus, OrderType
from app.core.types import Account, Order, OrderResult, Position, Tick
from app.domain.broker.base import BrokerAdapter

logger = structlog.get_logger(__name__)

# Bybit REST base URLs
_LIVE_BASE     = "https://api.bybit.com"
_TESTNET_BASE  = "https://api-testnet.bybit.com"

# Bybit category constants
_CATEGORY_SPOT   = "spot"
_CATEGORY_LINEAR = "linear"

# Bybit timeframe mapping (our timeframe string → Bybit interval)
_TIMEFRAME_MAP: dict[str, str] = {
    "1m":  "1",
    "3m":  "3",
    "5m":  "5",
    "15m": "15",
    "30m": "30",
    "1h":  "60",
    "4h":  "240",
    "1d":  "D",
    "1w":  "W",
}

# Bybit order status → our OrderStatus
_ORDER_STATUS_MAP: dict[str, OrderStatus] = {
    "Created":         OrderStatus.SUBMITTED,
    "New":             OrderStatus.SUBMITTED,
    "PartiallyFilled": OrderStatus.PARTIAL,
    "Filled":          OrderStatus.FILLED,
    "Cancelled":       OrderStatus.CANCELLED,
    "Rejected":        OrderStatus.REJECTED,
    "Expired":         OrderStatus.EXPIRED,
    "PendingCancel":   OrderStatus.SUBMITTED,
}


class BybitAdapter(BrokerAdapter):
    """
    Bybit broker adapter — crypto spot and USDT perpetual futures.
    Paper mode routes all calls to the Bybit testnet.

    Requires: pybit==5.8.0  (pip install pybit)
    """

    def __init__(self, api_key: str, secret_key: str, paper_mode: bool = True):
        super().__init__(
            broker_id=BrokerID.BYBIT,
            api_key=api_key,
            secret_key=secret_key,
            paper_mode=paper_mode,
            supported_markets=[MarketType.CRYPTO, MarketType.FUTURES],
        )
        self._base_url: str = _TESTNET_BASE if paper_mode else _LIVE_BASE
        self._session = None  # pybit HTTP session, set in connect()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        from pybit.unified_trading import HTTP

        self._session = HTTP(
            testnet=self.paper_mode,
            api_key=self._api_key,
            api_secret=self._secret_key,
        )
        self._log.info("bybit.connected", testnet=self.paper_mode)

    async def disconnect(self) -> None:
        self._session = None
        self._log.info("bybit.disconnected")

    async def health_check(self) -> bool:
        try:
            await self.get_account()
            return True
        except Exception as exc:
            self._log.error("bybit.health_check.failed", error=str(exc))
            return False

    # ── Trading ────────────────────────────────────────────────────────────────

    async def place_order(self, order: Order) -> OrderResult:
        self._log.info(
            "bybit.place_order",
            symbol=order.symbol,
            side=order.side.value,
            qty=order.quantity,
            order_type=order.order_type.value,
        )

        category = self._resolve_category(order.symbol)
        bybit_side = "Buy" if order.side == OrderSide.BUY else "Sell"
        bybit_order_type, extra_kwargs = self._map_order_type(order)

        def _submit():
            return self._session.place_order(
                category=category,
                symbol=order.symbol,
                side=bybit_side,
                orderType=bybit_order_type,
                qty=str(order.quantity),
                timeInForce=self._map_time_in_force(order.time_in_force),
                **extra_kwargs,
            )

        response = await asyncio.get_event_loop().run_in_executor(None, _submit)
        self._assert_ok(response, "place_order")

        result_info = response["result"]
        return OrderResult(
            order_id=order.order_id,
            broker_order_id=result_info["orderId"],
            status=OrderStatus.SUBMITTED,
            submitted_at=datetime.utcnow(),
            metadata={
                "bybit_order_link_id": result_info.get("orderLinkId", ""),
                "category": category,
            },
        )

    async def cancel_order(self, broker_order_id: str) -> bool:
        # We need category to cancel; try linear first, then spot.
        for category in (_CATEGORY_LINEAR, _CATEGORY_SPOT):
            try:
                def _cancel(cat=category):
                    return self._session.cancel_order(
                        category=cat,
                        orderId=broker_order_id,
                    )

                response = await asyncio.get_event_loop().run_in_executor(None, _cancel)
                if response.get("retCode") == 0:
                    self._log.info(
                        "bybit.cancel_order.ok",
                        broker_order_id=broker_order_id,
                        category=category,
                    )
                    return True
            except Exception:
                continue

        self._log.error("bybit.cancel_order.failed", broker_order_id=broker_order_id)
        return False

    async def get_positions(self) -> List[Position]:
        def _fetch():
            return self._session.get_positions(
                category=_CATEGORY_LINEAR,
                settleCoin="USDT",
            )

        response = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        self._assert_ok(response, "get_positions")

        positions: List[Position] = []
        for raw in response["result"].get("list", []):
            size = float(raw.get("size", 0))
            if size == 0:
                continue
            positions.append(self._map_position(raw))

        return positions

    async def get_account(self) -> Account:
        def _fetch():
            return self._session.get_wallet_balance(accountType="UNIFIED")

        response = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        self._assert_ok(response, "get_account")

        accounts_list = response["result"].get("list", [])
        if not accounts_list:
            raise RuntimeError("Bybit returned empty wallet balance list")

        # UNIFIED account — first entry contains all coin balances
        account_data = accounts_list[0]
        total_equity      = float(account_data.get("totalEquity", 0) or 0)
        total_wallet_bal  = float(account_data.get("totalWalletBalance", 0) or 0)
        total_available   = float(account_data.get("totalAvailableBalance", 0) or 0)

        # Derive a stable account_id from the coin list (Bybit UNIFIED has no account ID in this endpoint)
        account_id = account_data.get("accountType", "UNIFIED")

        return Account(
            broker_id=self.broker_id.value,
            account_id=account_id,
            equity=total_equity,
            cash=total_wallet_bal,
            buying_power=total_available,
            paper_mode=self.paper_mode,
            currency="USDT",
            updated_at=datetime.utcnow(),
        )

    async def get_market_data(self, symbol: str, timeframe: str, limit: int = 200) -> List[dict]:
        bybit_interval = _TIMEFRAME_MAP.get(timeframe)
        if bybit_interval is None:
            raise ValueError(f"Unsupported timeframe for Bybit: {timeframe}")

        category = self._resolve_category(symbol)

        def _fetch():
            return self._session.get_kline(
                category=category,
                symbol=symbol,
                interval=bybit_interval,
                limit=limit,
            )

        response = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        self._assert_ok(response, "get_market_data")

        bars: List[dict] = []
        # Bybit returns newest first; reverse to chronological order
        for raw in reversed(response["result"].get("list", [])):
            # raw = [startTime(ms), open, high, low, close, volume, turnover]
            bars.append({
                "timestamp": datetime.utcfromtimestamp(int(raw[0]) / 1000),
                "open":      float(raw[1]),
                "high":      float(raw[2]),
                "low":       float(raw[3]),
                "close":     float(raw[4]),
                "volume":    float(raw[5]),
            })

        return bars

    async def stream_ticks(self, symbol: str) -> AsyncGenerator[Tick, None]:
        """
        Live tick streaming via Bybit WebSocket.
        NOTE: Real implementation requires a background task running the pybit WebSocket client.
        This skeleton yields nothing — wire up pybit's WebSocket in production.
        """
        self._log.warning("bybit.stream_ticks.not_implemented", symbol=symbol)
        return
        yield  # makes this an async generator

    # ── Private Mappers ────────────────────────────────────────────────────────

    def _map_position(self, raw: dict) -> Position:
        size          = float(raw.get("size", 0))
        side_str      = raw.get("side", "Buy")
        # For short positions Bybit returns negative size via side="Sell"
        quantity      = size if side_str == "Buy" else -size
        avg_price     = float(raw.get("avgPrice", 0) or 0)
        mark_price    = float(raw.get("markPrice", 0) or 0)
        unrealized_pnl = float(raw.get("unrealisedPnl", 0) or 0)
        pnl_pct = (
            (unrealized_pnl / (avg_price * abs(quantity))) * 100
            if avg_price and quantity
            else 0.0
        )

        # Bybit linear positions are always FUTURES (USDT perp)
        return Position(
            symbol=raw.get("symbol", ""),
            market_type=MarketType.FUTURES,
            broker_id=self.broker_id.value,
            quantity=quantity,
            avg_entry_price=avg_price,
            current_price=mark_price,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=pnl_pct,
            opened_at=datetime.utcfromtimestamp(
                int(raw["createdTime"]) / 1000
            ) if raw.get("createdTime") else datetime.utcnow(),
        )

    def _map_order_status(self, bybit_status: str) -> OrderStatus:
        return _ORDER_STATUS_MAP.get(bybit_status, OrderStatus.SUBMITTED)

    def _map_order_type(self, order: Order) -> tuple[str, dict]:
        """Return (bybit_order_type, extra_kwargs) for place_order."""
        if order.order_type == OrderType.MARKET:
            return "Market", {}

        if order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                raise ValueError("limit_price required for LIMIT orders")
            return "Limit", {"price": str(order.limit_price)}

        if order.order_type == OrderType.STOP:
            # Bybit represents stop-market as Market with a triggerPrice
            if order.stop_price is None:
                raise ValueError("stop_price required for STOP orders")
            return "Market", {"triggerPrice": str(order.stop_price)}

        if order.order_type == OrderType.STOP_LIMIT:
            if order.stop_price is None or order.limit_price is None:
                raise ValueError("stop_price and limit_price required for STOP_LIMIT orders")
            return "Limit", {
                "price":        str(order.limit_price),
                "triggerPrice": str(order.stop_price),
            }

        raise NotImplementedError(f"OrderType '{order.order_type}' not supported for Bybit")

    @staticmethod
    def _map_time_in_force(tif: str) -> str:
        """Map our time_in_force string to Bybit's TimeInForce value."""
        mapping = {
            "day":  "GTC",   # Bybit has no DAY TIF for crypto; GTC is the standard
            "gtc":  "GTC",
            "ioc":  "IOC",
            "fok":  "FOK",
            "GTC":  "GTC",
            "IOC":  "IOC",
            "FOK":  "FOK",
        }
        return mapping.get(tif, "GTC")

    @staticmethod
    def _resolve_category(symbol: str) -> str:
        """
        Heuristic category resolver.
        Symbols ending in USDT that are perp futures are treated as linear.
        Plain spot pairs are treated as spot.
        Callers can override by passing category explicitly where needed.
        """
        # Bybit USDT perpetuals share the same symbol format as spot (e.g. BTCUSDT).
        # Without additional metadata we default to "linear" (futures) so that
        # get_positions works correctly; strategies should set market_type explicitly.
        return _CATEGORY_LINEAR

    @staticmethod
    def _assert_ok(response: dict, context: str) -> None:
        """Raise RuntimeError if Bybit returned a non-zero retCode."""
        ret_code = response.get("retCode", -1)
        if ret_code != 0:
            ret_msg = response.get("retMsg", "unknown error")
            raise RuntimeError(
                f"Bybit API error in {context}: retCode={ret_code}, retMsg={ret_msg}"
            )
