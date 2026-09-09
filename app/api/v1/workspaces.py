from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Path,
    Query,
)

from app.api.dependencies.credentials import (
    get_fabric_access_token,
    get_powerbi_access_token,
)
from app.schemas.normalized_report_definition import (
    NormalizedReportDefinitionResponse,
)
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelResponse,
)
from app.schemas.report import (
    Report,
    ReportListResponse,
)
from app.schemas.report_definition import (
    ReportDefinitionResponse,
)
from app.schemas.report_page import (
    ReportPage,
    ReportPageListResponse,
)
from app.schemas.report_semantic_lineage import (
    ReportSemanticLineageResponse,
)
from app.schemas.semantic_model import (
    SemanticModelListResponse,
)
from app.schemas.semantic_model_definition import (
    SemanticModelDefinitionResponse,
)
from app.schemas.semantic_model_metadata import (
    SemanticModelMetadataResponse,
)
from app.schemas.workspace import (
    Workspace,
    WorkspaceListResponse,
)
from app.schemas.xmla_metadata import (
    XmlaSemanticModelMetadataResponse,
)
from app.services.report_definition_service import (
    ReportDefinitionService,
)
from app.services.report_semantic_lineage_service import (
    ReportSemanticLineageService,
)
from app.services.report_service import (
    ReportService,
)
from app.services.semantic_model_definition_service import (
    SemanticModelDefinitionService,
)
from app.services.semantic_model_metadata_service import (
    SemanticModelMetadataService,
)
from app.services.semantic_model_service import (
    SemanticModelService,
)
from app.services.workspace_service import (
    WorkspaceService,
)
from app.services.xmla_metadata_service import (
    XmlaMetadataService,
)

router = APIRouter()


@router.get(
    "",
    response_model=WorkspaceListResponse,
)
async def list_workspaces(
    access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
    top: Annotated[
        int,
        Query(
            ge=1,
            le=500,
        ),
    ] = 100,
    skip: Annotated[
        int,
        Query(
            ge=0,
        ),
    ] = 0,
) -> WorkspaceListResponse:
    service = WorkspaceService()

    return await service.list_workspaces(
        access_token=access_token,
        top=top,
        skip=skip,
    )


@router.get(
    "/{workspace_id}",
    response_model=Workspace,
)
async def get_workspace(
    workspace_id: UUID,
    access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> Workspace:
    service = WorkspaceService()

    return await service.get_workspace(
        workspace_id=str(workspace_id),
        access_token=access_token,
    )


@router.get(
    "/{workspace_id}/reports",
    response_model=ReportListResponse,
)
async def list_workspace_reports(
    workspace_id: UUID,
    access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> ReportListResponse:
    service = ReportService()

    return await service.list_reports(
        workspace_id=str(workspace_id),
        access_token=access_token,
    )


@router.get(
    "/{workspace_id}/semantic-models",
    response_model=SemanticModelListResponse,
)
async def list_workspace_semantic_models(
    workspace_id: UUID,
    access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> SemanticModelListResponse:
    service = SemanticModelService()

    return await service.list_semantic_models(
        workspace_id=str(workspace_id),
        access_token=access_token,
    )


@router.get(
    "/{workspace_id}/reports/{report_id}",
    response_model=Report,
)
async def get_workspace_report(
    workspace_id: UUID,
    report_id: UUID,
    access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> Report:
    service = ReportService()

    return await service.get_report(
        workspace_id=str(workspace_id),
        report_id=str(report_id),
        access_token=access_token,
    )


@router.get(
    "/{workspace_id}/reports/{report_id}/pages",
    response_model=ReportPageListResponse,
)
async def list_workspace_report_pages(
    workspace_id: UUID,
    report_id: UUID,
    access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> ReportPageListResponse:
    service = ReportService()

    return await service.list_pages(
        workspace_id=str(workspace_id),
        report_id=str(report_id),
        access_token=access_token,
    )


@router.get(
    ("/{workspace_id}/reports/{report_id}/pages/{page_name}"),
    response_model=ReportPage,
)
async def get_workspace_report_page(
    workspace_id: UUID,
    report_id: UUID,
    page_name: Annotated[
        str,
        Path(
            min_length=1,
            max_length=256,
        ),
    ],
    access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> ReportPage:
    service = ReportService()

    return await service.get_page(
        workspace_id=str(workspace_id),
        report_id=str(report_id),
        page_name=page_name,
        access_token=access_token,
    )


@router.post(
    ("/{workspace_id}/reports/{report_id}/definition"),
    response_model=(ReportDefinitionResponse),
)
async def get_workspace_report_definition(
    workspace_id: UUID,
    report_id: UUID,
    access_token: Annotated[
        str,
        Depends(get_fabric_access_token),
    ],
    definition_format: Annotated[
        Literal[
            "PBIR",
            "PBIR-Legacy",
        ],
        Query(
            alias="format",
        ),
    ] = "PBIR",
) -> ReportDefinitionResponse:
    service = ReportDefinitionService()

    return await service.get_definition(
        workspace_id=str(workspace_id),
        report_id=str(report_id),
        access_token=access_token,
        definition_format=(definition_format),
    )


@router.post(
    ("/{workspace_id}/reports/{report_id}/definition/normalized"),
    response_model=(NormalizedReportDefinitionResponse),
)
async def get_normalized_report_definition(
    workspace_id: UUID,
    report_id: UUID,
    access_token: Annotated[
        str,
        Depends(get_fabric_access_token),
    ],
    definition_format: Annotated[
        Literal[
            "PBIR",
            "PBIR-Legacy",
        ],
        Query(
            alias="format",
        ),
    ] = "PBIR",
) -> NormalizedReportDefinitionResponse:
    service = ReportDefinitionService()

    return await service.get_normalized_definition(
        workspace_id=str(workspace_id),
        report_id=str(report_id),
        access_token=access_token,
        definition_format=(definition_format),
    )


@router.post(
    ("/{workspace_id}/semantic-models/{semantic_model_id}/definition"),
    response_model=(SemanticModelDefinitionResponse),
)
async def get_workspace_semantic_model_definition(
    workspace_id: UUID,
    semantic_model_id: UUID,
    access_token: Annotated[
        str,
        Depends(get_fabric_access_token),
    ],
    definition_format: Annotated[
        Literal[
            "TMDL",
            "TMSL",
        ],
        Query(
            alias="format",
        ),
    ] = "TMDL",
) -> SemanticModelDefinitionResponse:
    service = SemanticModelDefinitionService()

    return await service.get_definition(
        workspace_id=str(workspace_id),
        semantic_model_id=str(semantic_model_id),
        access_token=access_token,
        definition_format=(definition_format),
    )


@router.post(
    ("/{workspace_id}/semantic-models/{semantic_model_id}/definition/parsed"),
    response_model=ParsedSemanticModelResponse,
)
async def get_workspace_parsed_semantic_model_definition(
    workspace_id: UUID,
    semantic_model_id: UUID,
    access_token: Annotated[
        str,
        Depends(get_fabric_access_token),
    ],
    definition_format: Annotated[
        Literal[
            "TMDL",
            "TMSL",
        ],
        Query(
            alias="format",
        ),
    ] = "TMDL",
) -> ParsedSemanticModelResponse:
    service = SemanticModelDefinitionService()

    return await service.get_parsed_definition(
        workspace_id=str(workspace_id),
        semantic_model_id=str(semantic_model_id),
        access_token=access_token,
        definition_format=definition_format,
    )


@router.get(
    ("/{workspace_id}/semantic-models/{semantic_model_id}/xmla/metadata"),
    response_model=XmlaSemanticModelMetadataResponse,
)
async def get_workspace_semantic_model_xmla_metadata(
    workspace_id: UUID,
    semantic_model_id: UUID,
    access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
    workspace_name: Annotated[
        str | None,
        Query(
            alias="workspaceName",
            min_length=1,
            max_length=256,
        ),
    ] = None,
    database_name: Annotated[
        str | None,
        Query(
            alias="databaseName",
            min_length=1,
            max_length=256,
        ),
    ] = None,
) -> XmlaSemanticModelMetadataResponse:
    service = XmlaMetadataService()

    return await service.get_metadata(
        workspace_id=str(workspace_id),
        semantic_model_id=str(semantic_model_id),
        access_token=access_token,
        workspace_name=workspace_name,
        database_name=database_name,
    )


@router.get(
    ("/{workspace_id}/semantic-models/{semantic_model_id}/metadata"),
    response_model=SemanticModelMetadataResponse,
)
async def get_workspace_semantic_model_metadata(
    workspace_id: UUID,
    semantic_model_id: UUID,
    fabric_access_token: Annotated[
        str,
        Depends(get_fabric_access_token),
    ],
    powerbi_access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
    workspace_name: Annotated[
        str | None,
        Query(
            alias="workspaceName",
            min_length=1,
            max_length=256,
        ),
    ] = None,
    database_name: Annotated[
        str | None,
        Query(
            alias="databaseName",
            min_length=1,
            max_length=256,
        ),
    ] = None,
    definition_format: Annotated[
        Literal["TMDL"],
        Query(
            alias="format",
        ),
    ] = "TMDL",
) -> SemanticModelMetadataResponse:
    service = SemanticModelMetadataService()

    return await service.get_metadata(
        workspace_id=str(workspace_id),
        semantic_model_id=str(semantic_model_id),
        fabric_access_token=fabric_access_token,
        powerbi_access_token=powerbi_access_token,
        workspace_name=workspace_name,
        database_name=database_name,
        definition_format=definition_format,
    )


@router.post(
    ("/{workspace_id}/reports/{report_id}/semantic-lineage"),
    response_model=ReportSemanticLineageResponse,
)
async def get_workspace_report_semantic_lineage(
    workspace_id: UUID,
    report_id: UUID,
    semantic_model_id: Annotated[
        UUID,
        Query(),
    ],
    access_token: Annotated[
        str,
        Depends(get_fabric_access_token),
    ],
    semantic_model_workspace_id: Annotated[
        UUID | None,
        Query(),
    ] = None,
    report_definition_format: Annotated[
        Literal[
            "PBIR",
            "PBIR-Legacy",
        ],
        Query(
            alias="reportFormat",
        ),
    ] = "PBIR",
    semantic_model_definition_format: Annotated[
        Literal[
            "TMDL",
            "TMSL",
        ],
        Query(
            alias="semanticModelFormat",
        ),
    ] = "TMDL",
) -> ReportSemanticLineageResponse:
    service = ReportSemanticLineageService()

    resolved_semantic_model_workspace_id = semantic_model_workspace_id or workspace_id

    return await service.build_lineage(
        workspace_id=str(workspace_id),
        report_id=str(report_id),
        semantic_model_workspace_id=str(resolved_semantic_model_workspace_id),
        semantic_model_id=str(semantic_model_id),
        access_token=access_token,
        report_definition_format=(report_definition_format),
        semantic_model_definition_format=(semantic_model_definition_format),
    )
