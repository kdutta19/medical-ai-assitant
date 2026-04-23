"""
FAISS vector store with metadata persistence.

FAISS stores only float vectors — chunk text and source metadata are kept
in a parallel JSON sidecar file so they survive serialization.

Index type: IndexFlatIP (inner product on L2-normalized vectors = cosine similarity)
Upgrade path: swap for IndexIVFFlat when corpus exceeds ~100k chunks for faster search.
"""
import json
import numpy as np
import faiss
from dataclasses import asdict
from pathlib import Path

from app.rag.chunking import Chunk
from app.rag.embeddings import EMBEDDING_DIM

INDEX_FILE = "faiss.index"
METADATA_FILE = "metadata.json"


class VectorStore:
    def __init__(self, index_dir: Path):
        self.index_dir = index_dir
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = index_dir / INDEX_FILE
        self._metadata_path = index_dir / METADATA_FILE
        self._index: faiss.IndexFlatIP | None = None
        self._metadata: list[dict] = []  # parallel list to FAISS vectors

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self, chunks: list[Chunk], embeddings: np.ndarray) -> None:
        """Create a new index from scratch. Overwrites any existing index."""
        if len(chunks) != embeddings.shape[0]:
            raise ValueError(
                f"chunks ({len(chunks)}) and embeddings ({embeddings.shape[0]}) must have equal length"
            )

        self._index = faiss.IndexFlatIP(EMBEDDING_DIM)
        self._index.add(embeddings)
        self._metadata = [asdict(c) for c in chunks]
        self._save()

    # ------------------------------------------------------------------
    # Persist / load
    # ------------------------------------------------------------------

    def _save(self) -> None:
        faiss.write_index(self._index, str(self._index_path))
        self._metadata_path.write_text(
            json.dumps(self._metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self) -> None:
        if not self._index_path.exists():
            raise FileNotFoundError(
                f"No FAISS index found at {self._index_path}. "
                "Run the ingestion script first: python scripts/ingest_data.py"
            )
        self._index = faiss.read_index(str(self._index_path))
        self._metadata = json.loads(self._metadata_path.read_text(encoding="utf-8"))

    def is_loaded(self) -> bool:
        return self._index is not None

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query_vector: np.ndarray, top_k: int = 5) -> list[dict]:
        """
        Return top_k most similar chunks.
        Each result dict contains the chunk fields plus a `score` (cosine similarity).
        """
        if not self.is_loaded():
            self.load()

        scores, indices = self._index.search(query_vector, top_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:  # FAISS returns -1 when fewer results than top_k exist
                continue
            result = dict(self._metadata[idx])
            result["score"] = float(score)
            results.append(result)

        return results

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        if not self.is_loaded():
            self.load()
        return {
            "total_vectors": self._index.ntotal,
            "embedding_dim": EMBEDDING_DIM,
            "index_path": str(self._index_path),
            "metadata_path": str(self._metadata_path),
        }
