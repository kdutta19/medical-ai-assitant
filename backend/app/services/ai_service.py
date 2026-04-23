import uuid
import anthropic
from app.config import settings
from app.models.schemas import ChatRequest, ChatResponse, Message, Role
from app.core.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a Clinical AI Assistant designed to support healthcare professionals.

Guidelines:
- Provide evidence-based clinical information only.
- Always recommend consulting a licensed physician for diagnosis and treatment decisions.
- Never provide definitive diagnoses — support clinical reasoning instead.
- Flag drug interactions, contraindications, and safety alerts clearly.
- Do not store or repeat personally identifiable patient information.
- Cite clinical guidelines (e.g., AHA, WHO, UpToDate) when relevant.

You assist with: differential diagnosis support, drug reference, clinical guidelines, lab interpretation, and medical literature summaries."""


class AIService:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = "claude-sonnet-4-6"

    def chat(self, request: ChatRequest) -> ChatResponse:
        conversation_id = request.conversation_id or str(uuid.uuid4())

        messages = [
            {"role": msg.role.value, "content": msg.content}
            for msg in request.history
        ]
        messages.append({"role": "user", "content": request.message})

        logger.info(
            "Sending chat request",
            extra={"conversation_id": conversation_id, "message_count": len(messages)},
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        reply = response.content[0].text

        logger.info(
            "Chat response received",
            extra={
                "conversation_id": conversation_id,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )

        return ChatResponse(
            response=reply,
            conversation_id=conversation_id,
            model=self.model,
        )


ai_service = AIService()
