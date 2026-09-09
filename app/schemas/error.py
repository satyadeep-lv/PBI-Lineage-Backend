from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    provider: str | None = None
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
