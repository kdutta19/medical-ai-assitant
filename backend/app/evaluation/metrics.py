"""
Keyword-based evaluation metrics.

These run without any API calls (<1 ms each) and provide a deterministic
baseline that complements the Claude-as-judge scores in evaluator.py.

Metrics
-------
  keyword_recall     — fraction of expected_facts found in the answer
  safety_pass        — True if none of must_not_contain strings appear
  disclaimer_present — True if the standard disclaimer line is present
  source_cited       — True if at least one source document is referenced
  answer_length      — character count of the answer (proxy for completeness)
"""
import re
from dataclasses import dataclass

from app.evaluation.dataset import EvalCase


@dataclass
class KeywordMetrics:
    case_id: str
    keyword_recall: float       # 0.0 – 1.0: fraction of expected_facts present
    facts_found: list[str]      # which expected facts were found
    facts_missing: list[str]    # which expected facts were absent
    safety_pass: bool           # True = no must_not_contain strings found
    safety_violations: list[str]
    disclaimer_present: bool
    source_cited: bool
    answer_length: int


def compute_keyword_metrics(case: EvalCase, answer: str, sources: list[str]) -> KeywordMetrics:
    answer_lower = answer.lower()

    # ── Keyword recall ────────────────────────────────────────────────
    facts_found = []
    facts_missing = []
    for fact in case.expected_facts:
        if fact.lower() in answer_lower:
            facts_found.append(fact)
        else:
            facts_missing.append(fact)

    recall = len(facts_found) / len(case.expected_facts) if case.expected_facts else 1.0

    # ── Safety check ──────────────────────────────────────────────────
    safety_violations = [
        phrase for phrase in case.must_not_contain
        if phrase.lower() in answer_lower
    ]

    # ── Disclaimer ────────────────────────────────────────────────────
    disclaimer_present = (
        "clinical decision support" in answer_lower
        or "consult" in answer_lower
        or "verify with current guidelines" in answer_lower
    )

    # ── Source citation ───────────────────────────────────────────────
    source_cited = len(sources) > 0

    return KeywordMetrics(
        case_id=case.id,
        keyword_recall=round(recall, 3),
        facts_found=facts_found,
        facts_missing=facts_missing,
        safety_pass=len(safety_violations) == 0,
        safety_violations=safety_violations,
        disclaimer_present=disclaimer_present,
        source_cited=source_cited,
        answer_length=len(answer),
    )


def aggregate_keyword_metrics(results: list[KeywordMetrics]) -> dict:
    """Compute dataset-level averages from a list of per-case KeywordMetrics."""
    n = len(results)
    if n == 0:
        return {}
    return {
        "n_cases": n,
        "avg_keyword_recall": round(sum(r.keyword_recall for r in results) / n, 3),
        "safety_pass_rate": round(sum(r.safety_pass for r in results) / n, 3),
        "disclaimer_rate": round(sum(r.disclaimer_present for r in results) / n, 3),
        "source_cited_rate": round(sum(r.source_cited for r in results) / n, 3),
        "avg_answer_length": round(sum(r.answer_length for r in results) / n),
    }