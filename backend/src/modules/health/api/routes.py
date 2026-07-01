from fastapi import APIRouter
from src.shared.cache.client import get_redis
from src.shared.responses import ApiResponse

router = APIRouter(tags=["Health"])


@router.get("/health/live")
async def liveness():
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness():
    checks = {}
    try:
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "fail"

    all_ok = all(v == "ok" for v in checks.values())
    return ApiResponse.ok({"status": "ready" if all_ok else "degraded", "checks": checks})


@router.get("/health/status")
async def status():
    return ApiResponse.ok({
        "service": "VisionGuard AI Backend",
        "version": "1.0.0",
        "environment": "development",
    })
