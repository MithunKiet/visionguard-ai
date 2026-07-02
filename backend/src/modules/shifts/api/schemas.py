from datetime import time
from uuid import UUID

from pydantic import BaseModel, Field

_VALID_DAYS = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}


class CreateShiftRequest(BaseModel):
    factory_id: UUID
    name: str = Field(min_length=1, max_length=100)
    start_time: time
    end_time: time
    days: list[str] = ["MON", "TUE", "WED", "THU", "FRI"]

    def validated_days(self) -> list[str]:
        return [d for d in self.days if d.upper() in _VALID_DAYS]


class UpdateShiftRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    start_time: time | None = None
    end_time: time | None = None
    days: list[str] | None = None
    status: str | None = None
