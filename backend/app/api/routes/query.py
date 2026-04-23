from fastapi import APIRouter, HTTPException
from app.schemas.query import QueryRequest, QueryResponse
from app.services.rag_service import rag_service
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/query", response_model=QueryResponse, summary="Submit a clinical query")
def clinical_query(request: QueryRequest):
    try:
        return rag_service.query(request)
    except FileNotFoundError as e:
        logger.error("Vector index not found", extra={"error": str(e)})
        raise HTTPException(
            status_code=503,
            detail="Knowledge base not initialised. Run: python scripts/ingest_data.py",
        )
    except Exception as e:
        logger.error("Query failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to process clinical query.")
