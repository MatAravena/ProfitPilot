from __future__ import annotations
import asyncio
from datetime import datetime
from typing import AsyncGenerator, List

import structlog

from app.core.enums import BrokerID, MarketType, OrderSide, OrderStatus, OrderType
from app.core.types import Account, Order, OrderResult, Position, Tick
from app.domain.broker.base import BrokerAdapter

logger = structlog.get_logger(__name__)

# Timeframe mapping: ProfitPilot → Binance kline interval strings
_TIMEFRAME_MAP = {
    "1m":  "1m",
    "5m":  "5m",
    "15m": "15m",
    "30m": "30m",
    "1h":  "1h",
    "4h":  "4h",
    "1d":  "1d",
    "1w":  "1w",
}

# Binance order type strings
_ORDER_TYPE_MAP = {
    OrderType.MARKET:     "MARKET",
    OrderType.LIMIT:      "LIMIT",
    OrderType.STOP:       "STOP_LOSS_LIMIT",
    OrderType.STOP_LIMIT: "STOP_LOSS_LIMIT",
}

# Binance order status → our OrderStatus
_STATUS_MAP = {
    "NEW":              OrderStatus.SUBMITTED,
    "PARTIALLY_FILLED": OrderStatus.PARTIAL,
    "FILLED":           OrderStatus.FILLED,
    "CANCELED":         OrderStatus.CANCELLED,
    "REJECTED":         OrderStatus.REJECTED,
    "EXPIRED":          OrderStatus.EXPIRED,
    "PENDING_CANCEL":   OrderStatus.SUBMITTED,
}


class BinanceAdapter(BrokerAdapter):
    """
    Binance broker adapter — spot crypto and futures.
    Paper mode uses the Binance testnet (https://testnet.binance.vision).

    Requires: python-binance==1.0.19
    """

    def __init__(self, api_key: str, secret_key: str, paper_mode: bool = True):
        super().__init__(
            broker_id=BrokerID.BINANCE,
            api_key=api_key,
            secret_key=secret_key,
            paper_mode=paper_mode,
            supported_markets=[MarketType.CRYPTO, MarketType.FUTURES],
        )
        self._client = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        from binance.client import Client

        self._client = Client(
            api_key=self._api_key,
            api_secret=self._secret_key,
            testnet=self.paper_mode,
        )
        self._log.info("binance.connected", testnet=self.paper_mode)

    async def disconnect(self) -> None:
        self._client = None
        self._log.info("binance.disconnected")

    async def health_check(self) -> bool:
        try:
            await self.get_account()
            return True
        except Exception as exc:
            self._log.error("binance.health_check.failed", error=str(exc))
            return False

    # ── Trading ────────────────────────────────────────────────────────────────

    async def place_order(self, order: Order) -> OrderResult:
        from binance.exceptions import BinanceAPIException

        self._log.info(
            "binance.place_order",
            symbol=order.symbol,
            side=order.side.value,
            qty=order.quantity,
            order_type=order.order_type.value,
        )

        side_str = "BUY" if order.side == OrderSide.BUY else "SELL"
        order_type_str = _ORDER_TYPE_MAP.get(order.order_type)
        if order_type_str is None:
            raise NotImplementedError(f"OrderType '{order.order_type}' not supported for Binance")

        params: dict = {
            "symbol": order.symbol.upper(),
            "side": side_str,
            "type": order_type_str,
            "quantity": order.quantity,
        }

        if order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                raise ValueError("limit_price required for LIMIT orders")
            params["price"] = order.limit_price
            params["timeInForce"] = "GTC"

        elif order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
            if order.stop_price is None:
                raise ValueError("stop_price required for STOP/STOP_LIMIT orders")
            params["stopPrice"] = order.stop_price
            params["timeInForce"] = "GTC"
            if order.limit_price is not None:
                params["price"] = order.limit_price
            else:
                # STOP_LOSS_LIMIT requires a price; default to stop_price as limit
                params["price"] = order.stop_price

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._client.create_order(**params)
            )
        except BinanceAPIException as exc:
            self._log.error(
                "binance.place_order.failed",
                symbol=order.symbol,
                error=str(exc),
                code=exc.code,
            )
            return OrderResult(
                order_id=order.order_id,
                broker_order_id="",
                status=OrderStatus.REJECTED,
                submitted_at=datetime.utcnow(),
                metadata={"binance_error": str(exc), "binance_code": exc.code},
            )

        broker_order_id = f"{response['symbol']}|{response['orderId']}"
        raw_status = response.get("status", "NEW")
        status = _STATUS_MAP.get(raw_status, OrderStatus.SUBMITTED)

        return OrderResult(
            order_id=order.order_id,
            broker_order_id=broker_order_id,
            status=status,
            submitted_at=datetime.utcnow(),
            metadata={
                "binance_order_id": response["orderId"],
                "binance_status": raw_status,
                "client_order_id": response.get("clientOrderId", ""),
                "transact_time": response.get("transactTime"),
            },
        )

    async def cancel_order(self, broker_order_id: str) -> bool:
        """
        broker_order_id must be in the format "{SYMBOL}|{orderId}" as set by place_order.
        """
        from binance.exceptions import BinanceAPIException

        try:
            symbol, order_id_str = broker_order_id.split("|", 1)
        except ValueError:
            self._log.error(
                "binance.cancel_order.invalid_id",
                broker_order_id=broker_order_id,
            )
            return False

        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._client.cancel_order(
                    symbol=symbol.upper(),
                    orderId=int(order_id_str),
                ),
            )
            self._log.info("binance.cancel_order.ok", broker_order_id=broker_order_id)
            return True
        except BinanceAPIException as exc:
            self._log.error(
                "binance.cancel_order.failed",
                broker_order_id=broker_order_id,
                error=str(exc),
                code=exc.code,
            )
            return False

    async def get_positions(self) -> List[Position]:
        """
        Returns spot balances with non-zero free or locked amounts as pseudo-positions.
        Each balance item is treated as a position in the base asset vs USDT.
        """
        raw_account = await asyncio.get_event_loop().run_in_executor(
            None, self._client.get_account
        )
        balances = raw_account.get("balances", [])
        positions: List[Position] = []

        for balance in balances:
            asset = balance["asset"]
            free = float(balance["free"])
            locked = float(balance["locked"])
            total = free + locked

            if total <= 0.0:
                continue

            # Skip stablecoins and fiat-pegged assets as they are not "positions"
            if asset in ("USDT", "BUSD", "USDC", "TUSD", "DAI", "EUR", "GBP"):
                continue

            symbol = f"{asset}USDT"
            current_price = await self._get_symbol_price(symbol)

            positions.append(
                Position(
                    symbol=symbol,
                    market_type=MarketType.CRYPTO,
                    broker_id=self.broker_id.value,
                    quantity=total,
                    avg_entry_price=current_price,   # spot has no avg entry — approximate with current
                    current_price=current_price,
                    unrealized_pnl=0.0,              # spot balances have no PnL without cost basis
                    unrealized_pnl_pct=0.0,
                    opened_at=datetime.utcnow(),
                )
            )

        return positions

    async def get_account(self) -> Account:
        raw_account = await asyncio.get_event_loop().run_in_executor(
            None, self._client.get_account
        )

        usdt_balance = await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._client.get_asset_balance(asset="USDT")
        )

        free_usdt = float(usdt_balance.get("free", 0.0)) if usdt_balance else 0.0
        locked_usdt = float(usdt_balance.get("locked", 0.0)) if usdt_balance else 0.0
        total_usdt = free_usdt + locked_usdt

        return Account(
            broker_id=self.broker_id.value,
            account_id=str(raw_account.get("accountType", "SPOT")),
            equity=total_usdt,
            cash=total_usdt,
            buying_power=free_usdt,
            paper_mode=self.paper_mode,
            currency="USDT",
            updated_at=datetime.utcnow(),
        )

    async def get_market_data(self, symbol: str, timeframe: str, limit: int = 200) -> List[dict]:
        interval = _TIMEFRAME_MAP.get(timeframe)
        if interval is None:
            raise ValueError(f"Unsupported timeframe for Binance: {timeframe}")

        klines = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._client.get_klines(
                symbol=symbol.upper(),
                interval=interval,
                limit=limit,
            ),
        )

        return [self._map_kline(k) for k in klines]

    async def stream_ticks(self, symbol: str) -> AsyncGenerator[Tick, None]:
        """
        Live tick streaming via Binance WebSocket is not implemented in this skeleton.
        Wire up python-binance's BinanceSocketManager in production.
        """
        self._log.warning("binance.stream_ticks.not_implemented", symbol=symbol)
        return
        yield  # noqa: unreachable — required to make this an async generator

    # ── Private Helpers ────────────────────────────────────────────────────────

    async def _get_symbol_price(self, symbol: str) -> float:
        """Fetch the latest price for a symbol. Returns 0.0 on any error."""
        try:
            ticker = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._client.get_symbol_ticker(symbol=symbol.upper())
            )
            return float(ticker.get("price", 0.0))
        except Exception as exc:
            self._log.warning(
                "binance.get_symbol_price.failed",
                symbol=symbol,
                error=str(exc),
            )
            return 0.0

    # ── Private Mappers ────────────────────────────────────────────────────────

    @staticmethod
    def _map_kline(kline: list) -> dict:
        """
        Convert a Binance kline tuple to a normalised OHLCV dict.

        Binance kline format (index → field):
          0  open_time (ms epoch)
          1  open
          2  high
          3  low
          4  close
          5  volume
          6  close_time
          7  quote_asset_volume
          8  number_of_trades
          9  taker_buy_base_asset_volume
          10 taker_buy_quote_asset_volume
          11 ignore
        """
        return {
            "timestamp": datetime.utcfromtimestamp(int(kline[0]) / 1000),
            "open":      float(kline[1]),
            "high":      float(kline[2]),
            "low":       float(kline[3]),
            "close":     float(kline[4]),
            "volume":    float(kline[5]),
        }
