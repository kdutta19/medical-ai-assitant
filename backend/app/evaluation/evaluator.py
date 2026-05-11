"""
Evaluation orchestrator.

Per-case pipeline
-----------------
  1. Run the full RAG pipeline (retrieve → Claude answer)
  2. Compute keyword metrics (deterministic, no API call)
  3. Call Claude-as-judge for correctness, completeness, groundedness scores
  4. Aggregate results into an EvalResult

Claude-as-judge
---------------
  A separate Claude call scores each answer on three dimensions (1-5):
    correctness   — factual accuracy vs. the reference
    completeness  — coverage of clinically relevant points
    groundedness  — answer stays within retrieved context, no hallucination

  The judge returns a JSON object which is parsed into structured scores.
  A separate system prompt ensures the judge is strict and consistent.
"""
import json
import time
from dataclasses import dataclass, field

import anthropic

from app.config import settings
from app.evaluation.dataset import EvalCase, EVAL_DATASET
from app.evaluation.metrics import KeywordMetrics, compute_keyword_metrics
from app.services.rag_service import rag_service
from app.schemas.query import QueryRequest
from app.core.logging import get_logger

logger = get_logger(__name__)

JUDGE_MODEL = "claude-sonnet-4-6"

JUDGE_SYSTEM_PROMPT = """\
You are a strict clinical AI evaluator assessing the quality of answers produced by a clinical decision support system.

Score each answer on three dimensions using a 1–5 integer scale:

CORRECTNESS (1–5)
  5 = All clinical facts are accurate, consistent with evidence-based guidelines.
  4 = Mostly accurate with minor omissions.
  3 = Partially correct; some important inaccuracies present.
  2 = Several factual errors that could mislead clinical decisions.
  1 = Fundamentally incorrect or dangerous advice.

COMPLETENESS (1–5)
  5 = All clinically relevant aspects of the question are addressed.
  4 = Most relevant points covered; minor gaps.
  3 = Key points present but important aspects missing.
  2 = Significant gaps; incomplete for practical use.
  1 = Fails to address the core question.

GROUNDEDNESS (1–5)
  5 = Answer is fully grounded in the provided context; no unsupported claims.
  4 = Mostly grounded; minor extrapolations that are clinically reasonable.
  3 = Some claims go beyond the provided context without acknowledgement.
  2 = Several unsupported or speculative statements.
  1 = Answer is largely detached from the provided context (hallucination).

Return ONLY valid JSON in this exact format — no prose before or after:
{
  "correctness": <int 1-5>,
  "completeness": <int 1-5>,
  "groundedness": <int 1-5>,
  "reasoning": "<one sentence per dimension, semicolon-separated>"
}
"""


@dataclass
class JudgeScores:
    correctness: int    # 1–5
    completeness: int   # 1–5
    groundedness: int   # 1–5
    reasoning: str
    composite: float = field(init=False)  # weighted mean

    def __post_init__(self):
        # Correctness weighted higher — wrong clinical facts are most dangerous
        self.composite = round(
            (self.correctness * 0.45 + self.completeness * 0.30 + self.groundedness * 0.25),
            2,
        )


@dataclass
class EvalResult:
    case: EvalCase
    answer: str
    sources: list[str]
    keyword: KeywordMetrics
    judge: JudgeScores | None          # None if judge call failed
    latency_ms: int
    retrieval_confidence: float
    context_used: bool
    error: str | None = None           # set if the RAG pipeline raised


def run_judge(
    question: str,
    answer: str,
    rag_context: str,
    reference: str,
    client: anthropic.Anthropic,
) -> JudgeScores:
    """Call Claude-as-judge and parse the JSON scores."""
    user_message = f"""## Reference
{reference}

## Retrieved Context (what the system had access to)
{rag_context[:2000] if rag_context else "No context retrieved."}

## Question
{question}

## Answer to Evaluate
{answer}

Score the answer now."""

    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=512,
        system=JUDGE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    data = json.loads(raw)
    return JudgeScores(
        correctness=int(data["correctness"]),
        completeness=int(data["completeness"]),
        groundedness=int(data["groundedness"]),
        reasoning=data.get("reasoning", ""),
    )


def evaluate_case(case: EvalCase, client: anthropic.Anthropic) -> EvalResult:
    """Run one evaluation case end-to-end."""
    t0 = time.monotonic()
    answer = ""
    sources = []
    rag_context = ""
    retrieval_confidence = 0.0
    context_used = False
    judge_scores = None
    error = None

    try:
        request = QueryRequest(
            question=case.question,
            query_type=case.query_type,
            patient_context=case.patient_context,
        )
        response = rag_service.query(request)
        answer = response.answer
        sources = [s.title for s in response.sources]
        retrieval_confidence = response.confidence
        context_used = response.context_used

        # Reconstruct context string for judge (best effort from source titles)
        rag_context = f"Sources used: {', '.join(sources)}" if sources else ""

    except Exception as e:
        error = str(e)
        logger.error("RAG pipeline error during evaluation", extra={"case_id": case.id, "error": error})

    latency_ms = int((time.monotonic() - t0) * 1000)

    # Keyword metrics (always computed even if answer is empty)
    keyword = compute_keyword_metrics(case, answer, sources)

    # Claude-as-judge (skipped if RAG pipeline failed)
    if not error and answer:
        try:
            judge_scores = run_judge(
                question=case.question,
                answer=answer,
                rag_context=rag_context,
                reference=case.reference,
                client=client,
            )
        except Exception as e:
            logger.error("Judge scoring failed", extra={"case_id": case.id, "error": str(e)})

    return EvalResult(
        case=case,
        answer=answer,
        sources=sources,
        keyword=keyword,
        judge=judge_scores,
        latency_ms=latency_ms,
        retrieval_confidence=retrieval_confidence,
        context_used=context_used,
        error=error,
    )


def run_evaluation(
    cases: list[EvalCase] | None = None,
    category_filter: str | None = None,
) -> list[EvalResult]:
    """
    Run the full evaluation suite.

    cases           — defaults to EVAL_DATASET
    category_filter — e.g. "treatment" to run only treatment cases
    """
    dataset = cases or EVAL_DATASET
    if category_filter:
        dataset = [c for c in dataset if c.category == category_filter]

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    results: list[EvalResult] = []

    for i, case in enumerate(dataset, 1):
        logger.info(f"Evaluating case {i}/{len(dataset)}", extra={"case_id": case.id})
        result = evaluate_case(case, client)
        results.append(result)

    return results


def aggregate_results(results: list[EvalResult]) -> dict:
    """Compute dataset-level summary statistics."""
    n = len(results)
    if n == 0:
        return {}

    completed = [r for r in results if r.error is None]
    nc = len(completed)
    judged = [r for r in completed if r.judge is not None]
    nj = len(judged)

    return {
        "total_cases": n,
        "completed": nc,
        "errors": n - nc,
        "keyword": {
            "avg_recall": round(sum(r.keyword.keyword_recall for r in results) / n, 3),
            "safety_pass_rate": round(sum(r.keyword.safety_pass for r in results) / n, 3),
            "disclaimer_rate": round(sum(r.keyword.disclaimer_present for r in results) / n, 3),
            "source_cited_rate": round(sum(r.keyword.source_cited for r in results) / n, 3),
        },
        "judge": {
            "avg_correctness": round(sum(r.judge.correctness for r in judged) / nj, 2) if nj else None,
            "avg_completeness": round(sum(r.judge.completeness for r in judged) / nj, 2) if nj else None,
            "avg_groundedness": round(sum(r.judge.groundedness for r in judged) / nj, 2) if nj else None,
            "avg_composite": round(sum(r.judge.composite for r in judged) / nj, 2) if nj else None,
        },
        "performance": {
            "avg_latency_ms": round(sum(r.latency_ms for r in results) / n),
            "avg_retrieval_confidence": round(sum(r.retrieval_confidence for r in results) / n, 3),
            "context_used_rate": round(sum(r.context_used for r in results) / n, 3),
        },
    }