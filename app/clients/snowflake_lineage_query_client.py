# import json
# from typing import Any

# from app.core.exceptions import UpstreamInvalidResponseError, UpstreamRequestError
# from app.services.auth.snowflake_session_store import SnowflakeConnection

# _GET_LINEAGE_SQL = """
# SELECT
#     DISTANCE,
#     SOURCE_OBJECT_DATABASE,
#     SOURCE_OBJECT_SCHEMA,
#     SOURCE_OBJECT_NAME,
#     SOURCE_OBJECT_DOMAIN,
#     SOURCE_COLUMN_NAME,
#     SOURCE_STATUS,
#     TARGET_OBJECT_DATABASE,
#     TARGET_OBJECT_SCHEMA,
#     TARGET_OBJECT_NAME,
#     TARGET_OBJECT_DOMAIN,
#     TARGET_COLUMN_NAME,
#     TARGET_STATUS,
#     PROCESS
# FROM TABLE(SNOWFLAKE.CORE.GET_LINEAGE(%s, %s, %s, %s))
# """.strip()


# class SnowflakeLineageQueryClient:
#     def get_lineage(
#         self,
#         connection: SnowflakeConnection,
#         *,
#         object_name: str,
#         object_domain: str,
#         direction: str,
#         max_distance: int,
#     ) -> list[dict[str, Any]]:
#         description = None
#         rows: list[Any] = []
#         cursor = None
#         try:
#             # Opening the cursor has to be inside the guard too: on a
#             # connection that has dropped or been left in a bad state, this is
#             # where the connector raises, and an unwrapped driver exception
#             # escapes every `AppException` handler above and 500s the request.
#             cursor = connection.cursor()
#             cursor.execute(
#                 _GET_LINEAGE_SQL,
#                 (object_name, object_domain, direction, max_distance),
#             )
#             description = cursor.description
#             rows = cursor.fetchall()
#         except Exception as exc:
#             raise UpstreamRequestError("snowflake", detail=str(exc)) from exc
#         finally:
#             if cursor is not None:
#                 self._close(cursor)

#         if not description:
#             raise UpstreamInvalidResponseError("snowflake")
#         columns = [str(item[0]).upper() for item in description]
#         results: list[dict[str, Any]] = []
#         for row in rows:
#             if len(row) != len(columns):
#                 raise UpstreamInvalidResponseError("snowflake")
#             mapped = dict(zip(columns, row, strict=True))
#             mapped["PROCESS"] = self._process(mapped.get("PROCESS"))
#             results.append(mapped)
#         return results

#     @staticmethod
#     def _process(value: Any) -> Any:
#         if not isinstance(value, str):
#             return value
#         try:
#             return json.loads(value)
#         except ValueError:
#             return value

#     @staticmethod
#     def _close(cursor: Any) -> None:
#         try:
#             cursor.close()
#         except Exception:  # noqa: BLE001 - cursor cleanup boundary
#             return

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

_CALL_CUSTOM_SP_SQL = """
CALL SALES_ANALYTICS.REPORTING.TRACE_COLUMN_LINEAGE(%s, %s, %s, %s)
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
        # Intercept COLUMN queries to use the custom stored procedure
        if object_domain.upper() == "COLUMN":
            return self._get_column_lineage_via_sp(
                connection, object_name, direction, max_distance
            )

        # Standard processing for TABLE/VIEW level requests
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
            mapped["PROCESS"] = self._process(mapped.get("PROCESS"))
            results.append(mapped)
        return results

    def _get_column_lineage_via_sp(
        self,
        connection: SnowflakeConnection,
        object_name: str,
        direction: str,
        max_distance: int,
    ) -> list[dict[str, Any]]:
        # Extract table fully qualified name and column name from DB.SCHEMA.TABLE.COLUMN
        parts = object_name.rsplit(".", 1)
        if len(parts) == 2:
            table_fqn, column_name = parts
        else:
            table_fqn, column_name = object_name, ""

        description = None
        rows: list[Any] = []
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(
                _CALL_CUSTOM_SP_SQL,
                (table_fqn, column_name, direction, max_distance),
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

            mapped_sp = dict(zip(columns, row, strict=True))

            # Split SOURCE_FULLY_QUALIFIED_NAME (DB.SCHEMA.TABLE) provided by SP
            src_fqn = str(mapped_sp.get("SOURCE_FULLY_QUALIFIED_NAME") or "")
            src_db, src_schema, src_table = self._split_fqn(src_fqn)

            # Split PARENT_OBJECT_NAME (DB.SCHEMA.TABLE.COLUMN) provided by SP
            tgt_full = str(mapped_sp.get("PARENT_OBJECT_NAME") or "")
            tgt_parts = tgt_full.rsplit(".", 1)
            tgt_fqn = tgt_parts[0] if len(tgt_parts) == 2 else tgt_full
            tgt_col = tgt_parts[1] if len(tgt_parts) == 2 else ""
            tgt_db, tgt_schema, tgt_table = self._split_fqn(tgt_fqn)

            # Map the SP output to the exact dictionary schema the Deep Lineage service demands
            mapped = {
                "DISTANCE": mapped_sp.get("LINEAGE_LEVEL"),
                "SOURCE_OBJECT_DATABASE": src_db,
                "SOURCE_OBJECT_SCHEMA": src_schema,
                "SOURCE_OBJECT_NAME": src_table,
                "SOURCE_OBJECT_DOMAIN": mapped_sp.get("SOURCE_OBJECT_TYPE", "COLUMN").upper(),
                "SOURCE_COLUMN_NAME": mapped_sp.get("SOURCE_COLUMN_NAME"),
                "SOURCE_STATUS": "ACTIVE",
                "TARGET_OBJECT_DATABASE": tgt_db,
                "TARGET_OBJECT_SCHEMA": tgt_schema,
                "TARGET_OBJECT_NAME": tgt_table,
                "TARGET_OBJECT_DOMAIN": mapped_sp.get("PARENT_OBJECT_TYPE", "COLUMN").upper(),
                "TARGET_COLUMN_NAME": tgt_col,
                "TARGET_STATUS": "ACTIVE",
                "PROCESS": None,
                "COLUMN_TRANSFORMATION": mapped_sp.get("COLUMN_TRANSFORMATION"),
                "MODIFICATION_SQL": mapped_sp.get("MODIFICATION_SQL"),
            }
            results.append(mapped)

        return results

    @staticmethod
    def _split_fqn(fqn: str) -> tuple[str, str, str]:
        """Safely parses DB.SCHEMA.TABLE strings into distinct parts."""
        parts = fqn.split(".")
        db = parts[0] if len(parts) > 0 else ""
        schema = parts[1] if len(parts) > 1 else ""
        table = parts[2] if len(parts) > 2 else ""
        return db, schema, table

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
        