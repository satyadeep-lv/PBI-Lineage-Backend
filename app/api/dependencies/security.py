import secrets
from typing import Annotated

from fastapi import Header

from app.core.config import get_settings
from app.core.exceptions import (
    LineageApiKeyInvalidError,
    LineageApiKeyRequiredError,
)


async def require_lineage_api_key(
    api_key: Annotated[str | None, Header(alias="X-Lineage-Admin-Key")] = None,
) -> None:
    configured = get_settings().lineage_admin_api_key
    if configured is None:
        return
    if api_key is None:
        raise LineageApiKeyRequiredError()
    if not secrets.compare_digest(api_key, configured.get_secret_value()):
        raise LineageApiKeyInvalidError()
