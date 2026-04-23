"""
Quick smoke-test for the RAG retrieval pipeline.

Usage:
    python scripts/test_retrieval.py
    python scripts/test_retrieval.py --query "first line treatment for hypertension"
"""
import sys
import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.rag.retriever import retrieve, format_context

TEST_QUERIES = [
    "What is the definition of hypertension?",
    "First-line drugs for type 2 diabetes",
    "Metformin contraindications and dosing",
    "ACE inhibitor side effects",
    "Blood pressure target in CKD patients",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", type=str, default=None, help="Single query to test")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=0.25)
    args = parser.parse_args()

    queries = [args.query] if args.query else TEST_QUERIES

    print(f"\n{'='*60}")
    print(f"  RAG Retrieval Smoke Test")
    print(f"  top_k={args.top_k}  threshold={args.threshold}")
    print(f"{'='*60}\n")

    for query in queries:
        print(f"Query: {query}")
        print("-" * 50)
        chunks = retrieve(query, top_k=args.top_k, score_threshold=args.threshold)

        if not chunks:
            print("  [no results above threshold]")
        else:
            for i, chunk in enumerate(chunks, 1):
                print(f"  [{i}] score={chunk['score']:.3f}  source={chunk['source']}")
                print(f"      {chunk['text'][:180].strip()}...")

        print()


if __name__ == "__main__":
    main()
