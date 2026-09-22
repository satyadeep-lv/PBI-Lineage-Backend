from dataclasses import dataclass

from app.schemas.dax_dependency import (
    DaxDependencyAnalysisResponse,
    DaxDependencyEdge,
    DaxObjectReference,
    DaxObjectType,
)
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelMeasure,
    ParsedSemanticModelPartition,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)
from app.schemas.xmla_metadata import (
    XmlaCalcDependency,
    XmlaSemanticModelMetadataResponse,
)

CALCULATED_OBJECT_TYPES = frozenset(
    {"measure", "calculated_column", "calculated_table"}
)

_OBJECT_TYPE_MAP: dict[str, DaxObjectType] = {
    "measure": "measure",
    "calc_column": "calculated_column",
    "calc_table": "calculated_table",
    "column": "column",
    "table": "table",
}


@dataclass(frozen=True)
class _CalculatedObject:
    object_type: DaxObjectType
    table_name: str
    object_name: str


def build_parsed_semantic_model(
    metadata: XmlaSemanticModelMetadataResponse,
) -> ParsedSemanticModelResponse:
    """Build a ``ParsedSemanticModelResponse`` from live XMLA metadata so the
    existing TMDL-oriented ``PhysicalSourceDiscoveryService`` can run
    unchanged against engine-reported partition M/SQL text
    (``TMSCHEMA_PARTITIONS.QueryDefinition``) instead of parsed TMDL text.
    """
    calculated_table_expressions, calculated_column_expressions = (
        _calculated_expressions(metadata.calc_dependencies)
    )

    tables: list[ParsedSemanticModelTable] = []

    for table in metadata.tables:
        table_key = table.name.casefold()
        table_expression = calculated_table_expressions.get(table_key)

        columns = [
            ParsedSemanticModelColumn(
                name=column.name,
                source_column=column.source_column,
                data_type=column.data_type,
                expression=calculated_column_expressions.get(
                    (table_key, column.name.casefold())
                ),
                is_hidden=column.is_hidden,
            )
            for column in table.columns
        ]
        measures = [
            ParsedSemanticModelMeasure(
                name=measure.name,
                expression=measure.expression,
                format_string=measure.format_string,
                is_hidden=measure.is_hidden,
            )
            for measure in table.measures
        ]
        partitions = [
            ParsedSemanticModelPartition(
                name=partition.name,
                mode=partition.mode,
                source_type=(
                    "calculated" if table_expression else (partition.source_type or "m")
                ),
                expression=partition.expression,
            )
            for partition in table.partitions
        ]

        tables.append(
            ParsedSemanticModelTable(
                name=table.name,
                expression=table_expression,
                columns=columns,
                measures=measures,
                partitions=partitions,
            )
        )

    return ParsedSemanticModelResponse(
        workspace_id=metadata.workspace_id,
        semantic_model_id=metadata.semantic_model_id,
        format="XMLA",
        tables=tables,
    )


def build_dax_dependency_analysis(
    metadata: XmlaSemanticModelMetadataResponse,
) -> DaxDependencyAnalysisResponse:
    """Build the DAX dependency graph directly from the engine-computed
    ``DISCOVER_CALC_DEPENDENCY`` DMV instead of regex-parsing DAX text. This
    is Microsoft's own dependency resolution, so there is no
    ``DAX_REFERENCE_UNRESOLVED``-style failure mode: every dependency the
    engine reports is authoritative.
    """
    calculated = _calculated_objects(metadata.calc_dependencies)

    objects = sorted(
        (
            DaxObjectReference(
                object_type=item.object_type,
                table_name=item.table_name,
                object_name=item.object_name,
                qualified_name=_qualified_name(
                    item.object_type,
                    item.table_name,
                    item.object_name,
                ),
            )
            for item in calculated.values()
        ),
        key=lambda item: item.qualified_name.casefold(),
    )

    dependencies: list[DaxDependencyEdge] = []
    seen_edges: set[tuple[str, str]] = set()

    for dependency in metadata.calc_dependencies:
        object_type = _map_object_type(dependency.object_type)

        if (
            object_type not in CALCULATED_OBJECT_TYPES
            or not dependency.table
            or not dependency.object
            or not dependency.referenced_object
        ):
            continue

        target = DaxObjectReference(
            object_type=object_type,
            table_name=dependency.table,
            object_name=dependency.object,
            qualified_name=_qualified_name(
                object_type,
                dependency.table,
                dependency.object,
            ),
        )

        referenced_table = dependency.referenced_table or dependency.table
        referenced_calc = calculated.get(
            (referenced_table.casefold(), dependency.referenced_object.casefold())
        )

        if referenced_calc is not None:
            source = DaxObjectReference(
                object_type=referenced_calc.object_type,
                table_name=referenced_calc.table_name,
                object_name=referenced_calc.object_name,
                qualified_name=_qualified_name(
                    referenced_calc.object_type,
                    referenced_calc.table_name,
                    referenced_calc.object_name,
                ),
            )
        else:
            source_type = _map_object_type(dependency.referenced_object_type)
            source = DaxObjectReference(
                object_type=source_type,
                table_name=referenced_table,
                object_name=dependency.referenced_object,
                qualified_name=_qualified_name(
                    source_type,
                    referenced_table,
                    dependency.referenced_object,
                ),
            )

        edge_key = (
            source.qualified_name.casefold(),
            target.qualified_name.casefold(),
        )

        if edge_key in seen_edges:
            continue

        seen_edges.add(edge_key)
        dependencies.append(
            DaxDependencyEdge(
                source=source,
                target=target,
                reference_text=dependency.expression or "",
            )
        )

    dependencies = _drop_redundant_table_dependencies(dependencies)

    dependencies.sort(
        key=lambda edge: (
            edge.target.qualified_name.casefold(),
            edge.source.qualified_name.casefold(),
        )
    )

    return DaxDependencyAnalysisResponse(
        workspace_id=metadata.workspace_id,
        semantic_model_id=metadata.semantic_model_id,
        objects=objects,
        dependencies=dependencies,
        cycles=[],
        warnings=[],
        object_count=len(objects),
        dependency_count=len(dependencies),
        cycle_count=0,
    )


def _drop_redundant_table_dependencies(
    dependencies: list[DaxDependencyEdge],
) -> list[DaxDependencyEdge]:
    """Drop a table-level dependency when the same owner already has a
    column/measure-level dependency into that same table.

    ``DISCOVER_CALC_DEPENDENCY`` reports a measure's row/filter-context
    dependency on its evaluation table alongside the specific column it
    aggregates (e.g. both ``SUM(T[Col])``'s column and ``T`` itself). That
    whole-table edge carries no physical-column information and only
    produces an empty duplicate row, so it is dropped once a more specific
    dependency into the same table already exists. A table dependency with
    no accompanying column dependency (e.g. a bare ``COUNTROWS(T)``) is kept,
    since it is the only lineage information available for that owner.
    """
    covered: set[tuple[str, str]] = {
        (edge.target.qualified_name.casefold(), edge.source.table_name.casefold())
        for edge in dependencies
        if edge.source.object_type != "table" and edge.source.table_name
    }

    return [
        edge
        for edge in dependencies
        if edge.source.object_type != "table"
        or (
            edge.target.qualified_name.casefold(),
            edge.source.table_name.casefold(),
        )
        not in covered
    ]


def _calculated_objects(
    calc_dependencies: list[XmlaCalcDependency],
) -> dict[tuple[str, str], _CalculatedObject]:
    calculated: dict[tuple[str, str], _CalculatedObject] = {}

    for dependency in calc_dependencies:
        object_type = _map_object_type(dependency.object_type)

        if object_type not in CALCULATED_OBJECT_TYPES or not dependency.object:
            continue

        table_name = dependency.table or dependency.object
        key = (table_name.casefold(), dependency.object.casefold())
        calculated.setdefault(
            key,
            _CalculatedObject(
                object_type=object_type,
                table_name=table_name,
                object_name=dependency.object,
            ),
        )

    return calculated


def _calculated_expressions(
    calc_dependencies: list[XmlaCalcDependency],
) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    calculated_tables: dict[str, str] = {}
    calculated_columns: dict[tuple[str, str], str] = {}

    for dependency in calc_dependencies:
        object_type = _map_object_type(dependency.object_type)

        if not dependency.object or not dependency.expression:
            continue

        if object_type == "calculated_table":
            table_name = dependency.table or dependency.object
            calculated_tables.setdefault(table_name.casefold(), dependency.expression)
        elif object_type == "calculated_column" and dependency.table:
            calculated_columns.setdefault(
                (dependency.table.casefold(), dependency.object.casefold()),
                dependency.expression,
            )

    return calculated_tables, calculated_columns


def _map_object_type(value: str | None) -> DaxObjectType:
    if value is None:
        return "unresolved"

    return _OBJECT_TYPE_MAP.get(value.strip().casefold(), "unresolved")


def _qualified_name(
    object_type: DaxObjectType,
    table_name: str,
    object_name: str,
) -> str:
    if object_type in {"table", "calculated_table"}:
        return table_name

    return f"{table_name}[{object_name}]"
