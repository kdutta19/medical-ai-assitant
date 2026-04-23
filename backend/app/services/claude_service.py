"""
Claude API client and prompt templates for the Clinical AI Assistant.

Responsibilities:
- Own the Anthropic client lifecycle
- Define system prompt and per-query-type prompt templates
- Accept pre-retrieved RAG context and inject it into the user turn
- Return raw text + token usage; leave business logic to rag_service.py
"""
import anthropic
from app.config import settings
from app.core.logging import get_logger
from app.schemas.query import QueryType

logger = get_logger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a Clinical AI Assistant supporting licensed healthcare professionals.

STRICT RULES — follow these without exception:
1. Base every answer exclusively on the Retrieved Clinical Context provided in the user message, \
combined with established medical knowledge. Never fabricate citations, drug names, dosages, or statistics.
2. If the retrieved context does not contain enough information to answer confidently, \
explicitly state: "The available reference material does not fully address this question. \
Please consult primary clinical resources."
3. Never provide a definitive diagnosis. Support differential reasoning only.
4. Always flag safety-critical information (contraindications, black-box warnings, \
drug interactions, emergency thresholds) with a ⚠ prefix.
5. Never reproduce personally identifiable patient information, even if present in the query.
6. End every response with a one-line disclaimer: \
"[Clinical decision support only — verify with current guidelines before acting.]"

RESPONSE FORMAT:
- Use clear markdown: headers, bullet points, and bold for critical values.
- For drug queries: cover mechanism, dosing, contraindications, and monitoring in that order.
- For differential diagnosis: list conditions ranked by likelihood, with key distinguishing features.
- Keep answers focused. Do not pad with generic advice that adds no clinical value.
"""

# ---------------------------------------------------------------------------
# Per-query-type prompt templates
# ---------------------------------------------------------------------------

_QUERY_TYPE_INSTRUCTIONS: dict[QueryType, str] = {
    QueryType.differential_diagnosis: (
        "Generate a ranked differential diagnosis. For each condition include: "
        "likelihood reasoning, key supporting/opposing features, and recommended next investigations."
    ),
    QueryType.drug_reference: (
        "Provide a structured drug reference covering: drug class, mechanism of action, "
        "indications, dosing (including renal/hepatic adjustments), contraindications, "
        "adverse effects, and monitoring parameters."
    ),
    QueryType.lab_interpretation: (
        "Interpret the lab value(s) in clinical context. Cover: normal range, significance of the "
        "reported value, likely causes, and recommended follow-up or workup."
    ),
    QueryType.clinical_guideline: (
        "Summarise the relevant clinical guideline. Cover: diagnostic criteria or thresholds, "
        "first-line management, escalation steps, and target outcomes. Cite the guideline name and year."
    ),
    QueryType.literature_summary: (
        "Summarise the current evidence base. Cover: key RCTs or systematic reviews, "
        "level of evidence, consensus vs. controversy, and practical clinical implications."
    ),
    QueryType.general: (
        "Answer the clinical question clearly and concisely, citing relevant guidelines or "
        "evidence where available."
    ),
}

# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ClaudeService:
    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def answer(
        self,
        question: str,
        query_type: QueryType,
        rag_context: str,
        patient_context: str | None = None,
    ) -> tuple[str, dict]:
        """
        Call Claude and return (answer_text, usage_dict).

        rag_context  — pre-formatted string from retriever.format_context()
        usage_dict   — {"input_tokens": int, "output_tokens": int}
        """
        user_message = _build_user_message(
            question=question,
            query_type=query_type,
            rag_context=rag_context,
            patient_context=patient_context,
        )

        logger.info(
            "Calling Claude",
            extra={
                "model": MODEL,
                "query_type": query_type.value,
                "context_chars": len(rag_context),
                "has_patient_context": patient_context is not None,
            },
        )

        response = self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        answer_text = response.content[0].text
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }

        logger.info("Claude response received", extra=usage)
        return answer_text, usage


def _build_user_message(
    question: str,
    query_type: QueryType,
    rag_context: str,
    patient_context: str | None,
) -> str:
    """Assemble the full user turn injected into Claude."""
    parts: list[str] = []

    # 1. Task instruction scoped to query type
    parts.append(f"## Task\n{_QUERY_TYPE_INSTRUCTIONS[query_type]}")

    # 2. RAG context block (may be empty string if no chunks passed threshold)
    if rag_context:
        parts.append(rag_context)
    else:
        parts.append(
            "### Retrieved Clinical Context\n"
            "_No relevant context found in the reference database. "
            "Answer from general medical knowledge and flag uncertainty explicitly._"
        )

    # 3. Optional de-identified patient context
    if patient_context:
        parts.append(f"### Patient Context (de-identified)\n{patient_context}")

    # 4. The question itself
    parts.append(f"### Question\n{question}")

    return "\n\n".join(parts)


# Singleton — one Anthropic client for the process
claude_service = ClaudeService()
