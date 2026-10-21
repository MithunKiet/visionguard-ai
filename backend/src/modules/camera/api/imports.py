"""Camera CSV endpoints deliberately avoid reflecting credential-bearing input."""
import json

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from src.modules.camera.application import imports
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, require_roles

router = APIRouter(prefix="/cameras/import", tags=["Camera import"])
manager = require_roles("SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER")


async def read_body(request):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > imports.MAX_BYTES:
            imports.fail("Import request exceeds 512 KiB", 413)
    try:
        body = json.loads(raw)
        if not isinstance(body, dict) or not isinstance(body.get("csv_text"), str):
            raise ValueError()
    except (ValueError, UnicodeError):
        imports.fail("Expected a JSON object containing csv_text")
    return body


@router.post("/preview", response_model=ApiResponse[dict])
async def preview(request: Request, response: Response, user: AuthUser = Depends(manager), db: AsyncSession = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    body = await read_body(request)
    return ApiResponse(data=await imports.preview(db, user, body["csv_text"]))


@router.post("/commit", response_model=ApiResponse[dict])
async def commit(request: Request, response: Response, user: AuthUser = Depends(manager), db: AsyncSession = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    body = await read_body(request)
    try:
        return ApiResponse(data=await imports.commit(db, user, body["csv_text"], body.get("preview_token"), body.get("request_key")))
    except SQLAlchemyError:
        await db.rollback()
        imports.fail("Import could not be confirmed; retry with the same request key", 503)
