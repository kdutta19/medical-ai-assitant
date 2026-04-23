"""
Guardrails service — input validation, unsafe query detection, and output validation.

Pipeline position:
    POST /query
        → [INPUT GUARDRAILS]   ← this module
        → RAG retrieve
        → Claude generate
        → [OUTPUT GUARDRAILS]  ← this module
        → return QueryResponse

All checks are pure Python with no external calls, so they add <1 ms latency.
"""
import re
from dataclasses import dataclass
from enum import Enum

from app.core.logging import get_logger
from app.schemas.query import QueryType

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class GuardrailStatus(str, Enum):
    PASSED = "passed"
    BLOCKED = "blocked"
    WARNED = "warned"   # passes through but logged for review


@dataclass
class GuardrailResult:
    status: GuardrailStatus
    reason: str | None = None          # internal log reason
    safe_message: str | None = None    # user-facing message when blocked


# ---------------------------------------------------------------------------
# Fallback messages (safe, consistent, non-alarming)
# ---------------------------------------------------------------------------

_FALLBACK_OFF_TOPIC = (
    "This assistant is designed exclusively for clinical decision support. "
    "Your question does not appear to be related to medicine or healthcare. "
    "Please rephrase your question as a clinical query."
)

_FALLBACK_PII_DETECTED = (
    "Your query appears to contain personally identifiable information (e.g. a patient name or ID). "
    "Please remove all identifiers and resubmit using only de-identified clinical details "
    "(e.g. '45yo male with...')."
)

_FALLBACK_SELF_HARM = (
    "This assistant supports clinical professionals and is not able to assist with this request. "
    "If you or someone you know is in crisis, please contact emergency services (911) "
    "or a crisis helpline immediately."
)

_FALLBACK_HARMFUL_INTENT = (
    "This request cannot be processed. The assistant is intended for legitimate clinical "
    "decision support only."
)

_FALLBACK_EMPTY_ANSWER = (
    "The system was unable to generate a reliable answer for this query. "
    "Please consult current clinical guidelines or a specialist directly."
)

_FALLBACK_HALLUCINATION = (
    "The generated response did not meet quality standards and has been withheld. "
    "Please rephrase your question or consult primary clinical resources."
)


# ---------------------------------------------------------------------------
# Input guardrails
# ---------------------------------------------------------------------------

# Patterns that suggest the query is not clinical
_OFF_TOPIC_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b(weather|forecast|temperature outside)\b",
        r"\b(stock|crypto|bitcoin|invest|trading|finance)\b",
        r"\b(recipe|cooking|ingredient|bake|chef)\b",
        r"\b(movie|film|actor|actress|celebrity|music|song|lyrics)\b",
        r"\b(sport|football|basketball|soccer|nfl|nba|cricket)\b",
        r"\b(politics|election|president|congress|parliament)\b",
        r"\b(write (me |a )?(poem|story|essay|joke|rap|code))\b",
        r"\b(translate (this|to|into))\b",
        r"\bhow (to|do I) (hack|crack|bypass|cheat)\b",
    ]
]

# Patterns strongly suggesting PII in the query
_PII_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        # Full names (FirstName LastName — crude heuristic)
        r"\b([A-Z][a-z]+ [A-Z][a-z]+)\b(?=.*\b(patient|dob|mrn|ssn|born|admitted)\b)",
        # US Social Security
        r"\b\d{3}-\d{2}-\d{4}\b",
        # MRN-style identifiers
        r"\b(mrn|medical record|patient id|patient number)[:\s#]*\d+\b",
        # Date of birth
        r"\b(dob|date of birth)[:\s]*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        # US phone
        r"\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b",
        # Email address
        r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b",
    ]
]

# Patterns indicating self-harm or crisis content
_SELF_HARM_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b(suicide|suicidal|kill (myself|yourself|himself|herself))\b",
        r"\b(want to die|end my life|self[- ]harm|cut (myself|yourself))\b",
        r"\b(overdose on purpose|intentional overdose)\b",
    ]
]

# Patterns indicating harmful intent
_HARMFUL_INTENT_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b(poison|poisoning) (someone|a person|my (wife|husband|partner|patient))\b",
        r"\bhow (much|many).*(kill|lethal dose|LD50).*(human|person|someone)\b",
        # word order independent — undetectable/untraceable anywhere near poison/drug
        r"\b(undetectable|untraceable)\b.{0,60}\b(poison|drug|substance)\b",
        r"\b(poison|drug|substance)\b.{0,60}\b(undetectable|untraceable)\b",
        r"\bforging?.*(prescription|medical record)\b",
    ]
]

# Minimum ratio of alphabetic characters — filters gibberish/injection attempts
_MIN_ALPHA_RATIO = 0.5
_MIN_MEANINGFUL_WORDS = 4   # require at least 4 words for a meaningful clinical query
_MIN_AVG_WORD_LENGTH = 3    # blocks single-char and two-char word spam (e.g. "asd qwe zxc")


def validate_input(question: str, patient_context: str | None = None) -> GuardrailResult:
    """
    Run all input checks. Returns on first failure (fast-fail).
    Order: harmful intent → self-harm → PII → off-topic → gibberish
    """

    # 1. Harmful intent (highest priority — block immediately)
    for pattern in _HARMFUL_INTENT_PATTERNS:
        if pattern.search(question):
            logger.warning("Guardrail blocked: harmful intent", extra={"pattern": pattern.pattern})
            return GuardrailResult(
                status=GuardrailStatus.BLOCKED,
                reason="harmful_intent_detected",
                safe_message=_FALLBACK_HARMFUL_INTENT,
            )

    # 2. Self-harm / crisis
    for pattern in _SELF_HARM_PATTERNS:
        if pattern.search(question):
            logger.warning("Guardrail blocked: self-harm content")
            return GuardrailResult(
                status=GuardrailStatus.BLOCKED,
                reason="self_harm_content",
                safe_message=_FALLBACK_SELF_HARM,
            )

    # 3. PII in question or patient_context
    combined = question + (" " + patient_context if patient_context else "")
    for pattern in _PII_PATTERNS:
        if pattern.search(combined):
            logger.warning("Guardrail blocked: PII detected")
            return GuardrailResult(
                status=GuardrailStatus.BLOCKED,
                reason="pii_detected",
                safe_message=_FALLBACK_PII_DETECTED,
            )

    # 4. Off-topic (non-clinical)
    for pattern in _OFF_TOPIC_PATTERNS:
        if pattern.search(question):
            logger.warning("Guardrail blocked: off-topic query", extra={"pattern": pattern.pattern})
            return GuardrailResult(
                status=GuardrailStatus.BLOCKED,
                reason="off_topic",
                safe_message=_FALLBACK_OFF_TOPIC,
            )

    # 5. Gibberish / low-content input
    alpha_chars = sum(1 for c in question if c.isalpha())
    alpha_ratio = alpha_chars / max(len(question), 1)
    words = question.split()
    word_count = len(words)
    avg_word_len = sum(len(w) for w in words) / max(word_count, 1)

    if (
        alpha_ratio < _MIN_ALPHA_RATIO
        or word_count < _MIN_MEANINGFUL_WORDS
        or avg_word_len < _MIN_AVG_WORD_LENGTH
    ):
        logger.warning(
            "Guardrail blocked: low-quality input",
            extra={
                "alpha_ratio": round(alpha_ratio, 2),
                "word_count": word_count,
                "avg_word_len": round(avg_word_len, 2),
            },
        )
        return GuardrailResult(
            status=GuardrailStatus.BLOCKED,
            reason="low_quality_input",
            safe_message=_FALLBACK_OFF_TOPIC,
        )

    return GuardrailResult(status=GuardrailStatus.PASSED)


# ---------------------------------------------------------------------------
# Output guardrails
# ---------------------------------------------------------------------------

# Phrases Claude uses when it has no information — catch and replace
_UNCERTAINTY_PHRASES: list[str] = [
    "i don't know",
    "i cannot answer",
    "i'm not sure",
    "i am not sure",
    "no information available",
    "cannot find",
    "not in my knowledge",
    "i don't have access",
    "i do not have access",
    "as an ai",
    "as a language model",
]

# Patterns that suggest the model is fabricating structure with no real content
_HALLUCINATION_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        # Invented citations with made-up journal volumes
        r"\(\w+ et al\.,?\s*\d{4}[a-z]?\)",   # (Smith et al., 2024a)
        # Placeholder text that leaked into output
        r"\[insert\b",
        r"\[your\b",
        r"\bXXX\b",
        r"\bN/A\b.*\bN/A\b.*\bN/A\b",         # three or more N/A — table padding
    ]
]

_MIN_ANSWER_LENGTH = 80     # characters — anything shorter is suspiciously empty
_MAX_ANSWER_LENGTH = 12000  # characters — runaway generation safety net


def validate_output(answer: str, query_type: QueryType) -> GuardrailResult:
    """
    Validate Claude's answer before returning it to the caller.
    Check order: uncertainty → length → hallucination patterns.
    Uncertainty is checked first so a brief "I don't know" isn't
    misclassified as just a short answer.
    """
    stripped = answer.strip()
    lower = stripped.lower()

    # 1. Explicit uncertainty — model admitted it cannot answer (check before length)
    for phrase in _UNCERTAINTY_PHRASES:
        if phrase in lower:
            logger.warning(
                "Guardrail warned: uncertainty phrase detected",
                extra={"phrase": phrase},
            )
            return GuardrailResult(
                status=GuardrailStatus.WARNED,
                reason="uncertainty_phrase",
                safe_message=_FALLBACK_EMPTY_ANSWER,
            )

    # 2. Empty / too short
    if len(stripped) < _MIN_ANSWER_LENGTH:
        logger.warning(
            "Guardrail blocked: answer too short",
            extra={"length": len(stripped)},
        )
        return GuardrailResult(
            status=GuardrailStatus.BLOCKED,
            reason="answer_too_short",
            safe_message=_FALLBACK_EMPTY_ANSWER,
        )

    # 3. Too long (runaway generation)
    if len(stripped) > _MAX_ANSWER_LENGTH:
        logger.warning(
            "Guardrail warned: answer exceeds max length — truncating",
            extra={"length": len(stripped)},
        )
        truncated = _truncate_at_sentence(stripped, _MAX_ANSWER_LENGTH)
        return GuardrailResult(
            status=GuardrailStatus.WARNED,
            reason="answer_truncated",
            safe_message=truncated + "\n\n_[Response truncated for length.]_",
        )

    # 4. Hallucination signals
    for pattern in _HALLUCINATION_PATTERNS:
        if pattern.search(stripped):
            logger.warning(
                "Guardrail blocked: hallucination pattern detected",
                extra={"pattern": pattern.pattern},
            )
            return GuardrailResult(
                status=GuardrailStatus.BLOCKED,
                reason="hallucination_detected",
                safe_message=_FALLBACK_HALLUCINATION,
            )

    return GuardrailResult(status=GuardrailStatus.PASSED)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate_at_sentence(text: str, max_chars: int) -> str:
    """Truncate text to max_chars at the nearest sentence boundary."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_period = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
    return truncated[:last_period + 1] if last_period > 0 else truncated


class _GuardrailsService:
    """Thin wrapper so the service can be imported as a singleton object."""

    def check_input(self, question: str, patient_context: str | None = None) -> GuardrailResult:
        return validate_input(question, patient_context)

    def check_output(self, answer: str, query_type: QueryType) -> GuardrailResult:
        return validate_output(answer, query_type)


guardrails_service = _GuardrailsService()
