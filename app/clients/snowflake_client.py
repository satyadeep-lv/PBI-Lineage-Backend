import asyncio
import re
from typing import Any
from uuid import uuid4

import httpx

from app.clients.provider_http_client import provider_get, provider_post
from app.core.exceptions import UpstreamInvalidResponseError, UpstreamTimeoutError

_ACCOUNT_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_OBJECT_DEPENDENCIES_SQL = """
SELECT
    REFERENCED_DATABASE,
    REFERENCED_SCHEMA,
    REFERENCED_OBJECT_NAME,
    REFERENCED_OBJECT_DOMAIN,
    REFERENCING_DATABASE,
    REFERENCING_SCHEMA,
    REFERENCING_OBJECT_NAME,
    REFERENCING_OBJECT_DOMAIN,
    DEPENDENCY_TYPE
FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES
WHERE REFERENCED_OBJECT_NAME IS NOT NULL
  AND REFERENCING_OBJECT_NAME IS NOT NULL
""".strip()


class SnowflakeClient:
    def __init__(
        self,
        account_identifier: str,
        *,
        token_type: str = "OAUTH",
        poll_interval_seconds: float = 0.25,
        max_poll_attempts: int = 40,
    ) -> None:
        if not _ACCOUNT_IDENTIFIER_PATTERN.fullmatch(account_identifier):
            raise ValueError("Invalid Snowflake account identifier.")
        if token_type not in {"OAUTH", "KEYPAIR_JWT", "PROGRAMMATIC_ACCESS_TOKEN"}:
            raise ValueError("Unsupported Snowflake token type.")

        self.account_identifier = account_identifier
        self.base_url = (
            f"https://{account_identifier}.snowflakecomputing.com/api/v2/statements"
        )
        self.token_type = token_type
        self.poll_interval_seconds = poll_interval_seconds
        self.max_poll_attempts = max_poll_attempts

    async def get_object_dependencies(
        self,
        *,
        access_token: str,
        warehouse: str | None = None,
        role: str | None = None,
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {
            "statement": _OBJECT_DEPENDENCIES_SQL,
            "timeout": 60,
        }
        if warehouse:
            body["warehouse"] = warehouse
        if role:
            body["role"] = role

        response = await provider_post(
            provider="snowflake",
            url=self.base_url,
            access_token=access_token,
            params={"requestId": str(uuid4())},
            json_body=body,
            additional_headers={
                "X-Snowflake-Authorization-Token-Type": self.token_type,
            },
        )

        for _ in range(self.max_poll_attempts):
            payload = self._object_payload(response)

            if "data" in payload:
                return await self._all_rows(
                    payload,
                    access_token=access_token,
                )

            statement_handle = payload.get("statementHandle")
            if not isinstance(statement_handle, str) or not statement_handle.strip():
                raise UpstreamInvalidResponseError("snowflake")

            await asyncio.sleep(self.poll_interval_seconds)
            response = await provider_get(
                provider="snowflake",
                url=f"{self.base_url}/{statement_handle}",
                access_token=access_token,
                additional_headers={
                    "X-Snowflake-Authorization-Token-Type": self.token_type,
                },
            )

        raise UpstreamTimeoutError("snowflake")

    async def _all_rows(
        self,
        payload: dict[str, Any],
        *,
        access_token: str,
    ) -> list[dict[str, Any]]:
        columns = self._columns(payload)
        rows = self._data_rows(payload, columns)
        metadata = payload["resultSetMetaData"]
        partition_info = metadata.get("partitionInfo")

        if partition_info is None:
            return rows
        if not isinstance(partition_info, list) or not all(
            isinstance(partition, dict) for partition in partition_info
        ):
            raise UpstreamInvalidResponseError("snowflake")
        if len(partition_info) <= 1:
            return rows

        statement_handle = payload.get("statementHandle")
        if not isinstance(statement_handle, str) or not statement_handle.strip():
            raise UpstreamInvalidResponseError("snowflake")

        for partition_number in range(1, len(partition_info)):
            response = await provider_get(
                provider="snowflake",
                url=f"{self.base_url}/{statement_handle}",
                access_token=access_token,
                params={"partition": partition_number},
                additional_headers={
                    "X-Snowflake-Authorization-Token-Type": self.token_type,
                },
            )
            partition_payload = self._object_payload(response)
            rows.extend(self._data_rows(partition_payload, columns))
        return rows

    @staticmethod
    def _object_payload(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise UpstreamInvalidResponseError("snowflake") from exc

        if not isinstance(payload, dict):
            raise UpstreamInvalidResponseError("snowflake")
        return payload

    @staticmethod
    def _columns(payload: dict[str, Any]) -> list[str]:
        metadata = payload.get("resultSetMetaData")
        if not isinstance(metadata, dict):
            raise UpstreamInvalidResponseError("snowflake")

        row_type = metadata.get("rowType")
        if not isinstance(row_type, list):
            raise UpstreamInvalidResponseError("snowflake")

        columns: list[str] = []
        for column in row_type:
            if not isinstance(column, dict) or not isinstance(column.get("name"), str):
                raise UpstreamInvalidResponseError("snowflake")
            columns.append(column["name"])

        return columns

    @staticmethod
    def _data_rows(
        payload: dict[str, Any],
        columns: list[str],
    ) -> list[dict[str, Any]]:
        data = payload.get("data")
        if not isinstance(data, list):
            raise UpstreamInvalidResponseError("snowflake")
        rows: list[dict[str, Any]] = []
        for row in data:
            if not isinstance(row, list) or len(row) != len(columns):
                raise UpstreamInvalidResponseError("snowflake")
            rows.append(dict(zip(columns, row, strict=True)))
        return rows
