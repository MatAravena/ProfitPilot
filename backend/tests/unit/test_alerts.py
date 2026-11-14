"""Telegram alerting: off unless configured, and never able to break the caller."""
from __future__ import annotations

import json
import logging

import httpx
import pytest

from app.services import alerts

pytestmark = pytest.mark.asyncio


def _configure(monkeypatch, token="123:ABC", chat="42"):
    monkeypatch.setattr(alerts.settings, "TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setattr(alerts.settings, "TELEGRAM_CHAT_ID", chat)


async def test_not_configured_sends_nothing(monkeypatch):
    _configure(monkeypatch, token="", chat="")
    calls = []
    transport = httpx.MockTransport(lambda req: calls.append(req) or httpx.Response(200))

    await alerts.send_alert("hello", transport=transport)

    assert calls == []


async def test_configured_posts_message_to_the_chat(monkeypatch):
    _configure(monkeypatch)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True})

    await alerts.send_alert("strategy halted", transport=httpx.MockTransport(handler))

    assert len(calls) == 1
    assert str(calls[0].url) == "https://api.telegram.org/bot123:ABC/sendMessage"
    body = json.loads(calls[0].content)
    assert body["chat_id"] == "42"
    assert "strategy halted" in body["text"]


async def test_telegram_failure_is_swallowed_and_token_not_logged(monkeypatch, capsys, caplog):
    _configure(monkeypatch, token="SECRET-TOKEN")

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    # INFO on the root logger: httpx logs every request URL at INFO, and the URL holds the token.
    with caplog.at_level(logging.INFO):
        await alerts.send_alert("x", transport=httpx.MockTransport(boom))   # must not raise
        await alerts.send_alert("x", transport=httpx.MockTransport(lambda r: httpx.Response(500)))
        await alerts.send_alert("x", transport=httpx.MockTransport(lambda r: httpx.Response(200)))

    out = capsys.readouterr()
    assert "SECRET-TOKEN" not in out.out + out.err + caplog.text
