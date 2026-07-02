from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class GenerateReportRequest(BaseModel):
    report_type: Literal["violations_summary", "alerts_summary"]
    format: Literal["pdf", "xlsx"]
    from_date: datetime
    to_date: datetime
