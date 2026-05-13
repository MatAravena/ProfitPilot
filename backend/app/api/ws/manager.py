from __future__ import annotations
import asyncio
import json
from typing import Any

import structlog
from starlette.websockets import WebSocket, WebSocketState

logger = structlog.get_logger(__name__)


class ConnectionManager:
    """
    Manages active WebSocket connections and channel subscriptions.
    Thread-safe for use in a single asyncio event loop.
    """

    def __init__(self):
        # client_id → WebSocket
        self._connections: dict[str, WebSocket] = {}
        # channel → set of client_ids
        self._subscriptions: dict[str, set[str]] = {}

    async def connect(self, ws: WebSocket, client_id: str) -> None:
        await ws.accept()
        self._connections[client_id] = ws
        logger.info("ws.client_connected", client_id=client_id, total=len(self._connections))

    def disconnect(self, client_id: str) -> None:
        self._connections.pop(client_id, None)
        for subs in self._subscriptions.values():
            subs.discard(client_id)
        logger.info("ws.client_disconnected", client_id=client_id, total=len(self._connections))

    def subscribe(self, client_id: str, channel: str) -> None:
        self._subscriptions.setdefault(channel, set()).add(client_id)

    def unsubscribe(self, client_id: str, channel: str) -> None:
        self._subscriptions.get(channel, set()).discard(client_id)

    async def send(self, client_id: str, channel: str, data: Any) -> None:
        ws = self._connections.get(client_id)
        if ws and ws.client_state == WebSocketState.CONNECTED:
            try:
                await ws.send_text(json.dumps({"channel": channel, "data": data}))
            except Exception as exc:
                logger.warning("ws.send_failed", client_id=client_id, error=str(exc))
                self.disconnect(client_id)

    async def broadcast(self, channel: str, data: Any) -> None:
        subscribers = list(self._subscriptions.get(channel, set()))
        if not subscribers:
            return
        payload = json.dumps({"channel": channel, "data": data})
        dead: list[str] = []
        for client_id in subscribers:
            ws = self._connections.get(client_id)
            if ws and ws.client_state == WebSocketState.CONNECTED:
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append(client_id)
            else:
                dead.append(client_id)
        for d in dead:
            self.disconnect(d)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


# Singleton — imported everywhere
manager = ConnectionManager()
