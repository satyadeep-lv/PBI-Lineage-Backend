from pydantic import BaseModel

from app.ai.models.enums import MessageRole


class ModelMessage(BaseModel):
    role: MessageRole
    content: str
