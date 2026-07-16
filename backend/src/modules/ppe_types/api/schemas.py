from pydantic import BaseModel, Field


class CreatePpeTypeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class UpdatePpeTypeRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    is_active: bool | None = None
