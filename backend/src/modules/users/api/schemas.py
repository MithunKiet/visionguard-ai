from pydantic import BaseModel, EmailStr, Field


class InviteUserRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    roles: list[str] = Field(min_length=1)
    factory_id: str | None = None
    department_id: str | None = None
    assigned_zone_ids: list[str] | None = None


class UpdateUserRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    status: str | None = None
    roles: list[str] | None = None
    factory_id: str | None = None
    department_id: str | None = None
    assigned_zone_ids: list[str] | None = None
