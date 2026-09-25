"""Visual field -> physical database column lineage for one report.

Feeds the Explorer's "Report visuals" grid: one row per field a visual uses,
with the database columns and tables that field ultimately reads. It composes
what already exists rather than re-deriving it -- the report/model matcher
behind ``/semantic-lineage``, the TMDL DAX dependency graph walked by
``terminal_dependencies`` (the same walk the measure-source dataset uses),
physical source discovery, and composite-model resolution.

Every evidence source degrades on its own. A report definition, model
definition or source lookup that cannot be read becomes a warning plus rows
that say why they are unresolved -- never a 500, and never an invented column.
"""

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.core.exceptions import AppException
from app.domain.dax_lineage import (
    expression_index,
    physical_sources_by_table,
    terminal_dependencies,
)
from app.domain.semantic_model_filters import exclude_auto_date_tables
from app.schemas.dax_dependency import (
    DaxDependencyAnalysisResponse,
    DaxDependencyCycle,
    DaxObjectReference,
)
from app.schemas.explorer import (
    ExplorerReportSelection,
    ExplorerWarning,
    ReportVisualSourceColumnRow,
    ReportVisualSourceColumnsRequest,
    ReportVisualSourceColumnsResponse,
)
from app.schemas.gateway import GatewayDatasource
from app.schemas.normalized_report_definition import (
    NormalizedReportDefinitionResponse,
    VisualFieldReference,
)
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)
from app.schemas.physical_source import (
    PhysicalDataSource,
    PhysicalSourceDiscoveryResponse,
)
from app.schemas.report import Report
from app.schemas.report_semantic_lineage import SemanticLineageFieldMatch
from app.services.cross_workspace_source_resolver import (
    ANALYSIS_SERVICES_PROVIDER,
    CrossWorkspaceSourceResolver,
)
from app.services.dax_dependency_service import DaxDependencyService
from app.services.explorer_service import ExplorerService
from app.services.gateway_service import GatewayService
from app.services.physical_source_service import PhysicalSourceDiscoveryService
from app.services.report_definition_service import ReportDefinitionService
from app.services.report_semantic_lineage_service import (
    ReportSemanticLineageService,
)
from app.services.report_service import ReportService
from app.services.semantic_column_lineage_service import physical_column_references
from app.services.semantic_model_definition_service import (
    SemanticModelDefinitionService,
)
from app.services.semantic_model_service import SemanticModelService
from app.services.workspace_service import WorkspaceService

ResolutionStatus = Literal["resolved", "partial", "unresolved"]
SemanticObjectType = Literal["column", "measure", "calculated_column"]

REPORT_DEFINITION_FORMAT = "PBIR"
SEMANTIC_MODEL_DEFINITION_FORMAT = "TMDL"
_WORKSPACE_PAGE_SIZE = 5000
_MAX_LISTED_UNRESOLVED_REFERENCES = 3

# PBIR `Aggregation.Function` codes, used only to word a note.
_AGGREGATION_LABELS = {
    0: "Sum",
    1: "Average",
    2: "Count (distinct)",
    3: "Minimum",
    4: "Maximum",
    5: "Count",
    6: "Median",
    7: "Standard deviation",
    8: "Variance",
}


@dataclass
class _Evidence:
    """What is known about where one visual field's data comes from."""

    columns: set[str] = field(default_factory=set)
    tables: set[str] = field(default_factory=set)
    via_workspaces: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)
    # Some of the field's inputs could not be traced to a database.
    has_gap: bool = False
    has_cycle: bool = False
    # No database evidence can exist for this field at all (it is not in the
    # model, or it is a field parameter), whatever else is found.
    blocked: bool = False

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)

    def gap(self, text: str) -> None:
        self.has_gap = True
        self.note(text)

    def block(self, text: str) -> None:
        self.blocked = True
        self.note(text)

    def merge(self, other: "_Evidence") -> None:
        self.columns |= other.columns
        self.tables |= other.tables
        self.via_workspaces |= other.via_workspaces
        for text in other.notes:
            self.note(text)
        self.has_gap = self.has_gap or other.has_gap
        self.has_cycle = self.has_cycle or other.has_cycle
        self.blocked = self.blocked or other.blocked

    @property
    def status(self) -> ResolutionStatus:
        if self.blocked:
            return "unresolved"
        if self.has_cycle:
            return "partial"
        if self.columns or self.tables:
            return "partial" if self.has_gap else "resolved"
        return "unresolved"


class _ModelLineage:
    """Everything needed to trace a semantic object down to the database."""

    def __init__(
        self,
        *,
        model: ParsedSemanticModelResponse,
        model_key: tuple[str, str],
        physical: PhysicalSourceDiscoveryResponse,
        dax: DaxDependencyAnalysisResponse,
        upstream_models: dict[tuple[str, str], ParsedSemanticModelResponse],
    ) -> None:
        self.model = model
        self.model_key = model_key
        self.dax = dax
        self.upstream_models = upstream_models
        self.expressions = expression_index(model)
        self.sources_by_table = physical_sources_by_table(physical)
        self.tables = {table.name.casefold(): table for table in model.tables}
        self.columns = {
            (table.name.casefold(), column.name.casefold()): column
            for table in model.tables
            for column in table.columns
        }

        self.predecessors: dict[str, list[DaxObjectReference]] = defaultdict(list)
        for edge in dax.dependencies:
            self.predecessors[edge.target.qualified_name.casefold()].append(edge.source)

        self.cycles = [
            ({member.casefold() for member in cycle.members}, cycle)
            for cycle in dax.cycles
        ]
        self.unresolved_references: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for warning in dax.warnings:
            if warning.code == "DAX_REFERENCE_UNRESOLVED" and warning.object_name:
                self.unresolved_references[warning.object_name.casefold()].append(
                    (warning.object_name, warning.reference_text or "?")
                )

        # Only DAX problems a visual field actually reaches are reported, so
        # the grid is not buried under warnings for unused measures.
        self.reached_cycles: dict[str, DaxDependencyCycle] = {}
        self.reached_unresolved: set[tuple[str, str]] = set()
        self.unfollowed_hops: dict[str, tuple[str, PhysicalDataSource]] = {}

    def table(self, name: str | None) -> ParsedSemanticModelTable | None:
        return self.tables.get((name or "").casefold())

    def column(
        self,
        table_name: str | None,
        column_name: str | None,
    ) -> ParsedSemanticModelColumn | None:
        return self.columns.get(
            ((table_name or "").casefold(), (column_name or "").casefold())
        )

    def expression(self, owner: DaxObjectReference) -> str | None:
        return self.expressions.get(owner.qualified_name.casefold())

    # -- DAX objects -------------------------------------------------------

    def dax_evidence(
        self,
        owner: DaxObjectReference,
        *,
        visiting: frozenset[str] = frozenset(),
    ) -> _Evidence:
        """Follow a measure/calculated object to the base objects it reads."""
        evidence = _Evidence()
        owner_key = owner.qualified_name.casefold()
        if owner_key in visiting:
            return evidence
        visiting = visiting | {owner_key}

        closure = self._closure(owner_key)
        for members, cycle in self.cycles:
            if members & closure:
                self.reached_cycles[cycle.members[0].casefold()] = cycle
                evidence.has_cycle = True
                evidence.note(
                    "DAX dependency cycle: " + " -> ".join(cycle.members) + "."
                )

        unresolved = [
            item
            for name in sorted(closure)
            for item in self.unresolved_references.get(name, [])
        ]
        self.reached_unresolved.update(unresolved)
        if unresolved:
            listed = ", ".join(
                reference
                for _, reference in unresolved[:_MAX_LISTED_UNRESOLVED_REFERENCES]
            )
            more = len(unresolved) - _MAX_LISTED_UNRESOLVED_REFERENCES
            evidence.gap(
                f"DAX reference(s) {listed}"
                + (f" and {more} more" if more > 0 else "")
                + " could not be resolved to a model object."
            )

        terminals = terminal_dependencies(owner, self.dax)
        if not terminals and not evidence.has_cycle:
            evidence.note(
                f"{owner.qualified_name} reads no model column or table "
                "(for example a constant)."
            )

        for dependency, _depth in terminals:
            evidence.merge(self._terminal_evidence(dependency, visiting=visiting))

        return evidence

    def _terminal_evidence(
        self,
        dependency: DaxObjectReference,
        *,
        visiting: frozenset[str],
    ) -> _Evidence:
        if dependency.object_type == "column":
            column = self.column(dependency.table_name, dependency.object_name)
            if column is None:
                evidence = _Evidence()
                evidence.gap(f"{dependency.qualified_name} is not in the model.")
                return evidence
            return self.column_evidence(
                dependency.table_name or "",
                column,
                visiting=visiting,
            )

        if dependency.object_type == "table":
            # A whole-table read, e.g. COUNTROWS: the physical table is known,
            # no particular column is.
            evidence = self.source_evidence(dependency.table_name or "", column=None)
            evidence.note(f"Reads table '{dependency.table_name}' as a whole.")
            return evidence

        evidence = _Evidence()
        if dependency.object_type in {"calculated_column", "calculated_table"}:
            evidence.note(f"{dependency.qualified_name} reads no other model object.")
        else:
            evidence.gap(f"{dependency.qualified_name} could not be traced.")
        return evidence

    def _closure(self, owner_key: str) -> set[str]:
        seen = {owner_key}
        pending = [owner_key]
        while pending:
            current = pending.pop()
            for source in self.predecessors.get(current, []):
                source_key = source.qualified_name.casefold()
                if source_key not in seen:
                    seen.add(source_key)
                    pending.append(source_key)
        return seen

    # -- Columns and tables -----------------------------------------------

    def column_evidence(
        self,
        table_name: str,
        column: ParsedSemanticModelColumn,
        *,
        visiting: frozenset[str] = frozenset(),
    ) -> _Evidence:
        """Trace a non-calculated column to its physical column(s)."""
        table = self.table(table_name)
        if table is not None and table.expression:
            return self._calculated_table_column_evidence(
                table,
                column,
                visiting=visiting,
            )
        return self.source_evidence(table_name, column=column)

    def _calculated_table_column_evidence(
        self,
        table: ParsedSemanticModelTable,
        column: ParsedSemanticModelColumn,
        *,
        visiting: frozenset[str],
    ) -> _Evidence:
        if _is_field_parameter(table):
            evidence = _Evidence()
            evidence.block(
                f"'{table.name}' is a field parameter: the column it shows is "
                "chosen at run time, so no single source column applies."
            )
            return evidence

        evidence = self.dax_evidence(
            DaxObjectReference(
                object_type="calculated_table",
                table_name=table.name,
                object_name=table.name,
                qualified_name=table.name,
            ),
            visiting=visiting,
        )
        if evidence.columns or evidence.tables:
            evidence.gap(
                f"'{table.name}'[{column.name}] belongs to a calculated table; "
                "the sources shown are everything the table's DAX reads, not "
                "necessarily this column alone."
            )
        return evidence

    def source_evidence(
        self,
        table_name: str,
        *,
        column: ParsedSemanticModelColumn | None,
    ) -> _Evidence:
        """Physical tables (and, given a column, columns) behind a table."""
        evidence = _Evidence()
        sources = self.sources_by_table.get(table_name.casefold(), [])
        if not sources:
            evidence.gap(
                f"No physical source was detected for table '{table_name}' "
                "(for example a local file, web data, a dataflow or entered "
                "data)."
            )
            return evidence

        direct: list[PhysicalDataSource] = []
        via_groups: dict[tuple[str, str, str], list[PhysicalDataSource]] = {}
        for source in sources:
            if source.provider == ANALYSIS_SERVICES_PROVIDER:
                # The composite hop survived resolution: its "table" is a Power
                # BI model, which must never be reported as a database table.
                self.unfollowed_hops.setdefault(
                    table_name.casefold(),
                    (table_name, source),
                )
                evidence.gap(
                    f"Table '{table_name}' is a DirectQuery link to Power BI "
                    f"model '{source.database or '?'}' that could not be "
                    "followed to its database."
                )
            elif source.via_workspace_id and source.via_semantic_model_id:
                via_groups.setdefault(
                    (
                        source.via_workspace_id,
                        source.via_semantic_model_id,
                        source.via_semantic_table or table_name,
                    ),
                    [],
                ).append(source)
            elif source.kind == "database" and source.object_name:
                direct.append(source)
            else:
                evidence.gap(
                    f"Table '{table_name}' reads from {_describe_source(source)}, "
                    "which has no database columns to report."
                )

        if direct:
            _add_physical(
                evidence,
                direct,
                source_column_name=(
                    (column.source_column or column.name) if column else None
                ),
            )

        for (workspace_id, model_id, upstream_table), group in via_groups.items():
            evidence.via_workspaces.update(
                source.via_workspace_name
                for source in group
                if source.via_workspace_name
            )
            database_sources = [
                source
                for source in group
                if source.kind == "database" and source.object_name
            ]
            if not database_sources:
                evidence.gap(
                    f"Upstream table '{upstream_table}' reads from "
                    f"{_describe_source(group[0])}, which has no database "
                    "columns to report."
                )
                continue

            upstream_column_name = (
                self._upstream_column_name(
                    evidence,
                    workspace_id=workspace_id,
                    model_id=model_id,
                    model_label=group[0].via_semantic_model_name or model_id,
                    upstream_table_name=upstream_table,
                    column=column,
                )
                if column is not None
                else None
            )
            _add_physical(
                evidence,
                database_sources,
                source_column_name=upstream_column_name,
            )

        return evidence

    def _upstream_column_name(
        self,
        evidence: _Evidence,
        *,
        workspace_id: str,
        model_id: str,
        model_label: str,
        upstream_table_name: str,
        column: ParsedSemanticModelColumn,
    ) -> str | None:
        """The upstream model's ``sourceColumn`` for a composite column.

        A composite table's ``sourceColumn`` names the *upstream model's*
        column, not the database's, so the name has to be looked up again on
        the far side of the link.
        """
        upstream = self.upstream_models.get((workspace_id, model_id))
        if upstream is None:
            evidence.gap(
                f"The definition of upstream model '{model_label}' could not be "
                f"read, so the database column behind '{column.name}' is not "
                "known."
            )
            return None

        table = next(
            (
                candidate
                for candidate in upstream.tables
                if candidate.name.casefold() == upstream_table_name.casefold()
            ),
            None,
        )
        if table is None:
            evidence.gap(
                f"Table '{upstream_table_name}' was not found in upstream model "
                f"'{model_label}'."
            )
            return None

        upstream_column = None
        if column.source_lineage_tag:
            upstream_column = next(
                (
                    candidate
                    for candidate in table.columns
                    if candidate.lineage_tag
                    and candidate.lineage_tag.casefold()
                    == column.source_lineage_tag.casefold()
                ),
                None,
            )
        for name in (column.source_column, column.name):
            if upstream_column is not None or not name:
                continue
            upstream_column = next(
                (
                    candidate
                    for candidate in table.columns
                    if candidate.name.casefold() == name.casefold()
                ),
                None,
            )

        if upstream_column is None:
            evidence.gap(
                f"Column '{column.source_column or column.name}' was not found "
                f"in table '{table.name}' of upstream model '{model_label}'."
            )
            return None

        if upstream_column.expression:
            evidence.gap(
                f"'{table.name}'[{upstream_column.name}] is a calculated column "
                f"in upstream model '{model_label}'; its inputs are not followed "
                "across models."
            )
            return None

        if any(
            partition.expression_source
            or (partition.source_type or "").casefold() == "entity"
            for partition in table.partitions
        ):
            evidence.gap(
                f"Upstream table '{table.name}' is itself a composite link; the "
                "column name shown is the one that model carries and may differ "
                "from the database column."
            )

        return upstream_column.source_column or upstream_column.name

    # -- Warnings ----------------------------------------------------------

    def warnings(self) -> list[ExplorerWarning]:
        workspace_id, semantic_model_id = self.model_key
        warnings = [
            ExplorerWarning(
                code="DAX_DEPENDENCY_CYCLE",
                message="DAX dependency cycle detected: " + " -> ".join(cycle.members),
                workspace_id=workspace_id,
                semantic_model_id=semantic_model_id,
            )
            for cycle in self.reached_cycles.values()
        ]
        warnings.extend(
            ExplorerWarning(
                code="DAX_REFERENCE_UNRESOLVED",
                message=(
                    f"DAX reference {reference} in {owner} could not be resolved."
                ),
                workspace_id=workspace_id,
                semantic_model_id=semantic_model_id,
            )
            for owner, reference in sorted(self.reached_unresolved)
        )
        warnings.extend(
            ExplorerWarning(
                code="CROSS_WORKSPACE_SOURCE_UNRESOLVED",
                message=(
                    f"Table '{table_name}' links to Power BI model "
                    f"'{source.database or '?'}' at {source.server or '?'}; "
                    "fields from it are returned without database columns."
                ),
                workspace_id=workspace_id,
                semantic_model_id=semantic_model_id,
            )
            for table_name, source in self.unfollowed_hops.values()
        )
        return warnings


class ReportVisualSourceColumnService:
    def __init__(
        self,
        *,
        workspace_service: WorkspaceService | None = None,
        report_service: ReportService | None = None,
        report_definition_service: ReportDefinitionService | None = None,
        semantic_model_definition_service: (
            SemanticModelDefinitionService | None
        ) = None,
        semantic_model_service: SemanticModelService | None = None,
        report_semantic_lineage_service: (ReportSemanticLineageService | None) = None,
        gateway_service: GatewayService | None = None,
        cross_workspace_source_resolver: (CrossWorkspaceSourceResolver | None) = None,
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
        self.semantic_model_service = semantic_model_service or SemanticModelService()
        self.report_semantic_lineage_service = (
            report_semantic_lineage_service or ReportSemanticLineageService()
        )
        self.gateway_service = gateway_service or GatewayService()
        self.cross_workspace_source_resolver = (
            cross_workspace_source_resolver
            or CrossWorkspaceSourceResolver(
                workspace_service=self.workspace_service,
                semantic_model_service=self.semantic_model_service,
                semantic_model_definition_service=(
                    self.semantic_model_definition_service
                ),
            )
        )
        self.max_concurrency = max_concurrency

    async def build(
        self,
        request: ReportVisualSourceColumnsRequest,
        *,
        powerbi_access_token: str,
        fabric_access_token: str | None,
    ) -> ReportVisualSourceColumnsResponse:
        workspace_id = str(request.workspace_id)
        report_id = str(request.report_id)
        warnings: list[ExplorerWarning] = []

        if fabric_access_token is None:
            warnings.append(
                ExplorerWarning(
                    code="FABRIC_SESSION_REQUIRED",
                    message=(
                        "This session has no Fabric access, so the report and "
                        "semantic model definitions cannot be read and no "
                        "visual fields can be listed. Sign in with Fabric "
                        "access to see them."
                    ),
                    workspace_id=workspace_id,
                    report_id=report_id,
                )
            )

        # The workspace and report are the only hard requirements: without
        # them there is nothing to describe, so their errors propagate.
        workspace, report, report_definition = await asyncio.gather(
            self.workspace_service.get_workspace(
                workspace_id=workspace_id,
                access_token=powerbi_access_token,
            ),
            self.report_service.get_report(
                workspace_id=workspace_id,
                report_id=report_id,
                access_token=powerbi_access_token,
            ),
            self._report_definition(
                workspace_id=workspace_id,
                report_id=report_id,
                fabric_access_token=fabric_access_token,
                warnings=warnings,
            ),
        )

        selection = ExplorerReportSelection(
            workspace_id=request.workspace_id,
            report_id=request.report_id,
        )
        model_id = ExplorerService.resolve_semantic_model_id(
            selection,
            report,
            report_definition,
        )
        model_workspace_id: str | None = None
        model_name: str | None = None
        if model_id is None:
            warnings.append(
                ExplorerWarning(
                    code="SEMANTIC_MODEL_NOT_RESOLVED",
                    message=(
                        "The report does not name the semantic model it is "
                        "bound to, so no field could be traced to a source."
                    ),
                    workspace_id=workspace_id,
                    report_id=report_id,
                )
            )
        else:
            model_workspace_id, model_name = await self._locate_model(
                selection=selection,
                report=report,
                model_id=model_id,
                powerbi_access_token=powerbi_access_token,
                warnings=warnings,
            )

        lineage: _ModelLineage | None = None
        if (
            model_id is not None
            and model_workspace_id is not None
            and fabric_access_token is not None
        ):
            lineage = await self._model_lineage(
                model_workspace_id=model_workspace_id,
                model_id=model_id,
                include_gateway_sources=request.include_gateway_sources,
                powerbi_access_token=powerbi_access_token,
                fabric_access_token=fabric_access_token,
                warnings=warnings,
            )

        rows: list[ReportVisualSourceColumnRow] = []
        if report_definition is not None:
            warnings.extend(
                ExplorerWarning(
                    code="REPORT_DEFINITION_WARNING",
                    message=message,
                    workspace_id=workspace_id,
                    report_id=report_id,
                    semantic_model_id=model_id,
                )
                for message in report_definition.warnings
            )
            if lineage is not None:
                matches = await asyncio.to_thread(
                    self.report_semantic_lineage_service.match,
                    report=report_definition,
                    semantic_model=lineage.model,
                    semantic_model_workspace_id=lineage.model_key[0],
                )
                rows = [_row(match, lineage) for match in matches.field_matches]
            else:
                rows = _rows_without_model(
                    report_definition,
                    (
                        "The report's semantic model is not known."
                        if model_id is None
                        else "The semantic model definition could not be read."
                    ),
                )

        if lineage is not None:
            warnings.extend(lineage.warnings())

        statuses = [row.resolution_status for row in rows]
        return ReportVisualSourceColumnsResponse(
            workspace_id=workspace.id,
            workspace_name=workspace.name,
            report_id=report.id,
            report_name=report.name,
            semantic_model_id=model_id,
            semantic_model_name=model_name,
            semantic_model_workspace_id=model_workspace_id,
            rows=rows,
            total_field_reference_count=len(rows),
            resolved_count=statuses.count("resolved"),
            partial_count=statuses.count("partial"),
            unresolved_count=statuses.count("unresolved"),
            warnings=_deduplicate(warnings),
        )

    async def _report_definition(
        self,
        *,
        workspace_id: str,
        report_id: str,
        fabric_access_token: str | None,
        warnings: list[ExplorerWarning],
    ) -> NormalizedReportDefinitionResponse | None:
        if fabric_access_token is None:
            return None
        try:
            return await self.report_definition_service.get_normalized_definition(
                workspace_id=workspace_id,
                report_id=report_id,
                access_token=fabric_access_token,
                definition_format=REPORT_DEFINITION_FORMAT,
            )
        except AppException as exc:
            warnings.append(
                ExplorerWarning(
                    code="REPORT_DEFINITION_UNAVAILABLE",
                    message=(
                        "The report definition could not be read, so no visual "
                        f"fields can be listed: {exc.message}"
                    ),
                    workspace_id=workspace_id,
                    report_id=report_id,
                )
            )
            return None

    async def _locate_model(
        self,
        *,
        selection: ExplorerReportSelection,
        report: Report,
        model_id: str,
        powerbi_access_token: str,
        warnings: list[ExplorerWarning],
    ) -> tuple[str, str | None]:
        """Where the bound model lives, and what it is called.

        The workspace is inferred exactly as the other explorer routes do. That
        chain ends in "assume the report's own workspace" whenever Power BI
        omits ``datasetWorkspaceId`` -- which it routinely does -- so when the
        model is not listed there, the caller's other workspaces are searched
        before giving up. Every listing is a cached per-session read.
        """
        workspace_id = ExplorerService.resolve_semantic_model_workspace_id(
            selection,
            report,
        )
        name = await self._model_name(
            workspace_id=workspace_id,
            model_id=model_id,
            powerbi_access_token=powerbi_access_token,
        )
        if name is not None or report.dataset_workspace_id:
            return workspace_id, name

        found = await self._search_model_workspace(
            model_id=model_id,
            exclude_workspace_id=workspace_id,
            powerbi_access_token=powerbi_access_token,
        )
        if found is not None:
            return found

        warnings.append(
            ExplorerWarning(
                code="SEMANTIC_MODEL_WORKSPACE_UNRESOLVED",
                message=(
                    f"Semantic model {model_id} was not found in any workspace "
                    "visible to the signed-in user; its definition is requested "
                    "from the report's own workspace."
                ),
                workspace_id=workspace_id,
                report_id=report.id,
                semantic_model_id=model_id,
            )
        )
        return workspace_id, None

    async def _model_name(
        self,
        *,
        workspace_id: str,
        model_id: str,
        powerbi_access_token: str,
    ) -> str | None:
        try:
            listing = await self.semantic_model_service.list_semantic_models(
                workspace_id=workspace_id,
                access_token=powerbi_access_token,
            )
        except AppException:
            return None
        return next(
            (
                model.name
                for model in listing.semantic_models
                if model.id.casefold() == model_id.casefold()
            ),
            None,
        )

    async def _search_model_workspace(
        self,
        *,
        model_id: str,
        exclude_workspace_id: str,
        powerbi_access_token: str,
    ) -> tuple[str, str] | None:
        try:
            listing = await self.workspace_service.list_workspaces(
                access_token=powerbi_access_token,
                top=_WORKSPACE_PAGE_SIZE,
                skip=0,
            )
        except AppException:
            return None

        candidates = [
            workspace.id
            for workspace in listing.workspaces
            if workspace.id.casefold() != exclude_workspace_id.casefold()
        ]
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def probe(workspace_id: str) -> str | None:
            async with semaphore:
                return await self._model_name(
                    workspace_id=workspace_id,
                    model_id=model_id,
                    powerbi_access_token=powerbi_access_token,
                )

        names = await asyncio.gather(*(probe(item) for item in candidates))
        for workspace_id, name in zip(candidates, names, strict=True):
            if name is not None:
                return workspace_id, name
        return None

    async def _model_lineage(
        self,
        *,
        model_workspace_id: str,
        model_id: str,
        include_gateway_sources: bool,
        powerbi_access_token: str,
        fabric_access_token: str,
        warnings: list[ExplorerWarning],
    ) -> _ModelLineage | None:
        model_key = (model_workspace_id, model_id)

        async def no_gateways() -> tuple[list[GatewayDatasource], list[Any]]:
            return [], []

        model, (gateway_datasources, gateway_warnings) = await asyncio.gather(
            self._semantic_model(
                model_key=model_key,
                fabric_access_token=fabric_access_token,
                warnings=warnings,
            ),
            (
                self._gateway_datasources(access_token=powerbi_access_token)
                if include_gateway_sources
                else no_gateways()
            ),
        )
        warnings.extend(gateway_warnings)
        if model is None:
            return None

        warnings.extend(
            ExplorerWarning(
                code=warning.code,
                message=warning.message,
                workspace_id=model_workspace_id,
                semantic_model_id=model_id,
                source_path=warning.path,
            )
            for warning in model.warnings
        )

        physical = await asyncio.to_thread(
            PhysicalSourceDiscoveryService().discover,
            model,
            gateway_datasources=gateway_datasources,
        )
        warnings.extend(
            ExplorerWarning(
                code=warning.code,
                message=warning.message,
                workspace_id=model_workspace_id,
                semantic_model_id=model_id,
                source_path=warning.source_path,
            )
            for warning in physical.warnings
        )

        # Always on: a composite table must report the database behind the
        # link, not the Power BI model it points at.
        try:
            (
                resolved,
                resolver_warnings,
            ) = await self.cross_workspace_source_resolver.resolve(
                physical_by_model={model_key: physical},
                models_by_key={model_key: model},
                powerbi_access_token=powerbi_access_token,
                fabric_access_token=fabric_access_token,
                definition_format=SEMANTIC_MODEL_DEFINITION_FORMAT,
            )
        except AppException as exc:
            warnings.append(
                ExplorerWarning(
                    code="CROSS_WORKSPACE_RESOLUTION_FAILED",
                    message=(
                        "Composite model links could not be followed; affected "
                        f"fields are returned without database columns: "
                        f"{exc.message}"
                    ),
                    workspace_id=model_workspace_id,
                    semantic_model_id=model_id,
                )
            )
        else:
            physical = resolved[model_key]
            warnings.extend(resolver_warnings)

        dax = await asyncio.to_thread(DaxDependencyService().analyze, model)
        upstream_models = await self._upstream_models(
            physical,
            fabric_access_token=fabric_access_token,
        )

        return _ModelLineage(
            model=model,
            model_key=model_key,
            physical=physical,
            dax=dax,
            upstream_models=upstream_models,
        )

    async def _semantic_model(
        self,
        *,
        model_key: tuple[str, str],
        fabric_access_token: str,
        warnings: list[ExplorerWarning],
    ) -> ParsedSemanticModelResponse | None:
        definitions = self.semantic_model_definition_service
        try:
            model = await definitions.get_parsed_definition(
                workspace_id=model_key[0],
                semantic_model_id=model_key[1],
                access_token=fabric_access_token,
                definition_format=SEMANTIC_MODEL_DEFINITION_FORMAT,
            )
        except AppException as exc:
            warnings.append(
                ExplorerWarning(
                    code="SEMANTIC_MODEL_DEFINITION_UNAVAILABLE",
                    message=(
                        "The semantic model definition could not be read, so "
                        f"no field could be traced to a source: {exc.message}"
                    ),
                    workspace_id=model_key[0],
                    semantic_model_id=model_key[1],
                )
            )
            return None
        # The same filter every explorer dataset applies, so a date axis does
        # not surface Power BI's generated tables as sources.
        return exclude_auto_date_tables(model)

    async def _upstream_models(
        self,
        physical: PhysicalSourceDiscoveryResponse,
        *,
        fabric_access_token: str,
    ) -> dict[tuple[str, str], ParsedSemanticModelResponse]:
        """Upstream models behind resolved composite sources.

        The resolver has just fetched these, so with the session cache on this
        is a cache hit, not another Fabric definition call.
        """
        keys = list(
            dict.fromkeys(
                (source.via_workspace_id, source.via_semantic_model_id)
                for source in physical.sources
                if source.via_workspace_id and source.via_semantic_model_id
            )
        )

        definitions = self.semantic_model_definition_service

        async def fetch(key: tuple[str, str]) -> ParsedSemanticModelResponse | None:
            try:
                return await definitions.get_parsed_definition(
                    workspace_id=key[0],
                    semantic_model_id=key[1],
                    access_token=fabric_access_token,
                    definition_format=SEMANTIC_MODEL_DEFINITION_FORMAT,
                )
            except AppException:
                return None

        results = await asyncio.gather(*(fetch(key) for key in keys))
        return {
            key: model
            for key, model in zip(keys, results, strict=True)
            if model is not None
        }

    async def _gateway_datasources(
        self,
        *,
        access_token: str,
    ) -> tuple[list[GatewayDatasource], list[ExplorerWarning]]:
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def bounded(factory: Callable[[], Awaitable[Any]]) -> Any:
            async with semaphore:
                return await factory()

        try:
            gateways = await self.gateway_service.list_gateways(
                access_token=access_token,
            )
        except AppException as exc:
            return [], [_gateway_warning(exc)]

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
                warnings.append(_gateway_warning(result))
            elif isinstance(result, BaseException):
                raise result
            else:
                datasources.extend(result.datasources)
        return datasources, warnings


def _row(
    match: SemanticLineageFieldMatch,
    lineage: _ModelLineage,
) -> ReportVisualSourceColumnRow:
    reference = match.field_reference
    semantic_object = match.semantic_object

    if semantic_object is None:
        evidence = _Evidence()
        evidence.block(_unmatched_note(reference, match.reason))
        return _build_row(
            match,
            evidence,
            semantic_table=reference.table_name,
            semantic_object_name=_reference_name(reference),
            semantic_object_type=_reference_type(reference),
            dax_expression=None,
        )

    table_name = semantic_object.table_name

    if semantic_object.object_type == "measure":
        owner = _dax_reference("measure", table_name, semantic_object.object_name)
        return _build_row(
            match,
            lineage.dax_evidence(owner),
            semantic_table=table_name,
            semantic_object_name=semantic_object.object_name,
            semantic_object_type="measure",
            dax_expression=lineage.expression(owner),
        )

    if semantic_object.object_type == "column":
        column = lineage.column(table_name, semantic_object.object_name)
        evidence, object_type, expression = _column_field_evidence(
            lineage,
            table_name,
            column,
        )
        if reference.aggregation_function is not None and column is not None:
            label = _AGGREGATION_LABELS.get(
                reference.aggregation_function,  # type: ignore[arg-type]
                f"Aggregation {reference.aggregation_function}",
            )
            evidence.note(
                f"Implicit measure: {label} of '{table_name}'[{column.name}]."
            )
        return _build_row(
            match,
            evidence,
            semantic_table=table_name,
            semantic_object_name=semantic_object.object_name,
            semantic_object_type=object_type,
            dax_expression=expression,
        )

    # Hierarchies are read through the column(s) behind their levels.
    table = lineage.table(table_name)
    hierarchy = next(
        (
            candidate
            for candidate in (table.hierarchies if table else [])
            if candidate.name.casefold()
            == (semantic_object.hierarchy_name or "").casefold()
        ),
        None,
    )
    levels = [
        level
        for level in (hierarchy.levels if hierarchy else [])
        if semantic_object.object_type == "hierarchy"
        or level.name.casefold()
        == (semantic_object.level_name or semantic_object.object_name).casefold()
    ]
    evidence = _Evidence()
    object_types: set[SemanticObjectType] = set()
    expressions: list[str] = []
    level_columns: list[str] = []
    for level in levels:
        column = lineage.column(table_name, level.column)
        level_evidence, object_type, expression = _column_field_evidence(
            lineage,
            table_name,
            column,
        )
        evidence.merge(level_evidence)
        if object_type:
            object_types.add(object_type)
        if expression:
            expressions.append(expression)
        if column is not None:
            level_columns.append(column.name)
    if not levels:
        evidence.block(
            f"No level of hierarchy '{semantic_object.hierarchy_name}' could be "
            "matched to a column."
        )

    if semantic_object.object_type == "hierarchy_level":
        evidence.note(
            f"Hierarchy level '{semantic_object.level_name}' of "
            f"'{semantic_object.hierarchy_name}'."
        )
        name = level_columns[0] if level_columns else semantic_object.object_name
        object_type = next(iter(object_types)) if len(object_types) == 1 else None
    else:
        evidence.note(
            f"Hierarchy '{semantic_object.hierarchy_name}' over "
            + (", ".join(level_columns) or "no known column")
            + "."
        )
        name = semantic_object.object_name
        object_type = None

    return _build_row(
        match,
        evidence,
        semantic_table=table_name,
        semantic_object_name=name,
        semantic_object_type=object_type,
        dax_expression=expressions[0] if len(expressions) == 1 else None,
    )


def _column_field_evidence(
    lineage: _ModelLineage,
    table_name: str,
    column: ParsedSemanticModelColumn | None,
) -> tuple[_Evidence, SemanticObjectType | None, str | None]:
    if column is None:
        evidence = _Evidence()
        evidence.block(f"A column of '{table_name}' could not be found in the model.")
        return evidence, None, None

    if column.expression:
        owner = _dax_reference("calculated_column", table_name, column.name)
        return lineage.dax_evidence(owner), "calculated_column", column.expression

    return lineage.column_evidence(table_name, column), "column", None


def _build_row(
    match: SemanticLineageFieldMatch,
    evidence: _Evidence,
    *,
    semantic_table: str | None,
    semantic_object_name: str | None,
    semantic_object_type: SemanticObjectType | None,
    dax_expression: str | None,
) -> ReportVisualSourceColumnRow:
    return ReportVisualSourceColumnRow(
        page_name=match.page_display_name,
        page_id=match.page_name,
        visual_id=match.visual_id,
        visual_title=match.visual_title,
        visual_type=match.visual_type,
        field_role=_field_role(match.field_reference),
        semantic_table=semantic_table,
        semantic_object_name=semantic_object_name,
        semantic_object_type=semantic_object_type,
        dax_expression=dax_expression,
        source_columns=sorted(evidence.columns, key=str.casefold),
        source_tables=sorted(evidence.tables, key=str.casefold),
        via_workspace_name=(
            ", ".join(sorted(evidence.via_workspaces, key=str.casefold)) or None
        ),
        resolution_status=evidence.status,
        resolution_note=" ".join(evidence.notes) or None,
    )


def _rows_without_model(
    definition: NormalizedReportDefinitionResponse,
    note: str,
) -> list[ReportVisualSourceColumnRow]:
    """Every visual field, unresolved, when there is no model to trace into."""
    rows: list[ReportVisualSourceColumnRow] = []
    for page in definition.pages:
        for visual in page.visuals:
            for reference in visual.field_references:
                evidence = _Evidence()
                evidence.block(note)
                rows.append(
                    _build_row(
                        SemanticLineageFieldMatch(
                            page_name=page.name,
                            page_display_name=page.display_name,
                            visual_id=visual.id,
                            visual_title=visual.title,
                            visual_type=visual.visual_type,
                            field_reference=reference,
                            status="unmatched",
                        ),
                        evidence,
                        semantic_table=reference.table_name,
                        semantic_object_name=_reference_name(reference),
                        semantic_object_type=_reference_type(reference),
                        dax_expression=None,
                    )
                )
    return rows


def _add_physical(
    evidence: _Evidence,
    sources: list[PhysicalDataSource],
    *,
    source_column_name: str | None,
) -> None:
    for source in sources:
        evidence.tables.add(
            ".".join(
                part
                for part in (source.database, source.schema_name, source.object_name)
                if part
            )
        )
    if source_column_name:
        evidence.columns.update(
            reference.column_name
            for reference in physical_column_references(
                source_column_name=source_column_name,
                sources=sources,
            )
        )


def _describe_source(source: PhysicalDataSource) -> str:
    if source.path:
        return f"a file ({source.path})"
    if source.url:
        return f"a web source ({source.url})"
    if source.native_query:
        return "a native query whose tables could not be identified"
    return f"a {source.provider} source"


def _is_field_parameter(table: ParsedSemanticModelTable) -> bool:
    # Field parameters are calculated tables built from NAMEOF() tuples.
    return "nameof(" in (table.expression or "").casefold()


def _dax_reference(
    object_type: Literal["measure", "calculated_column"],
    table_name: str,
    object_name: str,
) -> DaxObjectReference:
    return DaxObjectReference(
        object_type=object_type,
        table_name=table_name,
        object_name=object_name,
        qualified_name=f"{table_name}[{object_name}]",
    )


def _field_role(reference: VisualFieldReference) -> str | None:
    if reference.role:
        return reference.role
    return {"filter": "Filter", "sort": "Sort"}.get(reference.usage)


def _reference_name(reference: VisualFieldReference) -> str | None:
    if reference.object_type == "hierarchy_level":
        return reference.level_name or reference.object_name
    if reference.object_type == "hierarchy":
        return reference.hierarchy_name or reference.object_name
    return reference.object_name


def _reference_type(reference: VisualFieldReference) -> SemanticObjectType | None:
    if reference.object_type in {"column", "measure"}:
        return reference.object_type  # type: ignore[return-value]
    return None


def _unmatched_note(reference: VisualFieldReference, reason: str | None) -> str:
    table = reference.table_name or "?"
    name = _reference_name(reference) or "?"
    if reason == "visual_calculation":
        return (
            f"Visual calculation '{name}' is defined on the visual, not in the "
            "semantic model; it has no database source of its own."
        )
    if reason == "table_not_found":
        return f"Table '{table}' is not in the semantic model."
    if reason == "object_not_found":
        return (
            f"'{table}'[{name}] is not in the semantic model (for example a "
            "report-level measure)."
        )
    if reason == "hierarchy_not_found":
        hierarchy = reference.hierarchy_name or name
        hint = (
            " It is likely Power BI's automatic date hierarchy, whose generated "
            "table is excluded."
            if hierarchy.casefold() == "date hierarchy"
            else ""
        )
        return f"Hierarchy '{hierarchy}' is not in table '{table}'.{hint}"
    if reason == "hierarchy_level_not_found":
        return (
            f"Level '{name}' is not in hierarchy '{reference.hierarchy_name}' of "
            f"table '{table}'."
        )
    if reason in {"missing_table_name", "missing_hierarchy_name"}:
        return "The visual does not say which table this field comes from."
    if reason in {"missing_object_name", "missing_level_name"}:
        return "The visual does not name this field."
    return f"This field could not be matched to the semantic model ({reason})."


def _gateway_warning(exc: AppException) -> ExplorerWarning:
    return ExplorerWarning(
        code=exc.code,
        message=(
            "Gateway metadata could not be included; semantic-model "
            "definition analysis continued."
        ),
    )


def _deduplicate(warnings: list[ExplorerWarning]) -> list[ExplorerWarning]:
    unique: dict[tuple[Any, ...], ExplorerWarning] = {}
    for warning in warnings:
        unique.setdefault(
            (
                warning.code,
                warning.message,
                warning.workspace_id,
                warning.report_id,
                warning.semantic_model_id,
                warning.source_path,
            ),
            warning,
        )
    return sorted(unique.values(), key=lambda item: item.code.casefold())
