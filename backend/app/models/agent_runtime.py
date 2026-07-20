"""Content-free control-plane ledger for first-party Agent runs."""
from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.sql import func

from app.database import Base
from app.models.agent_audit_log import JSONColumn


class AgentRun(Base):
    __tablename__ = "agent_runs"

    run_id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(
        Integer,
        ForeignKey("agent_conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_message_id = Column(
        Integer,
        ForeignKey("agent_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    assistant_message_id = Column(
        Integer,
        ForeignKey("agent_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    client_turn_id = Column(String(112), nullable=True)
    input_seq = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    current_attempt_id = Column(String(64), nullable=False, index=True)
    retryable = Column(Boolean, nullable=False, default=False)
    origin = Column(String(32), nullable=False, default="unknown")
    origin_device_id = Column(String(128), nullable=True)
    local_execution_id = Column(String(128), nullable=True)
    privacy_mode = Column(String(32), nullable=False, default="cloud")
    deadline_at = Column(DateTime(timezone=True), nullable=True)
    cancel_requested_at = Column(DateTime(timezone=True), nullable=True)
    error_code = Column(String(80), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'waiting_for_user', 'succeeded', "
            "'failed', 'cancelled', 'reconciliation_required')",
            name="ck_agent_runs_status",
        ),
        Index(
            "uq_agent_runs_user_client_turn",
            "user_id",
            "client_turn_id",
            unique=True,
            postgresql_where=text("client_turn_id IS NOT NULL"),
            sqlite_where=text("client_turn_id IS NOT NULL"),
        ),
        Index(
            "uq_agent_runs_active_conversation",
            "conversation_id",
            unique=True,
            postgresql_where=text(
                "conversation_id IS NOT NULL AND status IN ('queued', 'running')"
            ),
            sqlite_where=text(
                "conversation_id IS NOT NULL AND status IN ('queued', 'running')"
            ),
        ),
        Index(
            "uq_agent_runs_conversation_input_seq",
            "conversation_id",
            "input_seq",
            unique=True,
            postgresql_where=text("conversation_id IS NOT NULL AND input_seq IS NOT NULL"),
            sqlite_where=text("conversation_id IS NOT NULL AND input_seq IS NOT NULL"),
        ),
        Index("ix_agent_runs_user_created", "user_id", "created_at"),
    )


class AgentRunAttempt(Base):
    __tablename__ = "agent_run_attempts"

    attempt_id = Column(String(64), primary_key=True)
    run_id = Column(
        String(64),
        ForeignKey("agent_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_no = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, default="queued", index=True)
    worker_id = Column(String(128), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    error_code = Column(String(80), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_agent_run_attempts_status",
        ),
        Index("uq_agent_run_attempt_number", "run_id", "attempt_no", unique=True),
        Index(
            "ix_agent_run_attempts_running_lease",
            "lease_expires_at",
            postgresql_where=text("status = 'running'"),
            sqlite_where=text("status = 'running'"),
        ),
    )


class AgentToolOperation(Base):
    __tablename__ = "agent_tool_operations"

    operation_id = Column(String(96), primary_key=True)
    run_id = Column(
        String(64),
        ForeignKey("agent_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_id = Column(
        String(64),
        ForeignKey("agent_run_attempts.attempt_id", ondelete="SET NULL"),
        nullable=True,
    )
    tool_name = Column(String(80), nullable=False)
    effect_class = Column(String(32), nullable=False)
    operation_fingerprint = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="requested", index=True)
    resource_type = Column(String(80), nullable=True)
    resource_id = Column(String(128), nullable=True)
    error_code = Column(String(80), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('requested', 'executing', 'succeeded', 'failed', "
            "'reconciliation_required')",
            name="ck_agent_tool_operations_status",
        ),
        Index(
            "uq_agent_tool_operations_run_fingerprint",
            "run_id",
            "operation_fingerprint",
            unique=True,
        ),
    )


class AgentRunEvent(Base):
    __tablename__ = "agent_run_events"

    id = Column(Integer, primary_key=True)
    run_id = Column(
        String(64),
        ForeignKey("agent_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_id = Column(
        String(64),
        ForeignKey("agent_run_attempts.attempt_id", ondelete="SET NULL"),
        nullable=True,
    )
    sequence_no = Column(Integer, nullable=False)
    event_name = Column(String(64), nullable=False, index=True)
    payload = Column(JSONColumn, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("uq_agent_run_events_sequence", "run_id", "sequence_no", unique=True),
        Index("ix_agent_run_events_run_created", "run_id", "created_at"),
    )
