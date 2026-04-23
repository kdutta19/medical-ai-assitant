import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from app.schemas.feedback import FeedbackRequest, FeedbackResponse
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse, status_code=201, summary="Submit feedback on a response")
def submit_feedback(request: FeedbackRequest):
    try:
        feedback_id = str(uuid.uuid4())
        received_at = datetime.now(timezone.utc)

        logger.info(
            "Feedback received",
            extra={
                "feedback_id": feedback_id,
                "conversation_id": request.conversation_id,
                "rating": request.rating.value,
                "is_clinically_accurate": request.is_clinically_accurate,
                "is_helpful": request.is_helpful,
            },
        )

        # Phase 3: persist to database

        return FeedbackResponse(
            feedback_id=feedback_id,
            conversation_id=request.conversation_id,
            rating=request.rating,
            received_at=received_at,
            message="Thank you for your feedback. It helps us improve clinical accuracy.",
        )
    except Exception as e:
        logger.error("Feedback submission failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to record feedback.")
