from fastapi import APIRouter, HTTPException
from app.models.schemas import ChatRequest, ChatResponse
from app.services.ai_service import ai_service
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    try:
        return ai_service.chat(request)
    except Exception as e:
        logger.error("Chat request failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to process chat request.")
