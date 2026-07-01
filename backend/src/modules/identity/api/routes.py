from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.api.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RefreshedTokenResponse,
    RemoveMasterPasswordRequest,
    SetMasterPasswordRequest,
    TokenResponse,
)
from src.modules.identity.application.services import AuthService
from src.shared.database.session import get_db
from src.shared.responses import ApiResponse
from src.shared.security.dependencies import AuthUser, get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])

_REFRESH_COOKIE = "refresh_token"
_COOKIE_MAX_AGE = 7 * 24 * 3600  # 7 days in seconds


def _get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(db)


@router.post("/login", response_model=ApiResponse[TokenResponse], summary="Login")
async def login(
    body: LoginRequest,
    response: Response,
    svc: AuthService = Depends(_get_auth_service),
):
    result = await svc.login(body.email, body.password)
    # Also set refresh token as HttpOnly cookie for browser clients
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=result["refresh_token"],
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=_COOKIE_MAX_AGE,
        path="/api/v1/auth",
    )
    return ApiResponse(data=result)


@router.post(
    "/refresh",
    response_model=ApiResponse[RefreshedTokenResponse],
    summary="Refresh access token",
)
async def refresh(
    response: Response,
    body: RefreshRequest | None = None,
    refresh_token_cookie: Annotated[str | None, Cookie(alias=_REFRESH_COOKIE)] = None,
    svc: AuthService = Depends(_get_auth_service),
):
    # Accept token from either JSON body or cookie
    token = (body.refresh_token if body else None) or refresh_token_cookie
    if not token:
        from src.core.exceptions import UnauthorizedException
        raise UnauthorizedException("No refresh token provided")

    result = await svc.refresh(token)
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=result["refresh_token"],
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=_COOKIE_MAX_AGE,
        path="/api/v1/auth",
    )
    return ApiResponse(data=result)


@router.post("/logout", response_model=ApiResponse[None], summary="Logout")
async def logout(
    response: Response,
    body: LogoutRequest | None = None,
    refresh_token_cookie: Annotated[str | None, Cookie(alias=_REFRESH_COOKIE)] = None,
    current_user=Depends(get_current_user),
    svc: AuthService = Depends(_get_auth_service),
):
    refresh_token = (body.refresh_token if body else None) or refresh_token_cookie
    await svc.logout(current_user.jti, refresh_token)
    response.delete_cookie(_REFRESH_COOKIE, path="/api/v1/auth")
    return ApiResponse(data=None)


@router.post(
    "/change-password",
    response_model=ApiResponse[None],
    summary="Change own password",
)
async def change_password(
    body: ChangePasswordRequest,
    current_user=Depends(get_current_user),
    svc: AuthService = Depends(_get_auth_service),
):
    from uuid import UUID
    await svc.change_password(
        UUID(current_user.user_id),
        body.current_password,
        body.new_password,
    )
    return ApiResponse(data=None)


@router.get("/me", response_model=ApiResponse[dict], summary="Current user info")
async def me(current_user: AuthUser = Depends(get_current_user)):
    return ApiResponse(data={
        "user_id": current_user.user_id,
        "enterprise_id": current_user.enterprise_id,
        "role": current_user.role,
        "email": current_user.email,
    })


# ── Master password ─────────────────────────────────────────────────────────

@router.post(
    "/master-password",
    response_model=ApiResponse[None],
    summary="Set or update master password",
    description=(
        "Set a secondary password for use on untrusted devices. "
        "Master-password sessions expire in 2 hours instead of 8. "
        "Requires your normal password to confirm identity."
    ),
)
async def set_master_password(
    body: SetMasterPasswordRequest,
    current_user: AuthUser = Depends(get_current_user),
    svc: AuthService = Depends(_get_auth_service),
):
    from uuid import UUID
    await svc.set_master_password(
        UUID(current_user.user_id),
        body.current_password,
        body.master_password,
    )
    return ApiResponse(data=None)


@router.delete(
    "/master-password",
    response_model=ApiResponse[None],
    summary="Remove master password",
)
async def remove_master_password(
    body: RemoveMasterPasswordRequest,
    current_user: AuthUser = Depends(get_current_user),
    svc: AuthService = Depends(_get_auth_service),
):
    from uuid import UUID
    await svc.remove_master_password(UUID(current_user.user_id), body.current_password)
    return ApiResponse(data=None)


@router.get(
    "/master-password/status",
    response_model=ApiResponse[dict],
    summary="Check if master password is set",
)
async def master_password_status(
    current_user: AuthUser = Depends(get_current_user),
    svc: AuthService = Depends(_get_auth_service),
):
    from uuid import UUID
    from src.modules.identity.infrastructure.repositories import UserRepository
    from src.shared.database.session import get_db
    # Re-use the db from svc
    user = await svc._users.get_by_id(UUID(current_user.user_id))
    return ApiResponse(data={
        "master_password_set": user.master_password_hash is not None if user else False
    })
