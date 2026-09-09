import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.core.exceptions import AppException, InvalidLineageRequestError
from app.schemas.dax_dependency import (
    DaxDependencyAnalysisResponse,
    DaxObjectReference,
)
from app.schemas.explorer import (
    ExplorerReportContext,
    ExplorerReportSelection,
    ExplorerRequest,
    ExplorerSnapshotResponse,
    ExplorerWarning,
    MeasureSourceLineageDataset,
    MeasureSourceLineageRow,
    ReportLayoutDataset,
    ReportLayoutRow,
    SemanticModelObjectRow,
    SemanticModelObjectsDataset,
    SourceDatabaseLineageDataset,
    SourceDatabaseLineageRow,
    VisualSourceLookupDataset,
    VisualSourceLookupRow,
)
from app.schemas.gateway import GatewayDatasource
from app.schemas.normalized_report_definition import (
    NormalizedReportDefinitionResponse,
    NormalizedReportVisual,
)
from app.schemas.parsed_semantic_model import ParsedSemanticModelResponse
from app.schemas.physical_source import (
    PhysicalDataSource,
    PhysicalSourceDiscoveryResponse,
)
from app.schemas.report import Report
from app.schemas.report_semantic_lineage import ReportSemanticLineageResponse
from app.schemas.workspace import Workspace
from app.services.dax_dependency_service import DaxDependencyService
from app.services.gateway_service import GatewayService
from app.services.physical_source_service import PhysicalSourceDiscoveryService
from app.services.report_definition_service import ReportDefinitionService
from app.services.report_semantic_lineage_service import (
    ReportSemanticLineageService,
)
from app.services.report_service import ReportService
from app.services.semantic_model_definition_service import (
    SemanticModelDefinitionService,
)
from app.services.workspace_service import WorkspaceService

ExplorerDatasetName = Literal[
    "source_database_lineage",
    "semantic_model_objects",
    "measure_source_lineage",
    "report_layout",
    "visual_source_lookup",
]

SOURCE_DATABASE_LINEAGE: ExplorerDatasetName = "source_database_lineage"
SEMANTIC_MODEL_OBJECTS: ExplorerDatasetName = "semantic_model_objects"
MEASURE_SOURCE_LINEAGE: ExplorerDatasetName = "measure_source_lineage"
REPORT_LAYOUT: ExplorerDatasetName = "report_layout"
VISUAL_SOURCE_LOOKUP: ExplorerDatasetName = "visual_source_lookup"

ALL_EXPLORER_DATASETS = frozenset(
    {
        SOURCE_DATABASE_LINEAGE,
        SEMANTIC_MODEL_OBJECTS,
        MEASURE_SOURCE_LINEAGE,
        REPORT_LAYOUT,
        VISUAL_SOURCE_LOOKUP,
    }
)


@dataclass(frozen=True)
class _ReportEvidence:
    selection: ExplorerReportSelection
    workspace: Workspace
    report: Report
    semantic_model_workspace_id: str | None
    semantic_model_id: str | None
    report_definition: NormalizedReportDefinitionResponse | None
    semantic_model: ParsedSemanticModelResponse | None

    @property
    def model_key(self) -> tuple[str, str] | None:
        if not self.semantic_model_workspace_id or not self.semantic_model_id:
            return None
        return (
            self.semantic_model_workspace_id,
            self.semantic_model_id,
        )


class ExplorerService:
    def __init__(
        self,
        *,
        workspace_service: WorkspaceService | None = None,
        report_service: ReportService | None = None,
        report_definition_service: ReportDefinitionService | None = None,
        semantic_model_definition_service: (
            SemanticModelDefinitionService | None
        ) = None,
        report_semantic_lineage_service: (ReportSemanticLineageService | None) = None,
        gateway_service: GatewayService | None = None,
        max_concurrency: int = 8,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1.")

        self.workspace_service = workspace_service or WorkspaceService()
        self.report_service = report_service or ReportService()
        self.report_definition_service = (
            report_definition_service or ReportDefinitionService()
        )
        self.semantic_model_definition_service = (
            semantic_model_definition_service or SemanticModelDefinitionService()
        )
        self.report_semantic_lineage_service = (
            report_semantic_lineage_service or ReportSemanticLineageService()
        )
        self.gateway_service = gateway_service or GatewayService()
        self.max_concurrency = max_concurrency

    async def build_snapshot(
        self,
        request: ExplorerRequest,
        *,
        fabric_access_token: str,
        powerbi_access_token: str,
        datasets: frozenset[ExplorerDatasetName] | None = None,
    ) -> ExplorerSnapshotResponse:
        requested = datasets or ALL_EXPLORER_DATASETS
        unknown = requested - ALL_EXPLORER_DATASETS
        if unknown:
            raise ValueError(f"Unknown explorer datasets: {sorted(unknown)}")

        needs_report_definition = bool(
            requested & {REPORT_LAYOUT, VISUAL_SOURCE_LOOKUP}
        )
        needs_semantic_model = bool(
            requested
            & {
                SOURCE_DATABASE_LINEAGE,
                SEMANTIC_MODEL_OBJECTS,
                MEASURE_SOURCE_LINEAGE,
                VISUAL_SOURCE_LOOKUP,
            }
        )
        needs_physical_sources = bool(
            requested & {SOURCE_DATABASE_LINEAGE, MEASURE_SOURCE_LINEAGE}
        )
        needs_dax = MEASURE_SOURCE_LINEAGE in requested

        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def bounded(
            factory: Callable[[], Awaitable[Any]],
        ) -> Any:
            async with semaphore:
                return await factory()

        workspace_ids = list(
            dict.fromkeys(str(item.workspace_id) for item in request.reports)
        )
        selections = {
            (str(item.workspace_id), str(item.report_id)): item
            for item in request.reports
        }

        workspace_tasks = {
            workspace_id: asyncio.create_task(
                bounded(
                    lambda workspace_id=workspace_id: (
                        self.workspace_service.get_workspace(
                            workspace_id=workspace_id,
                            access_token=powerbi_access_token,
                        )
                    )
                )
            )
            for workspace_id in workspace_ids
        }
        report_tasks = {
            key: asyncio.create_task(
                bounded(
                    lambda key=key: self.report_service.get_report(
                        workspace_id=key[0],
                        report_id=key[1],
                        access_token=powerbi_access_token,
                    )
                )
            )
            for key in selections
        }
        report_definition_tasks = {
            key: asyncio.create_task(
                bounded(
                    lambda key=key: (
                        self.report_definition_service.get_normalized_definition(
                            workspace_id=key[0],
                            report_id=key[1],
                            access_token=fabric_access_token,
                            definition_format=request.report_definition_format,
                        )
                    )
                )
            )
            for key in selections
            if needs_report_definition
        }

        semantic_model_tasks: dict[
            tuple[str, str], asyncio.Task[ParsedSemanticModelResponse]
        ] = {}
        if needs_semantic_model:
            for selection in request.reports:
                if selection.semantic_model_id is None:
                    continue
                model_key = (
                    str(
                        selection.semantic_model_workspace_id or selection.workspace_id
                    ),
                    str(selection.semantic_model_id),
                )
                if model_key not in semantic_model_tasks:
                    semantic_model_tasks[model_key] = asyncio.create_task(
                        bounded(
                            lambda model_key=model_key: (
                                self.semantic_model_definition_service.get_parsed_definition(
                                    workspace_id=model_key[0],
                                    semantic_model_id=model_key[1],
                                    access_token=fabric_access_token,
                                    definition_format=(
                                        request.semantic_model_definition_format
                                    ),
                                )
                            )
                        )
                    )

        gateway_task = None
        if needs_physical_sources and request.include_gateway_sources:
            gateway_task = asyncio.create_task(
                self._gateway_datasources(
                    access_token=powerbi_access_token,
                    bounded=bounded,
                )
            )

        resolution_tasks: list[asyncio.Task[Any]] = [
            *report_tasks.values(),
            *report_definition_tasks.values(),
        ]
        await asyncio.gather(*resolution_tasks)

        model_keys_by_report: dict[tuple[str, str], tuple[str, str] | None] = {}
        for report_key, selection in selections.items():
            report = report_tasks[report_key].result()
            report_definition = (
                report_definition_tasks[report_key].result()
                if needs_report_definition
                else None
            )
            semantic_model_id = self._resolve_semantic_model_id(
                selection,
                report,
                report_definition,
            )
            semantic_model_workspace_id = (
                str(selection.semantic_model_workspace_id or selection.workspace_id)
                if semantic_model_id
                else None
            )
            model_key = (
                (
                    semantic_model_workspace_id,
                    semantic_model_id,
                )
                if semantic_model_workspace_id and semantic_model_id
                else None
            )
            model_keys_by_report[report_key] = model_key

            if needs_semantic_model and model_key is None:
                raise InvalidLineageRequestError(
                    "A semantic model could not be resolved for report "
                    f"{report_key[1]}. Supply semantic_model_id explicitly."
                )

            if needs_semantic_model and model_key not in semantic_model_tasks:
                semantic_model_tasks[model_key] = asyncio.create_task(
                    bounded(
                        lambda model_key=model_key: (
                            self.semantic_model_definition_service.get_parsed_definition(
                                workspace_id=model_key[0],
                                semantic_model_id=model_key[1],
                                access_token=fabric_access_token,
                                definition_format=(
                                    request.semantic_model_definition_format
                                ),
                            )
                        )
                    )
                )

        completion_tasks: list[asyncio.Task[Any]] = [
            *workspace_tasks.values(),
            *report_tasks.values(),
            *report_definition_tasks.values(),
            *semantic_model_tasks.values(),
        ]
        if gateway_task is not None:
            completion_tasks.append(gateway_task)
        await asyncio.gather(*completion_tasks)

        gateway_datasources: list[GatewayDatasource] = []
        warnings: list[ExplorerWarning] = []
        if gateway_task is not None:
            gateway_datasources, gateway_warnings = gateway_task.result()
            warnings.extend(gateway_warnings)

        evidence: list[_ReportEvidence] = []
        for report_key, selection in selections.items():
            model_key = model_keys_by_report[report_key]
            evidence.append(
                _ReportEvidence(
                    selection=selection,
                    workspace=workspace_tasks[report_key[0]].result(),
                    report=report_tasks[report_key].result(),
                    semantic_model_workspace_id=(model_key[0] if model_key else None),
                    semantic_model_id=model_key[1] if model_key else None,
                    report_definition=(
                        report_definition_tasks[report_key].result()
                        if needs_report_definition
                        else None
                    ),
                    semantic_model=(
                        semantic_model_tasks[model_key].result()
                        if needs_semantic_model and model_key
                        else None
                    ),
                )
            )

        physical_by_model: dict[tuple[str, str], PhysicalSourceDiscoveryResponse] = {}
        if needs_physical_sources:
            physical_tasks = {
                model_key: asyncio.create_task(
                    bounded(
                        lambda model_key=model_key: asyncio.to_thread(
                            PhysicalSourceDiscoveryService().discover,
                            semantic_model_tasks[model_key].result(),
                            gateway_datasources=gateway_datasources,
                        )
                    )
                )
                for model_key in self._model_keys(evidence)
            }
            await asyncio.gather(*physical_tasks.values())
            physical_by_model = {
                key: task.result() for key, task in physical_tasks.items()
            }

        dax_by_model: dict[tuple[str, str], DaxDependencyAnalysisResponse] = {}
        if needs_dax:
            dax_tasks = {
                model_key: asyncio.create_task(
                    bounded(
                        lambda model_key=model_key: asyncio.to_thread(
                            DaxDependencyService().analyze,
                            semantic_model_tasks[model_key].result(),
                        )
                    )
                )
                for model_key in self._model_keys(evidence)
            }
            await asyncio.gather(*dax_tasks.values())
            dax_by_model = {key: task.result() for key, task in dax_tasks.items()}

        lineage_by_report: dict[tuple[str, str], ReportSemanticLineageResponse] = {}
        if VISUAL_SOURCE_LOOKUP in requested:
            lineage_tasks = {
                self._report_key(item): asyncio.create_task(
                    bounded(
                        lambda item=item: asyncio.to_thread(
                            self.report_semantic_lineage_service.match,
                            report=item.report_definition,
                            semantic_model=item.semantic_model,
                            semantic_model_workspace_id=(
                                item.semantic_model_workspace_id
                            ),
                        )
                    )
                )
                for item in evidence
            }
            await asyncio.gather(*lineage_tasks.values())
            lineage_by_report = {
                key: task.result() for key, task in lineage_tasks.items()
            }

        warnings.extend(
            self._collect_warnings(
                evidence=evidence,
                physical_by_model=physical_by_model,
                dax_by_model=dax_by_model,
            )
        )
        warnings = self._deduplicate_warnings(warnings)

        source_rows = (
            self._source_database_rows(evidence, physical_by_model)
            if SOURCE_DATABASE_LINEAGE in requested
            else []
        )
        semantic_rows = (
            self._semantic_model_object_rows(evidence)
            if SEMANTIC_MODEL_OBJECTS in requested
            else []
        )
        measure_rows = (
            self._measure_source_rows(
                evidence,
                physical_by_model,
                dax_by_model,
            )
            if MEASURE_SOURCE_LINEAGE in requested
            else []
        )
        report_layout_rows = (
            self._report_layout_rows(evidence) if REPORT_LAYOUT in requested else []
        )
        visual_rows = (
            self._visual_source_rows(evidence, lineage_by_report)
            if VISUAL_SOURCE_LOOKUP in requested
            else []
        )

        contexts = [self._report_context(item) for item in evidence]
        return ExplorerSnapshotResponse(
            generated_at=datetime.now(UTC),
            reports=contexts,
            report_count=len(contexts),
            semantic_model_count=len(self._model_keys(evidence)),
            warnings=warnings,
            source_database_lineage=SourceDatabaseLineageDataset(
                rows=source_rows,
                count=len(source_rows),
            ),
            semantic_model_objects=SemanticModelObjectsDataset(
                rows=semantic_rows,
                count=len(semantic_rows),
            ),
            measure_source_lineage=MeasureSourceLineageDataset(
                rows=measure_rows,
                count=len(measure_rows),
            ),
            report_layout=ReportLayoutDataset(
                rows=report_layout_rows,
                count=len(report_layout_rows),
            ),
            visual_source_lookup=VisualSourceLookupDataset(
                rows=visual_rows,
                count=len(visual_rows),
            ),
        )

    async def _gateway_datasources(
        self,
        *,
        access_token: str,
        bounded: Callable[
            [Callable[[], Awaitable[Any]]],
            Awaitable[Any],
        ],
    ) -> tuple[list[GatewayDatasource], list[ExplorerWarning]]:
        try:
            gateways = await bounded(
                lambda: self.gateway_service.list_gateways(
                    access_token=access_token,
                )
            )
        except AppException as exc:
            return [], [self._gateway_warning(exc)]

        results = await asyncio.gather(
            *(
                bounded(
                    lambda gateway_id=gateway.id: self.gateway_service.list_datasources(
                        gateway_id=gateway_id,
                        access_token=access_token,
                    )
                )
                for gateway in gateways.gateways
            ),
            return_exceptions=True,
        )

        datasources: list[GatewayDatasource] = []
        warnings: list[ExplorerWarning] = []
        for result in results:
            if isinstance(result, AppException):
                warnings.append(self._gateway_warning(result))
            elif isinstance(result, BaseException):
                raise result
            else:
                datasources.extend(result.datasources)
        return datasources, warnings

    @staticmethod
    def _gateway_warning(exc: AppException) -> ExplorerWarning:
        return ExplorerWarning(
            code=exc.code,
            message=(
                "Gateway metadata could not be included; semantic-model "
                "definition analysis continued."
            ),
        )

    @staticmethod
    def _resolve_semantic_model_id(
        selection: ExplorerReportSelection,
        report: Report,
        report_definition: NormalizedReportDefinitionResponse | None,
    ) -> str | None:
        if selection.semantic_model_id is not None:
            return str(selection.semantic_model_id)
        if report.dataset_id:
            return report.dataset_id
        if (
            report_definition is not None
            and report_definition.semantic_model is not None
            and report_definition.semantic_model.semantic_model_id
        ):
            return report_definition.semantic_model.semantic_model_id
        return None

    @staticmethod
    def _report_key(item: _ReportEvidence) -> tuple[str, str]:
        return (item.workspace.id, item.report.id)

    @staticmethod
    def _model_keys(evidence: list[_ReportEvidence]) -> set[tuple[str, str]]:
        return {
            model_key for item in evidence if (model_key := item.model_key) is not None
        }

    @staticmethod
    def _report_context(item: _ReportEvidence) -> ExplorerReportContext:
        return ExplorerReportContext(
            workspace_id=item.workspace.id,
            workspace_name=item.workspace.name,
            report_id=item.report.id,
            report_name=item.report.name,
            semantic_model_workspace_id=item.semantic_model_workspace_id,
            semantic_model_id=item.semantic_model_id,
            app_name=item.selection.app_name,
        )

    def _collect_warnings(
        self,
        *,
        evidence: list[_ReportEvidence],
        physical_by_model: dict[tuple[str, str], PhysicalSourceDiscoveryResponse],
        dax_by_model: dict[tuple[str, str], DaxDependencyAnalysisResponse],
    ) -> list[ExplorerWarning]:
        warnings: list[ExplorerWarning] = []
        seen_models: set[tuple[str, str]] = set()

        for item in evidence:
            if item.report_definition is not None:
                warnings.extend(
                    ExplorerWarning(
                        code="REPORT_DEFINITION_WARNING",
                        message=message,
                        workspace_id=item.workspace.id,
                        report_id=item.report.id,
                        semantic_model_id=item.semantic_model_id,
                    )
                    for message in item.report_definition.warnings
                )

            model_key = item.model_key
            if model_key is None or model_key in seen_models:
                continue
            seen_models.add(model_key)

            if item.semantic_model is not None:
                warnings.extend(
                    ExplorerWarning(
                        code=warning.code,
                        message=warning.message,
                        workspace_id=model_key[0],
                        semantic_model_id=model_key[1],
                        source_path=warning.path,
                    )
                    for warning in item.semantic_model.warnings
                )

            physical = physical_by_model.get(model_key)
            if physical is not None:
                warnings.extend(
                    ExplorerWarning(
                        code=warning.code,
                        message=warning.message,
                        workspace_id=model_key[0],
                        semantic_model_id=model_key[1],
                        source_path=warning.source_path,
                    )
                    for warning in physical.warnings
                )

            dax = dax_by_model.get(model_key)
            if dax is not None:
                warnings.extend(
                    ExplorerWarning(
                        code=warning.code,
                        message=warning.message,
                        workspace_id=model_key[0],
                        semantic_model_id=model_key[1],
                    )
                    for warning in dax.warnings
                )
                warnings.extend(
                    ExplorerWarning(
                        code="DAX_DEPENDENCY_CYCLE",
                        message=(
                            "DAX dependency cycle detected: "
                            + " -> ".join(cycle.members)
                        ),
                        workspace_id=model_key[0],
                        semantic_model_id=model_key[1],
                    )
                    for cycle in dax.cycles
                )

        return warnings

    @staticmethod
    def _deduplicate_warnings(
        warnings: list[ExplorerWarning],
    ) -> list[ExplorerWarning]:
        unique: dict[tuple[Any, ...], ExplorerWarning] = {}
        for warning in warnings:
            key = (
                warning.code,
                warning.message,
                warning.workspace_id,
                warning.report_id,
                warning.semantic_model_id,
                warning.source_path,
            )
            unique.setdefault(key, warning)
        return sorted(
            unique.values(),
            key=lambda item: (
                item.code.casefold(),
                (item.workspace_id or "").casefold(),
                (item.report_id or "").casefold(),
                (item.semantic_model_id or "").casefold(),
                (item.source_path or "").casefold(),
            ),
        )

    def _source_database_rows(
        self,
        evidence: list[_ReportEvidence],
        physical_by_model: dict[tuple[str, str], PhysicalSourceDiscoveryResponse],
    ) -> list[SourceDatabaseLineageRow]:
        rows: list[SourceDatabaseLineageRow] = []
        for item in evidence:
            if item.model_key is None:
                continue
            physical = physical_by_model[item.model_key]
            source_by_id = {source.source_id: source for source in physical.sources}

            for mapping in physical.mappings:
                for source_id in mapping.source_ids:
                    source = source_by_id.get(source_id)
                    if source is None:
                        continue
                    rows.append(
                        SourceDatabaseLineageRow(
                            workspace_id=item.workspace.id,
                            workspace_name=item.workspace.name,
                            report_id=item.report.id,
                            report_name=item.report.name,
                            semantic_model_workspace_id=item.model_key[0],
                            semantic_model_id=item.model_key[1],
                            app_name=item.selection.app_name,
                            semantic_table=mapping.semantic_table,
                            query_id=mapping.query_id,
                            partition_name=mapping.partition_name,
                            source_id=source.source_id,
                            source_kind=source.kind,
                            source_provider=source.provider,
                            source_connector=source.connector,
                            source_server=source.server,
                            source_database=source.database,
                            source_schema=source.schema_name,
                            source_object_name=source.object_name,
                            source_object_type=self._physical_object_type(source),
                            source_fully_qualified_name=(
                                self._physical_qualified_name(source)
                            ),
                            gateway_id=source.gateway_id,
                            gateway_datasource_id=(source.gateway_datasource_id),
                        )
                    )

        return sorted(
            rows,
            key=lambda row: (
                row.workspace_name.casefold(),
                row.report_name.casefold(),
                row.semantic_table.casefold(),
                row.partition_name.casefold(),
                row.source_fully_qualified_name.casefold(),
                row.source_id,
            ),
        )

    @staticmethod
    def _semantic_model_object_rows(
        evidence: list[_ReportEvidence],
    ) -> list[SemanticModelObjectRow]:
        rows: list[SemanticModelObjectRow] = []
        for item in evidence:
            model = item.semantic_model
            if model is None or item.model_key is None:
                continue
            common = {
                "workspace_id": item.workspace.id,
                "workspace_name": item.workspace.name,
                "report_id": item.report.id,
                "report_name": item.report.name,
                "semantic_model_workspace_id": item.model_key[0],
                "semantic_model_id": item.model_key[1],
                "app_name": item.selection.app_name,
            }

            for table in model.tables:
                rows.append(
                    SemanticModelObjectRow(
                        **common,
                        semantic_table=table.name,
                        semantic_object_type=(
                            "calculated_table" if table.expression else "table"
                        ),
                        semantic_object_name=table.name,
                        semantic_dax_expression=table.expression,
                        source_path=table.source_path,
                    )
                )
                rows.extend(
                    SemanticModelObjectRow(
                        **common,
                        semantic_table=table.name,
                        semantic_object_type=(
                            "calculated_column" if column.expression else "column"
                        ),
                        semantic_object_name=column.name,
                        semantic_data_type=column.data_type,
                        semantic_source_column=column.source_column,
                        semantic_dax_expression=column.expression,
                        is_hidden=column.is_hidden,
                        source_path=column.source_path,
                    )
                    for column in table.columns
                )
                rows.extend(
                    SemanticModelObjectRow(
                        **common,
                        semantic_table=table.name,
                        semantic_object_type="measure",
                        semantic_object_name=measure.name,
                        semantic_data_type="measure",
                        semantic_dax_expression=measure.expression,
                        format_string=measure.format_string,
                        is_hidden=measure.is_hidden,
                        source_path=measure.source_path,
                    )
                    for measure in table.measures
                )
                for hierarchy in table.hierarchies:
                    rows.append(
                        SemanticModelObjectRow(
                            **common,
                            semantic_table=table.name,
                            semantic_object_type="hierarchy",
                            semantic_object_name=hierarchy.name,
                            source_path=hierarchy.source_path,
                        )
                    )
                    rows.extend(
                        SemanticModelObjectRow(
                            **common,
                            semantic_table=table.name,
                            semantic_object_type="hierarchy_level",
                            semantic_object_name=level.name,
                            semantic_source_column=level.column,
                            source_path=level.source_path,
                        )
                        for level in hierarchy.levels
                    )

        return sorted(
            rows,
            key=lambda row: (
                row.workspace_name.casefold(),
                row.report_name.casefold(),
                row.semantic_table.casefold(),
                row.semantic_object_type,
                row.semantic_object_name.casefold(),
            ),
        )

    def _measure_source_rows(
        self,
        evidence: list[_ReportEvidence],
        physical_by_model: dict[tuple[str, str], PhysicalSourceDiscoveryResponse],
        dax_by_model: dict[tuple[str, str], DaxDependencyAnalysisResponse],
    ) -> list[MeasureSourceLineageRow]:
        rows: list[MeasureSourceLineageRow] = []
        for item in evidence:
            if item.model_key is None or item.semantic_model is None:
                continue
            dax = dax_by_model[item.model_key]
            physical = physical_by_model[item.model_key]
            expressions = self._expression_index(item.semantic_model)
            sources_by_table = self._physical_sources_by_table(physical)

            for owner in dax.objects:
                terminal_dependencies = self._terminal_dependencies(owner, dax)
                if not terminal_dependencies:
                    rows.append(
                        self._measure_source_row(
                            item=item,
                            owner=owner,
                            expression=expressions.get(owner.qualified_name.casefold()),
                            dependency=None,
                            dependency_depth=None,
                            physical_source=None,
                        )
                    )
                    continue

                for dependency, depth in terminal_dependencies:
                    physical_sources = sources_by_table.get(
                        (dependency.table_name or "").casefold(),
                        [],
                    )
                    if not physical_sources:
                        physical_sources = [None]

                    for physical_source in physical_sources:
                        rows.append(
                            self._measure_source_row(
                                item=item,
                                owner=owner,
                                expression=expressions.get(
                                    owner.qualified_name.casefold()
                                ),
                                dependency=dependency,
                                dependency_depth=depth,
                                physical_source=physical_source,
                            )
                        )

        return sorted(
            rows,
            key=lambda row: (
                row.workspace_name.casefold(),
                row.report_name.casefold(),
                (row.semantic_table or "").casefold(),
                row.semantic_object_name.casefold(),
                row.dependency_depth or 0,
                (row.source_semantic_table or "").casefold(),
                (row.source_semantic_object_name or "").casefold(),
                (row.source_fully_qualified_name or "").casefold(),
            ),
        )

    def _measure_source_row(
        self,
        *,
        item: _ReportEvidence,
        owner: DaxObjectReference,
        expression: str | None,
        dependency: DaxObjectReference | None,
        dependency_depth: int | None,
        physical_source: PhysicalDataSource | None,
    ) -> MeasureSourceLineageRow:
        if item.model_key is None:
            raise ValueError("Measure-source rows require a semantic model.")

        return MeasureSourceLineageRow(
            workspace_id=item.workspace.id,
            workspace_name=item.workspace.name,
            report_id=item.report.id,
            report_name=item.report.name,
            semantic_model_workspace_id=item.model_key[0],
            semantic_model_id=item.model_key[1],
            app_name=item.selection.app_name,
            semantic_table=owner.table_name,
            semantic_object_type=owner.object_type,
            semantic_object_name=owner.object_name,
            semantic_dax_expression=expression,
            source_semantic_table=(dependency.table_name if dependency else None),
            source_semantic_object_type=(
                dependency.object_type if dependency else None
            ),
            source_semantic_object_name=(
                dependency.object_name if dependency else None
            ),
            source_column_name=(
                dependency.object_name
                if dependency
                and dependency.object_type in {"column", "calculated_column"}
                else None
            ),
            dependency_depth=dependency_depth,
            is_direct_dependency=(
                dependency_depth == 1 if dependency_depth is not None else None
            ),
            source_id=(physical_source.source_id if physical_source else None),
            source_provider=(physical_source.provider if physical_source else None),
            source_server=(physical_source.server if physical_source else None),
            source_database=(physical_source.database if physical_source else None),
            source_schema=(physical_source.schema_name if physical_source else None),
            source_object_name=(
                physical_source.object_name if physical_source else None
            ),
            source_object_type=(
                self._physical_object_type(physical_source) if physical_source else None
            ),
            source_fully_qualified_name=(
                self._physical_qualified_name(physical_source)
                if physical_source
                else None
            ),
        )

    @staticmethod
    def _expression_index(
        semantic_model: ParsedSemanticModelResponse,
    ) -> dict[str, str]:
        expressions: dict[str, str] = {}
        for table in semantic_model.tables:
            if table.expression:
                expressions[table.name.casefold()] = table.expression
            for column in table.columns:
                if column.expression:
                    expressions[f"{table.name}[{column.name}]".casefold()] = (
                        column.expression
                    )
            for measure in table.measures:
                if measure.expression:
                    expressions[f"{table.name}[{measure.name}]".casefold()] = (
                        measure.expression
                    )
        return expressions

    @staticmethod
    def _terminal_dependencies(
        owner: DaxObjectReference,
        dax: DaxDependencyAnalysisResponse,
    ) -> list[tuple[DaxObjectReference, int]]:
        predecessors: dict[str, list[DaxObjectReference]] = defaultdict(list)
        for edge in dax.dependencies:
            predecessors[edge.target.qualified_name.casefold()].append(edge.source)

        terminals: dict[tuple[str, str], tuple[DaxObjectReference, int]] = {}

        def walk(
            current: DaxObjectReference,
            depth: int,
            path: frozenset[str],
        ) -> None:
            current_key = current.qualified_name.casefold()
            sources = predecessors.get(current_key, [])
            if not sources:
                if depth > 0:
                    terminal_key = (current.object_type, current_key)
                    existing = terminals.get(terminal_key)
                    if existing is None or depth < existing[1]:
                        terminals[terminal_key] = (current, depth)
                return

            for source in sources:
                source_key = source.qualified_name.casefold()
                if source_key in path:
                    continue
                walk(source, depth + 1, path | {source_key})

        owner_key = owner.qualified_name.casefold()
        walk(owner, 0, frozenset({owner_key}))
        return sorted(
            terminals.values(),
            key=lambda item: (
                item[1],
                item[0].qualified_name.casefold(),
                item[0].object_type,
            ),
        )

    @staticmethod
    def _physical_sources_by_table(
        physical: PhysicalSourceDiscoveryResponse,
    ) -> dict[str, list[PhysicalDataSource]]:
        source_by_id = {source.source_id: source for source in physical.sources}
        sources_by_table: dict[str, dict[str, PhysicalDataSource]] = defaultdict(dict)
        for mapping in physical.mappings:
            table_sources = sources_by_table[mapping.semantic_table.casefold()]
            for source_id in mapping.source_ids:
                source = source_by_id.get(source_id)
                if source is not None:
                    table_sources.setdefault(source_id, source)
        return {
            table_name: sorted(values.values(), key=lambda item: item.source_id)
            for table_name, values in sources_by_table.items()
        }

    @staticmethod
    def _report_layout_rows(
        evidence: list[_ReportEvidence],
    ) -> list[ReportLayoutRow]:
        rows: list[ReportLayoutRow] = []
        for item in evidence:
            definition = item.report_definition
            if definition is None:
                continue

            for page in definition.pages:
                for visual in page.visuals:
                    references = visual.field_references or [None]
                    position = visual.position
                    for reference in references:
                        rows.append(
                            ReportLayoutRow(
                                workspace_id=item.workspace.id,
                                workspace_name=item.workspace.name,
                                report_id=item.report.id,
                                report_name=item.report.name,
                                semantic_model_id=item.semantic_model_id,
                                app_name=item.selection.app_name,
                                report_definition_format=definition.format,
                                definition_part_count=definition.source_part_count,
                                page_id=page.name,
                                page_name=page.display_name,
                                page_order=page.order,
                                visual_id=visual.id,
                                visual_name=(visual.title or visual.internal_name),
                                visual_type=visual.visual_type,
                                field_usage=(reference.usage if reference else None),
                                field_role=reference.role if reference else None,
                                field_type=(
                                    reference.object_type if reference else None
                                ),
                                table_name=(
                                    reference.table_name if reference else None
                                ),
                                column_measure_name=(
                                    ExplorerService._field_name(reference)
                                    if reference
                                    else None
                                ),
                                aggregation=(
                                    reference.aggregation_function
                                    if reference
                                    else None
                                ),
                                query_reference=(
                                    reference.query_ref if reference else None
                                ),
                                visual_x=position.x if position else None,
                                visual_y=position.y if position else None,
                                visual_width=(position.width if position else None),
                                visual_height=(position.height if position else None),
                            )
                        )

        return sorted(
            rows,
            key=lambda row: (
                row.workspace_name.casefold(),
                row.report_name.casefold(),
                row.page_order if row.page_order is not None else 10**9,
                row.page_name.casefold(),
                row.visual_name.casefold(),
                (row.field_role or "").casefold(),
                (row.table_name or "").casefold(),
                (row.column_measure_name or "").casefold(),
            ),
        )

    @staticmethod
    def _visual_source_rows(
        evidence: list[_ReportEvidence],
        lineage_by_report: dict[tuple[str, str], ReportSemanticLineageResponse],
    ) -> list[VisualSourceLookupRow]:
        rows: list[VisualSourceLookupRow] = []
        for item in evidence:
            definition = item.report_definition
            model_key = item.model_key
            if definition is None or model_key is None:
                continue
            lineage = lineage_by_report[ExplorerService._report_key(item)]
            visual_index = ExplorerService._visual_index(definition)

            for match in lineage.field_matches:
                visual = visual_index.get((match.page_name, match.visual_id))
                if visual is None:
                    continue
                position = visual.position
                semantic_object = match.semantic_object
                reference = match.field_reference
                rows.append(
                    VisualSourceLookupRow(
                        workspace_id=item.workspace.id,
                        workspace_name=item.workspace.name,
                        report_id=item.report.id,
                        report_name=item.report.name,
                        semantic_model_workspace_id=model_key[0],
                        semantic_model_id=model_key[1],
                        app_name=item.selection.app_name,
                        page_id=match.page_name,
                        page_name=match.page_display_name,
                        visual_id=match.visual_id,
                        visual_name=(visual.title or visual.internal_name),
                        visual_type=match.visual_type,
                        field_usage=reference.usage,
                        field_role=reference.role,
                        field_type=reference.object_type,
                        visual_table_name=reference.table_name,
                        visual_field_name=(ExplorerService._field_name(reference)),
                        aggregation=reference.aggregation_function,
                        query_reference=reference.query_ref,
                        semantic_table=(
                            semantic_object.table_name if semantic_object else None
                        ),
                        semantic_object_name=(
                            semantic_object.object_name if semantic_object else None
                        ),
                        semantic_object_type=(
                            semantic_object.object_type if semantic_object else None
                        ),
                        semantic_object_source_path=(
                            semantic_object.source_path if semantic_object else None
                        ),
                        match_status=match.status,
                        match_confidence=match.match_confidence,
                        match_reason=match.reason,
                        visual_x=position.x if position else None,
                        visual_y=position.y if position else None,
                        visual_width=position.width if position else None,
                        visual_height=position.height if position else None,
                    )
                )

        return sorted(
            rows,
            key=lambda row: (
                row.workspace_name.casefold(),
                row.report_name.casefold(),
                row.page_name.casefold(),
                row.visual_name.casefold(),
                (row.field_role or "").casefold(),
                (row.visual_table_name or "").casefold(),
                (row.visual_field_name or "").casefold(),
            ),
        )

    @staticmethod
    def _visual_index(
        definition: NormalizedReportDefinitionResponse,
    ) -> dict[tuple[str, str], NormalizedReportVisual]:
        return {
            (page.name, visual.id): visual
            for page in definition.pages
            for visual in page.visuals
        }

    @staticmethod
    def _field_name(reference: Any) -> str | None:
        if reference.object_type == "hierarchy_level":
            return reference.level_name or reference.object_name
        if reference.object_type == "hierarchy":
            return reference.hierarchy_name or reference.object_name
        return reference.object_name

    @staticmethod
    def _physical_object_type(
        source: PhysicalDataSource,
    ) -> Literal["table", "query", "file", "url", "endpoint", "unknown"]:
        if source.object_name:
            return "table"
        if source.native_query:
            return "query"
        if source.path:
            return "file"
        if source.url:
            return "url"
        if any((source.server, source.database, source.account)):
            return "endpoint"
        return "unknown"

    @staticmethod
    def _physical_qualified_name(source: PhysicalDataSource) -> str:
        object_name = ".".join(
            part
            for part in (
                source.database,
                source.schema_name,
                source.object_name,
            )
            if part
        )
        if object_name:
            return object_name

        return (
            source.path
            or source.url
            or source.account
            or source.server
            or source.provider
        )
