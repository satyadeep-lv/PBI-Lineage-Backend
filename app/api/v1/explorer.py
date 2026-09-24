from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.dependencies.credentials import (
    get_fabric_access_token,
    get_optional_fabric_access_token,
    get_powerbi_access_token,
)
from app.api.dependencies.security import require_lineage_api_key
from app.schemas.error import ErrorResponse
from app.schemas.explorer import (
    ExplorerRequest,
    ExplorerSnapshotResponse,
    MeasureSourceLineageResponse,
    ReportLayoutResponse,
    ReportSourceTableResponse,
    ReportVisualSourceColumnsRequest,
    ReportVisualSourceColumnsResponse,
    SemanticModelObjectsResponse,
    SourceDatabaseLineageResponse,
    VisualSourceLookupResponse,
)
from app.services.explorer_service import (
    MEASURE_SOURCE_LINEAGE,
    REPORT_LAYOUT,
    REPORT_SOURCE_TABLES,
    SEMANTIC_MODEL_OBJECTS,
    SOURCE_DATABASE_LINEAGE,
    VISUAL_SOURCE_LOOKUP,
    ExplorerDatasetName,
    ExplorerService,
)
from app.services.report_visual_source_column_service import (
    ReportVisualSourceColumnService,
)

router = APIRouter()


@router.post(
    "/snapshot",
    response_model=ExplorerSnapshotResponse,
)
async def get_explorer_snapshot(
    request: ExplorerRequest,
    fabric_access_token: Annotated[
        str,
        Depends(get_fabric_access_token),
    ],
    powerbi_access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> ExplorerSnapshotResponse:
    return await ExplorerService().build_snapshot(
        request,
        fabric_access_token=fabric_access_token,
        powerbi_access_token=powerbi_access_token,
    )


@router.post(
    "/source-database-lineage",
    response_model=SourceDatabaseLineageResponse,
)
async def get_source_database_lineage(
    request: ExplorerRequest,
    fabric_access_token: Annotated[
        str,
        Depends(get_fabric_access_token),
    ],
    powerbi_access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> SourceDatabaseLineageResponse:
    snapshot = await _build_dataset(
        request,
        dataset=SOURCE_DATABASE_LINEAGE,
        fabric_access_token=fabric_access_token,
        powerbi_access_token=powerbi_access_token,
    )
    return SourceDatabaseLineageResponse(
        **_response_context(snapshot),
        rows=snapshot.source_database_lineage.rows,
        count=snapshot.source_database_lineage.count,
    )


@router.post(
    "/report-source-tables",
    response_model=ReportSourceTableResponse,
)
async def get_report_source_tables(
    request: ExplorerRequest,
    fabric_access_token: Annotated[
        str,
        Depends(get_fabric_access_token),
    ],
    powerbi_access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> ReportSourceTableResponse:
    snapshot = await _build_dataset(
        request,
        dataset=REPORT_SOURCE_TABLES,
        fabric_access_token=fabric_access_token,
        powerbi_access_token=powerbi_access_token,
    )
    return ReportSourceTableResponse(
        **_response_context(snapshot),
        rows=snapshot.report_source_tables.rows,
        count=snapshot.report_source_tables.count,
    )


@router.post(
    "/semantic-model-objects",
    response_model=SemanticModelObjectsResponse,
)
async def get_semantic_model_objects(
    request: ExplorerRequest,
    fabric_access_token: Annotated[
        str,
        Depends(get_fabric_access_token),
    ],
    powerbi_access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> SemanticModelObjectsResponse:
    snapshot = await _build_dataset(
        request,
        dataset=SEMANTIC_MODEL_OBJECTS,
        fabric_access_token=fabric_access_token,
        powerbi_access_token=powerbi_access_token,
    )
    return SemanticModelObjectsResponse(
        **_response_context(snapshot),
        rows=snapshot.semantic_model_objects.rows,
        count=snapshot.semantic_model_objects.count,
    )


@router.post(
    "/measure-source-lineage",
    response_model=MeasureSourceLineageResponse,
)
async def get_measure_source_lineage(
    request: ExplorerRequest,
    fabric_access_token: Annotated[
        str,
        Depends(get_fabric_access_token),
    ],
    powerbi_access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> MeasureSourceLineageResponse:
    snapshot = await _build_dataset(
        request,
        dataset=MEASURE_SOURCE_LINEAGE,
        fabric_access_token=fabric_access_token,
        powerbi_access_token=powerbi_access_token,
    )
    return MeasureSourceLineageResponse(
        **_response_context(snapshot),
        rows=snapshot.measure_source_lineage.rows,
        count=snapshot.measure_source_lineage.count,
    )


@router.post(
    "/report-layout",
    response_model=ReportLayoutResponse,
)
async def get_report_layout(
    request: ExplorerRequest,
    fabric_access_token: Annotated[
        str,
        Depends(get_fabric_access_token),
    ],
    powerbi_access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> ReportLayoutResponse:
    snapshot = await _build_dataset(
        request,
        dataset=REPORT_LAYOUT,
        fabric_access_token=fabric_access_token,
        powerbi_access_token=powerbi_access_token,
    )
    return ReportLayoutResponse(
        **_response_context(snapshot),
        rows=snapshot.report_layout.rows,
        count=snapshot.report_layout.count,
    )


@router.post(
    "/visual-source-lookup",
    response_model=VisualSourceLookupResponse,
)
async def get_visual_source_lookup(
    request: ExplorerRequest,
    fabric_access_token: Annotated[
        str,
        Depends(get_fabric_access_token),
    ],
    powerbi_access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> VisualSourceLookupResponse:
    snapshot = await _build_dataset(
        request,
        dataset=VISUAL_SOURCE_LOOKUP,
        fabric_access_token=fabric_access_token,
        powerbi_access_token=powerbi_access_token,
    )
    return VisualSourceLookupResponse(
        **_response_context(snapshot),
        rows=snapshot.visual_source_lookup.rows,
        count=snapshot.visual_source_lookup.count,
    )


@router.post(
    "/report-visual-source-columns",
    response_model=ReportVisualSourceColumnsResponse,
    dependencies=[Depends(require_lineage_api_key)],
    summary="Physical source columns behind each report visual field",
    responses={
        status_code: {"model": ErrorResponse, "description": description}
        for status_code, description in (
            (400, "The request could not be processed."),
            (401, "No signed-in Power BI session, or a missing admin key."),
            (403, "The admin key is invalid, or access to the report is denied."),
            (404, "The workspace or report was not found."),
            (429, "Power BI is rate limiting the caller."),
            (502, "Power BI returned an unexpected response."),
        )
    },
)
async def get_report_visual_source_columns(
    request: ReportVisualSourceColumnsRequest,
    powerbi_access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
    fabric_access_token: Annotated[
        str | None,
        Depends(get_optional_fabric_access_token),
    ],
) -> ReportVisualSourceColumnsResponse:
    """One row per field used in a report visual, with the physical database
    columns and tables it reads.

    The semantic model is inferred from the report's binding (it may live in
    another workspace), and composite-model links are always followed to the
    database behind them. Measures and calculated columns are traced through
    their DAX dependencies to terminal columns. A definition or source that
    cannot be read degrades to warnings and unresolved rows rather than an
    error; only the workspace and report themselves are required.
    """
    return await ReportVisualSourceColumnService().build(
        request,
        powerbi_access_token=powerbi_access_token,
        fabric_access_token=fabric_access_token,
    )


async def _build_dataset(
    request: ExplorerRequest,
    *,
    dataset: ExplorerDatasetName,
    fabric_access_token: str,
    powerbi_access_token: str,
) -> ExplorerSnapshotResponse:
    return await ExplorerService().build_snapshot(
        request,
        fabric_access_token=fabric_access_token,
        powerbi_access_token=powerbi_access_token,
        datasets=frozenset({dataset}),
    )


def _response_context(snapshot: ExplorerSnapshotResponse) -> dict[str, Any]:
    return {
        "generated_at": snapshot.generated_at,
        "reports": snapshot.reports,
        "report_count": snapshot.report_count,
        "semantic_model_count": snapshot.semantic_model_count,
        "warnings": snapshot.warnings,
    }
