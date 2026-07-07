from uuid import UUID

from pydantic import BaseModel, Field


class CreateFactoryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=50)
    location: str | None = Field(None, max_length=300)
    plant_head_id: UUID | None = None


class UpdateFactoryRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    location: str | None = Field(None, max_length=300)
    plant_head_id: UUID | None = None
    status: str | None = None
