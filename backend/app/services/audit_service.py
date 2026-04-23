"""
Audit service — persists every query and its outcome to PostgreSQL.

Designed to never raise into the request path: if the DB write fails,
the error is logged and swallowed so the user still receives their answer.
"""
from datetime import datetime, timezone

from app.db.session import db_session
from app.models.query_log import QueryLog
from app.schemas.query import QueryRequest, QueryResponse
from app.core.logging import get_logger

logger = get_logger(__name__)


def log_query(
    request: QueryRequest,
    response: QueryResponse,
    latency_ms: int,
    input_blocked: bool = False,
    output_blocked: bool = False,
    blocked_reason: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> None:
    """
    Write one QueryLog row. Safe to call fire-and-forget — swallows DB errors.
    Called after the response is assembled so latency_ms is accurate.
    """
    try:
        sources_data = [
            {"title": s.title, "reference": s.reference}
            for s in response.sources
        ]

        record = QueryLog(
            conversation_id=response.conversation_id,
            question=request.question,
            query_type=request.query_type.value,
            has_patient_ctx=request.patient_context is not None,
            input_blocked=input_blocked,
            output_blocked=output_blocked,
            blocked_reason=blocked_reason,
            answer=response.answer,
            sources=sources_data,
            confidence=response.confidence,
            context_used=response.context_used,
            model=response.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            created_at=datetime.now(timezone.utc),
        )

        with db_session() as db:
            db.add(record)

        logger.info(
            "Audit log written",
            extra={
                "conversation_id": response.conversation_id,
                "query_type": request.query_type.value,
                "latency_ms": latency_ms,
                "input_blocked": input_blocked,
                "output_blocked": output_blocked,
                "confidence": response.confidence,
            },
        )

    except Exception as e:
        # Never let audit failures surface to the caller
        logger.error(
            "Audit log write failed",
            extra={"conversation_id": response.conversation_id, "error": str(e)},
        )
