"""360-degree evidence about one object, one report, or the model in view.

A good answer to "explain Total Revenue" is not just its DAX: it says which
semantic model it lives in, which measures and columns it reads, which
database tables those columns come from, what is built on top of it, which
tables that touches, and which visuals would change if it did. The narrower
tools each answered one of those; a reader had to ask five questions to get
the picture. These dossiers gather all of it in one deterministic pass.

Everything here is read from the already-authorized `ResolvedAIContext`:
the parsed model, its DAX dependency graph, its physical sources (with
composite-model hops already followed), and the report definitions the
caller could open. Nothing is inferred, and every item says where it came
from.
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.ai.composition.dax_narrator import describe
from app.ai.models.context import ResolvedAIContext, ResolvedObject, ResolvedReport
from app.ai.models.enums import VerificationStatus
from app.ai.models.evidence import EvidenceFactType, EvidenceItem, EvidenceSourceType
from app.domain.dax_lineage import physical_sources_by_table
from app.schemas.dax_dependency import DaxObjectReference
from app.schemas.normalized_report_definition import (
    NormalizedReportDefinitionResponse,
)
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelMeasure,
    ParsedSemanticModelTable,
)
from app.schemas.physical_source import PhysicalDataSource
from app.schemas.report_semantic_lineage import SemanticLineageObject
from app.services.dax_dependency_service import DaxDependencyService
from app.services.physical_source_service import PhysicalSourceDiscoveryService
from app.services.report_semantic_lineage_service import ReportSemanticLineageService

# Bounds that keep one dossier readable (and inside a model's tool-result
# budget) on a large model. Truncation is always stated, never silent.
_MAX_DAX_CHARS = 600
_MAX_VISUALS = 60
_MAX_VISUALS_PER_PAGE = 25
_MAX_MODEL_MEASURES = 80
_MAX_LISTED_COLUMNS = 12

_PROVIDER_LABELS = {
    "snowflake": "Snowflake",
    "sqlserver": "SQL Server",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "oracle": "Oracle",
    "analysis_services": "Power BI semantic model",
    "odata": "OData feed",
    "web": "Web source",
    "sharepoint": "SharePoint",
    "azure_data_lake": "Azure Data Lake",
    "file": "File",
    "folder": "Folder",
    "azure_blob": "Azure Blob Storage",
    "odbc": "ODBC source",
}

_OBJECT_TYPE_LABELS = {
    "measure": "measure",
    "calculated_column": "calculated column",
    "column": "column",
    "table": "table",
    "calculated_table": "calculated table",
}


# ---------------------------------------------------------------------------
# Public dossiers
# ---------------------------------------------------------------------------


def object_dossier(context: ResolvedAIContext) -> list[EvidenceItem]:
    """Everything known about `context.resolved_object`, in reading order."""
    resolved = context.resolved_object
    if resolved is None or context.parsed_semantic_model is None:
        return []

    index = _ModelIndex(context)
    builder = _EvidenceBuilder(context)
    members = index.members(resolved)

    if not members:
        return []

    builder.add(
        fact_type="relationship",
        object_type="context",
        object_name=resolved.object_name,
        object_id=resolved.qualified_name,
        value={
            "object": resolved.qualified_name,
            "object_type": resolved.object_type,
            "table": resolved.table_name,
            **_model_identity(context),
        },
        display_value=_identity_sentence(context, resolved),
        source_type="tmdl",
        source_reference=f"semantic_model:{context.semantic_model_id}",
    )

    _add_definition(builder, index, resolved)

    upstream = index.walk(members, upstream=True)
    _add_upstream(builder, index, upstream)
    _add_database_lineage(builder, index, resolved, upstream)

    downstream = index.walk(members, upstream=False)
    _add_downstream(builder, index, downstream)
    _add_table_impact(builder, index, resolved, downstream)

    impacted = set(members) | set(downstream)
    _add_visual_impact(builder, index, context, impacted, resolved)

    for note in context.coverage_notes:
        builder.coverage(note)

    return builder.items


def report_dossier(context: ResolvedAIContext) -> list[EvidenceItem]:
    """The report in view: pages, visuals, fields, measures, and sources."""
    report = context.report_definition
    if report is None:
        return []

    builder = _EvidenceBuilder(context)
    index = _ModelIndex(context) if context.parsed_semantic_model else None

    report_name = context.report_name or report.report_id
    model_label = _model_label(context)
    builder.add(
        fact_type="definition",
        object_type="report",
        object_name=report_name,
        object_id=report.report_id,
        value={
            "report": report_name,
            "format": report.format,
            "page_count": report.page_count,
            "visual_count": report.visual_count,
            **_model_identity(context),
        },
        display_value=(
            f"Report '{report_name}'"
            + (
                f" in workspace '{context.workspace_name}'"
                if context.workspace_name
                else ""
            )
            + (f", built on semantic model {model_label}" if model_label else "")
            + f" ({report.format}, {report.page_count} page"
            + ("" if report.page_count == 1 else "s")
            + f", {report.visual_count} visual"
            + ("" if report.visual_count == 1 else "s")
            + ")."
        ),
        source_type="pbir",
        source_reference=f"report:{report.report_id}",
    )

    _add_pages(builder, report)

    if index is None:
        builder.coverage(
            "The report's semantic model could not be read, so the fields "
            "below are named as the report references them, without DAX or "
            "database lineage."
        )
        _add_raw_fields(builder, report)
    else:
        _add_report_fields(builder, index, context, report)

    for note in context.coverage_notes:
        builder.coverage(note)

    return builder.items


def model_dossier(context: ResolvedAIContext) -> list[EvidenceItem]:
    """The semantic model in view: tables, measures, relationships, sources."""
    model = context.parsed_semantic_model
    if model is None:
        return []

    index = _ModelIndex(context)
    builder = _EvidenceBuilder(context)
    model_label = _model_label(context) or "This semantic model"

    measures = [
        (table, measure) for table in model.tables for measure in table.measures
    ]
    column_count = sum(len(table.columns) for table in model.tables)
    builder.add(
        fact_type="definition",
        object_type="semantic_model",
        object_name=context.semantic_model_name or "This semantic model",
        object_id=model.semantic_model_id,
        value={
            "table_count": len(model.tables),
            "measure_count": len(measures),
            "column_count": column_count,
            "table_names": [table.name for table in model.tables],
            "measures_by_table": {
                table.name: [measure.name for measure in table.measures]
                for table in model.tables
                if table.measures
            },
            **_model_identity(context),
        },
        display_value=(
            f"Semantic model {model_label}"
            + (
                f" in workspace '{context.semantic_model_workspace_name}'"
                if context.semantic_model_workspace_name
                else ""
            )
            + f" has {len(model.tables)} table"
            + ("" if len(model.tables) == 1 else "s")
            + f", {len(measures)} measure"
            + ("" if len(measures) == 1 else "s")
            + f" and {column_count} column"
            + ("" if column_count == 1 else "s")
            + "."
        ),
        source_type="tmdl",
        source_reference=f"semantic_model:{model.semantic_model_id}",
    )

    for table in model.tables:
        sources = index.sources_for_table(table.name)
        calculated = [column.name for column in table.columns if column.expression]
        parts = [
            f"{len(table.columns)} column" + ("" if len(table.columns) == 1 else "s")
        ]
        if table.measures:
            parts.append(
                f"measures: {', '.join(measure.name for measure in table.measures)}"
            )
        if calculated:
            parts.append(f"calculated columns: {', '.join(calculated)}")
        mode = _storage_mode(table)
        if mode:
            parts.append(f"{mode} mode")
        origin = (
            "calculated in DAX"
            if table.expression
            else (
                "loaded from "
                + "; ".join(describe_source(source) for source in sources)
                if sources
                else "source not identified"
            )
        )
        builder.add(
            fact_type="relationship",
            object_type="semantic_table",
            object_name=table.name,
            object_id=table.name,
            value={
                "table": table.name,
                "column_count": len(table.columns),
                "measures": [measure.name for measure in table.measures],
                "calculated_columns": calculated,
                "storage_mode": mode,
                "sources": [_source_value(source) for source in sources],
            },
            display_value=f"{table.name}: {'; '.join(parts)}; {origin}.",
            source_type="tmdl",
            source_reference=table.source_path,
        )

    for relationship in model.relationships:
        if not (relationship.from_table and relationship.to_table):
            continue
        detail = [
            part
            for part in (
                relationship.cardinality,
                "active" if relationship.is_active is not False else "inactive",
                (
                    f"filters {relationship.cross_filter_direction}"
                    if relationship.cross_filter_direction
                    else None
                ),
            )
            if part
        ]
        builder.add(
            fact_type="relationship",
            object_type="relationship",
            object_name=relationship.name
            or f"{relationship.from_table} to {relationship.to_table}",
            value=relationship.model_dump(exclude_none=True, exclude={"source_path"}),
            display_value=(
                f"{relationship.from_table}[{relationship.from_column}] -> "
                f"{relationship.to_table}[{relationship.to_column}]"
                + (f" ({', '.join(detail)})" if detail else "")
            ),
            source_type="tmdl",
            source_reference=relationship.source_path,
        )

    for table, measure in measures[:_MAX_MODEL_MEASURES]:
        if measure.expression:
            _add_measure_definition(builder, table.name, measure, brief=True)
    if len(measures) > _MAX_MODEL_MEASURES:
        builder.coverage(
            f"The model has {len(measures)} measures; the DAX of the first "
            f"{_MAX_MODEL_MEASURES} is included. Ask about any other by name."
        )

    for source in index.physical.sources:
        _add_source(builder, source, tables=index.tables_fed_by(source.source_id))

    for report in _reports_in_scope(context):
        builder.add(
            fact_type="usage",
            object_type="report",
            object_name=report.report_name or report.report_id,
            object_id=report.report_id,
            value={
                "report": report.report_name,
                "workspace": report.workspace_name,
                "page_count": report.definition.page_count,
                "visual_count": report.definition.visual_count,
            },
            display_value=(
                f"Report '{report.report_name or report.report_id}'"
                + (
                    f" in workspace '{report.workspace_name}'"
                    if report.workspace_name
                    else ""
                )
                + f" ({_count(report.definition.page_count, 'page')}, "
                f"{_count(report.definition.visual_count, 'visual')})"
            ),
            source_type="pbir",
            source_reference=f"report:{report.report_id}",
        )

    for note in context.coverage_notes:
        builder.coverage(note)

    return builder.items


def describe_source(source: PhysicalDataSource) -> str:
    """`Snowflake view DB.SCHEMA.V_SALES`, `File C:\\data\\sales.xlsx`, ..."""
    provider = _PROVIDER_LABELS.get(source.provider, source.provider)
    qualified = ".".join(
        part
        for part in (source.database, source.schema_name, source.object_name)
        if part
    )

    if qualified:
        kind = source.object_kind or (
            "database" if not source.object_name else "object"
        )
        text = f"{provider} {kind} {qualified}"
        if source.provider not in {"snowflake", "analysis_services"} and source.server:
            text += f" on {source.server}"
    else:
        location = source.path or source.url or source.server or source.account
        text = f"{provider} {location}" if location else provider

    if source.native_query:
        text += " (via a native SQL query)"

    if source.via_semantic_model_name:
        via = f"semantic model '{source.via_semantic_model_name}'"
        if source.via_workspace_name:
            via += f" in workspace '{source.via_workspace_name}'"
        text += f", reached through {via}"

    return text


# ---------------------------------------------------------------------------
# Model index: the DAX graph plus physical sources, keyed for walking
# ---------------------------------------------------------------------------


class _ModelIndex:
    def __init__(self, context: ResolvedAIContext) -> None:
        model = context.parsed_semantic_model
        assert model is not None
        self.model = model
        self.dax = DaxDependencyService().analyze(model)
        self.physical = (
            context.physical_sources or PhysicalSourceDiscoveryService().discover(model)
        )
        self._sources_by_table = physical_sources_by_table(self.physical)

        self.tables: dict[str, ParsedSemanticModelTable] = {
            table.name.casefold(): table for table in model.tables
        }
        self.measures: dict[str, tuple[str, ParsedSemanticModelMeasure]] = {}
        self.columns: dict[str, tuple[str, ParsedSemanticModelColumn]] = {}
        for table in model.tables:
            for measure in table.measures:
                self.measures[_key(table.name, measure.name)] = (table.name, measure)
            for column in table.columns:
                self.columns[_key(table.name, column.name)] = (table.name, column)

        self._predecessors: dict[str, list[str]] = defaultdict(list)
        self._successors: dict[str, list[str]] = defaultdict(list)
        self.references: dict[str, DaxObjectReference] = {}
        for edge in self.dax.dependencies:
            source = edge.source.qualified_name.casefold()
            target = edge.target.qualified_name.casefold()
            self._predecessors[target].append(source)
            self._successors[source].append(target)
            self.references.setdefault(source, edge.source)
            self.references.setdefault(target, edge.target)

        self._tables_by_source: dict[str, list[str]] = defaultdict(list)
        for mapping in self.physical.mappings:
            for source_id in mapping.source_ids:
                if mapping.semantic_table not in self._tables_by_source[source_id]:
                    self._tables_by_source[source_id].append(mapping.semantic_table)

    def members(self, resolved: ResolvedObject) -> list[str]:
        """The graph keys an object stands for; a table stands for its contents."""
        if resolved.object_type != "table":
            key = resolved.qualified_name.casefold()
            return [key] if key in self.measures or key in self.columns else []

        table = self.tables.get(resolved.table_name.casefold())
        if table is None:
            return []
        return [
            table.name.casefold(),
            *(_key(table.name, column.name) for column in table.columns),
            *(_key(table.name, measure.name) for measure in table.measures),
        ]

    def walk(self, starts: list[str], *, upstream: bool) -> dict[str, int]:
        """Every object reachable from `starts`, with its hop distance."""
        edges = self._predecessors if upstream else self._successors
        start_set = set(starts)
        distances: dict[str, int] = {}
        queue = deque((key, 0) for key in starts)

        while queue:
            current, distance = queue.popleft()
            for neighbour in edges.get(current, []):
                if neighbour in start_set or neighbour in distances:
                    continue
                distances[neighbour] = distance + 1
                queue.append((neighbour, distance + 1))

        return distances

    def describe(self, key: str) -> tuple[str, str, str, str]:
        """(object_type, table, name, qualified_name) for a graph key."""
        if key in self.measures:
            table_name, measure = self.measures[key]
            return "measure", table_name, measure.name, f"{table_name}[{measure.name}]"
        if key in self.columns:
            table_name, column = self.columns[key]
            kind = "calculated_column" if column.expression else "column"
            return kind, table_name, column.name, f"{table_name}[{column.name}]"
        if key in self.tables:
            table = self.tables[key]
            kind = "calculated_table" if table.expression else "table"
            return kind, table.name, table.name, table.name
        reference = self.references.get(key)
        if reference is not None:
            return (
                reference.object_type,
                reference.table_name or "",
                reference.object_name,
                reference.qualified_name,
            )
        return "unresolved", "", key, key

    def expression(self, key: str) -> str | None:
        if key in self.measures:
            return self.measures[key][1].expression
        if key in self.columns:
            return self.columns[key][1].expression
        if key in self.tables:
            return self.tables[key].expression
        return None

    def sources_for_table(self, table_name: str) -> list[PhysicalDataSource]:
        return self._sources_by_table.get(table_name.casefold(), [])

    def tables_fed_by(self, source_id: str) -> list[str]:
        return self._tables_by_source.get(source_id, [])

    def field_key(self, item: SemanticLineageObject) -> str | None:
        """Graph key for a report field; a hierarchy level is its column."""
        if item.object_type in ("column", "measure"):
            return _key(item.table_name, item.object_name)

        if item.object_type == "hierarchy_level":
            table = self.tables.get(item.table_name.casefold())
            for hierarchy in table.hierarchies if table else []:
                if hierarchy.name.casefold() != (item.hierarchy_name or "").casefold():
                    continue
                for level in hierarchy.levels:
                    if (
                        level.name.casefold()
                        == (item.level_name or item.object_name).casefold()
                    ):
                        return _key(item.table_name, level.column or level.name)

        return None


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


@dataclass
class _EvidenceBuilder:
    context: ResolvedAIContext
    items: list[EvidenceItem] = field(default_factory=list)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def add(
        self,
        *,
        fact_type: EvidenceFactType,
        object_type: str,
        object_name: str,
        value: Any,
        display_value: str | None,
        source_type: EvidenceSourceType,
        source_reference: str | None,
        object_id: str | None = None,
        plain_language: str | None = None,
        report_id: str | None = None,
    ) -> None:
        self.items.append(
            EvidenceItem(
                evidence_id="",
                object_type=object_type,
                object_id=object_id,
                object_name=object_name,
                fact_type=fact_type,
                source_type=source_type,
                value=value,
                plain_language=plain_language,
                display_value=display_value,
                workspace_id=self.context.semantic_model_workspace_id
                or self.context.workspace_id,
                report_id=report_id,
                semantic_model_id=self.context.semantic_model_id,
                verification_status=VerificationStatus.VERIFIED,
                retrieved_at=self.retrieved_at,
                source_reference=source_reference,
            )
        )

    def coverage(self, note: str) -> None:
        if any(
            item.object_type == "coverage" and item.display_value == note
            for item in self.items
        ):
            return
        self.add(
            fact_type="relationship",
            object_type="coverage",
            object_name="Coverage",
            value={"note": note},
            display_value=note,
            source_type="other",
            source_reference=None,
        )


def _add_definition(
    builder: _EvidenceBuilder,
    index: _ModelIndex,
    resolved: ResolvedObject,
) -> None:
    key = resolved.qualified_name.casefold()

    if resolved.object_type == "measure" and key in index.measures:
        table_name, measure = index.measures[key]
        _add_measure_definition(builder, table_name, measure, brief=False)
        return

    if resolved.object_type in ("column", "calculated_column") and key in index.columns:
        table_name, column = index.columns[key]
        if column.expression:
            builder.add(
                fact_type="definition",
                object_type="calculated_column",
                object_id=f"{table_name}[{column.name}]",
                object_name=column.name,
                value=column.expression,
                plain_language=describe(column.expression, object_name=column.name),
                display_value=_column_detail(column, calculated=True),
                source_type="tmdl",
                source_reference=column.source_path,
            )
            return

        builder.add(
            fact_type="definition",
            object_type="column",
            object_id=f"{table_name}[{column.name}]",
            object_name=column.name,
            value={
                "data_type": column.data_type,
                "source_column": column.source_column,
                "is_hidden": column.is_hidden,
            },
            display_value=_column_detail(column, calculated=False),
            source_type="tmdl",
            source_reference=column.source_path,
        )
        return

    table = index.tables.get(resolved.table_name.casefold())
    if resolved.object_type == "table" and table is not None:
        calculated = [column.name for column in table.columns if column.expression]
        mode = _storage_mode(table)
        text = (
            f"{table.name} has {_count(len(table.columns), 'column')} and "
            f"{_count(len(table.measures), 'measure')}"
        )
        if table.measures:
            text += f" ({', '.join(measure.name for measure in table.measures)})"
        if calculated:
            text += f"; calculated columns: {', '.join(calculated)}"
        if mode:
            text += f"; {mode} mode"
        builder.add(
            fact_type="definition",
            object_type="table",
            object_id=table.name,
            object_name=table.name,
            value=(
                table.expression
                if table.expression
                else {
                    "columns": [column.name for column in table.columns],
                    "measures": [measure.name for measure in table.measures],
                    "calculated_columns": calculated,
                    "storage_mode": mode,
                }
            ),
            plain_language=(
                describe(table.expression, object_name=table.name)
                if table.expression
                else None
            ),
            display_value=text + ".",
            source_type="tmdl",
            source_reference=table.source_path,
        )


def _add_measure_definition(
    builder: _EvidenceBuilder,
    table_name: str,
    measure: ParsedSemanticModelMeasure,
    *,
    brief: bool,
) -> None:
    if measure.expression is None:
        return

    expression = measure.expression
    if brief and len(expression) > _MAX_DAX_CHARS:
        expression = expression[:_MAX_DAX_CHARS] + " ... (truncated)"

    detail = [f"measure in table {table_name}"]
    if measure.format_string:
        detail.append(f"format {measure.format_string}")
    if measure.is_hidden:
        detail.append("hidden")

    builder.add(
        fact_type="definition",
        object_type="measure",
        object_id=f"{table_name}[{measure.name}]",
        object_name=measure.name,
        value=expression,
        plain_language=describe(measure.expression, object_name=measure.name),
        display_value="; ".join(detail),
        source_type="tmdl",
        source_reference=measure.source_path,
    )


def _add_upstream(
    builder: _EvidenceBuilder,
    index: _ModelIndex,
    upstream: dict[str, int],
) -> None:
    for key, distance in sorted(
        upstream.items(), key=lambda entry: (entry[1], entry[0])
    ):
        object_type, table_name, name, qualified = index.describe(key)
        expression = index.expression(key)
        detail = (
            f"{qualified} ({_OBJECT_TYPE_LABELS.get(object_type, object_type)}, "
            + ("referenced directly" if distance == 1 else f"{distance} steps away")
            + ")"
        )
        if expression and object_type in ("measure", "calculated_column"):
            detail += f" = {_shorten(expression)}"
        builder.add(
            fact_type="dependency",
            object_type=object_type,
            object_id=qualified,
            object_name=name,
            value={
                "qualified_name": qualified,
                "table": table_name,
                "distance": distance,
                **({"expression": _shorten(expression)} if expression else {}),
            },
            display_value=detail,
            source_type="tmdl",
            source_reference=f"dax:{qualified}",
        )


def _add_database_lineage(
    builder: _EvidenceBuilder,
    index: _ModelIndex,
    resolved: ResolvedObject,
    upstream: dict[str, int],
) -> None:
    """Which database objects, and which of their columns, the object reads.

    A column's physical name is its TMDL `sourceColumn`; that is the name
    Power Query hands the model, and for a straight table import it is the
    database column itself.
    """
    columns_by_table: dict[str, list[str]] = defaultdict(list)
    tables_read: list[str] = []

    def read(table_name: str, source_column: str | None) -> None:
        if table_name not in tables_read:
            tables_read.append(table_name)
        if source_column and source_column not in columns_by_table[table_name]:
            columns_by_table[table_name].append(source_column)

    keys = [resolved.qualified_name.casefold(), *upstream]
    for key in keys:
        if key in index.columns:
            table_name, column = index.columns[key]
            if not column.expression:
                read(table_name, column.source_column or column.name)
        elif key in index.tables:
            read(index.tables[key].name, None)

    if resolved.object_type == "table":
        table = index.tables.get(resolved.table_name.casefold())
        if table is not None:
            for column in table.columns:
                if not column.expression:
                    read(table.name, column.source_column or column.name)

    for table_name in tables_read:
        sources = index.sources_for_table(table_name)
        columns = columns_by_table.get(table_name, [])
        table = index.tables.get(table_name.casefold())

        if not sources:
            reason = (
                "calculated in DAX, so it has no database source"
                if table is not None and table.expression
                else "its database source could not be identified"
            )
            builder.add(
                fact_type="source",
                object_type="physical_source",
                object_name=table_name,
                value={
                    "semantic_table": table_name,
                    "columns": columns,
                    "source": None,
                },
                display_value=f"Semantic table {table_name}: {reason}.",
                source_type="tmdl",
                source_reference=f"semantic_table:{table_name}",
            )
            continue

        for source in sources:
            _add_source(builder, source, tables=[table_name], columns=columns)


def _add_source(
    builder: _EvidenceBuilder,
    source: PhysicalDataSource,
    *,
    tables: list[str],
    columns: list[str] | None = None,
) -> None:
    text = describe_source(source)
    if tables:
        text += (
            " -> semantic table"
            + ("s " if len(tables) > 1 else " ")
            + ", ".join(tables)
        )
    if columns:
        listed = columns[:_MAX_LISTED_COLUMNS]
        text += f" (columns: {', '.join(listed)}"
        if len(columns) > len(listed):
            text += f", and {len(columns) - len(listed)} more"
        text += ")"

    builder.add(
        fact_type="source",
        object_type="physical_source",
        object_id=source.source_id,
        object_name=source.object_name
        or source.database
        or source.path
        or source.url
        or _PROVIDER_LABELS.get(source.provider, source.provider),
        value={
            **_source_value(source),
            "semantic_tables": tables,
            **({"columns": columns} if columns else {}),
        },
        display_value=text,
        source_type="tmdl",
        source_reference=f"physical_source:{source.source_id}",
    )


def _add_downstream(
    builder: _EvidenceBuilder,
    index: _ModelIndex,
    downstream: dict[str, int],
) -> None:
    for key, distance in sorted(
        downstream.items(), key=lambda entry: (entry[1], entry[0])
    ):
        object_type, table_name, name, qualified = index.describe(key)
        builder.add(
            fact_type="impact",
            object_type=object_type,
            object_id=qualified,
            object_name=name,
            value={
                "qualified_name": qualified,
                "table": table_name,
                "distance": distance,
            },
            display_value=(
                f"{qualified} ({_OBJECT_TYPE_LABELS.get(object_type, object_type)}, "
                + (
                    "uses it directly"
                    if distance == 1
                    else f"{distance} steps downstream"
                )
                + ")"
            ),
            source_type="tmdl",
            source_reference=f"dax:{qualified}",
        )


def _add_table_impact(
    builder: _EvidenceBuilder,
    index: _ModelIndex,
    resolved: ResolvedObject,
    downstream: dict[str, int],
) -> None:
    by_table: dict[str, list[str]] = defaultdict(list)
    for key in downstream:
        object_type, table_name, name, _ = index.describe(key)
        if table_name:
            by_table[table_name].append(name)

    for table_name, names in sorted(by_table.items()):
        own = table_name.casefold() == resolved.table_name.casefold()
        builder.add(
            fact_type="impact",
            object_type="semantic_table",
            object_id=table_name,
            object_name=table_name,
            value={"table": table_name, "dependent_objects": names, "same_table": own},
            display_value=(
                f"{table_name}{' (its own table)' if own else ''}: "
                f"{len(names)} dependent object"
                + ("" if len(names) == 1 else "s")
                + f" ({', '.join(names)})"
            ),
            source_type="tmdl",
            source_reference=f"semantic_table:{table_name}",
        )


def _add_visual_impact(
    builder: _EvidenceBuilder,
    index: _ModelIndex,
    context: ResolvedAIContext,
    impacted: set[str],
    resolved: ResolvedObject,
) -> None:
    reports = _reports_in_scope(context)

    if not reports:
        builder.coverage(
            "No report definition was available, so visual impact could not be checked."
        )
        return

    own_keys = set(index.members(resolved))
    visuals: dict[tuple[str, str, str], dict[str, Any]] = {}

    for report in reports:
        lineage = _match_report(index, report.definition)
        if lineage is None:
            continue
        for match in lineage.field_matches:
            if match.status != "matched" or match.semantic_object is None:
                continue
            key = index.field_key(match.semantic_object)
            if key is None or key not in impacted:
                continue

            visual_key = (report.report_id, match.page_name, match.visual_id)
            entry = visuals.setdefault(
                visual_key,
                {
                    "report": report.report_name or report.report_id,
                    "report_id": report.report_id,
                    "workspace": report.workspace_name,
                    "page": match.page_display_name,
                    "visual_title": match.visual_title,
                    "visual_type": match.visual_type,
                    "fields": [],
                    "via": [],
                    "direct": False,
                },
            )
            semantic = match.semantic_object
            field_name = f"{semantic.table_name}[{semantic.object_name}]"
            if field_name not in entry["fields"]:
                entry["fields"].append(field_name)
            if key in own_keys:
                entry["direct"] = True
            elif match.semantic_object.object_name not in entry["via"]:
                entry["via"].append(match.semantic_object.object_name)

    checked = ", ".join(
        f"'{report.report_name or report.report_id}'" for report in reports
    )
    builder.coverage(
        f"Visual impact was checked in {len(reports)} report"
        + ("" if len(reports) == 1 else "s")
        + f": {checked}. "
        + (
            f"{len(visuals)} visual"
            + ("" if len(visuals) == 1 else "s")
            + " would be affected."
            if visuals
            else "No visual uses this object, directly or through a dependent measure."
        )
    )

    ordered = sorted(
        visuals.values(),
        key=lambda entry: (entry["report"], entry["page"], entry["visual_title"] or ""),
    )
    for entry in ordered[:_MAX_VISUALS]:
        how = "uses it directly" if entry["direct"] else ""
        if entry["via"]:
            how = (how + "; " if how else "") + "through " + ", ".join(entry["via"])
        builder.add(
            fact_type="impact",
            object_type="visual",
            object_id=f"{entry['report_id']}:{entry['page']}:{entry['visual_title']}",
            object_name=entry["visual_title"]
            or f"{entry['visual_type'] or 'untitled'} visual",
            value={
                "report": entry["report"],
                "workspace": entry["workspace"],
                "page": entry["page"],
                "visual_title": entry["visual_title"],
                "visual_type": entry["visual_type"],
                "fields": entry["fields"],
                "direct": entry["direct"],
                "via": entry["via"],
            },
            display_value=(
                f"Report '{entry['report']}' > page '{entry['page']}' > "
                f"{_visual_name(entry['visual_title'], entry['visual_type'])} ({how})"
            ),
            source_type="pbir",
            source_reference=f"report:{entry['report_id']}",
            report_id=entry["report_id"],
        )

    if len(ordered) > _MAX_VISUALS:
        builder.coverage(
            f"{len(ordered)} visuals are affected; the first {_MAX_VISUALS} are listed."
        )


def _add_pages(
    builder: _EvidenceBuilder, report: NormalizedReportDefinitionResponse
) -> None:
    for page in sorted(
        report.pages, key=lambda item: (item.order is None, item.order or 0)
    ):
        visible = [visual for visual in page.visuals if not visual.is_hidden]
        names = [
            _visual_name(visual.title, visual.visual_type)
            for visual in visible[:_MAX_VISUALS_PER_PAGE]
        ]
        text = f"Page '{page.display_name}': {page.visual_count} visual" + (
            "" if page.visual_count == 1 else "s"
        )
        if names:
            text += " - " + ", ".join(names)
        if len(visible) > len(names):
            text += f", and {len(visible) - len(names)} more"
        builder.add(
            fact_type="relationship",
            object_type="report_page",
            object_id=page.name,
            object_name=page.display_name,
            value={
                "page": page.display_name,
                "visual_count": page.visual_count,
                "visuals": [
                    {"title": visual.title, "type": visual.visual_type}
                    for visual in visible[:_MAX_VISUALS_PER_PAGE]
                ],
            },
            display_value=text,
            source_type="pbir",
            source_reference=f"report_page:{report.report_id}.{page.name}",
            report_id=report.report_id,
        )


def _add_report_fields(
    builder: _EvidenceBuilder,
    index: _ModelIndex,
    context: ResolvedAIContext,
    report: NormalizedReportDefinitionResponse,
) -> None:
    lineage = _match_report(index, report)
    if lineage is None:
        builder.coverage(
            "The report's fields could not be matched to its semantic model."
        )
        return

    used: dict[str, set[str]] = defaultdict(set)
    unmatched: list[str] = []
    visual_calculations: list[str] = []

    for match in lineage.field_matches:
        visual = _visual_name(match.visual_title, match.visual_type)
        where = f"{visual} on '{match.page_display_name}'"
        if match.status != "matched" or match.semantic_object is None:
            reference = match.field_reference
            if reference.object_type == "visual_calculation":
                visual_calculations.append(
                    f"{reference.object_name or 'unnamed'} in {where}"
                )
            else:
                table = reference.table_name or "?"
                unmatched.append(f"{table}[{reference.object_name or '?'}] in {where}")
            continue
        key = index.field_key(match.semantic_object)
        if key is not None:
            used[key].add(where)

    for key in sorted(used, key=lambda item: (item not in index.measures, item)):
        object_type, table_name, name, qualified = index.describe(key)
        expression = index.expression(key)
        places = sorted(used[key])
        kind = _OBJECT_TYPE_LABELS.get(object_type, object_type)
        text = (
            f"{qualified} ({kind}) is used by "
            f"{len(places)} visual"
            + ("" if len(places) == 1 else "s")
            + f": {', '.join(places[:6])}"
        )
        if len(places) > 6:
            text += f", and {len(places) - 6} more"
        builder.add(
            fact_type="usage",
            object_type=object_type,
            object_id=qualified,
            object_name=name,
            value={
                "qualified_name": qualified,
                "table": table_name,
                "used_by_visuals": places,
                **({"expression": _shorten(expression)} if expression else {}),
            },
            plain_language=(
                describe(expression, object_name=name)
                if expression and object_type == "measure"
                else None
            ),
            display_value=text
            + (f". DAX: {_shorten(expression)}" if expression else ""),
            source_type="pbir",
            source_reference=f"dax:{qualified}",
            report_id=report.report_id,
        )

    # Where the report's data comes from: the tables its fields read,
    # directly or through the measures it shows.
    upstream = index.walk(list(used), upstream=True)
    tables: list[str] = []
    columns_by_table: dict[str, list[str]] = defaultdict(list)
    for key in [*used, *upstream]:
        if key in index.columns:
            table_name, column = index.columns[key]
            if table_name not in tables:
                tables.append(table_name)
            source_column = column.source_column or column.name
            if (
                not column.expression
                and source_column not in columns_by_table[table_name]
            ):
                columns_by_table[table_name].append(source_column)
        elif key in index.tables and index.tables[key].name not in tables:
            tables.append(index.tables[key].name)

    for table_name in tables:
        sources = index.sources_for_table(table_name)
        if not sources:
            table = index.tables.get(table_name.casefold())
            builder.add(
                fact_type="source",
                object_type="physical_source",
                object_name=table_name,
                value={"semantic_table": table_name, "source": None},
                display_value=(
                    f"Semantic table {table_name}: "
                    + (
                        "calculated in DAX, so it has no database source."
                        if table is not None and table.expression
                        else "its database source could not be identified."
                    )
                ),
                source_type="tmdl",
                source_reference=f"semantic_table:{table_name}",
            )
        for source in sources:
            _add_source(
                builder,
                source,
                tables=[table_name],
                columns=columns_by_table[table_name],
            )

    if visual_calculations:
        builder.coverage(
            "Visual calculations are defined in the report itself, not the model: "
            + "; ".join(visual_calculations[:10])
        )
    if unmatched:
        builder.coverage(
            f"{len(unmatched)} visual field reference"
            + ("" if len(unmatched) == 1 else "s")
            + " could not be matched to the semantic model: "
            + "; ".join(unmatched[:10])
        )


def _add_raw_fields(
    builder: _EvidenceBuilder, report: NormalizedReportDefinitionResponse
) -> None:
    used: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for page in report.pages:
        for visual in page.visuals:
            for reference in visual.field_references:
                if not reference.object_name:
                    continue
                used[
                    (
                        reference.object_type,
                        reference.table_name or "",
                        reference.object_name,
                    )
                ].add(
                    f"{_visual_name(visual.title, visual.visual_type)} "
                    f"on '{page.display_name}'"
                )

    for (object_type, table_name, name), places in sorted(used.items()):
        qualified = f"{table_name}[{name}]" if table_name else name
        builder.add(
            fact_type="usage",
            object_type=object_type,
            object_id=qualified,
            object_name=name,
            value={"qualified_name": qualified, "used_by_visuals": sorted(places)},
            display_value=(
                f"{qualified} ({object_type}) is used by {len(places)} visual"
                + ("" if len(places) == 1 else "s")
            ),
            source_type="pbir",
            source_reference=f"report:{report.report_id}",
            report_id=report.report_id,
        )


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _reports_in_scope(context: ResolvedAIContext) -> list[ResolvedReport]:
    reports: list[ResolvedReport] = []
    if context.report_definition is not None:
        reports.append(
            ResolvedReport(
                workspace_id=context.report_definition.workspace_id,
                workspace_name=context.workspace_name,
                report_id=context.report_definition.report_id,
                report_name=context.report_name,
                definition=context.report_definition,
            )
        )
    seen = {report.report_id for report in reports}
    for report in context.related_reports:
        if report.report_id not in seen:
            seen.add(report.report_id)
            reports.append(report)
    return reports


def _match_report(index: _ModelIndex, report: NormalizedReportDefinitionResponse):
    try:
        return ReportSemanticLineageService().match(
            report=report,
            semantic_model=index.model,
            semantic_model_workspace_id=index.model.workspace_id,
        )
    except Exception:  # noqa: BLE001 - heuristic matcher, degrade not crash
        return None


def _model_identity(context: ResolvedAIContext) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "semantic_model": context.semantic_model_name or context.semantic_model_id,
            "semantic_model_workspace": context.semantic_model_workspace_name,
            "report": context.report_name,
            "workspace": context.workspace_name,
        }.items()
        if value
    }


def _model_label(context: ResolvedAIContext) -> str | None:
    if context.semantic_model_name:
        return f"'{context.semantic_model_name}'"
    if context.semantic_model_id:
        return f"'{context.semantic_model_id}'"
    return None


def _identity_sentence(context: ResolvedAIContext, resolved: ResolvedObject) -> str:
    kind = _OBJECT_TYPE_LABELS.get(resolved.object_type, resolved.object_type)
    if resolved.object_type == "table":
        text = f"{resolved.table_name} is a table"
    else:
        text = f"{resolved.object_name} is a {kind} in table {resolved.table_name}"

    model_label = _model_label(context)
    if model_label:
        text += f" of semantic model {model_label}"
    workspace = context.semantic_model_workspace_name or context.workspace_name
    if workspace:
        text += f" (workspace '{workspace}')"
    if context.report_name:
        text += f", viewed from report '{context.report_name}'"
    return text + "."


def _column_detail(column: ParsedSemanticModelColumn, *, calculated: bool) -> str:
    parts = ["calculated column" if calculated else "column"]
    if column.data_type:
        parts.append(f"data type {column.data_type}")
    if not calculated and column.source_column:
        parts.append(f"loaded from source column {column.source_column}")
    if column.is_hidden:
        parts.append("hidden")
    return "; ".join(parts)


def _storage_mode(table: ParsedSemanticModelTable) -> str | None:
    modes = sorted({partition.mode for partition in table.partitions if partition.mode})
    return "/".join(modes) if modes else None


def _source_value(source: PhysicalDataSource) -> dict[str, Any]:
    return source.model_dump(
        exclude_none=True,
        include={
            "provider",
            "kind",
            "server",
            "database",
            "schema_name",
            "object_name",
            "object_kind",
            "path",
            "url",
            "warehouse",
            "via_workspace_name",
            "via_semantic_model_name",
            "via_semantic_table",
        },
    )


def _visual_name(title: str | None, visual_type: str | None) -> str:
    if title and visual_type:
        return f"'{title}' ({visual_type})"
    if title:
        return f"'{title}'"
    return f"untitled {visual_type or ''} visual".replace("  ", " ")


def _shorten(expression: str | None) -> str:
    if not expression:
        return ""
    flat = " ".join(expression.split())
    return flat if len(flat) <= _MAX_DAX_CHARS else flat[:_MAX_DAX_CHARS] + " ..."


def _count(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _key(table_name: str, object_name: str) -> str:
    return f"{table_name}[{object_name}]".casefold()
