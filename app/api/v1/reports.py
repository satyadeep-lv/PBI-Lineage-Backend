from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies.credentials import (
    get_powerbi_access_token,
)
from app.schemas.report import Report
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
