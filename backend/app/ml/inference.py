"""
Query route classifier — inference module.

Loads the trained scikit-learn pipeline once at process startup and
exposes classify() for synchronous, sub-millisecond prediction.

Route categories and their effect on retrieval
-----------------------------------------------
  treatment  → high TOP_K (8), low threshold (0.25)
               More drug/therapy chunks; be generous — missing a dosage note is worse
               than retrieving one extra irrelevant chunk.

  diagnosis  → high TOP_K (8), standard threshold (0.30)
               Differential diagnosis benefits from breadth of retrieved evidence.

  lifestyle  → low TOP_K (4), high threshold (0.35)
               Reference material for lifestyle queries is sparse; only retrieve
               when highly relevant to avoid hallucination via weak context.

  general    → default TOP_K (6), default threshold (0.30)
               Balanced retrieval for mixed or unclear intent.
"""
import json
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_DIR = REPO_ROOT / "models"
MODEL_FILENAME = "query_classifier.joblib"
META_FILENAME = "query_classifier_meta.json"


# ---------------------------------------------------------------------------
# Route category
# ---------------------------------------------------------------------------

class RouteCategory(str, Enum):
    treatment = "treatment"
    diagnosis = "diagnosis"
    lifestyle = "lifestyle"
    general   = "general"


# ---------------------------------------------------------------------------
# Retrieval params per route
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetrievalParams:
    top_k: int
    score_threshold: float


ROUTE_RETRIEVAL_PARAMS: dict[RouteCategory, RetrievalParams] = {
    RouteCategory.treatment: RetrievalParams(top_k=8, score_threshold=0.25),
    RouteCategory.diagnosis: RetrievalParams(top_k=8, score_threshold=0.30),
    RouteCategory.lifestyle: RetrievalParams(top_k=4, score_threshold=0.35),
    RouteCategory.general:   RetrievalParams(top_k=6, score_threshold=0.30),
}


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    category: RouteCategory
    confidence: float                    # probability of the predicted class [0, 1]
    all_scores: dict[str, float]         # probabilities for all classes
    retrieval: RetrievalParams           # retrieval params to use for this route


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class QueryClassifier:
    def __init__(self, model_dir: Path = DEFAULT_MODEL_DIR) -> None:
        self._model_dir = model_dir
        self._pipeline = None
        self._meta: dict = {}
        self._load()

    def _load(self) -> None:
        model_path = self._model_dir / MODEL_FILENAME
        meta_path = self._model_dir / META_FILENAME

        if not model_path.exists():
            raise FileNotFoundError(
                f"Classifier model not found at {model_path}. "
                "Run: python backend/app/ml/train.py"
            )

        self._pipeline = joblib.load(model_path)
        self._meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}

        logger.info(
            "Query classifier loaded",
            extra={
                "model_path": str(model_path),
                "cv_accuracy": self._meta.get("cv_accuracy_mean"),
                "n_features": self._meta.get("n_features"),
            },
        )

    def classify(self, question: str) -> ClassificationResult:
        """
        Classify a clinical question into a route category.
        Returns ClassificationResult with category, confidence, and retrieval params.
        """
        proba = self._pipeline.predict_proba([question])[0]
        classes = self._pipeline.classes_

        best_idx = int(np.argmax(proba))
        predicted_label = classes[best_idx]
        confidence = float(proba[best_idx])
        all_scores = {cls: round(float(p), 4) for cls, p in zip(classes, proba)}

        # Fallback to general if confidence is very low (ambiguous query)
        if confidence < 0.40:
            category = RouteCategory.general
            logger.info(
                "Classifier low confidence — routing to general",
                extra={"predicted": predicted_label, "confidence": round(confidence, 3)},
            )
        else:
            try:
                category = RouteCategory(predicted_label)
            except ValueError:
                category = RouteCategory.general

        retrieval = ROUTE_RETRIEVAL_PARAMS[category]

        logger.info(
            "Query classified",
            extra={
                "category": category.value,
                "confidence": round(confidence, 3),
                "all_scores": all_scores,
                "top_k": retrieval.top_k,
                "score_threshold": retrieval.score_threshold,
            },
        )

        return ClassificationResult(
            category=category,
            confidence=confidence,
            all_scores=all_scores,
            retrieval=retrieval,
        )

    @property
    def meta(self) -> dict:
        return self._meta


# ---------------------------------------------------------------------------
# Singleton — loaded once per process
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_classifier(model_dir: str = str(DEFAULT_MODEL_DIR)) -> QueryClassifier:
    return QueryClassifier(Path(model_dir))
