from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies.credentials import (
    get_powerbi_access_token,
)
from app.schemas.gateway import (
    GatewayDatasource,
    GatewayDatasourceListResponse,
    GatewayListResponse,
)
from app.services.gateway_service import GatewayService

router = APIRouter()


@router.get(
    "",
    response_model=GatewayListResponse,
)
async def list_gateways(
    access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> GatewayListResponse:
    service = GatewayService()

    return await service.list_gateways(
        access_token=access_token,
    )


@router.get(
    "/{gateway_id}/datasources",
    response_model=GatewayDatasourceListResponse,
)
async def list_gateway_datasources(
    gateway_id: UUID,
    access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> GatewayDatasourceListResponse:
    service = GatewayService()

    return await service.list_datasources(
        gateway_id=str(gateway_id),
        access_token=access_token,
    )


@router.get(
    "/{gateway_id}/datasources/{datasource_id}",
    response_model=GatewayDatasource,
)
async def get_gateway_datasource(
    gateway_id: UUID,
    datasource_id: UUID,
    access_token: Annotated[
        str,
        Depends(get_powerbi_access_token),
    ],
) -> GatewayDatasource:
    service = GatewayService()

    return await service.get_datasource(
        gateway_id=str(gateway_id),
        datasource_id=str(datasource_id),
        access_token=access_token,
    )
