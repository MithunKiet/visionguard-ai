from datetime import timedelta
from typing import Literal

from pydantic import AwareDatetime, BaseModel, model_validator


class GenerateReportRequest(BaseModel):
    report_type: Literal["violations_summary", "alerts_summary"]
    format: Literal["pdf", "xlsx"]
    from_date: AwareDatetime
    to_date: AwareDatetime

    @model_validator(mode="after")
    def validate_period(self):
        if self.to_date < self.from_date or self.to_date - self.from_date > timedelta(days=366):
            raise ValueError("Choose an ordered date range of at most 366 days")
        return self
