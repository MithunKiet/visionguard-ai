"""Safety asset (fire extinguisher) registry and private image transfers."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.assets.api.schemas import CreateSafetyAssetRequest, UpdateSafetyAssetRequest
from src.modules.assets.application.services import MANAGE_ROLES, AssetService
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse, MetaResponse
from src.shared.security.dependencies import AuthUser, get_current_user, require_roles
from src.shared.security.resource_policy import enforce_resource_scope

router = APIRouter(dependencies=[Depends(enforce_resource_scope)], prefix="/safety-assets", tags=["Safety Assets"])


def _image(content):
    return Response(content, media_type="image/jpeg", headers={
        "Cache-Control": "no-store", "Vary": "Authorization", "X-Content-Type-Options": "nosniff"})


@router.get("", response_model=ApiResponse[list[dict]], summary="List safety assets")
async def list_assets(factory_id: str | None = None, zone_id: str | None = None, camera_id: str | None = None,
                      page: int = Query(1, ge=1, le=1000000), page_size: int = Query(50, ge=1, le=100),
                      user: AuthUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows, total = await AssetService(db, user).list(factory_id, zone_id, camera_id, page, page_size)
    return ApiResponse(data=rows, meta=MetaResponse(page=page, page_size=page_size, total=total,
                                                    total_pages=(total + page_size - 1) // page_size))


@router.post("", response_model=ApiResponse[dict], summary="Register safety asset")
async def create_asset(body: CreateSafetyAssetRequest, user: AuthUser = Depends(require_roles(*MANAGE_ROLES)),
                       db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await AssetService(db, user).create(body))


@router.get("/{asset_id}", response_model=ApiResponse[dict], summary="Get safety asset")
async def get_asset(asset_id: UUID, user: AuthUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await AssetService(db, user).get(str(asset_id)))


@router.put("/{asset_id}", response_model=ApiResponse[dict], summary="Update safety asset")
async def update_asset(asset_id: UUID, body: UpdateSafetyAssetRequest,
                       user: AuthUser = Depends(require_roles(*MANAGE_ROLES)), db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await AssetService(db, user).update(str(asset_id), body))


@router.delete("/{asset_id}", response_model=ApiResponse[None], summary="Delete safety asset")
async def delete_asset(asset_id: UUID, user: AuthUser = Depends(require_roles("SYSTEM_ADMIN", "ENTERPRISE_ADMIN")),
                       db: AsyncSession = Depends(get_db)):
    await AssetService(db, user).delete(str(asset_id))
    return ApiResponse(data=None)


@router.post("/{asset_id}/reference", response_model=ApiResponse[dict], summary="Capture reference photo from camera")
async def capture_reference(asset_id: UUID, user: AuthUser = Depends(require_roles(*MANAGE_ROLES)),
                            db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await AssetService(db, user).capture_reference(str(asset_id)))


@router.get("/{asset_id}/reference", summary="Download reference photo")
async def reference_image(asset_id: UUID, user: AuthUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return _image(await AssetService(db, user).reference_image(str(asset_id)))


@router.get("/{asset_id}/incidents", response_model=ApiResponse[list[dict]], summary="List asset incidents")
async def list_incidents(asset_id: UUID, page: int = Query(1, ge=1, le=1000000), page_size: int = Query(20, ge=1, le=100),
                         user: AuthUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows, total = await AssetService(db, user).incidents(str(asset_id), page, page_size)
    return ApiResponse(data=rows, meta=MetaResponse(page=page, page_size=page_size, total=total,
                                                    total_pages=(total + page_size - 1) // page_size))


@router.get("/{asset_id}/incidents/{incident_id}/snapshot", summary="Download incident evidence photo")
async def incident_snapshot(asset_id: UUID, incident_id: UUID, user: AuthUser = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    return _image(await AssetService(db, user).incident_snapshot(str(asset_id), str(incident_id)))
