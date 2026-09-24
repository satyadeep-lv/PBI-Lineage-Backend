"""Resolve composite-model DirectQuery hops down to their real databases.

A composite model reaches another workspace's semantic model through a shared
`AnalysisServices.Database(<xmla endpoint>, <model>)` expression. Physical
source discovery can only see as far as that hop, so every table behind it is
reported as living in "Power BI workspace: DEV" rather than in the Snowflake
database that actually backs it. This service follows the hop: it resolves the
XMLA endpoint to a workspace, finds the upstream model, discovers *its*
physical sources, and swaps the resolved sources in -- keeping the hop itself
recorded on each source's `via_*` fields.
"""

import asyncio
from urllib.parse import unquote

from app.core.exceptions import AppException
from app.domain.semantic_model_filters import exclude_auto_date_tables
from app.schemas.explorer import ExplorerWarning
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)
from app.schemas.physical_source import (
    PhysicalDataSource,
    PhysicalSourceDiscoveryResponse,
)
from app.services.physical_source_service import PhysicalSourceDiscoveryService
from app.services.semantic_model_definition_service import (
    SemanticModelDefinitionService,
)
from app.services.semantic_model_service import SemanticModelService
from app.services.workspace_service import WorkspaceService

ANALYSIS_SERVICES_PROVIDER = "analysis_services"
_XMLA_WORKSPACE_MARKER = "/myorg/"
_WORKSPACE_PAGE_SIZE = 5000

ModelKey = tuple[str, str]


class _ResolvedUpstreamModel:
    """An upstream model plus the lookups needed to match tables into it."""

    def __init__(
        self,
        *,
        workspace_id: str,
        workspace_name: str,
        semantic_model_id: str,
        semantic_model_name: str,
        model: ParsedSemanticModelResponse,
        physical: PhysicalSourceDiscoveryResponse,
    ) -> None:
        self.workspace_id = workspace_id
        self.workspace_name = workspace_name
        self.semantic_model_id = semantic_model_id
        self.semantic_model_name = semantic_model_name
        self.model = model
        self.physical = physical
        self.sources_by_id = {source.source_id: source for source in physical.sources}

        self.source_ids_by_table: dict[str, list[str]] = {}
        for mapping in physical.mappings:
            self.source_ids_by_table.setdefault(
                mapping.semantic_table.casefold(),
                [],
            ).extend(mapping.source_ids)

        self.table_by_lineage_tag: dict[str, ParsedSemanticModelTable] = {
            table.lineage_tag.casefold(): table
            for table in model.tables
            if table.lineage_tag
        }
        self.table_by_name: dict[str, ParsedSemanticModelTable] = {
            table.name.casefold(): table for table in model.tables
        }

    def sources_for(self, table: ParsedSemanticModelTable) -> list[PhysicalDataSource]:
        source_ids = self.source_ids_by_table.get(table.name.casefold(), [])
        resolved = [
            self.sources_by_id[source_id]
            for source_id in dict.fromkeys(source_ids)
            if source_id in self.sources_by_id
        ]
        return resolved


class CrossWorkspaceSourceResolver:
    def __init__(
        self,
        *,
        workspace_service: WorkspaceService | None = None,
        semantic_model_service: SemanticModelService | None = None,
        semantic_model_definition_service: (
            SemanticModelDefinitionService | None
        ) = None,
        max_depth: int = 3,
    ) -> None:
        if max_depth < 1:
            raise ValueError("max_depth must be at least 1.")

        self.workspace_service = workspace_service or WorkspaceService()
        self.semantic_model_service = semantic_model_service or SemanticModelService()
        self.semantic_model_definition_service = (
            semantic_model_definition_service or SemanticModelDefinitionService()
        )
        self.max_depth = max_depth

    async def resolve(
        self,
        *,
        physical_by_model: dict[ModelKey, PhysicalSourceDiscoveryResponse],
        models_by_key: dict[ModelKey, ParsedSemanticModelResponse],
        powerbi_access_token: str,
        fabric_access_token: str,
        definition_format: str,
    ) -> tuple[dict[ModelKey, PhysicalSourceDiscoveryResponse], list[ExplorerWarning]]:
        warnings: list[ExplorerWarning] = []
        if not any(
            self._has_cross_workspace_source(physical)
            for physical in physical_by_model.values()
        ):
            return physical_by_model, warnings

        state = _ResolutionState(
            resolver=self,
            powerbi_access_token=powerbi_access_token,
            fabric_access_token=fabric_access_token,
            definition_format=definition_format,
            warnings=warnings,
        )

        model_keys = list(physical_by_model)
        resolved = await asyncio.gather(
            *(
                self.resolve_one(
                    model_key=model_key,
                    physical=physical_by_model[model_key],
                    model=models_by_key.get(model_key),
                    state=state,
                    depth=0,
                )
                for model_key in model_keys
            )
        )

        return dict(zip(model_keys, resolved, strict=True)), warnings

    async def resolve_one(
        self,
        *,
        model_key: ModelKey,
        physical: PhysicalSourceDiscoveryResponse,
        model: ParsedSemanticModelResponse | None,
        state: "_ResolutionState",
        depth: int,
        chain: frozenset[tuple[str, str]] = frozenset(),
    ) -> PhysicalSourceDiscoveryResponse:
        if not self._has_cross_workspace_source(physical):
            return physical
        if depth >= self.max_depth:
            state.warnings.append(
                ExplorerWarning(
                    code="CROSS_WORKSPACE_DEPTH_EXCEEDED",
                    message=(
                        "Stopped following composite model links after "
                        f"{self.max_depth} hops; the deepest sources are "
                        "still reported as Power BI models."
                    ),
                    workspace_id=model_key[0],
                    semantic_model_id=model_key[1],
                )
            )
            return physical

        sources_by_id = {source.source_id: source for source in physical.sources}
        tables_by_name = {
            table.name.casefold(): table for table in (model.tables if model else [])
        }

        rewritten_sources: dict[str, PhysicalDataSource] = {}
        rewritten_mappings = []

        for mapping in physical.mappings:
            new_source_ids: list[str] = []
            for source_id in mapping.source_ids:
                source = sources_by_id.get(source_id)
                if source is None:
                    continue
                if source.provider != ANALYSIS_SERVICES_PROVIDER:
                    rewritten_sources.setdefault(source.source_id, source)
                    new_source_ids.append(source.source_id)
                    continue

                resolved = await self._resolve_source(
                    source=source,
                    model_key=model_key,
                    primary_table=tables_by_name.get(mapping.semantic_table.casefold()),
                    state=state,
                    depth=depth,
                    chain=chain,
                )
                if not resolved:
                    # Keep the hop itself rather than dropping the table: a
                    # partial answer still tells the user where to look.
                    rewritten_sources.setdefault(source.source_id, source)
                    new_source_ids.append(source.source_id)
                    continue

                for upstream_source in resolved:
                    rewritten_sources.setdefault(
                        upstream_source.source_id,
                        upstream_source,
                    )
                    new_source_ids.append(upstream_source.source_id)

            rewritten_mappings.append(
                mapping.model_copy(
                    update={"source_ids": list(dict.fromkeys(new_source_ids))}
                )
            )

        return physical.model_copy(
            update={
                "sources": list(rewritten_sources.values()),
                "mappings": rewritten_mappings,
            }
        )

    async def _resolve_source(
        self,
        *,
        source: PhysicalDataSource,
        model_key: ModelKey,
        primary_table: ParsedSemanticModelTable | None,
        state: "_ResolutionState",
        depth: int,
        chain: frozenset[tuple[str, str]],
    ) -> list[PhysicalDataSource]:
        workspace_name = self._workspace_name_from_endpoint(source.server)
        model_name = source.database
        if not workspace_name or not model_name:
            return []

        upstream = await state.upstream_model(
            workspace_name=workspace_name,
            model_name=model_name,
            requested_by=model_key,
            depth=depth,
            chain=chain,
        )
        if upstream is None:
            return []

        upstream_table = self._match_table(
            upstream=upstream,
            primary_table=primary_table,
            entity_name=source.object_name,
        )
        if upstream_table is None:
            state.warnings.append(
                ExplorerWarning(
                    code="CROSS_WORKSPACE_TABLE_NOT_MATCHED",
                    message=(
                        f"Table '{source.object_name or '?'}' was not found in "
                        f"upstream model '{upstream.semantic_model_name}' "
                        f"(workspace '{upstream.workspace_name}'), so its real "
                        "database could not be resolved."
                    ),
                    workspace_id=model_key[0],
                    semantic_model_id=model_key[1],
                )
            )
            return []

        upstream_sources = upstream.sources_for(upstream_table)
        if not upstream_sources:
            return []

        return [
            upstream_source.model_copy(
                update={
                    "via_workspace_id": upstream.workspace_id,
                    "via_workspace_name": upstream.workspace_name,
                    "via_semantic_model_id": upstream.semantic_model_id,
                    "via_semantic_model_name": upstream.semantic_model_name,
                    "via_semantic_table": upstream_table.name,
                }
            )
            for upstream_source in upstream_sources
        ]

    @staticmethod
    def _match_table(
        *,
        upstream: _ResolvedUpstreamModel,
        primary_table: ParsedSemanticModelTable | None,
        entity_name: str | None,
    ) -> ParsedSemanticModelTable | None:
        # `sourceLineageTag` survives a rename on either side, so it is tried
        # before the entity name the partition happens to carry today.
        tag = primary_table.source_lineage_tag if primary_table else None
        if tag:
            matched = upstream.table_by_lineage_tag.get(tag.casefold())
            if matched is not None:
                return matched

        for candidate in (entity_name, primary_table.name if primary_table else None):
            if candidate:
                matched = upstream.table_by_name.get(candidate.casefold())
                if matched is not None:
                    return matched

        return None

    @staticmethod
    def _has_cross_workspace_source(
        physical: PhysicalSourceDiscoveryResponse,
    ) -> bool:
        return any(
            source.provider == ANALYSIS_SERVICES_PROVIDER for source in physical.sources
        )

    @staticmethod
    def _workspace_name_from_endpoint(endpoint: str | None) -> str | None:
        if not endpoint:
            return None
        marker_at = endpoint.casefold().find(_XMLA_WORKSPACE_MARKER)
        if marker_at < 0:
            return None
        name = endpoint[marker_at + len(_XMLA_WORKSPACE_MARKER) :].strip("/")
        return unquote(name) or None


class _ResolutionState:
    """Per-request caches so a shared upstream model is fetched only once."""

    def __init__(
        self,
        *,
        resolver: CrossWorkspaceSourceResolver,
        powerbi_access_token: str,
        fabric_access_token: str,
        definition_format: str,
        warnings: list[ExplorerWarning],
    ) -> None:
        self.resolver = resolver
        self.powerbi_access_token = powerbi_access_token
        self.fabric_access_token = fabric_access_token
        self.definition_format = definition_format
        self.warnings = warnings
        self._workspaces_by_name: dict[str, str] | None = None
        self._models_by_workspace: dict[str, dict[str, str]] = {}
        # Futures, not plain values: tables resolve concurrently, so the
        # second table to ask for an upstream model must await the first
        # one's fetch rather than starting a second.
        self._upstream: dict[
            tuple[str, str],
            asyncio.Future[_ResolvedUpstreamModel | None],
        ] = {}
        self._workspace_lock = asyncio.Lock()
        self._model_locks: dict[str, asyncio.Lock] = {}

    async def upstream_model(
        self,
        *,
        workspace_name: str,
        model_name: str,
        requested_by: ModelKey,
        depth: int,
        chain: frozenset[tuple[str, str]],
    ) -> _ResolvedUpstreamModel | None:
        cache_key = (workspace_name.casefold(), model_name.casefold())
        if cache_key in chain:
            # A model that (transitively) points back at itself. Awaiting the
            # pending future here would deadlock, so stop the walk instead.
            return None

        pending = self._upstream.get(cache_key)
        if pending is not None:
            return await asyncio.shield(pending)

        future: asyncio.Future[_ResolvedUpstreamModel | None] = (
            asyncio.get_running_loop().create_future()
        )
        self._upstream[cache_key] = future

        try:
            resolved = await self._load(
                workspace_name=workspace_name,
                model_name=model_name,
                requested_by=requested_by,
                depth=depth,
                chain=chain | {cache_key},
            )
        except BaseException as error:
            self._upstream.pop(cache_key, None)
            if not future.done():
                future.set_exception(error)
            future.exception()
            raise

        if not future.done():
            future.set_result(resolved)
        return resolved

    async def _load(
        self,
        *,
        workspace_name: str,
        model_name: str,
        requested_by: ModelKey,
        depth: int,
        chain: frozenset[tuple[str, str]],
    ) -> _ResolvedUpstreamModel | None:
        workspace_id = await self._workspace_id(workspace_name)
        if workspace_id is None:
            self.warnings.append(
                ExplorerWarning(
                    code="CROSS_WORKSPACE_WORKSPACE_NOT_FOUND",
                    message=(
                        f"Workspace '{workspace_name}' is referenced by a "
                        "composite model but is not visible to the signed-in "
                        "user, so its tables keep their Power BI model as the "
                        "reported source."
                    ),
                    workspace_id=requested_by[0],
                    semantic_model_id=requested_by[1],
                )
            )
            return None

        model_id = await self._semantic_model_id(workspace_id, model_name)
        if model_id is None:
            self.warnings.append(
                ExplorerWarning(
                    code="CROSS_WORKSPACE_MODEL_NOT_FOUND",
                    message=(
                        f"Semantic model '{model_name}' was not found in "
                        f"workspace '{workspace_name}'."
                    ),
                    workspace_id=requested_by[0],
                    semantic_model_id=requested_by[1],
                )
            )
            return None

        definition_service = self.resolver.semantic_model_definition_service
        try:
            model = await definition_service.get_parsed_definition(
                workspace_id=workspace_id,
                semantic_model_id=model_id,
                access_token=self.fabric_access_token,
                definition_format=self.definition_format,
            )
        except AppException as error:
            self.warnings.append(
                ExplorerWarning(
                    code="CROSS_WORKSPACE_DEFINITION_UNAVAILABLE",
                    message=(
                        f"Could not read the definition of '{model_name}' in "
                        f"workspace '{workspace_name}': {error}"
                    ),
                    workspace_id=workspace_id,
                    semantic_model_id=model_id,
                )
            )
            return None

        model = exclude_auto_date_tables(model)
        physical = PhysicalSourceDiscoveryService().discover(model)
        # The upstream model can itself be composite, so follow its own hops
        # before indexing it.
        physical = await self.resolver.resolve_one(
            model_key=(workspace_id, model_id),
            physical=physical,
            model=model,
            state=self,
            depth=depth + 1,
            chain=chain,
        )

        return _ResolvedUpstreamModel(
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            semantic_model_id=model_id,
            semantic_model_name=model_name,
            model=model,
            physical=physical,
        )

    async def _workspace_id(self, workspace_name: str) -> str | None:
        # The lock keeps concurrent tables from each issuing their own
        # workspace listing; the second one finds the cache already filled.
        async with self._workspace_lock:
            if self._workspaces_by_name is None:
                try:
                    listing = await self.resolver.workspace_service.list_workspaces(
                        access_token=self.powerbi_access_token,
                        top=_WORKSPACE_PAGE_SIZE,
                        skip=0,
                    )
                except AppException:
                    self._workspaces_by_name = {}
                else:
                    self._workspaces_by_name = {
                        workspace.name.casefold(): workspace.id
                        for workspace in listing.workspaces
                    }
        return self._workspaces_by_name.get(workspace_name.casefold())

    async def _semantic_model_id(
        self,
        workspace_id: str,
        model_name: str,
    ) -> str | None:
        lock = self._model_locks.setdefault(workspace_id, asyncio.Lock())
        async with lock:
            models = self._models_by_workspace.get(workspace_id)
            if models is None:
                try:
                    listing = (
                        await self.resolver.semantic_model_service.list_semantic_models(
                            workspace_id=workspace_id,
                            access_token=self.powerbi_access_token,
                        )
                    )
                except AppException:
                    models = {}
                else:
                    models = {}
                    for model in listing.semantic_models:
                        models.setdefault(model.name.casefold(), model.id)
                self._models_by_workspace[workspace_id] = models
        return models.get(model_name.casefold())
