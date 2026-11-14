"""Operator alerts over Telegram.

Off unless TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are both set. `send_alert` never
raises: alerting is a side channel and must not be able to break the trading loop.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx
import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

# httpx logs every request URL at INFO, and the Telegram URL contains the bot token.
# Pin it to WARNING so turning on INFO logging later can't put the token in `docker logs`.
logging.getLogger("httpx").setLevel(logging.WARNING)

_TELEGRAM_API = "https://api.telegram.org"
_MAX_LEN = 3500   # Telegram caps a message at 4096 chars


async def send_alert(text: str, *, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
    token, chat_id = settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return
    try:
        async with httpx.AsyncClient(timeout=10, transport=transport) as client:
            resp = await client.post(
                f"{_TELEGRAM_API}/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": f"[ProfitPilot] {text}"[:_MAX_LEN]},
            )
            status = resp.status_code
        if status >= 400:
            logger.warning("alert.send_failed", status=status)
    except Exception as exc:
        # Log the exception TYPE only: httpx error text embeds the request URL, and the
        # URL embeds the bot token.
        logger.warning("alert.send_failed", error=type(exc).__name__)
