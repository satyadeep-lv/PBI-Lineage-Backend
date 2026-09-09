from app.schemas.gateway import GatewayDatasource
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelPartition,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)
from app.services.physical_source_service import PhysicalSourceDiscoveryService


def _semantic_model(expression: str) -> ParsedSemanticModelResponse:
    return ParsedSemanticModelResponse(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        tables=[
            ParsedSemanticModelTable(
                name="Sales",
                partitions=[
                    ParsedSemanticModelPartition(
                        name="Sales",
                        source_path="definition/tables/Sales.tmdl",
                        source_type="m",
                        expression=expression,
                    )
                ],
            )
        ],
    )


def test_discovers_sql_navigation_and_query_mapping():
    model = _semantic_model(
        """
let
    Source = Sql.Database("sql.example.com", "warehouse"),
    Sales = Source{[Schema="dbo",Item="FactSales"]}[Data]
in
    Sales
"""
    )

    result = PhysicalSourceDiscoveryService().discover(model)

    assert result.source_count == 1
    assert result.mapping_count == 1
    source = result.sources[0]
    assert source.provider == "sqlserver"
    assert source.server == "sql.example.com"
    assert source.database == "warehouse"
    assert source.schema_name == "dbo"
    assert source.object_name == "FactSales"
    assert result.mappings[0].source_ids == [source.source_id]


def test_discovers_each_object_in_native_sql():
    model = _semantic_model(
        """
let
    Source = Sql.Database("sql.example.com", "warehouse"),
    Result = Value.NativeQuery(
        Source,
        "SELECT * FROM dbo.Sales s JOIN dbo.Customer c ON s.CustomerId = c.Id"
    )
in
    Result
"""
    )

    result = PhysicalSourceDiscoveryService().discover(model)

    assert {(source.schema_name, source.object_name) for source in result.sources} == {
        ("dbo", "Customer"),
        ("dbo", "Sales"),
    }
    assert all(source.native_query for source in result.sources)


def test_discovers_file_and_web_sources():
    model = _semantic_model(
        """
let
    Local = File.Contents("C:\\imports\\sales.csv"),
    Remote = Web.Contents("https://example.com/sales.json")
in
    Remote
"""
    )

    result = PhysicalSourceDiscoveryService().discover(model)

    assert {source.provider for source in result.sources} == {"file", "web"}


def test_gateway_details_are_sanitized_and_matched_to_query_source():
    model = _semantic_model('Sql.Database("sql.example.com", "warehouse")')
    gateway = GatewayDatasource(
        id="datasource-1",
        gateway_id="gateway-1",
        datasource_type="Sql",
        connection_details=(
            '{"server":"sql.example.com","database":"warehouse",'
            '"username":"not-public","password":"not-public"}'
        ),
    )

    result = PhysicalSourceDiscoveryService().discover(
        model,
        gateway_datasources=[gateway],
    )

    query_source = next(
        source for source in result.sources if source.provider == "sqlserver"
    )
    assert query_source.gateway_id == "gateway-1"
    assert query_source.gateway_datasource_id == "datasource-1"
    assert "username" not in query_source.model_dump()
    assert "password" not in query_source.model_dump()


def test_invalid_gateway_connection_details_adds_warning():
    gateway = GatewayDatasource(
        id="datasource-1",
        gateway_id="gateway-1",
        connection_details="not-json",
    )

    result = PhysicalSourceDiscoveryService().discover(
        _semantic_model(""),
        gateway_datasources=[gateway],
    )

    assert result.warnings[-1].code == "GATEWAY_CONNECTION_DETAILS_INVALID"
    assert all(
        source.gateway_datasource_id != "datasource-1" for source in result.sources
    )


def test_calculated_partition_is_not_treated_as_physical_source():
    model = _semantic_model("SUMMARIZE(Sales, Sales[Amount])")
    model.tables[0].partitions[0].source_type = "calculated"

    result = PhysicalSourceDiscoveryService().discover(model)

    assert result.sources == []
    assert result.mappings == []
    assert result.warnings == []


def test_connector_names_in_m_text_and_comments_are_ignored():
    model = _semantic_model(
        """
let
    Description = "Sql.Database(""fake"", ""fake"")",
    // Web.Contents("https://fake.example")
    /* File.Contents("C:\\fake.csv") */
    Source = Sql.Database("real.example", "warehouse")
in
    Source
"""
    )

    result = PhysicalSourceDiscoveryService().discover(model)

    assert result.source_count == 1
    assert result.sources[0].provider == "sqlserver"
    assert result.sources[0].server == "real.example"
