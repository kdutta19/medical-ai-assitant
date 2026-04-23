import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.main import app
from app.models.schemas import ChatResponse

client = TestClient(app)


@patch("app.services.ai_service.ai_service.chat")
def test_chat_endpoint(mock_chat):
    mock_chat.return_value = ChatResponse(
        response="Hypertension is defined as systolic BP >= 130 mmHg per AHA guidelines.",
        conversation_id="test-uuid-1234",
        model="claude-sonnet-4-6",
    )

    response = client.post(
        "/api/chat",
        json={"message": "What is the AHA definition of hypertension?", "history": []},
    )

    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert "conversation_id" in data
    assert "model" in data


def test_chat_empty_message():
    response = client.post("/api/chat", json={"message": "", "history": []})
    assert response.status_code == 422
