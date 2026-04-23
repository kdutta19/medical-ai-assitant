from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime, timezone


class FeedbackRating(int, Enum):
    very_poor = 1
    poor = 2
    acceptable = 3
    good = 4
    excellent = 5


class FeedbackRequest(BaseModel):
    conversation_id: str = Field(..., description="ID of the conversation being rated")
    rating: FeedbackRating = Field(..., description="1 (very poor) to 5 (excellent)")
    comment: Optional[str] = Field(default=None, max_length=2000, description="Optional free-text comment")
    is_clinically_accurate: Optional[bool] = Field(
        default=None, description="Whether the response was clinically accurate"
    )
    is_helpful: Optional[bool] = Field(
        default=None, description="Whether the response was helpful in practice"
    )


class FeedbackResponse(BaseModel):
    feedback_id: str
    conversation_id: str
    rating: FeedbackRating
    received_at: datetime
    message: str
