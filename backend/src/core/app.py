from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.lifespan import lifespan
from src.core.exceptions import register_exception_handlers
from src.shared.responses import ErrorResponse
from src.core.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="VisionGuard AI",
        description="Enterprise Factory Safety Monitoring & Compliance Platform",
        version="1.0.0",
        docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    # Register routers
    _register_routers(app)

    return app


def _register_routers(app: FastAPI) -> None:
    from src.modules.health.api.routes import router as health_router
    app.include_router(health_router)

    # Phase 1
    from src.modules.identity.api.routes import router as identity_router
    from src.modules.camera.api.routes import router as camera_router
    from src.modules.worker.api.routes import router as worker_router
    from src.modules.ppe.api.routes import router as ppe_router
    from src.modules.alerts.api.routes import router as alerts_router

    app.include_router(identity_router, prefix="/api/v1")
    app.include_router(camera_router, prefix="/api/v1")
    app.include_router(worker_router, prefix="/api/v1")
    app.include_router(ppe_router, prefix="/api/v1")
    app.include_router(alerts_router, prefix="/api/v1")
