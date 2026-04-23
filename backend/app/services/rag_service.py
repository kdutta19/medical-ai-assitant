"""
RAG orchestration service.

Pipeline per request:
  1. retrieve()       — embed query → FAISS search → filter by score threshold
  2. format_context() — build the context string for the Claude prompt
  3. claude_service.answer() — call Claude with context + question
  4. _extract_sources()      — map retrieved chunks to Source schema objects
  5. _compute_confidence()   — mean retrieval score → normalised 0-1 float

This is the single entry point called by the /query route.
"""
import uuid
import time
import statistics
from pathlib import Path

from app.services.claude_service import claude_service, MODEL
from app.services.guardrails_service import guardrails_service, GuardrailStatus
from app.services.audit_service import log_query
from app.rag.retriever import retrieve, format_context, DEFAULT_INDEX_DIR
from app.schemas.query import QueryRequest, QueryResponse, QueryType, Source
from app.core.logging import get_logger

logger = get_logger(__name__)

# Retrieval hyper-parameters
TOP_K = 6
SCORE_THRESHOLD = 0.30


class RAGService:
    def query(self, request: QueryRequest, index_dir: Path = DEFAULT_INDEX_DIR) -> QueryResponse:
        conversation_id = request.conversation_id or str(uuid.uuid4())

        logger.info(
            "RAG query started",
            extra={
                "conversation_id": conversation_id,
                "query_type": request.query_type.value,
                "question_preview": request.question[:80],
            },
        )

        t_start = time.monotonic()

        # ── 0. Input guardrails ────────────────────────────────────────
        input_check = guardrails_service.check_input(request.question, request.patient_context)
        if input_check.status == GuardrailStatus.BLOCKED:
            logger.warning(
                "Input guardrail blocked request",
                extra={"conversation_id": conversation_id, "reason": input_check.reason},
            )
            response = QueryResponse(
                answer=input_check.safe_message,
                query_type=request.query_type,
                conversation_id=conversation_id,
                model="guardrails-v1",
                confidence=0.0,
                context_used=False,
            )
            log_query(
                request=request,
                response=response,
                latency_ms=int((time.monotonic() - t_start) * 1000),
                input_blocked=True,
                blocked_reason=input_check.reason,
            )
            return response

        # ── 1. Retrieve ────────────────────────────────────────────────
        chunks = retrieve(
            query=request.question,
            top_k=TOP_K,
            score_threshold=SCORE_THRESHOLD,
            index_dir=index_dir,
        )

        # ── 2. Format context ──────────────────────────────────────────
        rag_context = format_context(chunks)
        context_used = len(chunks) > 0

        # ── 3. Generate answer via Claude ──────────────────────────────
        answer_text, usage = claude_service.answer(
            question=request.question,
            query_type=request.query_type,
            rag_context=rag_context,
            patient_context=request.patient_context,
        )

        # ── 4. Output guardrails ───────────────────────────────────────
        output_check = guardrails_service.check_output(answer_text, request.query_type)
        if output_check.status == GuardrailStatus.BLOCKED:
            logger.warning(
                "Output guardrail blocked response",
                extra={"conversation_id": conversation_id, "reason": output_check.reason},
            )
            response = QueryResponse(
                answer=output_check.safe_message,
                query_type=request.query_type,
                conversation_id=conversation_id,
                model=MODEL,
                confidence=0.0,
                context_used=context_used,
            )
            log_query(
                request=request,
                response=response,
                latency_ms=int((time.monotonic() - t_start) * 1000),
                output_blocked=True,
                blocked_reason=output_check.reason,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
            )
            return response
        if output_check.status == GuardrailStatus.WARNED and output_check.safe_message:
            answer_text = output_check.safe_message

        # ── 5. Build sources ───────────────────────────────────────────
        sources = _extract_sources(chunks)

        # ── 6. Compute confidence ──────────────────────────────────────
        confidence = _compute_confidence(chunks)

        latency_ms = int((time.monotonic() - t_start) * 1000)

        logger.info(
            "RAG query complete",
            extra={
                "conversation_id": conversation_id,
                "chunks_used": len(chunks),
                "confidence": round(confidence, 3),
                "context_used": context_used,
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
                "latency_ms": latency_ms,
            },
        )

        response = QueryResponse(
            answer=answer_text,
            query_type=request.query_type,
            conversation_id=conversation_id,
            model=MODEL,
            sources=sources,
            confidence=round(confidence, 3),
            context_used=context_used,
        )

        # ── 7. Audit log ───────────────────────────────────────────────
        log_query(
            request=request,
            response=response,
            latency_ms=latency_ms,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
        )

        return response


def _extract_sources(chunks: list[dict]) -> list[Source]:
    """
    Deduplicate chunks by source filename and return one Source per unique file.
    Ordered by best score descending.
    """
    seen: dict[str, float] = {}
    for chunk in chunks:
        src = chunk["source"]
        score = chunk["score"]
        if src not in seen or score > seen[src]:
            seen[src] = score

    # Sort by score descending, return as Source objects
    return [
        Source(title=src, reference=f"Internal reference — {src}")
        for src, _ in sorted(seen.items(), key=lambda x: x[1], reverse=True)
    ]


def _compute_confidence(chunks: list[dict]) -> float:
    """
    Mean cosine similarity score across retrieved chunks.
    Returns 0.0 when no chunks pass the threshold.
    Scores are already in [0, 1] because embeddings are L2-normalised.
    """
    if not chunks:
        return 0.0
    return statistics.mean(c["score"] for c in chunks)


# Singleton
rag_service = RAGService()
