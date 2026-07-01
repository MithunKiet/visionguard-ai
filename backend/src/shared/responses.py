from typing import Any, Optional, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class MetaResponse(BaseModel):
    page: int = 1
    page_size: int = 20
    total: int = 0
    total_pages: int = 0


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = {}


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: Optional[T] = None
    meta: Optional[MetaResponse] = None
    error: Optional[ErrorDetail] = None

    @classmethod
    def ok(cls, data: Any, meta: MetaResponse | None = None) -> "ApiResponse":
        return cls(success=True, data=data, meta=meta)

    @classmethod
    def fail(cls, code: str, message: str) -> "ApiResponse":
        return cls(success=False, error=ErrorDetail(code=code, message=message))


ErrorResponse = ApiResponse
