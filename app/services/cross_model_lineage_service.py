import asyncio
from dataclasses import dataclass

from app.core.exceptions import AppException
from app.schemas.explorer import ExplorerWarning
from app.schemas.parsed_semantic_model import ParsedSemanticModelResponse
from app.schemas.report_semantic_lineage import SemanticLineageObject
from app.schemas.scanner import ScannerWorkspaceScanRequest
from app.services.scanner_service import ScannerService
from app.services.semantic_model_definition_service import (
    SemanticModelDefinitionService,
)
from app.services.semantic_model_service import SemanticModelService

_SCAN_POLL_INTERVAL_SECONDS = 2.0
_SCAN_MAX_POLL_ATTEMPTS = 30
_TERMINAL_FAILURE_STATUSES = {"Failed", "Cancelled"}


@dataclass(frozen=True)
class UpstreamModelRef:
    """An upstream (composite/DirectQuery-for-dataset) model discovered from
    the Power BI Admin API's ``getInfo?lineage=true`` scan of a primary
    dataset's own workspace(s)."""

    workspace_id: str
    semantic_model_id: str
    name: str | None


@dataclass(frozen=True)
class CrossModelDiscoveryResult:
    upstream_refs: dict[str, UpstreamModelRef]
    upstream_models: dict[str, ParsedSemanticModelResponse]
    warnings: list[ExplorerWarning]


class CrossModelLineageService:
    """Discovers upstream (composite-model) datasets for a set of primary
    semantic models, so callers can match a visual field that resolves to a
    local, DirectQuery-for-dataset table back to its true upstream source.

    This mirrors the legacy Streamlit reference app's approach: an Admin API
    tenant-lineage scan (``getInfo?lineage=true``) supplies each dataset's
    ``upstreamDatasets``, and the actual field-level join happens elsewhere
    (see ``build_lineage_tag_index``) by matching a column's
    ``source_lineage_tag`` against another model's column ``lineage_tag`` —
    the same DMV-level property the reference app reads over live XMLA, here
    parsed from TMDL instead so this stays usable without a Windows/MSOLAP
    host.
    """

    def __init__(
        self,
        *,
        scanner_service: ScannerService | None = None,
        semantic_model_service: SemanticModelService | None = None,
        semantic_model_definition_service: (
            SemanticModelDefinitionService | None
        ) = None,
        max_concurrency: int = 8,
    ) -> None:
        self.scanner_service = scanner_service or ScannerService()
        self.semantic_model_service = semantic_model_service or SemanticModelService()
        self.semantic_model_definition_service = (
            semantic_model_definition_service or SemanticModelDefinitionService()
        )
        self.max_concurrency = max_concurrency

    async def discover(
        self,
        *,
        primary_dataset_ids: set[str],
        primary_workspace_ids: set[str],
        powerbi_access_token: str,
        fabric_access_token: str,
        semantic_model_definition_format: str,
    ) -> CrossModelDiscoveryResult:
        if not primary_dataset_ids or not primary_workspace_ids:
            return CrossModelDiscoveryResult({}, {}, [])

        try:
            upstream_refs = await self._discover_upstream_refs(
                primary_dataset_ids=primary_dataset_ids,
                primary_workspace_ids=primary_workspace_ids,
                access_token=powerbi_access_token,
            )
        except AppException as exc:
            return CrossModelDiscoveryResult({}, {}, [self._scan_warning(exc)])

        upstream_refs = {
            dataset_id: ref
            for dataset_id, ref in upstream_refs.items()
            if dataset_id not in primary_dataset_ids
        }
        if not upstream_refs:
            return CrossModelDiscoveryResult({}, {}, [])

        named_refs, name_warnings = await self._resolve_upstream_names(
            upstream_refs=upstream_refs,
            access_token=powerbi_access_token,
        )
        models, fetch_warnings = await self._fetch_upstream_models(
            upstream_refs=named_refs,
            fabric_access_token=fabric_access_token,
            semantic_model_definition_format=semantic_model_definition_format,
        )

        return CrossModelDiscoveryResult(
            upstream_refs=named_refs,
            upstream_models=models,
            warnings=[*name_warnings, *fetch_warnings],
        )

    async def _discover_upstream_refs(
        self,
        *,
        primary_dataset_ids: set[str],
        primary_workspace_ids: set[str],
        access_token: str,
    ) -> dict[str, UpstreamModelRef]:
        scan = await self.scanner_service.start_scan(
            access_token=access_token,
            request=ScannerWorkspaceScanRequest(
                workspaces=list(primary_workspace_ids),
                lineage=True,
                datasource_details=False,
                dataset_schema=False,
                dataset_expressions=False,
                get_artifact_users=False,
            ),
        )

        scan_id = str(scan.scan_id)
        for _ in range(_SCAN_MAX_POLL_ATTEMPTS):
            status_response = await self.scanner_service.get_scan_status(
                access_token=access_token,
                scan_id=scan_id,
            )
            if status_response.status == "Succeeded":
                break
            if status_response.status in _TERMINAL_FAILURE_STATUSES:
                return {}
            await asyncio.sleep(_SCAN_POLL_INTERVAL_SECONDS)
        else:
            return {}

        result = await self.scanner_service.get_scan_result(
            access_token=access_token,
            scan_id=scan_id,
        )

        refs: dict[str, UpstreamModelRef] = {}
        for workspace in result.payload.get("workspaces", []):
            if not isinstance(workspace, dict):
                continue
            for dataset in workspace.get("datasets", []):
                if not isinstance(dataset, dict) or dataset.get("id") not in (
                    primary_dataset_ids
                ):
                    continue
                for upstream in dataset.get("upstreamDatasets", []) or []:
                    if not isinstance(upstream, dict):
                        continue
                    target_id = upstream.get("targetDatasetId")
                    group_id = upstream.get("groupId")
                    if not isinstance(target_id, str) or not isinstance(
                        group_id,
                        str,
                    ):
                        continue
                    refs.setdefault(
                        target_id,
                        UpstreamModelRef(
                            workspace_id=group_id,
                            semantic_model_id=target_id,
                            name=None,
                        ),
                    )
        return refs

    async def _resolve_upstream_names(
        self,
        *,
        upstream_refs: dict[str, UpstreamModelRef],
        access_token: str,
    ) -> tuple[dict[str, UpstreamModelRef], list[ExplorerWarning]]:
        workspace_ids = {ref.workspace_id for ref in upstream_refs.values()}
        warnings: list[ExplorerWarning] = []
        names_by_dataset: dict[str, str] = {}
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def list_one(workspace_id: str) -> None:
            async with semaphore:
                try:
                    response = await self.semantic_model_service.list_semantic_models(
                        workspace_id=workspace_id,
                        access_token=access_token,
                    )
                except AppException as exc:
                    warnings.append(self._name_lookup_warning(exc))
                    return
                for model in response.semantic_models:
                    names_by_dataset[model.id] = model.name

        await asyncio.gather(
            *(list_one(workspace_id) for workspace_id in workspace_ids)
        )

        named_refs = {
            dataset_id: UpstreamModelRef(
                workspace_id=ref.workspace_id,
                semantic_model_id=ref.semantic_model_id,
                name=names_by_dataset.get(dataset_id),
            )
            for dataset_id, ref in upstream_refs.items()
        }
        return named_refs, warnings

    async def _fetch_upstream_models(
        self,
        *,
        upstream_refs: dict[str, UpstreamModelRef],
        fabric_access_token: str,
        semantic_model_definition_format: str,
    ) -> tuple[dict[str, ParsedSemanticModelResponse], list[ExplorerWarning]]:
        warnings: list[ExplorerWarning] = []
        models: dict[str, ParsedSemanticModelResponse] = {}
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def fetch_one(dataset_id: str, ref: UpstreamModelRef) -> None:
            async with semaphore:
                try:
                    models[
                        dataset_id
                    ] = await (
                        self.semantic_model_definition_service.get_parsed_definition(
                            workspace_id=ref.workspace_id,
                            semantic_model_id=ref.semantic_model_id,
                            access_token=fabric_access_token,
                            definition_format=semantic_model_definition_format,
                        )
                    )
                except AppException as exc:
                    warnings.append(self._definition_warning(exc, dataset_id))

        await asyncio.gather(
            *(fetch_one(dataset_id, ref) for dataset_id, ref in upstream_refs.items())
        )
        return models, warnings

    @staticmethod
    def _scan_warning(exc: AppException) -> ExplorerWarning:
        return ExplorerWarning(
            code=exc.code,
            message=(
                "Cross-model (upstream dataset) lineage scan could not be "
                "completed; visual source lookup continued with same-model "
                "matches only."
            ),
        )

    @staticmethod
    def _name_lookup_warning(exc: AppException) -> ExplorerWarning:
        return ExplorerWarning(
            code=exc.code,
            message=(
                "An upstream dataset's display name could not be resolved; "
                "cross-model matches continue using the dataset ID."
            ),
        )

    @staticmethod
    def _definition_warning(exc: AppException, dataset_id: str) -> ExplorerWarning:
        return ExplorerWarning(
            code=exc.code,
            message=(
                "An upstream dataset's schema could not be retrieved; "
                "cross-model matching skipped it."
            ),
            semantic_model_id=dataset_id,
        )


def build_lineage_tag_index(
    *,
    primary_models: dict[str, ParsedSemanticModelResponse],
    upstream_models: dict[str, ParsedSemanticModelResponse],
) -> dict[str, list[tuple[str, SemanticLineageObject]]]:
    """Index every column with a ``lineageTag`` across all supplied models
    (primary datasets already in the batch, plus discovered upstream ones),
    keyed by casefolded lineage tag -> [(dataset_id, SemanticLineageObject)].

    A field matched in one model whose ``source_lineage_tag`` appears here
    under a *different* dataset id was generated from that other model's
    column — the same signal the reference app resolves over live XMLA.
    """

    index: dict[str, list[tuple[str, SemanticLineageObject]]] = {}

    for dataset_id, model in {**primary_models, **upstream_models}.items():
        for table in model.tables:
            for column in table.columns:
                if not column.lineage_tag:
                    continue
                index.setdefault(column.lineage_tag.casefold(), []).append(
                    (
                        dataset_id,
                        SemanticLineageObject(
                            object_type="column",
                            table_name=table.name,
                            object_name=column.name,
                            source_path=column.source_path or table.source_path,
                            lineage_tag=column.lineage_tag,
                            source_lineage_tag=column.source_lineage_tag,
                        ),
                    )
                )

    return index
