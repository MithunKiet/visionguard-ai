from pydantic import BaseModel, Field


class Roi(BaseModel):
    """Normalized to the reference frame: (0, 0) is top-left, 1 is full width/height."""
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)


class CreateSafetyAssetRequest(BaseModel):
    camera_id: str = Field(min_length=36, max_length=36)
    asset_code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    location_desc: str | None = Field(None, max_length=300)
    check_interval_seconds: int = Field(60, ge=10, le=3600)
    change_after_seconds: int = Field(300, ge=30, le=86400)
    similarity_threshold: float = Field(0.6, gt=0, lt=1)


class UpdateSafetyAssetRequest(BaseModel):
    version: int = Field(ge=1)
    name: str | None = Field(None, min_length=1, max_length=200)
    location_desc: str | None = Field(None, max_length=300)
    roi: Roi | None = None
    check_interval_seconds: int | None = Field(None, ge=10, le=3600)
    change_after_seconds: int | None = Field(None, ge=30, le=86400)
    similarity_threshold: float | None = Field(None, gt=0, lt=1)
    monitoring_enabled: bool | None = None
