from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import structlog

from app.core.types import EnrichedSignal, Signal

logger = structlog.get_logger(__name__)


class SentimentResult:
    def __init__(self, score: float, label: str, reasoning: Optional[str] = None):
        self.score = score          # -1.0 (very bearish) to 1.0 (very bullish)
        self.label = label          # "bullish" | "bearish" | "neutral"
        self.reasoning = reasoning


class LLMEnrichmentAdapter(ABC):
    """
    Optional enrichment layer using large language models (Claude, GPT, Ollama, etc.)

    This layer is NEVER required for a strategy to function.
    It adds context from unstructured data (news, filings, social) on top of
    the forecasting model signals.

    Rules:
    - Always Optional — wrap calls in try/except with graceful fallback
    - Never block order execution waiting for LLM response
    - Always set a timeout — LLM calls can be slow
    - Never call LLM APIs directly from a strategy — use this adapter
    """

    def __init__(self, provider_id: str, model_id: str, timeout_seconds: float = 10.0):
        self.provider_id = provider_id
        self.model_id = model_id
        self.timeout_seconds = timeout_seconds
        self._log = logger.bind(llm_provider=provider_id, llm_model=model_id)

    @abstractmethod
    async def analyze_sentiment(self, texts: List[str]) -> SentimentResult:
        """
        Analyze sentiment from a list of text inputs (news headlines, tweets, etc.)
        Returns a single aggregated sentiment score.
        """
        ...

    @abstractmethod
    async def enrich_signal(self, signal: Signal, context: str) -> EnrichedSignal:
        """
        Given a signal and unstructured context (news, events), return an
        enriched signal with LLM-added sentiment and reasoning.
        """
        ...

    @abstractmethod
    async def explain_trade(self, symbol: str, direction: str, reasoning_context: str) -> str:
        """
        Generate a plain-English explanation of why a trade is being placed.
        Used in the subscriber-facing UI — must be non-technical.
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} provider={self.provider_id} model={self.model_id}>"
