import pytest

from app.api.dependencies.credentials import (
    get_powerbi_access_token,
)
from app.main import app
from app.schemas.gateway import (
    Gateway,
    GatewayDatasource,
    GatewayDatasourceListResponse,
    GatewayListResponse,
)
from app.services.gateway_service import GatewayService

GATEWAY_ID = "1f69e798-5852-4fdd-ab01-33bb14b6e934"
DATASOURCE_ID = "252b9de8-d915-4788-aaeb-ec8c2395f970"


@pytest.fixture(autouse=True)
def override_authentication():
    async def fake_powerbi_token() -> str:
        return "fake-test-token"

    app.dependency_overrides[get_powerbi_access_token] = fake_powerbi_token

    yield

    app.dependency_overrides.pop(
        get_powerbi_access_token,
        None,
    )


def test_list_gateways(
    client,
    monkeypatch,
):
    async def fake_list_gateways(
        self,
        *,
        access_token: str,
    ) -> GatewayListResponse:
        assert access_token == "fake-test-token"

        return GatewayListResponse(
            gateways=[
                Gateway(
                    id=GATEWAY_ID,
                    name="Warehouse Gateway",
                    type="Resource",
                )
            ],
            count=1,
        )

    monkeypatch.setattr(
        GatewayService,
        "list_gateways",
        fake_list_gateways,
    )

    response = client.get("/api/v1/gateways")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["gateways"][0]["id"] == GATEWAY_ID


def test_get_gateway_datasource(
    client,
    monkeypatch,
):
    async def fake_get_datasource(
        self,
        *,
        gateway_id: str,
        datasource_id: str,
        access_token: str,
    ) -> GatewayDatasource:
        assert gateway_id == GATEWAY_ID
        assert datasource_id == DATASOURCE_ID
        assert access_token == "fake-test-token"

        return GatewayDatasource(
            id=datasource_id,
            gateway_id=gateway_id,
            datasource_type="Sql",
            datasource_name="Warehouse",
            connection_details=('{"server":"sql.example"}'),
        )

    monkeypatch.setattr(
        GatewayService,
        "get_datasource",
        fake_get_datasource,
    )

    response = client.get(f"/api/v1/gateways/{GATEWAY_ID}/datasources/{DATASOURCE_ID}")

    assert response.status_code == 200
    assert response.json()["id"] == DATASOURCE_ID
    assert response.json()["gateway_id"] == GATEWAY_ID


def test_list_gateway_datasources(
    client,
    monkeypatch,
):
    async def fake_list_datasources(
        self,
        *,
        gateway_id: str,
        access_token: str,
    ) -> GatewayDatasourceListResponse:
        assert gateway_id == GATEWAY_ID
        assert access_token == "fake-test-token"

        return GatewayDatasourceListResponse(
            gateway_id=gateway_id,
            datasources=[
                GatewayDatasource(
                    id=DATASOURCE_ID,
                    gateway_id=gateway_id,
                    datasource_type="Sql",
                )
            ],
            count=1,
        )

    monkeypatch.setattr(
        GatewayService,
        "list_datasources",
        fake_list_datasources,
    )

    response = client.get(f"/api/v1/gateways/{GATEWAY_ID}/datasources")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["datasources"][0]["id"] == DATASOURCE_ID


def test_gateway_datasource_rejects_invalid_gateway_uuid(
    client,
):
    response = client.get(f"/api/v1/gateways/not-a-uuid/datasources/{DATASOURCE_ID}")

    assert response.status_code == 422
