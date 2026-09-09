from unittest.mock import AsyncMock

import httpx
import pytest

from app.clients.snowflake_client import SnowflakeClient
from app.services.snowflake_lineage_service import SnowflakeLineageService


def _dependency_row() -> dict[str, str]:
    return {
        "REFERENCED_DATABASE": "RAW",
        "REFERENCED_SCHEMA": "SALES",
        "REFERENCED_OBJECT_NAME": "ORDERS",
        "REFERENCED_OBJECT_DOMAIN": "TABLE",
        "REFERENCING_DATABASE": "ANALYTICS",
        "REFERENCING_SCHEMA": "MART",
        "REFERENCING_OBJECT_NAME": "SALES_VIEW",
        "REFERENCING_OBJECT_DOMAIN": "VIEW",
        "DEPENDENCY_TYPE": "BY_NAME",
    }


def test_normalizes_snowflake_dependencies_upstream_to_downstream():
    result = SnowflakeLineageService().normalize_rows(
        account_identifier="org-account",
        rows=[_dependency_row(), _dependency_row()],
    )

    assert result.object_count == 2
    assert result.dependency_count == 1
    dependency = result.dependencies[0]
    assert dependency.source.qualified_name == "RAW.SALES.ORDERS"
    assert dependency.target.qualified_name == "ANALYTICS.MART.SALES_VIEW"
    assert dependency.dependency_type == "BY_NAME"


def test_invalid_snowflake_row_adds_warning():
    result = SnowflakeLineageService().normalize_rows(
        account_identifier="org-account",
        rows=[{"REFERENCED_DATABASE": "RAW"}],
    )

    assert result.dependency_count == 0
    assert result.warnings[0].code == "SNOWFLAKE_DEPENDENCY_ROW_INVALID"


@pytest.mark.asyncio
async def test_snowflake_client_submits_account_usage_query(monkeypatch):
    row = list(_dependency_row().values())
    response = httpx.Response(
        200,
        json={
            "resultSetMetaData": {
                "rowType": [{"name": name} for name in _dependency_row()],
            },
            "data": [row],
        },
    )
    provider_post = AsyncMock(return_value=response)
    monkeypatch.setattr(
        "app.clients.snowflake_client.provider_post",
        provider_post,
    )

    result = await SnowflakeClient("org-account").get_object_dependencies(
        access_token="snowflake-token",
        warehouse="LINEAGE_WH",
        role="OBJECT_VIEWER",
    )

    assert result == [_dependency_row()]
    call = provider_post.await_args.kwargs
    assert call["url"] == (
        "https://org-account.snowflakecomputing.com/api/v2/statements"
    )
    assert "OBJECT_DEPENDENCIES" in call["json_body"]["statement"]
    assert call["json_body"]["warehouse"] == "LINEAGE_WH"
    assert call["additional_headers"] == {
        "X-Snowflake-Authorization-Token-Type": "OAUTH"
    }


@pytest.mark.asyncio
async def test_snowflake_client_retrieves_all_result_partitions(monkeypatch):
    first_row = _dependency_row()
    second_row = {
        **_dependency_row(),
        "REFERENCING_OBJECT_NAME": "SECOND_VIEW",
    }
    columns = list(first_row)
    provider_post = AsyncMock(
        return_value=httpx.Response(
            200,
            json={
                "statementHandle": "statement-1",
                "resultSetMetaData": {
                    "rowType": [{"name": name} for name in columns],
                    "partitionInfo": [{"rowCount": 1}, {"rowCount": 1}],
                },
                "data": [list(first_row.values())],
            },
        )
    )
    provider_get = AsyncMock(
        return_value=httpx.Response(
            200,
            json={"data": [list(second_row.values())]},
        )
    )
    monkeypatch.setattr(
        "app.clients.snowflake_client.provider_post",
        provider_post,
    )
    monkeypatch.setattr(
        "app.clients.snowflake_client.provider_get",
        provider_get,
    )

    result = await SnowflakeClient("org-account").get_object_dependencies(
        access_token="snowflake-token",
    )

    assert result == [first_row, second_row]
    provider_get.assert_awaited_once_with(
        provider="snowflake",
        url=(
            "https://org-account.snowflakecomputing.com/api/v2/statements/statement-1"
        ),
        access_token="snowflake-token",
        params={"partition": 1},
        additional_headers={"X-Snowflake-Authorization-Token-Type": "OAUTH"},
    )


def test_snowflake_client_rejects_url_as_account_identifier():
    with pytest.raises(ValueError, match="account identifier"):
        SnowflakeClient("https://untrusted.example")
