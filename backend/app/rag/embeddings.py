"""
Embedding model wrapper using sentence-transformers.

Model choice: `BAAI/bge-small-en-v1.5`
- 384-dim vectors, ~33 MB on disk
- Top-ranked on MTEB for retrieval at small size
- Fast enough for real-time query embedding without a GPU
- Can be swapped for `bge-base-en-v1.5` (768-dim) for higher accuracy
"""
import numpy as np
from functools import lru_cache
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384

# BGE models perform better when queries are prefixed with this instruction
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    """Load model once and cache for the lifetime of the process."""
    return SentenceTransformer(EMBEDDING_MODEL)


def embed_documents(texts: list[str], batch_size: int = 64) -> np.ndarray:
    """
    Embed a list of document chunks.
    Returns float32 array of shape (n, EMBEDDING_DIM), L2-normalized.
    """
    model = _get_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,  # cosine similarity via dot product
        convert_to_numpy=True,
    )
    return embeddings.astype(np.float32)


def embed_query(query: str) -> np.ndarray:
    """
    Embed a single retrieval query.
    Returns float32 array of shape (1, EMBEDDING_DIM), L2-normalized.
    """
    model = _get_model()
    prefixed = BGE_QUERY_PREFIX + query
    embedding = model.encode(
        [prefixed],
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return embedding.astype(np.float32)
