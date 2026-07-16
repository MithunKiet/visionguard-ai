import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError

from src.modules.realtime.manager import manager
from src.shared.security.jwt import decode_token

log = structlog.get_logger()

router = APIRouter(tags=["Realtime"])


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    # Browsers can't attach custom headers (e.g. Authorization) to a
    # WebSocket handshake, and a `?token=` query param leaks the JWT into
    # server access logs and browser history. Sec-WebSocket-Protocol isn't
    # part of the request URI, so the frontend sends the token as the
    # (single) proposed subprotocol instead — we just echo it back on accept
    # as required by the WebSocket handshake spec.
    token = websocket.headers.get("sec-websocket-protocol")
    if not token:
        await websocket.close(code=4401)
        return
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise JWTError("not an access token")
    except JWTError:
        await websocket.close(code=4401)
        return

    enterprise_id = payload["enterprise_id"]
    await manager.connect(enterprise_id, websocket, subprotocol=token)
    try:
        while True:
            # Client -> server messages aren't used yet; just keep the connection alive.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(enterprise_id, websocket)
