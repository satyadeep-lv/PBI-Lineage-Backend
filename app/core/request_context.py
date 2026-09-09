from contextvars import ContextVar, Token

_request_id_context: ContextVar[str] = ContextVar(
    "request_id",
    default="unknown",
)


def set_request_id(request_id: str) -> Token[str]:
    return _request_id_context.set(request_id)


def get_request_id() -> str:
    return _request_id_context.get()


def reset_request_id(token: Token[str]) -> None:
    _request_id_context.reset(token)
