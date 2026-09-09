from typing import Literal

from pydantic import BaseModel, Field


class ReadinessCheck(BaseModel):
    status: Literal["pass", "fail", "warn"]
    message: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, ReadinessCheck] = Field(default_factory=dict)
