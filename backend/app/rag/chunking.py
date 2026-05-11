"""
Text chunking for clinical documents.

Strategy: sentence-aware sliding window so chunk boundaries never cut
mid-sentence, which matters for clinical text where a truncated sentence
can change meaning (e.g. "do NOT administer..." split after "do").
"""
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Chunk:
    text: str
    source: str                        # filename or document title
    chunk_index: int                   # position within source document
    metadata: dict = field(default_factory=dict)


def _split_sentences(text: str) -> list[str]:
    """Split on sentence boundaries while preserving clinical abbreviations."""
    # Protect common clinical abbreviations that contain periods
    abbreviations = [
        r"Dr\.", r"Mr\.", r"Ms\.", r"Mrs\.", r"Prof\.",
        r"vs\.", r"approx\.", r"e\.g\.", r"i\.e\.", r"et al\.",
        r"mg\.", r"mL\.", r"mcg\.", r"mmHg\.", r"bpm\.",
        r"q\.d\.", r"b\.i\.d\.", r"t\.i\.d\.", r"q\.i\.d\.",
        r"p\.o\.", r"i\.v\.", r"i\.m\.", r"s\.c\.",
    ]
    placeholder_map: dict[str, str] = {}
    protected = text
    for i, abbr in enumerate(abbreviations):
        token = f"__ABBR{i}__"
        protected, n = re.subn(abbr, token, protected, flags=re.IGNORECASE)
        if n:
            original = re.sub(r"\\", "", abbr)
            placeholder_map[token] = original

    # Split based on ., !, or ?
    sentences = re.split(r"(?<=[.!?])\s+", protected)

    restored = []
    for s in sentences:
        for token, original in placeholder_map.items():
            s = s.replace(token, original)
        s = s.strip()
        if s:
            restored.append(s)
    return restored


def chunk_text(
    text: str,
    source: str,
    chunk_size: int = 400,
    chunk_overlap: int = 80,
) -> list[Chunk]:
    """
    Sliding-window chunker operating on whole sentences.

    chunk_size    — target max characters per chunk
    chunk_overlap — characters of overlap between adjacent chunks
                    (achieved by re-including trailing sentences)
    """
    sentences = _split_sentences(text)
    chunks: list[Chunk] = []
    current_sentences: list[str] = []
    current_len = 0
    chunk_index = 0

    for sentence in sentences:
        sentence_len = len(sentence)

        if current_len + sentence_len > chunk_size and current_sentences:
            chunk_text_str = " ".join(current_sentences)
            chunks.append(Chunk(
                text=chunk_text_str,
                source=source,
                chunk_index=chunk_index,
            ))
            chunk_index += 1

            # Roll back by overlap: drop sentences from the front until
            # remaining length is within the overlap budget
            while current_sentences and current_len > chunk_overlap:
                removed = current_sentences.pop(0)
                current_len -= len(removed) + 1  # +1 for the space

        current_sentences.append(sentence)
        current_len += sentence_len + 1

    if current_sentences:
        chunks.append(Chunk(
            text=" ".join(current_sentences),
            source=source,
            chunk_index=chunk_index,
        ))

    return chunks


def load_and_chunk_file(
    path: Path,
    chunk_size: int = 400,
    chunk_overlap: int = 80,
) -> list[Chunk]:
    """Read a .txt or .md file and return its chunks."""
    if path.suffix not in {".txt", ".md"}:
        raise ValueError(f"Unsupported file type: {path.suffix}. Expected .txt or .md")

    text = path.read_text(encoding="utf-8")
    return chunk_text(text, source=path.name, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
