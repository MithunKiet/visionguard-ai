from uuid import UUID

from pydantic import BaseModel, Field


class CreateDepartmentRequest(BaseModel):
    factory_id: UUID
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=50)
    head_user_id: UUID | None = None


class UpdateDepartmentRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    head_user_id: UUID | None = None
    status: str | None = None
