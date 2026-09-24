import json
import re
from dataclasses import dataclass
from typing import Literal

from app.domain.lineage_ids import stable_lineage_id
from app.schemas.gateway import GatewayDatasource
from app.schemas.parsed_semantic_model import ParsedSemanticModelResponse
from app.schemas.physical_source import (
    PhysicalDataSource,
    PhysicalSourceDiscoveryResponse,
    PhysicalSourceWarning,
    QuerySourceMapping,
)
from app.services.sql_column_parser import split_dotted_identifier

_DATABASE_CONNECTORS = {
    "sql.database": "sqlserver",
    "snowflake.databases": "snowflake",
    "postgresql.database": "postgresql",
    "mysql.database": "mysql",
    "oracle.database": "oracle",
    # DirectQuery to a Power BI/AS semantic model: argument 0 is the XMLA
    # workspace endpoint and argument 1 is the upstream model, so the same
    # (server, database) shape as the SQL connectors above.
    "analysisservices.database": "analysis_services",
}
# `Snowflake.Databases(server, warehouse, options)` -- the second positional
# argument names the compute warehouse, not a database. Reading it as the
# database silently mislabels every Snowflake table whose database is only
# knowable from the navigation step or the native query.
_WAREHOUSE_POSITIONAL_CONNECTORS = frozenset({"snowflake.databases"})
_URL_CONNECTORS = {
    "odata.feed": "odata",
    "web.contents": "web",
    "sharepoint.files": "sharepoint",
    "sharepoint.contents": "sharepoint",
    "azuredatalakestorage.contents": "azure_data_lake",
}
_PATH_CONNECTORS = {
    "file.contents": "file",
    "folder.files": "folder",
}
_ACCOUNT_CONNECTORS = {
    "azurestorage.blobs": "azure_blob",
}
_OTHER_CONNECTORS = {
    "odbc.datasource": "odbc",
}
_NAVIGATION_PATTERN = re.compile(
    r"\[\s*(?:Schema|Name)\s*=\s*\"(?P<schema>(?:\"\"|[^\"])*)\""
    r"\s*,\s*(?:Item|Name)\s*=\s*\"(?P<object>(?:\"\"|[^\"])*)\"\s*\]",
    re.IGNORECASE,
)
_KIND_NAVIGATION_PATTERN = re.compile(
    r"\[\s*Name\s*=\s*\"(?P<name>(?:\"\"|[^\"])*)\""
    r"\s*,\s*Kind\s*=\s*\"(?P<kind>Database|Schema|Table|View)\"\s*\]",
    re.IGNORECASE,
)
_SQL_OBJECT_IDENTIFIER = r"\"[^\"]+\"|`[^`]+`|\[[^\]]+\]|[A-Za-z_][\w$]*"
_SQL_OBJECT_PATTERN = re.compile(
    rf"\b(?:from|join)\s+((?:{_SQL_OBJECT_IDENTIFIER})"
    rf"(?:\s*\.\s*(?:{_SQL_OBJECT_IDENTIFIER})){{0,2}})",
    re.IGNORECASE,
)
_SAFE_GATEWAY_KEYS = {
    "account",
    "database",
    "domain",
    "path",
    "server",
    "url",
    "warehouse",
}


@dataclass(frozen=True)
class _FunctionCall:
    name: str
    arguments: list[str]


class PhysicalSourceDiscoveryService:
    def discover(
        self,
        semantic_model: ParsedSemanticModelResponse,
        *,
        gateway_datasources: list[GatewayDatasource] | None = None,
    ) -> PhysicalSourceDiscoveryResponse:
        sources: dict[str, PhysicalDataSource] = {}
        mappings: list[QuerySourceMapping] = []
        warnings: list[PhysicalSourceWarning] = []
        shared_expressions = {
            expression.name.casefold(): (expression.expression or "")
            for expression in semantic_model.expressions
            if expression.name
        }

        for table in semantic_model.tables:
            if not table.partitions and not table.expression:
                # A table with no partition at all is neither a calculated
                # table nor an importable one -- without this it would drop
                # out of every downstream dataset with no trace at all.
                mappings.append(
                    QuerySourceMapping(
                        query_id=stable_lineage_id(
                            "query",
                            semantic_model.workspace_id,
                            semantic_model.semantic_model_id,
                            table.name,
                            "",
                        ),
                        semantic_table=table.name,
                        partition_name="",
                        source_path=table.source_path,
                        source_ids=[],
                    )
                )

            for partition in table.partitions:
                if (partition.source_type or "").casefold() == "calculated":
                    continue
                expression = partition.expression or ""
                if not expression.strip() and partition.expression_source:
                    expression = shared_expressions.get(
                        partition.expression_source.casefold(),
                        "",
                    )
                partition_sources = self._parse_expression(
                    expression,
                    entity_name=partition.entity_name,
                    schema_name=partition.schema_name,
                )

                if not partition_sources:
                    warnings.append(
                        PhysicalSourceWarning(
                            code="POWER_QUERY_SOURCE_NOT_DETECTED",
                            message=(
                                "No supported physical source was detected "
                                "in the partition."
                            ),
                            source_path=partition.source_path,
                        )
                    )

                source_ids: list[str] = []
                for source in partition_sources:
                    sources.setdefault(source.source_id, source)
                    source_ids.append(source.source_id)

                mappings.append(
                    QuerySourceMapping(
                        query_id=stable_lineage_id(
                            "query",
                            semantic_model.workspace_id,
                            semantic_model.semantic_model_id,
                            table.name,
                            partition.name,
                        ),
                        semantic_table=table.name,
                        partition_name=partition.name,
                        source_path=partition.source_path,
                        source_ids=source_ids,
                    )
                )

        gateway_sources = self._parse_gateway_datasources(
            gateway_datasources or [],
            warnings,
        )
        self._attach_gateway_sources(sources, gateway_sources)

        for source in gateway_sources:
            sources.setdefault(source.source_id, source)

        ordered_sources = sorted(sources.values(), key=lambda item: item.source_id)
        return PhysicalSourceDiscoveryResponse(
            workspace_id=semantic_model.workspace_id,
            semantic_model_id=semantic_model.semantic_model_id,
            sources=ordered_sources,
            mappings=mappings,
            warnings=warnings,
            source_count=len(ordered_sources),
            mapping_count=len(mappings),
        )

    def _parse_expression(
        self,
        expression: str,
        *,
        entity_name: str | None = None,
        schema_name: str | None = None,
    ) -> list[PhysicalDataSource]:
        navigation = self._navigation_target(expression)
        navigated_database = self._navigated_database(expression)
        native_queries = self._native_queries(expression)
        sources: dict[str, PhysicalDataSource] = {}

        for call in _find_function_calls(expression):
            normalized_name = call.name.casefold()

            if normalized_name in _DATABASE_CONNECTORS:
                server = _string_argument(call.arguments, 0)
                warehouse = _record_string(call.arguments, "Warehouse")
                if normalized_name in _WAREHOUSE_POSITIONAL_CONNECTORS:
                    database = None
                    warehouse = warehouse or _string_argument(call.arguments, 1)
                else:
                    database = _string_argument(call.arguments, 1)
                candidates = native_queries or [None]

                for native_query in candidates:
                    sql_objects = _sql_objects(native_query) if native_query else []
                    object_candidates = (
                        [(db, schema, obj, None) for db, schema, obj in sql_objects]
                        if sql_objects
                        else (
                            [navigation] if navigation else [(None, None, None, None)]
                        )
                    )

                    for object_target in object_candidates:
                        (
                            sql_database,
                            target_schema,
                            object_name,
                            object_kind,
                        ) = object_target
                        # An `entity` partition carries the upstream object
                        # name beside the connection, not inside the M.
                        object_name = object_name or entity_name
                        target_schema = target_schema or schema_name
                        source = self._source(
                            kind="database",
                            provider=_DATABASE_CONNECTORS[normalized_name],
                            connector=call.name,
                            server=server,
                            database=(sql_database or database or navigated_database),
                            schema_name=target_schema,
                            object_name=object_name,
                            object_kind=object_kind,
                            warehouse=warehouse,
                            native_query=native_query,
                        )
                        sources.setdefault(source.source_id, source)
                continue

            if normalized_name in _URL_CONNECTORS:
                url = _string_argument(call.arguments, 0)
                provider = _URL_CONNECTORS[normalized_name]
                source = self._source(
                    kind="odata" if provider == "odata" else "web",
                    provider=provider,
                    connector=call.name,
                    url=url,
                )
                sources.setdefault(source.source_id, source)
                continue

            if normalized_name in _PATH_CONNECTORS:
                source = self._source(
                    kind="file",
                    provider=_PATH_CONNECTORS[normalized_name],
                    connector=call.name,
                    path=_string_argument(call.arguments, 0),
                )
                sources.setdefault(source.source_id, source)
                continue

            if normalized_name in _ACCOUNT_CONNECTORS:
                source = self._source(
                    kind="storage",
                    provider=_ACCOUNT_CONNECTORS[normalized_name],
                    connector=call.name,
                    account=_string_argument(call.arguments, 0),
                )
                sources.setdefault(source.source_id, source)
                continue

            if normalized_name in _OTHER_CONNECTORS:
                source = self._source(
                    kind="database",
                    provider=_OTHER_CONNECTORS[normalized_name],
                    connector=call.name,
                    server=_string_argument(call.arguments, 0),
                )
                sources.setdefault(source.source_id, source)

        return list(sources.values())

    def _parse_gateway_datasources(
        self,
        datasources: list[GatewayDatasource],
        warnings: list[PhysicalSourceWarning],
    ) -> list[PhysicalDataSource]:
        parsed: list[PhysicalDataSource] = []

        for datasource in datasources:
            details = self._safe_connection_details(datasource, warnings)
            if details is None:
                continue

            provider = (datasource.datasource_type or "gateway").casefold()
            parsed.append(
                self._source(
                    kind="gateway",
                    provider=provider,
                    connector=datasource.datasource_type,
                    server=details.get("server") or details.get("domain"),
                    database=details.get("database"),
                    path=details.get("path"),
                    url=details.get("url"),
                    account=details.get("account"),
                    warehouse=details.get("warehouse"),
                    gateway_id=datasource.gateway_id,
                    gateway_datasource_id=datasource.id,
                    sso_enabled=datasource.sso_enabled,
                )
            )

        return parsed

    @staticmethod
    def _safe_connection_details(
        datasource: GatewayDatasource,
        warnings: list[PhysicalSourceWarning],
    ) -> dict[str, str] | None:
        if not datasource.connection_details:
            return {}

        try:
            payload = json.loads(datasource.connection_details)
        except (TypeError, ValueError):
            warnings.append(
                PhysicalSourceWarning(
                    code="GATEWAY_CONNECTION_DETAILS_INVALID",
                    message="Gateway connectionDetails is not valid JSON.",
                    datasource_id=datasource.id,
                )
            )
            return None

        if not isinstance(payload, dict):
            warnings.append(
                PhysicalSourceWarning(
                    code="GATEWAY_CONNECTION_DETAILS_INVALID",
                    message="Gateway connectionDetails must be a JSON object.",
                    datasource_id=datasource.id,
                )
            )
            return None

        return {
            str(key).casefold(): str(value).strip()
            for key, value in payload.items()
            if str(key).casefold() in _SAFE_GATEWAY_KEYS
            and isinstance(value, (str, int, float))
            and str(value).strip()
        }

    @staticmethod
    def _attach_gateway_sources(
        sources: dict[str, PhysicalDataSource],
        gateway_sources: list[PhysicalDataSource],
    ) -> None:
        for source in sources.values():
            for gateway_source in gateway_sources:
                if not _same_endpoint(source, gateway_source):
                    continue

                source.gateway_id = gateway_source.gateway_id
                source.gateway_datasource_id = gateway_source.gateway_datasource_id
                source.sso_enabled = gateway_source.sso_enabled
                break

    @staticmethod
    def _navigation_target(
        expression: str,
    ) -> tuple[str | None, str | None, str, Literal["table", "view"] | None] | None:
        kind_values: dict[str, str] = {}
        for match in _KIND_NAVIGATION_PATTERN.finditer(expression):
            kind_values.setdefault(
                match.group("kind").casefold(),
                match.group("name").replace('""', '"'),
            )

        for kind in ("table", "view"):
            object_name = kind_values.get(kind)
            if object_name:
                return (
                    kind_values.get("database"),
                    kind_values.get("schema"),
                    object_name,
                    kind,
                )

        match = _NAVIGATION_PATTERN.search(expression)
        if not match:
            return None
        return (
            None,
            match.group("schema").replace('""', '"'),
            match.group("object").replace('""', '"'),
            None,
        )

    @staticmethod
    def _navigated_database(expression: str) -> str | None:
        # The database can be navigated to even when the object itself comes
        # from a native query rather than a `Kind="Table"` step.
        for match in _KIND_NAVIGATION_PATTERN.finditer(expression):
            if match.group("kind").casefold() == "database":
                return match.group("name").replace('""', '"')
        return None

    @staticmethod
    def _native_queries(expression: str) -> list[str]:
        queries: list[str] = []

        for call in _find_function_calls(expression):
            if call.name.casefold() == "value.nativequery":
                query = _string_argument(call.arguments, 1)
                if query:
                    queries.append(query)

            query = _record_string(call.arguments, "Query")
            if query:
                queries.append(query)

        return list(dict.fromkeys(queries))

    @staticmethod
    def _source(
        *,
        kind: str,
        provider: str,
        connector: str | None = None,
        server: str | None = None,
        database: str | None = None,
        schema_name: str | None = None,
        object_name: str | None = None,
        object_kind: Literal["table", "view"] | None = None,
        path: str | None = None,
        url: str | None = None,
        account: str | None = None,
        warehouse: str | None = None,
        native_query: str | None = None,
        gateway_id: str | None = None,
        gateway_datasource_id: str | None = None,
        sso_enabled: bool | None = None,
    ) -> PhysicalDataSource:
        source_id = stable_lineage_id(
            "source",
            provider,
            server,
            database,
            schema_name,
            object_name,
            path,
            url,
            account,
            warehouse,
            gateway_datasource_id if not any((server, path, url, account)) else None,
        )
        return PhysicalDataSource(
            source_id=source_id,
            kind=kind,
            provider=provider,
            connector=connector,
            server=server,
            database=database,
            schema_name=schema_name,
            object_name=object_name,
            object_kind=object_kind,
            path=path,
            url=url,
            account=account,
            warehouse=warehouse,
            native_query=native_query,
            gateway_id=gateway_id,
            gateway_datasource_id=gateway_datasource_id,
            sso_enabled=sso_enabled,
        )


def _find_function_calls(expression: str) -> list[_FunctionCall]:
    calls: list[_FunctionCall] = []
    index = 0

    while index < len(expression):
        if expression.startswith("//", index):
            line_end = expression.find("\n", index + 2)
            index = len(expression) if line_end < 0 else line_end + 1
            continue
        if expression.startswith("/*", index):
            comment_end = expression.find("*/", index + 2)
            index = len(expression) if comment_end < 0 else comment_end + 2
            continue
        if expression[index] == '"':
            index = _after_string(expression, index)
            continue

        match = re.match(r"[A-Za-z_][A-Za-z0-9_.]*\s*\(", expression[index:])
        if not match:
            index += 1
            continue

        name_end = index + match.group(0).rfind("(")
        name = expression[index:name_end].strip()
        close_index = _matching_parenthesis(expression, name_end)
        if close_index is None:
            index = name_end + 1
            continue

        arguments = _split_arguments(expression[name_end + 1 : close_index])
        calls.append(_FunctionCall(name=name, arguments=arguments))
        index = name_end + 1

    return calls


def _matching_parenthesis(expression: str, opening_index: int) -> int | None:
    depth = 0
    state = "code"
    index = opening_index

    while index < len(expression):
        character = expression[index]
        next_character = expression[index + 1] if index + 1 < len(expression) else ""

        if state == "string":
            if character == '"' and next_character == '"':
                index += 2
                continue
            if character == '"':
                state = "code"
            index += 1
            continue

        if state == "line_comment":
            if character in "\r\n":
                state = "code"
            index += 1
            continue

        if state == "block_comment":
            if character == "*" and next_character == "/":
                state = "code"
                index += 2
            else:
                index += 1
            continue

        if character == '"':
            state = "string"
        elif character == "/" and next_character == "/":
            state = "line_comment"
            index += 1
        elif character == "/" and next_character == "*":
            state = "block_comment"
            index += 1
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1

    return None


def _split_arguments(value: str) -> list[str]:
    arguments: list[str] = []
    start = 0
    depths = {"(": 0, "[": 0, "{": 0}
    closing = {")": "(", "]": "[", "}": "{"}
    state = "code"
    index = 0

    while index < len(value):
        character = value[index]
        next_character = value[index + 1] if index + 1 < len(value) else ""

        if state == "string":
            if character == '"' and next_character == '"':
                index += 2
                continue
            if character == '"':
                state = "code"
            index += 1
            continue

        if state == "line_comment":
            if character in "\r\n":
                state = "code"
            index += 1
            continue

        if state == "block_comment":
            if character == "*" and next_character == "/":
                state = "code"
                index += 2
            else:
                index += 1
            continue

        if character == '"':
            state = "string"
        elif character == "/" and next_character == "/":
            state = "line_comment"
            index += 1
        elif character == "/" and next_character == "*":
            state = "block_comment"
            index += 1
        elif character in depths:
            depths[character] += 1
        elif character in closing:
            opener = closing[character]
            depths[opener] = max(0, depths[opener] - 1)
        elif character == "," and not any(depths.values()):
            arguments.append(value[start:index].strip())
            start = index + 1
        index += 1

    remainder = value[start:].strip()
    if remainder:
        arguments.append(remainder)
    return arguments


def _after_string(expression: str, opening_index: int) -> int:
    index = opening_index + 1
    while index < len(expression):
        if expression[index] != '"':
            index += 1
            continue
        if index + 1 < len(expression) and expression[index + 1] == '"':
            index += 2
            continue
        return index + 1
    return len(expression)


def _string_argument(arguments: list[str], index: int) -> str | None:
    if index >= len(arguments):
        return None
    value = arguments[index].strip()
    if len(value) < 2 or not value.startswith('"') or not value.endswith('"'):
        return None
    return value[1:-1].replace('""', '"')


def _record_string(arguments: list[str], key: str) -> str | None:
    pattern = re.compile(
        rf"\b{re.escape(key)}\s*=\s*\"(?P<value>(?:\"\"|[^\"])*)\"",
        re.IGNORECASE,
    )
    for argument in arguments:
        match = pattern.search(argument)
        if match:
            return match.group("value").replace('""', '"')
    return None


def _sql_objects(query: str) -> list[tuple[str | None, str | None, str]]:
    """Extract (database, schema, object) triples referenced by ``FROM``/
    ``JOIN`` in a native SQL query. Supports quoted/bracketed/backtick
    identifiers and up to three dotted parts; a bare or two-part reference
    leaves the missing leading part(s) as ``None``.
    """
    objects: list[tuple[str | None, str | None, str]] = []
    seen: set[tuple[str | None, str | None, str]] = set()

    for match in _SQL_OBJECT_PATTERN.finditer(query):
        raw_identifier = match.group(1)
        if raw_identifier.strip().startswith("("):
            continue

        parts = split_dotted_identifier(raw_identifier)
        if not parts:
            continue

        database: str | None = None
        schema_name: str | None = None
        object_name = parts[-1]

        if len(parts) == 3:
            database, schema_name, object_name = parts[-3], parts[-2], parts[-1]
        elif len(parts) == 2:
            schema_name, object_name = parts[-2], parts[-1]

        target = (database, schema_name, object_name)
        if target not in seen:
            seen.add(target)
            objects.append(target)

    return objects


def _same_endpoint(left: PhysicalDataSource, right: PhysicalDataSource) -> bool:
    pairs = (
        (left.server, right.server),
        (left.database, right.database),
        (left.path, right.path),
        (left.url, right.url),
        (left.account, right.account),
    )
    comparable = [(a, b) for a, b in pairs if a and b]
    return bool(comparable) and all(a.casefold() == b.casefold() for a, b in comparable)
