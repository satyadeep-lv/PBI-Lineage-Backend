import pytest

from app.core.exceptions import (
    ProviderResourceNotFoundError,
    UpstreamInvalidResponseError,
)
from app.services.xmla_metadata_service import (
    XmlaMetadataService,
)


class _FakeXmlaClient:
    def __init__(
        self,
        payload: dict,
    ) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def build_workspace_endpoint(
        self,
        *,
        workspace_id: str,
        workspace_name: str | None = None,
    ) -> str:
        target = workspace_name or workspace_id

        return f"powerbi://api.powerbi.com/v1.0/myorg/{target}"

    async def get_semantic_model_metadata(
        self,
        **kwargs,
    ) -> dict:
        self.calls.append(kwargs)

        return self.payload


class _FakePowerBIClient:
    def __init__(
        self,
        *,
        workspace_payload: dict | None = None,
        semantic_models: list[dict] | None = None,
    ) -> None:
        self.workspace_payload = (
            workspace_payload
            if workspace_payload is not None
            else {
                "id": "workspace-123",
                "name": "Sales Workspace",
            }
        )
        self.semantic_models = (
            semantic_models
            if semantic_models is not None
            else [
                {
                    "id": "model-123",
                    "name": "Sales Model",
                }
            ]
        )
        self.workspace_calls: list[dict] = []
        self.semantic_model_calls: list[dict] = []

    async def get_workspace(
        self,
        *,
        workspace_id: str,
        access_token: str,
    ) -> dict:
        self.workspace_calls.append(
            {
                "workspace_id": workspace_id,
                "access_token": access_token,
            }
        )

        return self.workspace_payload

    async def get_semantic_models_in_workspace(
        self,
        *,
        workspace_id: str,
        access_token: str,
    ) -> list[dict]:
        self.semantic_model_calls.append(
            {
                "workspace_id": workspace_id,
                "access_token": access_token,
            }
        )

        return self.semantic_models


def _metadata_payload() -> dict:
    return {
        "databaseName": "Sales Model",
        "tables": [
            {
                "name": "Sales",
                "description": ("Sales fact table"),
                "isHidden": False,
                "columns": [
                    {
                        "name": "Amount",
                        "dataType": "Decimal",
                        "sourceColumn": ("SalesAmount"),
                        "formatString": "$#,0.00",
                        "summarizeBy": "Sum",
                        "isHidden": False,
                        "lineageTag": ("amount-lineage"),
                    }
                ],
                "measures": [
                    {
                        "name": "Total Sales",
                        "expression": ("SUM(Sales[Amount])"),
                        "formatString": "$#,0.00",
                        "isHidden": False,
                    }
                ],
                "partitions": [
                    {
                        "name": "Sales",
                        "mode": "Import",
                        "sourceType": "M",
                        "expression": ("let Source = ..."),
                        "isRefreshable": True,
                    }
                ],
                "hierarchies": [
                    {
                        "name": "Calendar",
                        "isHidden": False,
                        "levels": [
                            {
                                "name": "Year",
                                "column": "Year",
                                "ordinal": 0,
                            }
                        ],
                    }
                ],
            }
        ],
        "relationships": [
            {
                "name": "Sales_Date",
                "fromTable": "Sales",
                "fromColumn": "DateKey",
                "toTable": "Date",
                "toColumn": "DateKey",
                "isActive": True,
                "cardinality": "ManyToOne",
                "crossFilterDirection": "Single",
                "securityFilteringBehavior": "OneDirection",
            }
        ],
        "warnings": [
            {
                "code": "XMLA_PARTIAL_METADATA",
                "message": ("Some annotations were skipped."),
                "objectName": "Sales",
            }
        ],
    }


@pytest.mark.asyncio
async def test_get_xmla_metadata_maps_client_payload():
    fake_client = _FakeXmlaClient(_metadata_payload())
    fake_powerbi_client = _FakePowerBIClient()
    service = XmlaMetadataService(
        xmla_client=fake_client,
        powerbi_client=fake_powerbi_client,
    )

    result = await service.get_metadata(
        workspace_id="workspace-123",
        semantic_model_id="model-123",
        access_token="token",
        workspace_name="Sales Workspace",
        database_name="Sales Model",
    )

    assert result.workspace_id == "workspace-123"
    assert result.semantic_model_id == "model-123"
    assert result.source == "xmla"
    assert result.xmla_endpoint == (
        "powerbi://api.powerbi.com/v1.0/myorg/Sales Workspace"
    )
    assert result.database_name == "Sales Model"
    assert result.table_count == 1
    assert result.column_count == 1
    assert result.measure_count == 1
    assert result.relationship_count == 1
    assert result.hierarchy_count == 1
    assert result.partition_count == 1

    table = result.tables[0]

    assert table.name == "Sales"
    assert table.columns[0].source_column == "SalesAmount"
    assert table.measures[0].expression == "SUM(Sales[Amount])"
    assert table.partitions[0].source_type == "M"
    assert table.hierarchies[0].levels[0].ordinal == 0
    assert result.relationships[0].cross_filter_direction == "Single"
    assert result.warnings[0].code == "XMLA_PARTIAL_METADATA"
    assert fake_client.calls == [
        {
            "workspace_id": "workspace-123",
            "semantic_model_id": "model-123",
            "access_token": "token",
            "workspace_name": "Sales Workspace",
            "database_name": "Sales Model",
        }
    ]
    assert fake_powerbi_client.workspace_calls == []
    assert fake_powerbi_client.semantic_model_calls == []


@pytest.mark.asyncio
async def test_get_xmla_metadata_resolves_missing_names():
    fake_client = _FakeXmlaClient(
        {
            "tables": [],
        }
    )
    fake_powerbi_client = _FakePowerBIClient()
    service = XmlaMetadataService(
        xmla_client=fake_client,
        powerbi_client=fake_powerbi_client,
    )

    result = await service.get_metadata(
        workspace_id="workspace-123",
        semantic_model_id="model-123",
        access_token="token",
    )

    assert result.database_name == "Sales Model"
    assert result.xmla_endpoint == (
        "powerbi://api.powerbi.com/v1.0/myorg/Sales Workspace"
    )
    assert result.table_count == 0
    assert fake_client.calls == [
        {
            "workspace_id": "workspace-123",
            "semantic_model_id": "model-123",
            "access_token": "token",
            "workspace_name": "Sales Workspace",
            "database_name": "Sales Model",
        }
    ]
    assert fake_powerbi_client.workspace_calls == [
        {
            "workspace_id": "workspace-123",
            "access_token": "token",
        }
    ]
    assert fake_powerbi_client.semantic_model_calls == [
        {
            "workspace_id": "workspace-123",
            "access_token": "token",
        }
    ]


@pytest.mark.asyncio
async def test_get_xmla_metadata_rejects_unresolved_model_name():
    service = XmlaMetadataService(
        xmla_client=_FakeXmlaClient(
            {
                "tables": [],
            }
        ),
        powerbi_client=_FakePowerBIClient(semantic_models=[]),
    )

    with pytest.raises(ProviderResourceNotFoundError):
        await service.get_metadata(
            workspace_id="workspace-123",
            semantic_model_id="model-123",
            access_token="token",
        )


@pytest.mark.asyncio
async def test_get_xmla_metadata_rejects_missing_tables():
    service = XmlaMetadataService(
        xmla_client=_FakeXmlaClient({}),
        powerbi_client=_FakePowerBIClient(),
    )

    with pytest.raises(UpstreamInvalidResponseError):
        await service.get_metadata(
            workspace_id="workspace-123",
            semantic_model_id="model-123",
            access_token="token",
        )


@pytest.mark.asyncio
async def test_get_xmla_metadata_rejects_invalid_table_name():
    service = XmlaMetadataService(
        xmla_client=_FakeXmlaClient(
            {
                "tables": [
                    {
                        "name": "",
                    }
                ],
            }
        ),
        powerbi_client=_FakePowerBIClient(),
    )

    with pytest.raises(UpstreamInvalidResponseError):
        await service.get_metadata(
            workspace_id="workspace-123",
            semantic_model_id="model-123",
            access_token="token",
        )
