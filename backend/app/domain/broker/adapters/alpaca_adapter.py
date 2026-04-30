from __future__ import annotations
import asyncio
from datetime import datetime
from typing import AsyncGenerator, List
from uuid import UUID

import structlog

from app.core.enums import BrokerID, MarketType, OrderSide, OrderStatus, OrderType
from app.core.types import Account, Fill, Order, OrderResult, Position, Tick
from app.domain.broker.base import BrokerAdapter

logger = structlog.get_logger(__name__)

# Alpaca base URLs
_LIVE_BASE   = "https://api.alpaca.markets"
_PAPER_BASE  = "https://paper-api.alpaca.markets"
_DATA_BASE   = "https://data.alpaca.markets"
_STREAM_BASE = "wss://stream.data.alpaca.markets/v2"


class AlpacaAdapter(BrokerAdapter):
    """
    Alpaca Markets broker adapter — stocks and crypto.
    Paper mode uses Alpaca's built-in paper trading environment.

    Requires: alpaca-py (pip install alpaca-py)
    """

    def __init__(self, api_key: str, secret_key: str, paper_mode: bool = True):
        super().__init__(
            broker_id=BrokerID.ALPACA,
            api_key=api_key,
            secret_key=secret_key,
            paper_mode=paper_mode,
            supported_markets=[MarketType.STOCK, MarketType.CRYPTO],
        )
        self._base_url = _PAPER_BASE if paper_mode else _LIVE_BASE
        self._trading_client = None
        self._data_client = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        from alpaca.trading.client import TradingClient
        from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient

        self._trading_client = TradingClient(
            api_key=self._api_key,
            secret_key=self._secret_key,
            paper=self.paper_mode,
        )
        self._stock_data_client = StockHistoricalDataClient(
            api_key=self._api_key,
            secret_key=self._secret_key,
        )
        self._crypto_data_client = CryptoHistoricalDataClient(
            api_key=self._api_key,
            secret_key=self._secret_key,
        )
        self._log.info("alpaca.connected")

    async def disconnect(self) -> None:
        self._trading_client = None
        self._log.info("alpaca.disconnected")

    async def health_check(self) -> bool:
        try:
            account = await self.get_account()
            return account is not None
        except Exception as exc:
            self._log.error("alpaca.health_check.failed", error=str(exc))
            return False

    # ── Trading ────────────────────────────────────────────────────────────────

    async def place_order(self, order: Order) -> OrderResult:
        from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
        from alpaca.trading.enums import OrderSide as AlpSide, TimeInForce

        self._log.info("alpaca.place_order", symbol=order.symbol, side=order.side.value, qty=order.quantity)

        side = AlpSide.BUY if order.side == OrderSide.BUY else AlpSide.SELL
        tif  = TimeInForce.DAY

        if order.order_type == OrderType.MARKET:
            request = MarketOrderRequest(
                symbol=order.symbol,
                qty=order.quantity,
                side=side,
                time_in_force=tif,
            )
        elif order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                raise ValueError("limit_price required for LIMIT orders")
            request = LimitOrderRequest(
                symbol=order.symbol,
                qty=order.quantity,
                side=side,
                time_in_force=tif,
                limit_price=order.limit_price,
            )
        else:
            raise NotImplementedError(f"OrderType '{order.order_type}' not yet implemented for Alpaca")

        response = await asyncio.get_event_loop().run_in_executor(
            None, self._trading_client.submit_order, request
        )

        return OrderResult(
            order_id=order.order_id,
            broker_order_id=str(response.id),
            status=OrderStatus.SUBMITTED,
            submitted_at=datetime.utcnow(),
            metadata={"alpaca_status": str(response.status)},
        )

    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self._trading_client.cancel_order_by_id, broker_order_id
            )
            self._log.info("alpaca.cancel_order.ok", broker_order_id=broker_order_id)
            return True
        except Exception as exc:
            self._log.error("alpaca.cancel_order.failed", broker_order_id=broker_order_id, error=str(exc))
            return False

    async def get_positions(self) -> List[Position]:
        raw = await asyncio.get_event_loop().run_in_executor(
            None, self._trading_client.get_all_positions
        )
        return [self._map_position(p) for p in raw]

    async def get_account(self) -> Account:
        raw = await asyncio.get_event_loop().run_in_executor(
            None, self._trading_client.get_account
        )
        return Account(
            broker_id=self.broker_id.value,
            account_id=str(raw.id),
            equity=float(raw.equity),
            cash=float(raw.cash),
            buying_power=float(raw.buying_power),
            paper_mode=self.paper_mode,
            currency="USD",
            updated_at=datetime.utcnow(),
        )

    async def get_market_data(self, symbol: str, timeframe: str, limit: int = 200) -> List[dict]:
        from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        tf_map = {
            "1m": TimeFrame(1, TimeFrameUnit.Minute),
            "5m": TimeFrame(5, TimeFrameUnit.Minute),
            "15m": TimeFrame(15, TimeFrameUnit.Minute),
            "1h": TimeFrame(1, TimeFrameUnit.Hour),
            "4h": TimeFrame(4, TimeFrameUnit.Hour),
            "1d": TimeFrame(1, TimeFrameUnit.Day),
        }
        alpaca_tf = tf_map.get(timeframe)
        if alpaca_tf is None:
            raise ValueError(f"Unsupported timeframe for Alpaca: {timeframe}")

        is_crypto = "/" in symbol  # Alpaca crypto symbols use BTC/USD format
        if is_crypto:
            request = CryptoBarsRequest(symbol_or_symbols=symbol, timeframe=alpaca_tf, limit=limit)
            bars = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._crypto_data_client.get_crypto_bars(request)
            )
        else:
            request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=alpaca_tf, limit=limit)
            bars = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._stock_data_client.get_stock_bars(request)
            )

        return [
            {"timestamp": b.timestamp, "open": b.open, "high": b.high,
             "low": b.low, "close": b.close, "volume": b.volume}
            for b in bars[symbol]
        ]

    async def stream_ticks(self, symbol: str) -> AsyncGenerator[Tick, None]:
        """
        Streams live trade ticks from Alpaca WebSocket.
        NOTE: Real implementation requires running an async stream in a background task.
        This skeleton yields nothing — wire up alpaca-py's streaming client in production.
        """
        self._log.warning("alpaca.stream_ticks.not_implemented", symbol=symbol)
        return
        yield   # makes this a generator

    # ── Private Mappers ────────────────────────────────────────────────────────

    def _map_position(self, raw) -> Position:
        qty = float(raw.qty)
        return Position(
            symbol=raw.symbol,
            market_type=MarketType.CRYPTO if "/" in raw.symbol else MarketType.STOCK,
            broker_id=self.broker_id.value,
            quantity=qty,
            avg_entry_price=float(raw.avg_entry_price),
            current_price=float(raw.current_price),
            unrealized_pnl=float(raw.unrealized_pl),
            unrealized_pnl_pct=float(raw.unrealized_plpc) * 100,
            opened_at=datetime.utcnow(),
        )
