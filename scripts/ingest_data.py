"""
Ingestion script: reads .txt/.md files from /data/raw, chunks them,
embeds with sentence-transformers, and persists a FAISS index to /data/index.

Usage:
    # From repo root
    python scripts/ingest_data.py

    # Custom paths
    python scripts/ingest_data.py --data-dir ./data/raw --index-dir ./data/index

    # Dry run (chunk only, no embedding/indexing)
    python scripts/ingest_data.py --dry-run
"""
import sys
import argparse
import time
from pathlib import Path

# Allow imports from backend/app without installing the package
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.rag.chunking import load_and_chunk_file, Chunk
from app.rag.embeddings import embed_documents
from app.rag.vector_store import VectorStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest clinical documents into FAISS vector store")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=REPO_ROOT / "data" / "raw",
        help="Directory containing .txt / .md source documents",
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=REPO_ROOT / "data" / "index",
        help="Directory where FAISS index and metadata will be written",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=400,
        help="Target character length per chunk (default: 400)",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=80,
        help="Character overlap between adjacent chunks (default: 80)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chunk documents only; skip embedding and indexing",
    )
    return parser.parse_args()


def load_documents(data_dir: Path) -> list[Path]:
    files = sorted(data_dir.glob("**/*.txt")) + sorted(data_dir.glob("**/*.md"))
    if not files:
        print(f"[WARNING] No .txt or .md files found in {data_dir}")
    return files


def main() -> None:
    args = parse_args()

    print(f"\n{'='*60}")
    print(f"  Clinical AI — Document Ingestion")
    print(f"{'='*60}")
    print(f"  Source dir : {args.data_dir}")
    print(f"  Index dir  : {args.index_dir}")
    print(f"  Chunk size : {args.chunk_size} chars  Overlap: {args.chunk_overlap} chars")
    print(f"  Dry run    : {args.dry_run}")
    print(f"{'='*60}\n")

    # ── 1. Discover files ──────────────────────────────────────────────
    files = load_documents(args.data_dir)
    if not files:
        sys.exit(1)
    print(f"Found {len(files)} document(s):\n" + "\n".join(f"  - {f.name}" for f in files))

    # ── 2. Chunk ───────────────────────────────────────────────────────
    print("\n[1/3] Chunking documents...")
    t0 = time.time()
    all_chunks: list[Chunk] = []
    for f in files:
        chunks = load_and_chunk_file(f, chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
        print(f"  {f.name}: {len(chunks)} chunks")
        all_chunks.extend(chunks)

    print(f"  Total chunks: {len(all_chunks)}  ({time.time()-t0:.1f}s)")

    if args.dry_run:
        print("\n[DRY RUN] Stopping before embedding. Sample chunks:")
        for chunk in all_chunks[:3]:
            print(f"\n  --- Chunk {chunk.chunk_index} [{chunk.source}] ---")
            print(f"  {chunk.text[:200]}...")
        return

    # ── 3. Embed ───────────────────────────────────────────────────────
    print("\n[2/3] Embedding chunks (this may take a minute on first run to download the model)...")
    t1 = time.time()
    texts = [c.text for c in all_chunks]
    embeddings = embed_documents(texts)
    print(f"  Embeddings shape: {embeddings.shape}  ({time.time()-t1:.1f}s)")

    # ── 4. Index ───────────────────────────────────────────────────────
    print("\n[3/3] Building and persisting FAISS index...")
    t2 = time.time()
    store = VectorStore(args.index_dir)
    store.build(all_chunks, embeddings)
    stats = store.stats()
    print(f"  Vectors indexed : {stats['total_vectors']}")
    print(f"  Index written to: {stats['index_path']}")
    print(f"  Metadata written: {stats['metadata_path']}")
    print(f"  ({time.time()-t2:.1f}s)")

    print(f"\n{'='*60}")
    print(f"  Ingestion complete in {time.time()-t0:.1f}s total")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
