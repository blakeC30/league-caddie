"""
DeletedLeague — audit snapshot created when a league is permanently deleted.

No FK constraints on this table by design: it must survive independent of any
other table so financial records (LeaguePurchase / LeaguePurchaseEvent) can
reference it even after all operational data is gone.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DeletedLeague(Base):
    """Immutable audit record of a deleted league. Written once; never updated."""

    __tablename__ = "deleted_leagues"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )  # Same UUID as the original League row
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )  # Plain UUID — no FK; user may be deleted later
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )  # Plain UUID — no FK
