"""Desktop client long-running job model."""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base
from app.models.agent_audit_log import JSONColumn


class DesktopJob(Base):
    __tablename__ = "desktop_jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    job_type = Column(String(50), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="queued", index=True)
    progress = Column(Integer, nullable=False, default=0)

    source_kind = Column(String(50))
    source_name = Column(String(500))
    source_hash = Column(String(128))

    request_payload = Column(JSONColumn)
    result_payload = Column(JSONColumn)
    error_message = Column(Text)
    retry_of_job_id = Column(Integer, ForeignKey("desktop_jobs.id", ondelete="SET NULL"))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_desktop_jobs_user_created", "user_id", "created_at"),
        Index("idx_desktop_jobs_user_status", "user_id", "status"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "job_type": self.job_type,
            "status": self.status,
            "progress": self.progress,
            "source_kind": self.source_kind,
            "source_name": self.source_name,
            "source_hash": self.source_hash,
            "request_payload": self.request_payload or {},
            "result_payload": self.result_payload or {},
            "error_message": self.error_message,
            "retry_of_job_id": self.retry_of_job_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
