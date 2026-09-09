from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies.credentials import get_powerbi_access_token
from app.api.dependencies.security import require_lineage_api_key
from app.schemas.scanner import (
    ScannerModifiedWorkspacesResponse,
    ScannerResultResponse,
    ScannerScanResponse,
    ScannerWorkspaceScanRequest,
)
from app.services.scanner_service import ScannerService

router = APIRouter(dependencies=[Depends(require_lineage_api_key)])


@router.get(
    "/workspaces/modified",
    response_model=ScannerModifiedWorkspacesResponse,
)
async def list_scanner_workspaces(
    access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
    modified_since: Annotated[
        datetime | None,
        Query(
            description=(
                "UTC timestamp from 30 minutes to 30 days ago. "
                "Omit it to return all workspace IDs."
            )
        ),
    ] = None,
    exclude_personal_workspaces: bool = True,
    exclude_inactive_workspaces: bool = True,
) -> ScannerModifiedWorkspacesResponse:
    return await ScannerService().list_modified_workspaces(
        access_token=access_token,
        modified_since=modified_since,
        exclude_personal_workspaces=exclude_personal_workspaces,
        exclude_inactive_workspaces=exclude_inactive_workspaces,
    )


@router.post(
    "/workspaces/scan",
    response_model=ScannerScanResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_scanner_workspace_scan(
    request: ScannerWorkspaceScanRequest,
    access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> ScannerScanResponse:
    return await ScannerService().start_scan(
        access_token=access_token,
        request=request,
    )


@router.get(
    "/scans/{scan_id}/status",
    response_model=ScannerScanResponse,
)
async def get_scanner_scan_status(
    scan_id: UUID,
    access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> ScannerScanResponse:
    return await ScannerService().get_scan_status(
        access_token=access_token,
        scan_id=str(scan_id),
    )


@router.get(
    "/scans/{scan_id}/result",
    response_model=ScannerResultResponse,
)
async def get_scanner_scan_result(
    scan_id: UUID,
    access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> ScannerResultResponse:
    return await ScannerService().get_scan_result(
        access_token=access_token,
        scan_id=str(scan_id),
    )
