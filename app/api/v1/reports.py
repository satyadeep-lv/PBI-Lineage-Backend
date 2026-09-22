from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.credentials import (
    get_powerbi_access_token,
)
from app.schemas.report import Report
from app.schemas.report import ReportUserListResponse
from app.services.report_service import ReportService

router = APIRouter()


@router.get(
    "/{report_id}",
    response_model=Report,
)
async def get_my_workspace_report(
    report_id: UUID,
    access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> Report:
    service = ReportService()

    return await service.get_my_workspace_report(
        report_id=str(report_id),
        access_token=access_token,
    )

@router.get(
    "/{report_id}/users",
    response_model=ReportUserListResponse,
)
async def get_report_users(
    report_id: UUID,
    access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
    workspace_id: Annotated[
        UUID | None,
        Query(description="Optional workspace ID. If provided, tries workspace endpoint before falling back to admin endpoint."),
    ] = None,
) -> ReportUserListResponse:
    """
    Equivalent to Streamlit's get_artifact_users for artifact_type='Report'.
    """
    service = ReportService()

    return await service.get_report_users(
        report_id=str(report_id),
        workspace_id=str(workspace_id) if workspace_id else None,
        access_token=access_token,
    )
