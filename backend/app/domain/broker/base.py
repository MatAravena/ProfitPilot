from __future__ import annotations
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, List, Optional
import structlog

from app.core.enums import BrokerID, MarketType
from app.core.types import Account, Fill, Order, OrderResult, Position, Tick

logger = structlog.get_logger(__name__)


class BrokerAdapter(ABC):
    """
    Abstract base for every broker integration in ProfitPilot.

    Rules:
    - Never call broker SDKs (alpaca-trade-api, pybit, etc.) from outside this class.
    - paper_mode is a flag — not a separate subclass.
    - Every adapter must implement retry + rate limiting internally.
    - Every adapter must be able to run in paper/testnet mode.
    """

    def __init__(
        self,
        broker_id: BrokerID,
        api_key: str,
        secret_key: str,
        paper_mode: bool,
        supported_markets: List[MarketType],
    ):
        self.broker_id = broker_id
        self.paper_mode = paper_mode
        self.supported_markets = supported_markets

        # Never log keys — mask them
        self._api_key = api_key
        self._secret_key = secret_key

        self._log = logger.bind(broker=broker_id.value, paper=paper_mode)

    # ── Abstract Interface ─────────────────────────────────────────────────────

    @abstractmethod
    async def place_order(self, order: Order) -> OrderResult:
        """Submit an order. Must not be called without passing through RiskManager first."""
        ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel a pending order. Returns True if successfully cancelled."""
        ...

    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """Return all current open positions."""
        ...

    @abstractmethod
    async def get_account(self) -> Account:
        """Return account equity, cash, and buying power."""
        ...

    @abstractmethod
    async def get_market_data(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 200,
    ) -> List[dict]:
        """Fetch recent OHLCV bars. Returns raw dicts — MarketDataProvider normalizes them."""
        ...

    @abstractmethod
    async def stream_ticks(self, symbol: str) -> AsyncGenerator[Tick, None]:
        """Open a live tick stream for a symbol. Yields Tick objects."""
        ...

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection / authenticate. Called on startup."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully close connections."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if broker API is reachable and authenticated."""
        ...

    # ── Concrete Helpers ───────────────────────────────────────────────────────

    def supports_market(self, market: MarketType) -> bool:
        return market in self.supported_markets

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} broker={self.broker_id.value} paper={self.paper_mode}>"


# ── Registry ────────────────────────────────────────────────────────────────────

class BrokerRegistry:
    """
    Central registry for all broker adapters.
    Strategies and services look up brokers here — never instantiate adapters directly.
    """

    _registry: Dict[BrokerID, BrokerAdapter] = {}

    @classmethod
    def register(cls, adapter: BrokerAdapter) -> None:
        cls._registry[adapter.broker_id] = adapter
        logger.info("broker.registered", broker=adapter.broker_id.value, paper=adapter.paper_mode)

    @classmethod
    def get(cls, broker_id: BrokerID) -> BrokerAdapter:
        adapter = cls._registry.get(broker_id)
        if adapter is None:
            raise KeyError(f"Broker '{broker_id.value}' not found in registry.")
        return adapter

    @classmethod
    def list_all(cls) -> List[BrokerAdapter]:
        return list(cls._registry.values())

    @classmethod
    def find_by_market(cls, market: MarketType) -> List[BrokerAdapter]:
        return [a for a in cls._registry.values() if a.supports_market(market)]
