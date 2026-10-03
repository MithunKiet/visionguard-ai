from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError

from src.modules.realtime.manager import manager
from src.shared.cache.client import get_redis
from src.shared.security.jwt import decode_token

router = APIRouter(tags=["Realtime"])


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    token = websocket.headers.get("sec-websocket-protocol")
    if not token:
        await websocket.close(code=4401)
        return

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise JWTError("not an access token")
        jti = payload.get("jti")
        if not jti:
            raise JWTError("missing jti")
        if await get_redis().exists(f"blacklist:{jti}"):
            raise JWTError("access token revoked")
    except JWTError:
        await websocket.close(code=4401)
        return

    enterprise_id = payload["enterprise_id"]
    await manager.connect(enterprise_id, websocket, subprotocol=token)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(enterprise_id, websocket)
