"""
Evaluation runner — executes the full evaluation suite and prints results.

Usage
-----
  # Full suite (all 20 cases, keyword + Claude-as-judge)
  python scripts/run_evaluation.py

  # Keyword metrics only (no API calls for judge — free and instant)
  python scripts/run_evaluation.py --keyword-only

  # Filter to one category
  python scripts/run_evaluation.py --category treatment

  # Single case by ID
  python scripts/run_evaluation.py --case-id T-001

  # Save full results to JSON
  python scripts/run_evaluation.py --output results/eval_run.json

  # Skip judge scoring (faster, no cost)
  python scripts/run_evaluation.py --keyword-only --output results/quick.json
"""
import sys
import json
import argparse
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.evaluation.dataset import EVAL_DATASET, EvalCase
from app.evaluation.evaluator import (
    run_evaluation, aggregate_results, evaluate_case, EvalResult,
)
from app.evaluation.metrics import compute_keyword_metrics


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

SCORE_COLORS = {5: "●●●●●", 4: "●●●●○", 3: "●●●○○", 2: "●●○○○", 1: "●○○○○"}


def _bar(score: int | None) -> str:
    if score is None:
        return "N/A  "
    return SCORE_COLORS.get(score, "?????")


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def print_case_result(result: EvalResult, verbose: bool = False) -> None:
    case = result.case
    k = result.keyword
    j = result.judge

    status = "ERROR" if result.error else "OK   "
    print(f"\n[{status}] {case.id}  |  {case.category:<12}  |  {case.question[:70]}")
    print(f"       Latency: {result.latency_ms}ms  |  Confidence: {result.retrieval_confidence:.3f}  |  Context: {'yes' if result.context_used else 'no '}")

    # Keyword metrics
    recall_pct = _pct(k.keyword_recall)
    safety = "PASS" if k.safety_pass else f"FAIL ({', '.join(k.safety_violations)})"
    disc = "yes" if k.disclaimer_present else "no "
    src = "yes" if k.source_cited else "no "
    print(f"       Keyword  ->  recall: {recall_pct:<6}  safety: {safety:<30}  disclaimer: {disc}  sources: {src}")

    if k.facts_missing:
        print(f"       Missing facts: {k.facts_missing}")

    # Judge scores
    if j:
        print(
            f"       Judge    ->  correctness: {_bar(j.correctness)} {j.correctness}  "
            f"completeness: {_bar(j.completeness)} {j.completeness}  "
            f"groundedness: {_bar(j.groundedness)} {j.groundedness}  "
            f"composite: {j.composite}"
        )
        if verbose:
            print(f"       Reasoning: {j.reasoning}")
    elif not result.error:
        print("       Judge    ->  skipped (keyword-only mode)")

    if result.error:
        print(f"       Error: {result.error}")


def print_summary(agg: dict) -> None:
    print("\n" + "=" * 70)
    print("  EVALUATION SUMMARY")
    print("=" * 70)
    print(f"  Cases run : {agg['total_cases']}  |  Completed: {agg['completed']}  |  Errors: {agg['errors']}")

    kw = agg["keyword"]
    print(f"\n  KEYWORD METRICS")
    print(f"    Fact recall        : {_pct(kw['avg_recall'])}")
    print(f"    Safety pass rate   : {_pct(kw['safety_pass_rate'])}")
    print(f"    Disclaimer rate    : {_pct(kw['disclaimer_rate'])}")
    print(f"    Source cited rate  : {_pct(kw['source_cited_rate'])}")

    jg = agg["judge"]
    if jg["avg_composite"] is not None:
        print(f"\n  CLAUDE-AS-JUDGE SCORES  (scale 1–5)")
        print(f"    Correctness   : {jg['avg_correctness']} / 5")
        print(f"    Completeness  : {jg['avg_completeness']} / 5")
        print(f"    Groundedness  : {jg['avg_groundedness']} / 5")
        print(f"    Composite     : {jg['avg_composite']} / 5  (weighted: 45% correct, 30% complete, 25% grounded)")
    else:
        print("\n  CLAUDE-AS-JUDGE SCORES  -- skipped (keyword-only mode)")

    perf = agg["performance"]
    print(f"\n  PERFORMANCE")
    print(f"    Avg latency         : {perf['avg_latency_ms']} ms")
    print(f"    Avg RAG confidence  : {perf['avg_retrieval_confidence']}")
    print(f"    Context used rate   : {_pct(perf['context_used_rate'])}")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run clinical AI evaluation suite")
    p.add_argument("--keyword-only", action="store_true", help="Skip Claude-as-judge scoring")
    p.add_argument("--category", choices=["treatment", "diagnosis", "lifestyle", "general"],
                   help="Run only cases matching this category")
    p.add_argument("--case-id", help="Run a single case by ID (e.g. T-001)")
    p.add_argument("--verbose", action="store_true", help="Print judge reasoning per case")
    p.add_argument("--output", type=Path, help="Save full results as JSON to this path")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    dataset = EVAL_DATASET
    if args.case_id:
        dataset = [c for c in dataset if c.id == args.case_id]
        if not dataset:
            print(f"Case ID '{args.case_id}' not found. Valid IDs: {[c.id for c in EVAL_DATASET]}")
            sys.exit(1)
    elif args.category:
        dataset = [c for c in dataset if c.category == args.category]

    print(f"\n{'='*70}")
    print(f"  Clinical AI Evaluation Pipeline")
    print(f"  Cases: {len(dataset)}  |  Judge: {'disabled' if args.keyword_only else 'enabled'}")
    if args.category:
        print(f"  Category filter: {args.category}")
    print(f"{'='*70}")

    t_total = time.monotonic()

    if args.keyword_only:
        # Fast path: RAG pipeline only, no judge API calls
        from app.schemas.query import QueryRequest
        from app.services.rag_service import rag_service
        results = []
        for i, case in enumerate(dataset, 1):
            print(f"  Running {i}/{len(dataset)}: {case.id}...", end=" ", flush=True)
            t0 = time.monotonic()
            try:
                request = QueryRequest(question=case.question, query_type=case.query_type,
                                       patient_context=case.patient_context)
                response = rag_service.query(request)
                answer = response.answer
                sources = [s.title for s in response.sources]
                latency = int((time.monotonic() - t0) * 1000)
                keyword = compute_keyword_metrics(case, answer, sources)
                result = EvalResult(
                    case=case, answer=answer, sources=sources,
                    keyword=keyword, judge=None,
                    latency_ms=latency,
                    retrieval_confidence=response.confidence,
                    context_used=response.context_used,
                )
            except Exception as e:
                keyword = compute_keyword_metrics(case, "", [])
                result = EvalResult(
                    case=case, answer="", sources=[], keyword=keyword, judge=None,
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    retrieval_confidence=0.0, context_used=False, error=str(e),
                )
            results.append(result)
            print(f"done ({result.latency_ms}ms)")
    else:
        results = run_evaluation(cases=dataset)

    print()
    for result in results:
        print_case_result(result, verbose=args.verbose)

    agg = aggregate_results(results)
    print_summary(agg)
    print(f"\n  Total wall time: {time.monotonic() - t_total:.1f}s")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        output_data = {
            "summary": agg,
            "cases": [
                {
                    "id": r.case.id,
                    "category": r.case.category,
                    "question": r.case.question,
                    "answer_preview": r.answer[:300],
                    "sources": r.sources,
                    "latency_ms": r.latency_ms,
                    "retrieval_confidence": r.retrieval_confidence,
                    "keyword": {
                        "recall": r.keyword.keyword_recall,
                        "facts_found": r.keyword.facts_found,
                        "facts_missing": r.keyword.facts_missing,
                        "safety_pass": r.keyword.safety_pass,
                        "disclaimer_present": r.keyword.disclaimer_present,
                    },
                    "judge": {
                        "correctness": r.judge.correctness,
                        "completeness": r.judge.completeness,
                        "groundedness": r.judge.groundedness,
                        "composite": r.judge.composite,
                        "reasoning": r.judge.reasoning,
                    } if r.judge else None,
                    "error": r.error,
                }
                for r in results
            ],
        }
        args.output.write_text(json.dumps(output_data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  Results saved to: {args.output}\n")


if __name__ == "__main__":
    main()