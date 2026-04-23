from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class Role(str, Enum):
    user = "user"
    assistant = "assistant"


class Message(BaseModel):
    role: Role
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    conversation_id: Optional[str] = None
    history: list[Message] = Field(default_factory=list)


class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    model: str


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
