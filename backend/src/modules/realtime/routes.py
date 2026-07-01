import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError

from src.modules.realtime.manager import manager
from src.shared.security.jwt import decode_token

log = structlog.get_logger()

router = APIRouter(tags=["Realtime"])


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket, token: str):
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise JWTError("not an access token")
    except JWTError:
        await websocket.close(code=4401)
        return

    enterprise_id = payload["enterprise_id"]
    await manager.connect(enterprise_id, websocket)
    try:
        while True:
            # Client -> server messages aren't used yet; just keep the connection alive.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(enterprise_id, websocket)
