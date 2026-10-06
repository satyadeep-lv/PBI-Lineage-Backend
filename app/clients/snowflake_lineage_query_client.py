import json
from typing import Any

from app.core.exceptions import UpstreamInvalidResponseError, UpstreamRequestError
from app.services.auth.snowflake_session_store import SnowflakeConnection

# SELECT * rather than a fixed column list: Snowflake has been adding columns
# to this function (SOURCE_DETAILS / TARGET_DETAILS carry the granular object
# type), and naming a column an older account lacks would fail every trace.
_GET_LINEAGE_SQL = """
SELECT *
FROM TABLE(SNOWFLAKE.CORE.GET_LINEAGE(%s, %s, %s, %s))
""".strip()
# Semi-structured columns arrive from the connector as JSON text.
_VARIANT_COLUMNS = ("PROCESS", "SOURCE_DETAILS", "TARGET_DETAILS")
# The connection's network_timeout (60 s) otherwise doubles as a client-side
# cancel timer on every statement, which a wide lineage graph can outlast.
_GET_LINEAGE_TIMEOUT_SECONDS = 120


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
        description = None
        rows: list[Any] = []
        cursor = None
        try:
            # Opening the cursor has to be inside the guard too: on a
            # connection that has dropped or been left in a bad state, this is
            # where the connector raises, and an unwrapped driver exception
            # escapes every `AppException` handler above and 500s the request.
            cursor = connection.cursor()
            cursor.execute(
                _GET_LINEAGE_SQL,
                (object_name, object_domain, direction, max_distance),
                timeout=_GET_LINEAGE_TIMEOUT_SECONDS,
            )
            description = cursor.description
            rows = cursor.fetchall()
        except Exception as exc:
            raise UpstreamRequestError("snowflake", detail=str(exc)) from exc
        finally:
            if cursor is not None:
                self._close(cursor)

        if not description:
            raise UpstreamInvalidResponseError("snowflake")
        columns = [str(item[0]).upper() for item in description]
        results: list[dict[str, Any]] = []
        for row in rows:
            if len(row) != len(columns):
                raise UpstreamInvalidResponseError("snowflake")
            mapped = dict(zip(columns, row, strict=True))
            for column in _VARIANT_COLUMNS:
                if column in mapped:
                    mapped[column] = self._variant(mapped[column])
            results.append(mapped)
        return results

    @staticmethod
    def _variant(value: Any) -> Any:
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
