from enum import Enum


class AudienceType(str, Enum):
    GENERAL = "general"
    BUSINESS = "business"
    DEVELOPER = "developer"


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
