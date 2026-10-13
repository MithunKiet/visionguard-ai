"""Redis fanout delivers events to authorized sockets on every API replica."""
import asyncio
import json
import uuid

from fastapi import WebSocket
import structlog

from src.shared.cache.client import get_redis

log = structlog.get_logger()
_CHANNEL = "visionguard:live"


class ConnectionManager:
    def __init__(self):
        self._rooms: dict[str, set[WebSocket]] = {}
        self._tokens: dict[WebSocket, str] = {}
        self._task = None
        self._pubsub = None

    async def start(self):
        redis = await get_redis()
        self._pubsub = redis.pubsub()
        await self._pubsub.subscribe(_CHANNEL)
        self._task = asyncio.create_task(self._listen())

    async def stop(self):
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        if self._pubsub:
            await self._pubsub.aclose()

    async def _listen(self):
        while True:
            try:
                async for item in self._pubsub.listen():
                    if item["type"] == "message":
                        event = json.loads(item["data"])
                        await self._deliver(event["enterprise_id"], event["message"])
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("ws.fanout_failed")
                await asyncio.sleep(1)

    async def connect(self, enterprise_id: str, ws: WebSocket, subprotocol: str | None = None):
        await ws.accept(subprotocol=subprotocol)
        self._rooms.setdefault(enterprise_id, set()).add(ws)
        self._tokens[ws] = subprotocol or ""

    def disconnect(self, enterprise_id: str, ws: WebSocket):
        room = self._rooms.get(enterprise_id)
        if room:
            room.discard(ws)
            if not room:
                self._rooms.pop(enterprise_id, None)
        self._tokens.pop(ws, None)

    async def broadcast(self, enterprise_id: str, message: dict):
        redis = await get_redis()
        await redis.publish(_CHANNEL, json.dumps({"enterprise_id": enterprise_id,
            "message": {**message, "event_id": str(uuid.uuid4())}}, default=str))

    async def _deliver(self, enterprise_id: str, message: dict):
        from src.shared.database.session import AsyncSessionFactory
        from src.shared.security.dependencies import authenticate_token
        from src.shared.security.resource_policy import require_reference
        from src.shared.security.scope import get_scope
        from src.shared.database.models import Camera, Zone
        from src.core.exceptions import UnauthorizedException, NotFoundException

        for ws in tuple(self._rooms.get(enterprise_id, ())):
            try:
                async with AsyncSessionFactory() as db:
                    user = await authenticate_token(self._tokens.get(ws, ""), db)
                    if user.is_first_login or user.enterprise_id != enterprise_id:
                        raise UnauthorizedException("Session unavailable")
                    data = message.get("data", {})
                    if data.get("camera_id"):
                        await require_reference(db, Camera, data["camera_id"], user)
                    elif data.get("zone_id"):
                        await require_reference(db, Zone, data["zone_id"], user)
                    elif not get_scope(user).unrestricted:
                        continue
                await asyncio.wait_for(ws.send_text(json.dumps(message, default=str)), timeout=5)
            except NotFoundException:
                continue
            except Exception:
                self.disconnect(enterprise_id, ws)
                try:
                    await ws.close(code=4401)
                except Exception:
                    pass


manager = ConnectionManager()
