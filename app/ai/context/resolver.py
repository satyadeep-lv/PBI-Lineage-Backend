import asyncio

from app.ai.context.semantic_objects import find_semantic_object
from app.ai.models.context import ResolvedAIContext, ResolvedObject, ResolvedReport
from app.ai.models.requests import AIChatContext
from app.core.exceptions import AppException
from app.domain.semantic_model_filters import exclude_auto_date_tables
from app.schemas.lineage_graph import (
    LineageGraph,
    LineageGraphBuildRequest,
    LineageNodeType,
)
from app.schemas.parsed_semantic_model import ParsedSemanticModelResponse
from app.schemas.physical_source import PhysicalSourceDiscoveryResponse
from app.schemas.report import Report
from app.schemas.report_semantic_lineage import ReportSemanticLineageResponse
from app.services.cross_workspace_source_resolver import CrossWorkspaceSourceResolver
from app.services.lineage_graph_service import LineageGraphService
from app.services.lineage_search_service import LineageSearchService
from app.services.physical_source_service import PhysicalSourceDiscoveryService
from app.services.report_definition_service import ReportDefinitionService
from app.services.report_service import ReportService
from app.services.semantic_model_definition_service import (
    SemanticModelDefinitionService,
)
from app.services.semantic_model_service import SemanticModelService
from app.services.workspace_service import WorkspaceService

_NODE_TYPES_BY_OBJECT_TYPE: dict[str, list[LineageNodeType]] = {
    "measure": ["semantic_measure"],
    "calculated_column": ["semantic_column"],
    "column": ["semantic_column"],
    "table": ["semantic_table"],
}
_DEFAULT_OBJECT_NODE_TYPES: list[LineageNodeType] = [
    "semantic_measure",
    "semantic_column",
]
_RESOLVED_OBJECT_TYPE_BY_NODE_TYPE = {
    "semantic_measure": "measure",
    "semantic_table": "table",
}

# Object types that name something inside the semantic model. A report,
# visual or model selection carries its own name as `object_name`, and
# searching the model for a report's name only produced a spurious
# "no object named ..." note that then blocked the answer.
_MODEL_OBJECT_TYPES = frozenset({"measure", "calculated_column", "column", "table"})

# Bounds on the best-effort enrichment below. Every step degrades to a
# coverage note, so these only ever trade completeness for latency.
_MAX_RELATED_REPORTS = 8
_WORKSPACE_PAGE_SIZE = 5000
_LOOKUP_CONCURRENCY = 8
_ENRICHMENT_TIMEOUT_SECONDS = 25.0


def build_lineage_graph(
    parsed_semantic_model: ParsedSemanticModelResponse,
    *,
    report_lineage: ReportSemanticLineageResponse | None = None,
    physical_sources: PhysicalSourceDiscoveryResponse | None = None,
) -> LineageGraph:
    """Single, shared entry point for turning fetched evidence into a graph.

    Reused by the context resolver (object resolution) and every lineage/
    impact tool, so the graph algorithm itself is never duplicated.
    """
    return LineageGraphService().build(
        LineageGraphBuildRequest(
            semantic_model=parsed_semantic_model,
            report_lineage=report_lineage,
            physical_sources=physical_sources,
        )
    )


class AIContextResolver:
    """Validates and resolves AI request context against real access.

    Each step only proceeds once the prior one succeeded, mirroring:
    workspace access -> report belongs to workspace -> semantic model
    belongs to workspace -> resolve named object. A failure at any step
    collapses to the same "could not verify" note regardless of whether the
    underlying cause was 401/403/404, so a caller can never distinguish
    "exists but you can't see it" from "does not exist".

    After that, a best-effort enrichment pass adds what makes an answer
    complete rather than merely correct: display names, the real databases
    behind a composite model, and the other reports bound to the model.
    Enrichment only ever reads with the caller's own tokens, and a failure
    there becomes a coverage note, never a refusal.
    """

    def __init__(
        self,
        *,
        powerbi_access_token: str | None,
        fabric_access_token: str | None,
    ) -> None:
        self._powerbi_access_token = powerbi_access_token
        self._fabric_access_token = fabric_access_token

    async def resolve(
        self,
        context: AIChatContext | None,
    ) -> ResolvedAIContext:
        resolved = ResolvedAIContext()

        if context is None:
            return resolved

        if context.workspace_id:
            await self._resolve_workspace(resolved, context.workspace_id)

        report: Report | None = None
        if resolved.workspace_id and context.report_id:
            report = await self._resolve_report(resolved, context.report_id)

        semantic_model_id = self._semantic_model_id(resolved, context, report)
        if resolved.workspace_id and semantic_model_id:
            await self._resolve_semantic_model(
                resolved,
                semantic_model_id,
                candidate_workspace_ids=[
                    context.semantic_model_workspace_id,
                    report.dataset_workspace_id if report else None,
                    resolved.workspace_id,
                ],
                # Only a model the report itself points at is worth hunting
                # for across workspaces; a client-supplied id is not.
                search_other_workspaces=report is not None,
            )

        if (
            resolved.parsed_semantic_model
            and (context.object_name or context.object_id)
            and (context.object_type or "") in (_MODEL_OBJECT_TYPES | {""})
        ):
            await self._resolve_object(resolved, context)

        if resolved.parsed_semantic_model is not None:
            try:
                await asyncio.wait_for(
                    self._enrich(resolved, context),
                    timeout=_ENRICHMENT_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                resolved.coverage_notes.append(
                    "Some related metadata (model name, database sources or "
                    "other reports on this model) took too long to load and "
                    "was left out."
                )

        return resolved

    @staticmethod
    def _semantic_model_id(
        resolved: ResolvedAIContext,
        context: AIChatContext,
        report: Report | None,
    ) -> str | None:
        if context.semantic_model_id:
            return context.semantic_model_id
        if report is not None and report.dataset_id:
            return report.dataset_id
        definition = resolved.report_definition
        if definition is not None and definition.semantic_model is not None:
            return definition.semantic_model.semantic_model_id
        return None

    async def _resolve_workspace(
        self,
        resolved: ResolvedAIContext,
        workspace_id: str,
    ) -> None:
        if not self._powerbi_access_token:
            resolved.resolution_notes.append(
                "No Power BI session is available to verify workspace access."
            )
            return

        try:
            workspace = await WorkspaceService().get_workspace(
                workspace_id=workspace_id,
                access_token=self._powerbi_access_token,
            )
        except AppException:
            resolved.resolution_notes.append(
                "The requested workspace could not be verified against the "
                "authenticated session."
            )
            return

        resolved.workspace_id = workspace_id
        resolved.workspace_name = workspace.name

    async def _resolve_report(
        self,
        resolved: ResolvedAIContext,
        report_id: str,
    ) -> Report | None:
        if not self._powerbi_access_token:
            resolved.resolution_notes.append(
                "No Power BI session is available to verify report access."
            )
            return None

        try:
            report = await ReportService().get_report(
                workspace_id=resolved.workspace_id,
                report_id=report_id,
                access_token=self._powerbi_access_token,
            )
        except AppException:
            resolved.resolution_notes.append(
                "The requested report could not be verified within the "
                "authorized workspace."
            )
            return None

        resolved.report_id = report_id
        resolved.report_name = report.name

        if not self._fabric_access_token:
            resolved.resolution_notes.append(
                "No Fabric session is available to retrieve the report definition."
            )
            return report

        try:
            resolved.report_definition = (
                await ReportDefinitionService().get_normalized_definition(
                    workspace_id=resolved.workspace_id,
                    report_id=report_id,
                    access_token=self._fabric_access_token,
                )
            )
        except AppException:
            resolved.resolution_notes.append(
                "The report definition could not be retrieved."
            )

        return report

    async def _resolve_semantic_model(
        self,
        resolved: ResolvedAIContext,
        semantic_model_id: str,
        *,
        candidate_workspace_ids: list[str | None],
        search_other_workspaces: bool,
    ) -> None:
        if not self._fabric_access_token:
            resolved.resolution_notes.append(
                "No Fabric session is available to verify the semantic model."
            )
            return

        # A report and the model it binds to are not always in one workspace,
        # and Power BI does not reliably report `datasetWorkspaceId`, so each
        # plausible home is tried in turn. The Fabric read itself is the
        # access check: it only succeeds where the caller may read the model.
        tried: list[str] = []
        for workspace_id in dict.fromkeys(filter(None, candidate_workspace_ids)):
            tried.append(workspace_id)
            if await self._load_semantic_model(
                resolved, workspace_id, semantic_model_id
            ):
                return

        if search_other_workspaces:
            workspace_id = await self._find_model_workspace(semantic_model_id, tried)
            if workspace_id and await self._load_semantic_model(
                resolved, workspace_id, semantic_model_id
            ):
                return

        resolved.resolution_notes.append(
            "The requested semantic model could not be verified within "
            "the authorized workspace."
        )

    async def _load_semantic_model(
        self,
        resolved: ResolvedAIContext,
        workspace_id: str,
        semantic_model_id: str,
    ) -> bool:
        try:
            model = await SemanticModelDefinitionService().get_parsed_definition(
                workspace_id=workspace_id,
                semantic_model_id=semantic_model_id,
                access_token=self._fabric_access_token,
            )
        except AppException:
            return False

        # Auto Date/Time tables can outnumber the real ones; every explorer
        # dataset drops them, and so must the evidence the AI reasons over.
        resolved.parsed_semantic_model = exclude_auto_date_tables(model)
        resolved.semantic_model_id = semantic_model_id
        resolved.semantic_model_workspace_id = workspace_id
        return True

    async def _find_model_workspace(
        self,
        semantic_model_id: str,
        already_tried: list[str],
    ) -> str | None:
        if not self._powerbi_access_token:
            return None

        try:
            workspaces = await WorkspaceService().list_workspaces(
                access_token=self._powerbi_access_token,
                top=_WORKSPACE_PAGE_SIZE,
                skip=0,
            )
        except AppException:
            return None

        candidates = [
            workspace.id
            for workspace in workspaces.workspaces
            if workspace.id not in already_tried
        ]
        listings = await self._gather_bounded(
            [
                lambda workspace_id=workspace_id: (
                    SemanticModelService().list_semantic_models(
                        workspace_id=workspace_id,
                        access_token=self._powerbi_access_token,
                    )
                )
                for workspace_id in candidates
            ]
        )

        for workspace_id, listing in zip(candidates, listings, strict=True):
            if isinstance(listing, BaseException):
                continue
            if any(model.id == semantic_model_id for model in listing.semantic_models):
                return workspace_id

        return None

    async def _resolve_object(
        self,
        resolved: ResolvedAIContext,
        context: AIChatContext,
    ) -> None:
        query = context.object_name or context.object_id

        if not query or resolved.parsed_semantic_model is None:
            return

        exact = find_semantic_object(
            resolved.parsed_semantic_model,
            query,
            object_type=context.object_type,
        )
        if exact is not None:
            resolved.resolved_object = exact
            return

        graph = build_lineage_graph(resolved.parsed_semantic_model)
        node_types = _NODE_TYPES_BY_OBJECT_TYPE.get(
            context.object_type or "",
            _DEFAULT_OBJECT_NODE_TYPES,
        )

        result = LineageSearchService().search(
            graph,
            query=query,
            node_types=node_types,
            semantic_model_id=resolved.semantic_model_id,
            limit=5,
        )

        if not result.results:
            resolved.resolution_notes.append(
                f"No object named '{query}' was found in the resolved semantic model."
            )
            return

        top_score = result.results[0].score
        top_matches = [item for item in result.results if item.score == top_score]

        if len(top_matches) > 1:
            resolved.resolution_notes.append(
                f"'{query}' matched more than one object: "
                + ", ".join(item.node.qualified_name for item in top_matches)
            )
            return

        node = top_matches[0].node
        table_name = str(
            node.properties.get("table_name")
            or (node.name if node.node_type == "semantic_table" else "")
        )
        object_type = _RESOLVED_OBJECT_TYPE_BY_NODE_TYPE.get(node.node_type)

        if object_type is None and node.node_type == "semantic_column":
            object_type = (
                "calculated_column"
                if node.properties.get("is_calculated")
                else "column"
            )

        if object_type is None:
            resolved.resolution_notes.append(
                f"'{query}' resolved to an unsupported object type ({node.node_type})."
            )
            return

        resolved.resolved_object = ResolvedObject(
            object_type=object_type,
            table_name=table_name,
            object_name=node.name,
            qualified_name=node.qualified_name,
        )

    async def _enrich(
        self,
        resolved: ResolvedAIContext,
        context: AIChatContext,
    ) -> None:
        await asyncio.gather(
            self._enrich_names(resolved),
            self._enrich_physical_sources(resolved),
            self._enrich_related_reports(resolved, context),
        )

    async def _enrich_names(self, resolved: ResolvedAIContext) -> None:
        model_workspace_id = resolved.semantic_model_workspace_id
        if not self._powerbi_access_token or not model_workspace_id:
            return

        if model_workspace_id == resolved.workspace_id:
            resolved.semantic_model_workspace_name = resolved.workspace_name
        else:
            try:
                workspace = await WorkspaceService().get_workspace(
                    workspace_id=model_workspace_id,
                    access_token=self._powerbi_access_token,
                )
                resolved.semantic_model_workspace_name = workspace.name
            except AppException:
                pass

        try:
            listing = await SemanticModelService().list_semantic_models(
                workspace_id=model_workspace_id,
                access_token=self._powerbi_access_token,
            )
        except AppException:
            resolved.coverage_notes.append(
                "The semantic model's display name could not be read; it is "
                "referred to by its id."
            )
            return

        for model in listing.semantic_models:
            if model.id == resolved.semantic_model_id:
                resolved.semantic_model_name = model.name
                return

    async def _enrich_physical_sources(self, resolved: ResolvedAIContext) -> None:
        model = resolved.parsed_semantic_model
        if model is None:
            return

        physical = await asyncio.to_thread(
            PhysicalSourceDiscoveryService().discover, model
        )
        resolved.physical_sources = physical

        if not (self._powerbi_access_token and self._fabric_access_token):
            return

        # The same composite-model hop the explorer follows, so a table that
        # reaches Snowflake through another workspace's model is reported as
        # the Snowflake table, not as "Power BI workspace: DEV".
        model_key = (model.workspace_id, model.semantic_model_id)
        try:
            by_model, warnings = await CrossWorkspaceSourceResolver().resolve(
                physical_by_model={model_key: physical},
                models_by_key={model_key: model},
                powerbi_access_token=self._powerbi_access_token,
                fabric_access_token=self._fabric_access_token,
                definition_format="TMDL",
            )
        except Exception:  # noqa: BLE001 - enrichment degrades, never fails
            resolved.coverage_notes.append(
                "Tables reached through another workspace's semantic model are "
                "reported at that hop; the database behind it could not be read."
            )
            return

        resolved.physical_sources = by_model.get(model_key, physical)
        resolved.coverage_notes.extend(warning.message for warning in warnings)

    async def _enrich_related_reports(
        self,
        resolved: ResolvedAIContext,
        context: AIChatContext,
    ) -> None:
        # A report-scoped question is about that report, which is already in
        # context; the model's other reports only matter for "which visuals
        # does this object reach" questions.
        if (context.object_type or "") == "report":
            return
        if not (self._powerbi_access_token and self._fabric_access_token):
            return

        bound = await self._bound_reports(resolved)
        if not bound:
            return

        if len(bound) > _MAX_RELATED_REPORTS:
            resolved.coverage_notes.append(
                f"{len(bound)} reports use this semantic model; visual impact "
                f"was checked in the first {_MAX_RELATED_REPORTS}."
            )
            bound = bound[:_MAX_RELATED_REPORTS]

        definitions = await self._gather_bounded(
            [
                lambda workspace_id=workspace_id, report_id=report.id: (
                    ReportDefinitionService().get_normalized_definition(
                        workspace_id=workspace_id,
                        report_id=report_id,
                        access_token=self._fabric_access_token,
                    )
                )
                for workspace_id, _, report in bound
            ]
        )

        unreadable: list[str] = []
        for (workspace_id, workspace_name, report), definition in zip(
            bound, definitions, strict=True
        ):
            if isinstance(definition, BaseException):
                unreadable.append(report.name)
                continue
            resolved.related_reports.append(
                ResolvedReport(
                    workspace_id=workspace_id,
                    workspace_name=workspace_name,
                    report_id=report.id,
                    report_name=report.name,
                    definition=definition,
                )
            )

        if unreadable:
            resolved.coverage_notes.append(
                "These reports use this semantic model but their definitions "
                "could not be read, so their visuals were not checked: "
                + ", ".join(unreadable)
            )

    async def _bound_reports(
        self,
        resolved: ResolvedAIContext,
    ) -> list[tuple[str, str | None, Report]]:
        """Every report the caller can see that is bound to the model in view.

        Report listings are session-cached provider reads, and the explorer
        screens have usually fetched them already.
        """
        try:
            workspaces = await WorkspaceService().list_workspaces(
                access_token=self._powerbi_access_token,
                top=_WORKSPACE_PAGE_SIZE,
                skip=0,
            )
        except AppException:
            resolved.coverage_notes.append(
                "The workspace list could not be read, so other reports using "
                "this semantic model were not checked for visual impact."
            )
            return []

        # The model's own workspace first: that is where its reports usually
        # live, so it survives the cap below.
        ordered = sorted(
            workspaces.workspaces,
            key=lambda workspace: workspace.id != resolved.semantic_model_workspace_id,
        )
        listings = await self._gather_bounded(
            [
                lambda workspace_id=workspace.id: ReportService().list_reports(
                    workspace_id=workspace_id,
                    access_token=self._powerbi_access_token,
                )
                for workspace in ordered
            ]
        )

        bound: list[tuple[str, str | None, Report]] = []
        for workspace, listing in zip(ordered, listings, strict=True):
            if isinstance(listing, BaseException):
                continue
            for report in listing.reports:
                if (
                    report.dataset_id == resolved.semantic_model_id
                    and report.id != resolved.report_id
                ):
                    bound.append((workspace.id, workspace.name, report))

        return bound

    @staticmethod
    async def _gather_bounded(factories: list) -> list:
        """Run lookups concurrently, a few at a time, keeping failures."""
        semaphore = asyncio.Semaphore(_LOOKUP_CONCURRENCY)

        async def run(factory):
            async with semaphore:
                return await factory()

        return await asyncio.gather(
            *(run(factory) for factory in factories),
            return_exceptions=True,
        )
