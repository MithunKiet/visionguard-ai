from pydantic import BaseModel, Field


class UpdateZoneConfigRequest(BaseModel):
    person_threshold: float | None = Field(None, ge=0.1, le=1.0)
    helmet_threshold: float | None = Field(None, ge=0.1, le=1.0)
    vest_threshold: float | None = Field(None, ge=0.1, le=1.0)
    gloves_threshold: float | None = Field(None, ge=0.1, le=1.0)
    shoes_threshold: float | None = Field(None, ge=0.1, le=1.0)
    mask_threshold: float | None = Field(None, ge=0.1, le=1.0)
    max_occupancy: int | None = Field(None, ge=1)
    frame_sample_fps: int | None = Field(None, ge=1, le=25)
    ppe_required: list[str] | None = None
    cooldown_seconds: int | None = Field(None, ge=0)
    required_consecutive_frames: int | None = Field(None, ge=1, le=30)
    low_confidence_floor: float | None = Field(None, ge=0.0, le=1.0)
    change_reason: str | None = None
