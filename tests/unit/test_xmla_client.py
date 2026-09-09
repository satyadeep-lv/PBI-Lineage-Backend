import sys
import types
from typing import Any, Self

import pytest

from app.clients.xmla_client import (
    TMSCHEMA_COLUMNS_QUERY,
    TMSCHEMA_HIERARCHIES_QUERY,
    TMSCHEMA_LEVELS_QUERY,
    TMSCHEMA_MEASURES_QUERY,
    TMSCHEMA_PARTITIONS_QUERY,
    TMSCHEMA_RELATIONSHIPS_QUERY,
    TMSCHEMA_TABLES_QUERY,
    AdoComXmlaConnection,
    XmlaClient,
)
from app.core.exceptions import (
    ProviderIntegrationNotConfiguredError,
    UpstreamRequestError,
)


class _FakeXmlaConnection:
    def __init__(
        self,
        rowsets: dict[str, list[dict[str, Any]]],
    ) -> None:
        self.rowsets = rowsets
        self.executed_queries: list[str] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> None:
        return None

    def execute(
        self,
        query: str,
    ) -> list[dict[str, Any]]:
        self.executed_queries.append(query)

        return self.rowsets.get(
            query,
            [],
        )


class _FakeConnectionFactory:
    def __init__(
        self,
        rowsets: dict[str, list[dict[str, Any]]],
    ) -> None:
        self.rowsets = rowsets
        self.calls: list[dict[str, Any]] = []
        self.connections: list[_FakeXmlaConnection] = []

    def __call__(
        self,
        **kwargs,
    ) -> _FakeXmlaConnection:
        self.calls.append(kwargs)
        connection = _FakeXmlaConnection(self.rowsets)
        self.connections.append(connection)

        return connection


class _MissingConnectionFactory:
    def __call__(
        self,
        **kwargs,
    ):
        raise ProviderIntegrationNotConfiguredError(
            "xmla",
            detail=("Install pywin32 and MSOLAP."),
        )


class _FailingConnection:
    def __init__(
        self,
        connection_string: str,
    ) -> None:
        self.connection_string = connection_string

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> None:
        return None

    def execute(
        self,
        query: str,
    ) -> list[dict[str, Any]]:
        raise RuntimeError(f"XMLA failed for {self.connection_string}")


class _FailingConnectionFactory:
    def __call__(
        self,
        *,
        connection_string: str,
    ) -> _FailingConnection:
        return _FailingConnection(connection_string)


class _MissingProviderComConnection:
    def Open(
        self,
        connection_string: str,
    ) -> None:
        raise RuntimeError(
            "Provider cannot be found. It may not be properly installed."
        )

    def Close(self) -> None:
        return None


def _rowsets() -> dict[
    str,
    list[dict[str, Any]],
]:
    return {
        TMSCHEMA_TABLES_QUERY: [
            {
                "ID": 1,
                "Name": "Sales",
                "Description": ("Sales fact table"),
                "IsHidden": False,
            },
            {
                "ID": 2,
                "Name": "Date",
                "IsHidden": False,
            },
        ],
        TMSCHEMA_COLUMNS_QUERY: [
            {
                "ID": 11,
                "TableID": 1,
                "ExplicitName": "Amount",
                "ExplicitDataType": "Decimal",
                "SourceColumn": ("SalesAmount"),
                "FormatString": "$#,0.00",
                "SummarizeBy": "Sum",
                "IsHidden": False,
                "LineageTag": ("amount-lineage"),
            },
            {
                "ID": 12,
                "TableID": 1,
                "ExplicitName": "DateKey",
                "SortByColumnID": 12,
            },
            {
                "ID": 21,
                "TableID": 2,
                "ExplicitName": "DateKey",
            },
        ],
        TMSCHEMA_MEASURES_QUERY: [
            {
                "ID": 31,
                "TableID": 1,
                "Name": "Total Sales",
                "Expression": ("SUM(Sales[Amount])"),
                "FormatString": "$#,0.00",
                "IsHidden": False,
            }
        ],
        TMSCHEMA_PARTITIONS_QUERY: [
            {
                "ID": 41,
                "TableID": 1,
                "Name": "Sales",
                "Mode": "Import",
                "SourceType": "M",
                "Expression": ("let Source = ..."),
                "IsRefreshable": True,
            }
        ],
        TMSCHEMA_HIERARCHIES_QUERY: [
            {
                "ID": 51,
                "TableID": 2,
                "Name": "Calendar",
                "IsHidden": False,
            }
        ],
        TMSCHEMA_LEVELS_QUERY: [
            {
                "ID": 61,
                "HierarchyID": 51,
                "Name": "Date",
                "ColumnID": 21,
                "Ordinal": 0,
            }
        ],
        TMSCHEMA_RELATIONSHIPS_QUERY: [
            {
                "ID": 71,
                "Name": "Sales_Date",
                "FromTableID": 1,
                "FromColumnID": 12,
                "ToTableID": 2,
                "ToColumnID": 21,
                "IsActive": True,
                "Cardinality": "ManyToOne",
                "CrossFilteringBehavior": "Single",
                "SecurityFilteringBehavior": ("OneDirection"),
            }
        ],
    }


def test_build_workspace_endpoint_encodes_workspace_name():
    endpoint = XmlaClient(tenant_name="myorg").build_workspace_endpoint(
        workspace_id="workspace-123",
        workspace_name="Sales Workspace",
    )

    assert endpoint == ("powerbi://api.powerbi.com/v1.0/myorg/Sales%20Workspace")


def test_build_workspace_endpoint_falls_back_to_workspace_id():
    endpoint = XmlaClient(tenant_name="myorg").build_workspace_endpoint(
        workspace_id="workspace-123",
    )

    assert endpoint == ("powerbi://api.powerbi.com/v1.0/myorg/workspace-123")


def test_build_connection_string_uses_initial_catalog():
    connection_string = XmlaClient(
        tenant_name="contoso.com",
        provider_name="MSOLAP.8",
    ).build_connection_string(
        workspace_id="workspace-123",
        semantic_model_id="model-123",
        workspace_name="Sales Workspace",
        database_name="Sales Model",
        access_token="token",
    )

    assert connection_string == (
        "Provider=MSOLAP.8;"
        "Data Source=powerbi://api.powerbi.com/"
        "v1.0/contoso.com/Sales%20Workspace;"
        "Initial Catalog=Sales Model;"
        "Password=token;"
    )


@pytest.mark.asyncio
async def test_xmla_metadata_reads_adodb_rowsets():
    factory = _FakeConnectionFactory(_rowsets())
    client = XmlaClient(
        connection_factory=factory,
        tenant_name="myorg",
    )

    metadata = await client.get_semantic_model_metadata(
        workspace_id="workspace-123",
        semantic_model_id="model-123",
        access_token="token",
        workspace_name="Sales Workspace",
        database_name="Sales Model",
    )

    assert factory.calls == [
        {
            "connection_string": (
                "Provider=MSOLAP;"
                "Data Source=powerbi://"
                "api.powerbi.com/v1.0/myorg/"
                "Sales%20Workspace;Initial Catalog="
                "Sales Model;Password=token;"
            ),
        }
    ]
    assert factory.connections[0].executed_queries == [
        TMSCHEMA_TABLES_QUERY,
        TMSCHEMA_COLUMNS_QUERY,
        TMSCHEMA_MEASURES_QUERY,
        TMSCHEMA_PARTITIONS_QUERY,
        TMSCHEMA_HIERARCHIES_QUERY,
        TMSCHEMA_LEVELS_QUERY,
        TMSCHEMA_RELATIONSHIPS_QUERY,
    ]
    assert metadata["database_name"] == ("Sales Model")
    assert len(metadata["tables"]) == 2

    sales_table = metadata["tables"][0]

    assert sales_table["name"] == "Sales"
    assert sales_table["columns"][0] == {
        "name": "Amount",
        "data_type": "Decimal",
        "source_column": "SalesAmount",
        "expression": None,
        "format_string": "$#,0.00",
        "summarize_by": "Sum",
        "sort_by_column": None,
        "is_hidden": False,
        "description": None,
        "lineage_tag": "amount-lineage",
    }
    assert sales_table["columns"][1]["sort_by_column"] == "DateKey"
    assert sales_table["measures"][0]["expression"] == "SUM(Sales[Amount])"
    assert sales_table["partitions"][0]["source_type"] == "M"

    date_table = metadata["tables"][1]

    assert date_table["hierarchies"][0]["levels"][0]["column"] == "DateKey"
    assert metadata["relationships"] == [
        {
            "name": "Sales_Date",
            "from_table": "Sales",
            "from_column": "DateKey",
            "to_table": "Date",
            "to_column": "DateKey",
            "is_active": True,
            "cardinality": "ManyToOne",
            "cross_filter_direction": "Single",
            "security_filtering_behavior": ("OneDirection"),
        }
    ]
    assert metadata["warnings"] == []


@pytest.mark.asyncio
async def test_xmla_metadata_boundary_reports_missing_adapter():
    client = XmlaClient(connection_factory=(_MissingConnectionFactory()))

    with pytest.raises(ProviderIntegrationNotConfiguredError) as exc_info:
        await client.get_semantic_model_metadata(
            workspace_id="workspace-123",
            semantic_model_id="model-123",
            access_token="token",
            workspace_name="Sales Workspace",
            database_name="Sales Model",
        )

    assert exc_info.value.provider == "xmla"
    assert exc_info.value.code == ("PROVIDER_INTEGRATION_NOT_CONFIGURED")
    assert "Install pywin32" in exc_info.value.message


def test_adocom_connection_reports_missing_msolap_provider(
    monkeypatch,
):
    fake_pythoncom = types.ModuleType("pythoncom")
    fake_pythoncom.CoInitialize = lambda: None
    fake_pythoncom.CoUninitialize = lambda: None

    fake_win32com = types.ModuleType("win32com")
    fake_win32com_client = types.ModuleType("win32com.client")
    fake_win32com_client.Dispatch = lambda name: _MissingProviderComConnection()
    fake_win32com.client = fake_win32com_client

    monkeypatch.setitem(
        sys.modules,
        "pythoncom",
        fake_pythoncom,
    )
    monkeypatch.setitem(
        sys.modules,
        "win32com",
        fake_win32com,
    )
    monkeypatch.setitem(
        sys.modules,
        "win32com.client",
        fake_win32com_client,
    )

    with (
        pytest.raises(ProviderIntegrationNotConfiguredError) as exc_info,
        AdoComXmlaConnection(connection_string="Provider=MSOLAP;"),
    ):
        pass

    assert exc_info.value.provider == "xmla"
    assert exc_info.value.code == ("PROVIDER_INTEGRATION_NOT_CONFIGURED")
    assert "MSOLAP" in exc_info.value.message


@pytest.mark.asyncio
async def test_xmla_metadata_redacts_access_token_from_failure():
    client = XmlaClient(connection_factory=(_FailingConnectionFactory()))

    with pytest.raises(UpstreamRequestError) as exc_info:
        await client.get_semantic_model_metadata(
            workspace_id="workspace-123",
            semantic_model_id="model-123",
            access_token="secret-token",
            workspace_name="Sales Workspace",
            database_name="Sales Model",
        )

    assert "secret-token" not in (exc_info.value.message)
    assert "[redacted]" in (exc_info.value.message)
