import json
from typing import Any

from app.core.exceptions import UpstreamInvalidResponseError, UpstreamRequestError
from app.services.auth.snowflake_session_store import SnowflakeConnection

_GET_LINEAGE_SQL = """
SELECT
    DISTANCE,
    SOURCE_OBJECT_DATABASE,
    SOURCE_OBJECT_SCHEMA,
    SOURCE_OBJECT_NAME,
    SOURCE_OBJECT_DOMAIN,
    SOURCE_COLUMN_NAME,
    SOURCE_STATUS,
    TARGET_OBJECT_DATABASE,
    TARGET_OBJECT_SCHEMA,
    TARGET_OBJECT_NAME,
    TARGET_OBJECT_DOMAIN,
    TARGET_COLUMN_NAME,
    TARGET_STATUS,
    PROCESS
FROM TABLE(SNOWFLAKE.CORE.GET_LINEAGE(%s, %s, %s, %s))
""".strip()


class SnowflakeLineageQueryClient:
    def get_lineage(
        self,
        connection: SnowflakeConnection,
        *,
        object_name: str,
        object_domain: str,
        direction: str,
        max_distance: int,
    ) -> list[dict[str, Any]]:
        cursor = connection.cursor()
        description = None
        rows: list[Any] = []
        try:
            cursor.execute(
                _GET_LINEAGE_SQL,
                (object_name, object_domain, direction, max_distance),
            )
            description = cursor.description
            rows = cursor.fetchall()
        except Exception as exc:
            raise UpstreamRequestError("snowflake") from exc
        finally:
            self._close(cursor)

        if not description:
            raise UpstreamInvalidResponseError("snowflake")
        columns = [str(item[0]).upper() for item in description]
        results: list[dict[str, Any]] = []
        for row in rows:
            if len(row) != len(columns):
                raise UpstreamInvalidResponseError("snowflake")
            mapped = dict(zip(columns, row, strict=True))
            mapped["PROCESS"] = self._process(mapped.get("PROCESS"))
            results.append(mapped)
        return results

    @staticmethod
    def _process(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except ValueError:
            return value

    @staticmethod
    def _close(cursor: Any) -> None:
        try:
            cursor.close()
        except Exception:  # noqa: BLE001 - cursor cleanup boundary
            return
