import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies.credentials import (
    get_bearer_token,
    get_fabric_access_token,
    get_powerbi_access_token,
    get_snowflake_session_id,
)
from app.api.dependencies.lineage import (
    get_lineage_scan_manager,
    get_lineage_store,
)
from app.api.dependencies.security import require_lineage_api_key
from app.core.exceptions import InvalidLineageRequestError, ResourceNotFoundError
from app.schemas.dax_dependency import DaxDependencyAnalysisResponse
from app.schemas.estate import EstateDiscoveryResponse
from app.schemas.impact_analysis import ImpactAnalysisResponse
from app.schemas.lineage_change import LineageChangeSet
from app.schemas.lineage_graph import (
    LineageGraphBuildRequest,
    LineageNodeType,
)
from app.schemas.lineage_persistence import (
    GraphVersionListResponse,
    StoredLineageGraph,
)
from app.schemas.lineage_search import (
    LineageNavigationResponse,
    LineageSearchResponse,
)
from app.schemas.lineage_validation import LineageValidationResponse
from app.schemas.parsed_semantic_model import ParsedSemanticModelResponse
from app.schemas.physical_source import (
    PhysicalSourceDiscoveryRequest,
    PhysicalSourceDiscoveryResponse,
)
from app.schemas.scan_job import (
    LineageScanJob,
    LineageScanJobRequest,
    LiveLineageScanRequest,
)
from app.schemas.snowflake_lineage import (
    SnowflakeDeepLineageRequest,
    SnowflakeDeepLineageResponse,
    SnowflakeLineageDiscoveryRequest,
    SnowflakeLineageRowsRequest,
    SnowflakeLineageSnapshot,
)
from app.services.auth.snowflake_auth_service import SnowflakeAuthService
from app.services.dax_dependency_service import DaxDependencyService
from app.services.estate_discovery_service import EstateDiscoveryService
from app.services.impact_analysis_service import ImpactAnalysisService
from app.services.lineage_change_service import LineageChangeService
from app.services.lineage_graph_service import LineageGraphService
from app.services.lineage_search_service import (
    LineageNavigationService,
    LineageSearchService,
)
from app.services.lineage_store_service import LineageStoreService
from app.services.lineage_validation_service import LineageValidationService
from app.services.live_lineage_scan_service import LiveLineageScanService
from app.services.physical_source_service import PhysicalSourceDiscoveryService
from app.services.scan_job_service import LineageScanJobManager
from app.services.snowflake_deep_lineage_service import (
    SnowflakeDeepLineageService,
)
from app.services.snowflake_lineage_service import SnowflakeLineageService

router = APIRouter(dependencies=[Depends(require_lineage_api_key)])


@router.post(
    "/dax/analyze",
    response_model=DaxDependencyAnalysisResponse,
)
async def analyze_dax(
    semantic_model: ParsedSemanticModelResponse,
) -> DaxDependencyAnalysisResponse:
    return await asyncio.to_thread(DaxDependencyService().analyze, semantic_model)


@router.post(
    "/physical-sources/analyze",
    response_model=PhysicalSourceDiscoveryResponse,
)
async def discover_physical_sources(
    request: PhysicalSourceDiscoveryRequest,
) -> PhysicalSourceDiscoveryResponse:
    return await asyncio.to_thread(
        PhysicalSourceDiscoveryService().discover,
        request.semantic_model,
        gateway_datasources=request.gateway_datasources,
    )


@router.post(
    "/snowflake/normalize",
    response_model=SnowflakeLineageSnapshot,
)
async def normalize_snowflake_lineage(
    request: SnowflakeLineageRowsRequest,
) -> SnowflakeLineageSnapshot:
    return await asyncio.to_thread(
        SnowflakeLineageService().normalize_rows,
        account_identifier=request.account_identifier,
        rows=request.rows,
    )


@router.post(
    "/snowflake/discover",
    response_model=SnowflakeLineageSnapshot,
)
async def discover_snowflake_lineage(
    request: SnowflakeLineageDiscoveryRequest,
    access_token: Annotated[str, Depends(get_bearer_token)],
) -> SnowflakeLineageSnapshot:
    try:
        return await SnowflakeAuthService().discover_lineage(
            account_identifier=request.account_identifier,
            access_token=access_token,
            warehouse=request.warehouse,
            role=request.role,
            token_type=request.token_type,
        )
    except ValueError as exc:
        raise InvalidLineageRequestError(str(exc)) from exc


@router.post(
    "/snowflake/trace",
    response_model=SnowflakeDeepLineageResponse,
)
async def trace_snowflake_lineage(
    request: SnowflakeDeepLineageRequest,
    session_id: Annotated[str, Depends(get_snowflake_session_id)],
) -> SnowflakeDeepLineageResponse:
    return await asyncio.to_thread(
        SnowflakeDeepLineageService().trace_session,
        session_id,
        request,
    )


@router.post(
    "/graphs",
    response_model=StoredLineageGraph,
    status_code=status.HTTP_201_CREATED,
)
async def build_lineage_graph(
    request: LineageGraphBuildRequest,
    store: Annotated[LineageStoreService, Depends(get_lineage_store)],
) -> StoredLineageGraph:
    try:
        graph = await asyncio.to_thread(LineageGraphService().build, request)
    except ValueError as exc:
        raise InvalidLineageRequestError(str(exc)) from exc
    validation = await asyncio.to_thread(LineageValidationService().validate, graph)
    if not validation.valid:
        raise InvalidLineageRequestError(
            "The generated lineage graph failed structural validation."
        )
    return await asyncio.to_thread(store.save, graph)


@router.post(
    "/live-graphs",
    response_model=StoredLineageGraph,
    status_code=status.HTTP_201_CREATED,
)
async def build_live_lineage_graph(
    request: LiveLineageScanRequest,
    fabric_access_token: Annotated[str, Depends(get_fabric_access_token)],
    powerbi_access_token: Annotated[str, Depends(get_powerbi_access_token)],
    store: Annotated[LineageStoreService, Depends(get_lineage_store)],
) -> StoredLineageGraph:
    graph = await LiveLineageScanService().build_graph(
        request,
        fabric_access_token=fabric_access_token,
        powerbi_access_token=powerbi_access_token,
    )
    validation = await asyncio.to_thread(LineageValidationService().validate, graph)
    if not validation.valid:
        raise InvalidLineageRequestError(
            "The generated lineage graph failed structural validation."
        )
    return await asyncio.to_thread(store.save, graph)


@router.get(
    "/graphs/{graph_id}",
    response_model=StoredLineageGraph,
)
async def get_lineage_graph(
    graph_id: str,
    store: Annotated[LineageStoreService, Depends(get_lineage_store)],
    version: int | None = Query(default=None, ge=1),
) -> StoredLineageGraph:
    return await _stored_graph(store, graph_id, version)


@router.get(
    "/graphs/{graph_id}/versions",
    response_model=GraphVersionListResponse,
)
async def list_lineage_graph_versions(
    graph_id: str,
    store: Annotated[LineageStoreService, Depends(get_lineage_store)],
) -> GraphVersionListResponse:
    versions = await asyncio.to_thread(store.versions, graph_id)
    if not versions.versions:
        raise ResourceNotFoundError("lineage graph")
    return versions


@router.get(
    "/graphs/{graph_id}/impact/{node_id}",
    response_model=ImpactAnalysisResponse,
)
async def analyze_lineage_impact(
    graph_id: str,
    node_id: str,
    store: Annotated[LineageStoreService, Depends(get_lineage_store)],
    version: int | None = Query(default=None, ge=1),
    max_depth: int = Query(default=10, ge=1, le=100),
    include_non_lineage: bool = False,
) -> ImpactAnalysisResponse:
    stored = await _stored_graph(store, graph_id, version)
    try:
        return await asyncio.to_thread(
            ImpactAnalysisService().analyze,
            stored.graph,
            node_id=node_id,
            max_depth=max_depth,
            include_non_lineage=include_non_lineage,
        )
    except KeyError as exc:
        raise ResourceNotFoundError("lineage node") from exc


@router.get(
    "/graphs/{graph_id}/search",
    response_model=LineageSearchResponse,
)
async def search_lineage_graph(
    graph_id: str,
    query: str,
    store: Annotated[LineageStoreService, Depends(get_lineage_store)],
    version: int | None = Query(default=None, ge=1),
    node_type: Annotated[list[LineageNodeType] | None, Query()] = None,
    workspace_id: str | None = None,
    semantic_model_id: str | None = None,
    report_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> LineageSearchResponse:
    stored = await _stored_graph(store, graph_id, version)
    try:
        return await asyncio.to_thread(
            LineageSearchService().search,
            stored.graph,
            query=query,
            node_types=node_type,
            workspace_id=workspace_id,
            semantic_model_id=semantic_model_id,
            report_id=report_id,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise InvalidLineageRequestError(str(exc)) from exc


@router.get(
    "/graphs/{graph_id}/navigate/{node_id}",
    response_model=LineageNavigationResponse,
)
async def navigate_lineage_graph(
    graph_id: str,
    node_id: str,
    store: Annotated[LineageStoreService, Depends(get_lineage_store)],
    version: int | None = Query(default=None, ge=1),
    direction: str = Query(default="both", pattern="^(upstream|downstream|both)$"),
    depth: int = Query(default=1, ge=1, le=20),
    include_non_lineage: bool = True,
) -> LineageNavigationResponse:
    stored = await _stored_graph(store, graph_id, version)
    try:
        return await asyncio.to_thread(
            LineageNavigationService().navigate,
            stored.graph,
            node_id=node_id,
            direction=direction,
            depth=depth,
            include_non_lineage=include_non_lineage,
        )
    except KeyError as exc:
        raise ResourceNotFoundError("lineage node") from exc


@router.get(
    "/graphs/{graph_id}/changes",
    response_model=LineageChangeSet,
)
async def compare_lineage_versions(
    graph_id: str,
    store: Annotated[LineageStoreService, Depends(get_lineage_store)],
    from_version: int = Query(ge=1),
    to_version: int = Query(ge=1),
) -> LineageChangeSet:
    from_stored = await _stored_graph(store, graph_id, from_version)
    to_stored = await _stored_graph(store, graph_id, to_version)
    return await asyncio.to_thread(
        LineageChangeService().compare,
        graph_id=graph_id,
        from_version=from_version,
        from_graph=from_stored.graph,
        to_version=to_version,
        to_graph=to_stored.graph,
    )


@router.get(
    "/graphs/{graph_id}/validate",
    response_model=LineageValidationResponse,
)
async def validate_lineage_graph(
    graph_id: str,
    store: Annotated[LineageStoreService, Depends(get_lineage_store)],
    version: int | None = Query(default=None, ge=1),
) -> LineageValidationResponse:
    stored = await _stored_graph(store, graph_id, version)
    return await asyncio.to_thread(LineageValidationService().validate, stored.graph)


@router.get(
    "/estate/discover",
    response_model=EstateDiscoveryResponse,
)
async def discover_estate(
    access_token: Annotated[str, Depends(get_powerbi_access_token)],
    top: int = Query(default=5000, ge=1, le=5000),
    skip: int = Query(default=0, ge=0),
) -> EstateDiscoveryResponse:
    return await EstateDiscoveryService().discover(
        access_token=access_token,
        top=top,
        skip=skip,
    )


@router.post(
    "/scan-jobs",
    response_model=LineageScanJob,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_scan_job(
    request: LineageScanJobRequest,
    manager: Annotated[
        LineageScanJobManager,
        Depends(get_lineage_scan_manager),
    ],
) -> LineageScanJob:
    return await manager.submit(request)


@router.post(
    "/scan-jobs/live",
    response_model=LineageScanJob,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_live_scan_job(
    request: LiveLineageScanRequest,
    fabric_access_token: Annotated[str, Depends(get_fabric_access_token)],
    powerbi_access_token: Annotated[str, Depends(get_powerbi_access_token)],
    manager: Annotated[
        LineageScanJobManager,
        Depends(get_lineage_scan_manager),
    ],
) -> LineageScanJob:
    return await manager.submit_live(
        request,
        fabric_access_token=fabric_access_token,
        powerbi_access_token=powerbi_access_token,
    )


@router.get(
    "/scan-jobs/{job_id}",
    response_model=LineageScanJob,
)
async def get_scan_job(
    job_id: str,
    manager: Annotated[
        LineageScanJobManager,
        Depends(get_lineage_scan_manager),
    ],
) -> LineageScanJob:
    job = await manager.get(job_id)
    if job is None:
        raise ResourceNotFoundError("lineage scan job")
    return job


async def _stored_graph(
    store: LineageStoreService,
    graph_id: str,
    version: int | None,
) -> StoredLineageGraph:
    stored = await asyncio.to_thread(store.get, graph_id, version=version)
    if stored is None:
        raise ResourceNotFoundError("lineage graph")
    return stored
