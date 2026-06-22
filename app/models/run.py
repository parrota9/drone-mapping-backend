from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.mission import Mission
    from app.models.run_output import RunOutput


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    mission_id: Mapped[int] = mapped_column(ForeignKey("missions.id"), nullable=False)
    celery_task_id: Mapped[str] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    odm_options: Mapped[dict] = mapped_column(JSON, nullable=True)
    progress: Mapped[float] = mapped_column(nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    mission: Mapped["Mission"] = relationship("Mission", back_populates="runs")
    outputs: Mapped[list["RunOutput"]] = relationship("RunOutput", back_populates="run")
