import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.modules.realtime.manager import manager
from src.shared.database.session import AsyncSessionFactory
from src.shared.security.dependencies import authenticate_token

router = APIRouter(tags=["Realtime"])


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    token = websocket.headers.get("sec-websocket-protocol")
    if not token:
        await websocket.close(code=4401)
        return

    async def validate():
        async with AsyncSessionFactory() as db:
            user = await authenticate_token(token, db)
            if user.is_first_login:
                raise ValueError("Password change required")
            return user

    try:
        user = await validate()
    except Exception:
        await websocket.close(code=4401)
        return
    await manager.connect(user.enterprise_id, websocket, subprotocol=token)
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=15)
            except asyncio.TimeoutError:
                pass
            await validate()
    except WebSocketDisconnect:
        pass
    except Exception:
        await websocket.close(code=4401)
    finally:
        manager.disconnect(user.enterprise_id, websocket)
