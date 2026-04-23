"""
SQLAlchemy ORM model for query audit logs.

Every request that reaches the /query endpoint — whether answered,
guardrail-blocked, or errored — is persisted here for:
  - Clinical audit trail (healthcare compliance)
  - Performance monitoring (confidence, latency, token usage)
  - Guardrail effectiveness analysis (blocked_reason distribution)
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, Boolean, Integer,
    DateTime, Text, JSON, Index,
)
from app.db.session import Base


class QueryLog(Base):
    __tablename__ = "query_logs"

    # ── Identity ───────────────────────────────────────────────────────
    id               = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id  = Column(String(36), nullable=False, index=True)

    # ── Request ────────────────────────────────────────────────────────
    question         = Column(Text, nullable=False)
    query_type       = Column(String(50), nullable=False)
    # patient_context is intentionally NOT stored — may contain PHI
    # even after de-identification attempts; log only its presence.
    has_patient_ctx  = Column(Boolean, default=False, nullable=False)

    # ── Guardrails ─────────────────────────────────────────────────────
    input_blocked    = Column(Boolean, default=False, nullable=False)
    output_blocked   = Column(Boolean, default=False, nullable=False)
    blocked_reason   = Column(String(100), nullable=True)  # e.g. "pii_detected"

    # ── Response ───────────────────────────────────────────────────────
    answer           = Column(Text, nullable=True)
    sources          = Column(JSON, nullable=True)   # list[{"title": ..., "reference": ...}]
    confidence       = Column(Float, nullable=True)
    context_used     = Column(Boolean, default=False, nullable=False)
    model            = Column(String(60), nullable=True)

    # ── Token usage ────────────────────────────────────────────────────
    input_tokens     = Column(Integer, nullable=True)
    output_tokens    = Column(Integer, nullable=True)

    # ── Latency ────────────────────────────────────────────────────────
    latency_ms       = Column(Integer, nullable=True)   # wall-clock ms for full pipeline

    # ── Timestamp ──────────────────────────────────────────────────────
    created_at       = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    # ── Indexes for common query patterns ─────────────────────────────
    __table_args__ = (
        Index("ix_query_logs_created_at_query_type", "created_at", "query_type"),
        Index("ix_query_logs_blocked", "input_blocked", "output_blocked"),
    )

    def __repr__(self) -> str:
        return (
            f"<QueryLog id={self.id} conv={self.conversation_id[:8]} "
            f"type={self.query_type} conf={self.confidence} "
            f"blocked_in={self.input_blocked} blocked_out={self.output_blocked}>"
        )
