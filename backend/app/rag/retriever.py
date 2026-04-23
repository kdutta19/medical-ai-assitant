"""
Retriever: single entry point for query-time RAG lookup.

Combines embed_query → vector_store.search → format context string.
The formatted context is passed directly into the Claude system prompt in Phase 4.
"""
from pathlib import Path
from functools import lru_cache

from app.rag.embeddings import embed_query
from app.rag.vector_store import VectorStore
from app.core.logging import get_logger

logger = get_logger(__name__)

# Default index location — overridden in tests or when S3-synced index is used
DEFAULT_INDEX_DIR = Path(__file__).resolve().parents[3] / "data" / "index"


@lru_cache(maxsize=1)
def _get_vector_store(index_dir: str) -> VectorStore:
    """Load and cache the vector store for the process lifetime."""
    store = VectorStore(Path(index_dir))
    store.load()
    logger.info("Vector store loaded", extra=store.stats())
    return store


def retrieve(
    query: str,
    top_k: int = 5,
    score_threshold: float = 0.30,
    index_dir: Path = DEFAULT_INDEX_DIR,
) -> list[dict]:
    """
    Retrieve the top_k most relevant chunks for a query.

    score_threshold filters out low-confidence results.
    Returns list of dicts with keys: text, source, chunk_index, score.
    """
    store = _get_vector_store(str(index_dir))
    query_vec = embed_query(query)
    results = store.search(query_vec, top_k=top_k)
    filtered = [r for r in results if r["score"] >= score_threshold]

    logger.info(
        "Retrieval complete",
        extra={
            "query_preview": query[:80],
            "total_results": len(results),
            "after_threshold": len(filtered),
            "score_threshold": score_threshold,
        },
    )
    return filtered


def format_context(chunks: list[dict], max_chars: int = 3000) -> str:
    """
    Format retrieved chunks into a context block for the Claude prompt.
    Truncates total context to stay within max_chars.
    """
    if not chunks:
        return ""

    lines: list[str] = ["### Retrieved Clinical Context\n"]
    total = 0

    for i, chunk in enumerate(chunks, start=1):
        entry = (
            f"[{i}] Source: {chunk['source']} (score: {chunk['score']:.3f})\n"
            f"{chunk['text']}\n"
        )
        if total + len(entry) > max_chars:
            break
        lines.append(entry)
        total += len(entry)

    return "\n".join(lines)
