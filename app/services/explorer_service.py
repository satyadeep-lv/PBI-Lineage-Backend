import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.core.exceptions import AppException, InvalidLineageRequestError
from app.domain.dax_lineage import (
    expression_index,
    physical_sources_by_table,
    terminal_dependencies,
)
from app.domain.lineage_ids import stable_lineage_id
from app.domain.semantic_model_filters import exclude_auto_date_tables
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
    ReportSourceTableDataset,
    ReportSourceTableRow,
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
    QuerySourceMapping,
)
from app.schemas.report import Report
from app.schemas.report_semantic_lineage import (
    ReportSemanticLineageResponse,
    SemanticLineageObject,
)
from app.schemas.workspace import Workspace
from app.services.cross_model_lineage_service import (
    CrossModelLineageService,
    build_lineage_tag_index,
)
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
    "report_source_tables",
    "semantic_model_objects",
    "measure_source_lineage",
    "report_layout",
    "visual_source_lookup",
]

SOURCE_DATABASE_LINEAGE: ExplorerDatasetName = "source_database_lineage"
REPORT_SOURCE_TABLES: ExplorerDatasetName = "report_source_tables"
SEMANTIC_MODEL_OBJECTS: ExplorerDatasetName = "semantic_model_objects"
MEASURE_SOURCE_LINEAGE: ExplorerDatasetName = "measure_source_lineage"
REPORT_LAYOUT: ExplorerDatasetName = "report_layout"
VISUAL_SOURCE_LOOKUP: ExplorerDatasetName = "visual_source_lookup"

ALL_EXPLORER_DATASETS = frozenset(
    {
        SOURCE_DATABASE_LINEAGE,
        REPORT_SOURCE_TABLES,
        SEMANTIC_MODEL_OBJECTS,
        MEASURE_SOURCE_LINEAGE,
        REPORT_LAYOUT,
        VISUAL_SOURCE_LOOKUP,
    }
)

_UNKNOWN_SOURCE_LABEL = (
    "Unknown Source (e.g., Local Excel File, Web Data, Dataflow, or Calculated Table)"
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
        cross_model_lineage_service: CrossModelLineageService | None = None,
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
        self.cross_model_lineage_service = (
            cross_model_lineage_service or CrossModelLineageService()
        )
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
                REPORT_SOURCE_TABLES,
                SEMANTIC_MODEL_OBJECTS,
                MEASURE_SOURCE_LINEAGE,
                VISUAL_SOURCE_LOOKUP,
            }
        )
        needs_physical_sources = bool(
            requested
            & {SOURCE_DATABASE_LINEAGE, REPORT_SOURCE_TABLES, MEASURE_SOURCE_LINEAGE}
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
                # Only pre-start the fetch when the caller pinned both halves
                # of the model's identity. Without an explicit workspace the
                # model may live in a different one than the report (a
                # cross-workspace binding), which is only knowable once the
                # report itself resolves.
                if (
                    selection.semantic_model_id is None
                    or selection.semantic_model_workspace_id is None
                ):
                    continue
                model_key = (
                    str(selection.semantic_model_workspace_id),
                    str(selection.semantic_model_id),
                )
                if model_key not in semantic_model_tasks:
                    semantic_model_tasks[model_key] = asyncio.create_task(
                        bounded(
                            lambda model_key=model_key: self._parsed_semantic_model(
                                workspace_id=model_key[0],
                                semantic_model_id=model_key[1],
                                access_token=fabric_access_token,
                                definition_format=(
                                    request.semantic_model_definition_format
                                ),
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
                self._resolve_semantic_model_workspace_id(selection, report)
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
                        lambda model_key=model_key: self._parsed_semantic_model(
                            workspace_id=model_key[0],
                            semantic_model_id=model_key[1],
                            access_token=fabric_access_token,
                            definition_format=(
                                request.semantic_model_definition_format
                            ),
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

        cross_model_index: dict[str, list[tuple[str, SemanticLineageObject]]] = {}
        dataset_display_names: dict[str, str] = {}
        if VISUAL_SOURCE_LOOKUP in requested and request.include_cross_model_matching:
            primary_models = {
                model_key[1]: semantic_model_tasks[model_key].result()
                for model_key in self._model_keys(evidence)
            }
            for item in evidence:
                if item.model_key is not None:
                    dataset_display_names.setdefault(
                        item.model_key[1],
                        item.report.name,
                    )

            discovery = await self.cross_model_lineage_service.discover(
                primary_dataset_ids=set(primary_models),
                primary_workspace_ids={
                    model_key[0] for model_key in self._model_keys(evidence)
                },
                powerbi_access_token=powerbi_access_token,
                fabric_access_token=fabric_access_token,
                semantic_model_definition_format=(
                    request.semantic_model_definition_format
                ),
            )
            warnings.extend(discovery.warnings)
            for dataset_id, ref in discovery.upstream_refs.items():
                if ref.name:
                    dataset_display_names.setdefault(dataset_id, ref.name)

            cross_model_index = build_lineage_tag_index(
                primary_models=primary_models,
                upstream_models=discovery.upstream_models,
            )

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
        report_source_table_rows = (
            self._report_source_table_rows(evidence, physical_by_model)
            if REPORT_SOURCE_TABLES in requested
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
            self._visual_source_rows(
                evidence,
                lineage_by_report,
                cross_model_index=cross_model_index,
                dataset_display_names=dataset_display_names,
            )
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
            report_source_tables=ReportSourceTableDataset(
                rows=report_source_table_rows,
                count=len(report_source_table_rows),
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

    async def _parsed_semantic_model(
        self,
        *,
        workspace_id: str,
        semantic_model_id: str,
        access_token: str,
        definition_format: str,
    ) -> ParsedSemanticModelResponse:
        """Fetch a model and strip Power BI's generated Auto Date/Time tables.

        Filtering here rather than per dataset keeps every explorer dataset
        (and the physical-source and DAX analysis they are derived from)
        consistent. The raw ``/definition/parsed`` route is left untouched so
        it still reports the model exactly as Fabric returns it.
        """
        model = await self.semantic_model_definition_service.get_parsed_definition(
            workspace_id=workspace_id,
            semantic_model_id=semantic_model_id,
            access_token=access_token,
            definition_format=definition_format,
        )
        return exclude_auto_date_tables(model)

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
    def _resolve_semantic_model_workspace_id(
        selection: ExplorerReportSelection,
        report: Report,
    ) -> str:
        """Where the report's semantic model actually lives.

        A report and the model it binds to are not always in the same
        workspace; Power BI reports that binding back as the report's
        ``datasetWorkspaceId``. Falling straight back to the report's own
        workspace (the previous behaviour) sends the Fabric definition call
        to the wrong workspace and the model resolves as missing.
        """
        if selection.semantic_model_workspace_id is not None:
            return str(selection.semantic_model_workspace_id)
        if report.dataset_workspace_id:
            return report.dataset_workspace_id
        return str(selection.workspace_id)

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
                resolved_sources = [
                    source_by_id[source_id]
                    for source_id in mapping.source_ids
                    if source_id in source_by_id
                ]
                if not resolved_sources:
                    rows.append(self._source_database_row(item, mapping, source=None))
                    continue

                rows.extend(
                    self._source_database_row(item, mapping, source=source)
                    for source in resolved_sources
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

    def _source_database_row(
        self,
        item: _ReportEvidence,
        mapping: QuerySourceMapping,
        *,
        source: PhysicalDataSource | None,
    ) -> SourceDatabaseLineageRow:
        if item.model_key is None:
            raise ValueError("Source-database rows require a semantic model.")

        common = {
            "workspace_id": item.workspace.id,
            "workspace_name": item.workspace.name,
            "report_id": item.report.id,
            "report_name": item.report.name,
            "semantic_model_workspace_id": item.model_key[0],
            "semantic_model_id": item.model_key[1],
            "app_name": item.selection.app_name,
            "semantic_table": mapping.semantic_table,
            "query_id": mapping.query_id,
            "partition_name": mapping.partition_name,
        }

        if source is None:
            return SourceDatabaseLineageRow(
                **common,
                source_id=stable_lineage_id(
                    "source",
                    "unknown",
                    item.model_key[0],
                    item.model_key[1],
                    mapping.semantic_table,
                    mapping.partition_name,
                ),
                source_kind="unknown",
                source_provider="unknown",
                source_object_type="unknown",
                source_fully_qualified_name=_UNKNOWN_SOURCE_LABEL,
            )

        return SourceDatabaseLineageRow(
            **common,
            source_id=source.source_id,
            source_kind=source.kind,
            source_provider=source.provider,
            source_connector=source.connector,
            source_server=source.server,
            source_database=source.database,
            source_schema=source.schema_name,
            source_object_name=source.object_name,
            source_object_type=self._physical_object_type(source),
            source_fully_qualified_name=self._physical_qualified_name(source),
            gateway_id=source.gateway_id,
            gateway_datasource_id=source.gateway_datasource_id,
        )

    def _report_source_table_rows(
        self,
        evidence: list[_ReportEvidence],
        physical_by_model: dict[tuple[str, str], PhysicalSourceDiscoveryResponse],
    ) -> list[ReportSourceTableRow]:
        seen: set[tuple[str, ...]] = set()
        rows: list[ReportSourceTableRow] = []
        for item in evidence:
            if item.model_key is None:
                continue
            physical = physical_by_model[item.model_key]
            source_by_id = {source.source_id: source for source in physical.sources}

            for mapping in physical.mappings:
                resolved_sources = [
                    source_by_id[source_id]
                    for source_id in mapping.source_ids
                    if source_id in source_by_id
                ]
                candidate_rows = (
                    [
                        ReportSourceTableRow(
                            workspace_name=item.workspace.name,
                            report_name=item.report.name,
                            report_id=item.report.id,
                            semantic_model_id=item.model_key[1],
                            source_account=source.account or source.server,
                            source_database=source.database,
                            source_schema=source.schema_name,
                            table_name=(
                                source.object_name or source.path or source.url
                            ),
                            source_object_type=self._physical_object_type(source),
                        )
                        for source in resolved_sources
                    ]
                    if resolved_sources
                    else [
                        ReportSourceTableRow(
                            workspace_name=item.workspace.name,
                            report_name=item.report.name,
                            report_id=item.report.id,
                            semantic_model_id=item.model_key[1],
                            source_object_type="unknown",
                        )
                    ]
                )

                for row in candidate_rows:
                    dedupe_key = (
                        row.report_id,
                        row.semantic_model_id,
                        (row.source_account or "").casefold(),
                        (row.source_database or "").casefold(),
                        (row.source_schema or "").casefold(),
                        (row.table_name or "").casefold(),
                        row.source_object_type,
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append(row)

        return sorted(
            rows,
            key=lambda row: (
                row.workspace_name.casefold(),
                row.report_name.casefold(),
                (row.source_database or "").casefold(),
                (row.source_schema or "").casefold(),
                (row.table_name or "").casefold(),
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
            expressions = expression_index(item.semantic_model)
            sources_by_table = physical_sources_by_table(physical)

            for owner in dax.objects:
                owner_terminal_dependencies = terminal_dependencies(owner, dax)
                if not owner_terminal_dependencies:
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

                for dependency, depth in owner_terminal_dependencies:
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
        *,
        cross_model_index: (
            dict[str, list[tuple[str, SemanticLineageObject]]] | None
        ) = None,
        dataset_display_names: dict[str, str] | None = None,
    ) -> list[VisualSourceLookupRow]:
        cross_model_index = cross_model_index or {}
        dataset_display_names = dataset_display_names or {}
        rows: list[VisualSourceLookupRow] = []
        for item in evidence:
            definition = item.report_definition
            model_key = item.model_key
            if definition is None or model_key is None:
                continue
            lineage = lineage_by_report[ExplorerService._report_key(item)]
            visual_index = ExplorerService._visual_index(definition)
            primary_dataset_id = model_key[1]

            for match in lineage.field_matches:
                visual = visual_index.get((match.page_name, match.visual_id))
                if visual is None:
                    continue
                position = visual.position
                semantic_object = match.semantic_object
                reference = match.field_reference

                (
                    semantic_object,
                    matched_dataset_id,
                    matched_semantic_model,
                    matched_model_role,
                    match_reason,
                ) = ExplorerService._resolve_matched_model(
                    semantic_object=semantic_object,
                    match_reason=match.reason,
                    primary_dataset_id=primary_dataset_id,
                    report_name=item.report.name,
                    cross_model_index=cross_model_index,
                    dataset_display_names=dataset_display_names,
                )

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
                        match_reason=match_reason,
                        primary_dataset_id=primary_dataset_id,
                        matched_dataset_id=matched_dataset_id,
                        matched_semantic_model=matched_semantic_model,
                        matched_model_role=matched_model_role,
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
    def _resolve_matched_model(
        *,
        semantic_object: SemanticLineageObject | None,
        match_reason: str | None,
        primary_dataset_id: str,
        report_name: str,
        cross_model_index: dict[str, list[tuple[str, SemanticLineageObject]]],
        dataset_display_names: dict[str, str],
    ) -> tuple[
        SemanticLineageObject | None,
        str | None,
        str | None,
        Literal["primary", "upstream"] | None,
        str | None,
    ]:
        if semantic_object is None:
            return None, None, None, None, match_reason

        matched_dataset_id = primary_dataset_id
        matched_semantic_model = dataset_display_names.get(
            primary_dataset_id,
            report_name,
        )
        matched_model_role: Literal["primary", "upstream"] = "primary"

        tag = semantic_object.source_lineage_tag
        if tag:
            for candidate_dataset_id, candidate_object in cross_model_index.get(
                tag.casefold(),
                [],
            ):
                if candidate_dataset_id == primary_dataset_id:
                    continue
                semantic_object = candidate_object
                matched_dataset_id = candidate_dataset_id
                matched_semantic_model = dataset_display_names.get(candidate_dataset_id)
                matched_model_role = "upstream"
                match_reason = (
                    f"{match_reason}; upstream object matched by SourceLineageTag"
                    if match_reason
                    else "Upstream object matched by SourceLineageTag"
                )
                break

        return (
            semantic_object,
            matched_dataset_id,
            matched_semantic_model,
            matched_model_role,
            match_reason,
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
    ) -> Literal["table", "view", "query", "file", "url", "endpoint", "unknown"]:
        if source.object_name:
            return source.object_kind or "table"
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
