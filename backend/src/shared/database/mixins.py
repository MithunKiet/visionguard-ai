import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, Boolean, Integer, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID


class AuditMixin:
    created_on = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    modified_on = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    modified_by = Column(UUID(as_uuid=True), nullable=True)
    version = Column(Integer, default=1, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    enterprise_id = Column(UUID(as_uuid=True), nullable=False, index=True)
