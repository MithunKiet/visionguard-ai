from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.lifespan import lifespan
from src.core.exceptions import register_exception_handlers
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
    from src.modules.realtime.routes import router as realtime_router
    from src.modules.notifications.api.routes import router as notifications_router
    from src.modules.occupancy.api.routes import router as occupancy_router
    from src.modules.zone.api.routes import router as zone_router

    app.include_router(identity_router, prefix="/api/v1")
    app.include_router(camera_router, prefix="/api/v1")
    app.include_router(worker_router, prefix="/api/v1")
    app.include_router(ppe_router, prefix="/api/v1")
    app.include_router(alerts_router, prefix="/api/v1")
    app.include_router(realtime_router, prefix="/api/v1")
    app.include_router(notifications_router, prefix="/api/v1")
    app.include_router(occupancy_router, prefix="/api/v1")
    app.include_router(zone_router, prefix="/api/v1")

    # Phase 2 — Operations
    from src.modules.config.api.routes import router as config_router
    from src.modules.audit.api.routes import router as audit_router
    from src.modules.shifts.api.routes import router as shifts_router
    from src.modules.maintenance.api.routes import router as maintenance_router

    app.include_router(config_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(shifts_router, prefix="/api/v1")
    app.include_router(maintenance_router, prefix="/api/v1")

    # Phase 3 — Enterprise
    from src.modules.analytics.api.routes import router as analytics_router
    from src.modules.reports.api.routes import router as reports_router
    from src.modules.enterprise.api.routes import router as enterprise_router
    from src.modules.onboarding.api.routes import router as onboarding_router

    app.include_router(analytics_router, prefix="/api/v1")
    app.include_router(reports_router, prefix="/api/v1")
    app.include_router(enterprise_router, prefix="/api/v1")
    app.include_router(onboarding_router, prefix="/api/v1")
