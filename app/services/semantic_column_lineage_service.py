from collections.abc import Iterable

from app.domain.dax_lineage import (
    expression_index,
    physical_sources_by_table,
    terminal_dependencies,
)
from app.schemas.dax_dependency import DaxDependencyAnalysisResponse, DaxObjectReference
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelResponse,
)
from app.schemas.physical_source import (
    PhysicalDataSource,
    PhysicalSourceDiscoveryResponse,
)
from app.schemas.semantic_column_lineage import (
    PhysicalColumnReference,
    PhysicalColumnResolutionMethod,
    SemanticColumnLineageRow,
    SemanticColumnLineageWarning,
    SemanticModelColumnLineageResponse,
)
from app.services.dax_dependency_service import DaxDependencyService
from app.services.physical_source_service import PhysicalSourceDiscoveryService
from app.services.sql_column_parser import parse_select_columns
from app.services.xmla_column_lineage_adapter import (
    build_dax_dependency_analysis,
    build_parsed_semantic_model,
)
from app.services.xmla_metadata_service import XmlaMetadataService


class SemanticColumnLineageService:
    """Maps every measure/calculated column/calculated table in a semantic
    model to the physical database columns it ultimately reads from.

    The dependency graph and physical column names come from live XMLA —
    ``DISCOVER_CALC_DEPENDENCY`` for "what depends on what" (the engine's own
    computed graph, not a regex guess) and ``TMSCHEMA_PARTITIONS.QueryDefinition``
    for the partition's real M/SQL text — rather than parsing TMDL text.
    ``PhysicalSourceDiscoveryService`` and the native-SQL column parser are
    reused unchanged against that engine-reported text.
    """

    def __init__(self) -> None:
        self.xmla_metadata_service = XmlaMetadataService()
        self.dax_dependency_service = DaxDependencyService()
        self.physical_source_service = PhysicalSourceDiscoveryService()

    async def build_lineage_from_xmla(
        self,
        *,
        workspace_id: str,
        semantic_model_id: str,
        access_token: str,
        workspace_name: str | None = None,
        database_name: str | None = None,
    ) -> SemanticModelColumnLineageResponse:
        metadata = await self.xmla_metadata_service.get_metadata(
            workspace_id=workspace_id,
            semantic_model_id=semantic_model_id,
            access_token=access_token,
            workspace_name=workspace_name,
            database_name=database_name,
        )

        semantic_model = build_parsed_semantic_model(metadata)
        dax = build_dax_dependency_analysis(metadata)

        return self.build_lineage_from_model(semantic_model, dax=dax)

    def build_lineage_from_model(
        self,
        semantic_model: ParsedSemanticModelResponse,
        *,
        dax: DaxDependencyAnalysisResponse | None = None,
    ) -> SemanticModelColumnLineageResponse:
        if dax is None:
            dax = self.dax_dependency_service.analyze(semantic_model)

        physical = self.physical_source_service.discover(semantic_model)

        expressions = expression_index(semantic_model)
        sources_by_table = physical_sources_by_table(physical)
        columns_by_key = _columns_by_key(semantic_model)

        rows: list[SemanticColumnLineageRow] = []
        for owner in dax.objects:
            owner_expression = expressions.get(owner.qualified_name.casefold())
            owner_terminals = terminal_dependencies(owner, dax)

            if not owner_terminals:
                rows.append(
                    _row(
                        owner=owner,
                        expression=owner_expression,
                        dependency=None,
                        dependency_depth=None,
                        physical_columns=[],
                    )
                )
                continue

            for dependency, depth in owner_terminals:
                rows.append(
                    _row(
                        owner=owner,
                        expression=owner_expression,
                        dependency=dependency,
                        dependency_depth=depth,
                        physical_columns=self._resolve_physical_columns(
                            dependency=dependency,
                            columns_by_key=columns_by_key,
                            sources_by_table=sources_by_table,
                        ),
                    )
                )

        rows.sort(
            key=lambda row: (
                (row.semantic_table or "").casefold(),
                row.semantic_object_name.casefold(),
                row.dependency_depth or 0,
                (row.referenced_semantic_column or "").casefold(),
            )
        )

        warnings = _warnings(dax, physical)

        return SemanticModelColumnLineageResponse(
            workspace_id=semantic_model.workspace_id,
            semantic_model_id=semantic_model.semantic_model_id,
            rows=rows,
            warnings=warnings,
            object_count=len(dax.objects),
            row_count=len(rows),
        )

    @staticmethod
    def _resolve_physical_columns(
        *,
        dependency: DaxObjectReference,
        columns_by_key: dict[tuple[str, str], ParsedSemanticModelColumn],
        sources_by_table: dict[str, list[PhysicalDataSource]],
    ) -> list[PhysicalColumnReference]:
        if dependency.object_type != "column" or dependency.table_name is None:
            return []

        column = columns_by_key.get(
            (dependency.table_name.casefold(), dependency.object_name.casefold())
        )
        source_column_name = (
            (column.source_column or column.name) if column else dependency.object_name
        )

        return physical_column_references(
            source_column_name=source_column_name,
            sources=sources_by_table.get(dependency.table_name.casefold(), []),
        )


def physical_column_references(
    *,
    source_column_name: str,
    sources: Iterable[PhysicalDataSource],
) -> list[PhysicalColumnReference]:
    """Map a semantic column's ``sourceColumn`` onto each database source it
    reads from.

    When the source is a native query, the ``SELECT`` list is consulted so an
    alias resolves to the physical column(s) behind it; otherwise the physical
    column is assumed to carry the ``sourceColumn`` name, which is how a plain
    table import behaves. Non-database sources (files, web) have no columns to
    report and are skipped.
    """
    references: list[PhysicalColumnReference] = []

    for source in sources:
        if source.kind != "database" or not source.object_name:
            continue

        column_names = [source_column_name]
        resolution_method: PhysicalColumnResolutionMethod = "same_name_assumed"

        if source.native_query:
            for projected in parse_select_columns(source.native_query):
                if projected.output_name.casefold() != source_column_name.casefold():
                    continue
                if projected.source_identifiers:
                    column_names = projected.source_identifiers
                    resolution_method = "native_query_select"
                break

        for column_name in column_names:
            qualified_parts = [
                part
                for part in (
                    source.database,
                    source.schema_name,
                    source.object_name,
                    column_name,
                )
                if part
            ]
            references.append(
                PhysicalColumnReference(
                    source_id=source.source_id,
                    provider=source.provider,
                    server=source.server,
                    database=source.database,
                    schema_name=source.schema_name,
                    object_name=source.object_name,
                    column_name=column_name,
                    resolution_method=resolution_method,
                    fully_qualified_name=".".join(qualified_parts),
                )
            )

    return references


def _row(
    *,
    owner: DaxObjectReference,
    expression: str | None,
    dependency: DaxObjectReference | None,
    dependency_depth: int | None,
    physical_columns: list[PhysicalColumnReference],
) -> SemanticColumnLineageRow:
    return SemanticColumnLineageRow(
        semantic_table=owner.table_name,
        semantic_object_type=owner.object_type,
        semantic_object_name=owner.object_name,
        semantic_dax_expression=expression,
        referenced_semantic_table=(dependency.table_name if dependency else None),
        referenced_semantic_column=(dependency.object_name if dependency else None),
        dependency_depth=dependency_depth,
        is_direct_dependency=(
            dependency_depth == 1 if dependency_depth is not None else None
        ),
        physical_columns=physical_columns,
    )


def _columns_by_key(
    semantic_model: ParsedSemanticModelResponse,
) -> dict[tuple[str, str], ParsedSemanticModelColumn]:
    return {
        (table.name.casefold(), column.name.casefold()): column
        for table in semantic_model.tables
        for column in table.columns
    }


def _warnings(
    dax: DaxDependencyAnalysisResponse,
    physical: PhysicalSourceDiscoveryResponse,
) -> list[SemanticColumnLineageWarning]:
    warnings = [
        SemanticColumnLineageWarning(
            code=warning.code,
            message=warning.message,
            object_name=warning.object_name,
        )
        for warning in dax.warnings
    ]
    warnings.extend(
        SemanticColumnLineageWarning(
            code=warning.code,
            message=warning.message,
            source_path=warning.source_path,
        )
        for warning in physical.warnings
    )
    return warnings
