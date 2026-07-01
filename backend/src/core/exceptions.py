import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

log = structlog.get_logger()


class VisionGuardException(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code


class NotFoundException(VisionGuardException):
    def __init__(self, entity: str, entity_id: str):
        super().__init__(
            code=f"{entity.upper()}_NOT_FOUND",
            message=f"{entity} not found: {entity_id}",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class UnauthorizedException(VisionGuardException):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(code="UNAUTHORIZED", message=message, status_code=401)


class ForbiddenException(VisionGuardException):
    def __init__(self, message: str = "Access denied"):
        super().__init__(code="FORBIDDEN", message=message, status_code=403)


def register_exception_handlers(app: FastAPI) -> None:

    @app.exception_handler(VisionGuardException)
    async def visionguard_exception_handler(
        request: Request, exc: VisionGuardException
    ) -> JSONResponse:
        log.warning("visionguard.exception", code=exc.code, message=exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": None,
                "error": {"code": exc.code, "message": exc.message, "details": {}},
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        log.error("visionguard.unhandled_error", error=str(exc), path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "data": None,
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred",
                    "details": {},
                },
            },
        )
