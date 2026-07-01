"""
In-process WebSocket connection manager, keyed by enterprise_id.

A single process instance is shared between the HTTP /ws/live route
(accepting connections) and the RabbitMQ consumer (broadcasting events),
since both run inside the same FastAPI/uvicorn process.
"""
import json

import structlog
from fastapi import WebSocket

log = structlog.get_logger()


class ConnectionManager:

    def __init__(self):
        self._rooms: dict[str, set[WebSocket]] = {}

    async def connect(self, enterprise_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._rooms.setdefault(enterprise_id, set()).add(ws)
        log.info("ws.connected", enterprise_id=enterprise_id, count=len(self._rooms[enterprise_id]))

    def disconnect(self, enterprise_id: str, ws: WebSocket) -> None:
        room = self._rooms.get(enterprise_id)
        if room and ws in room:
            room.discard(ws)
            if not room:
                self._rooms.pop(enterprise_id, None)

    async def broadcast(self, enterprise_id: str, message: dict) -> None:
        room = self._rooms.get(enterprise_id)
        if not room:
            return
        payload = json.dumps(message, default=str)
        dead = []
        for ws in room:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(enterprise_id, ws)


manager = ConnectionManager()
