from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class RouteCategory(str, Enum):
    treatment = "treatment"
    diagnosis = "diagnosis"
    lifestyle = "lifestyle"
    general   = "general"


class QueryType(str, Enum):
    differential_diagnosis = "differential_diagnosis"
    drug_reference = "drug_reference"
    lab_interpretation = "lab_interpretation"
    clinical_guideline = "clinical_guideline"
    literature_summary = "literature_summary"
    general = "general"


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=10000, description="Clinical question to answer")
    query_type: QueryType = Field(default=QueryType.general, description="Category of clinical query")
    patient_context: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="De-identified patient context (age, sex, relevant history). Never include names or identifiers.",
    )
    conversation_id: Optional[str] = Field(default=None, description="ID to continue an existing conversation")


class Source(BaseModel):
    title: str
    reference: str


class QueryResponse(BaseModel):
    answer: str
    query_type: QueryType
    conversation_id: str
    model: str
    sources: list[Source] = Field(default_factory=list)
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Mean retrieval score of supporting chunks (0 = no context found, 1 = perfect match)",
    )
    context_used: bool = Field(
        default=False,
        description="Whether RAG context was available and injected into the prompt",
    )
    route_category: Optional[RouteCategory] = Field(
        default=None,
        description="ML-predicted query route category",
    )
    route_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Classifier confidence for the predicted route category",
    )
    disclaimer: str = (
        "This response is for clinical decision support only. "
        "Always apply independent clinical judgement and consult appropriate specialists."
    )
