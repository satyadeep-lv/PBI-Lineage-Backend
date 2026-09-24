from app.schemas.gateway import GatewayDatasource
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelExpression,
    ParsedSemanticModelPartition,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)
from app.services.physical_source_service import PhysicalSourceDiscoveryService


def test_entity_partition_resolves_through_shared_expression():
    model = ParsedSemanticModelResponse(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        tables=[
            ParsedSemanticModelTable(
                name="PAYROLL_RECORDS",
                partitions=[
                    ParsedSemanticModelPartition(
                        name="PAYROLL_RECORDS",
                        source_type="entity",
                        mode="directQuery",
                        entity_name="PAYROLL_RECORDS",
                        expression_source=("DirectQuery to AS - NativeQueryReoprt"),
                    )
                ],
            )
        ],
        expressions=[
            ParsedSemanticModelExpression(
                name="DirectQuery to AS - NativeQueryReoprt",
                expression=(
                    "let\n"
                    "Source = AnalysisServices.Database"
                    '("powerbi://api.powerbi.com/v1.0/myorg/DEV", '
                    '"NativeQueryReoprt"),\n'
                    "Cubes = Table.Combine(Source[Data])\n"
                    "in\n"
                    "Cubes"
                ),
            )
        ],
    )

    result = PhysicalSourceDiscoveryService().discover(model)

    assert result.warnings == []
    assert result.source_count == 1
    source = result.sources[0]
    assert source.provider == "analysis_services"
    assert source.server == "powerbi://api.powerbi.com/v1.0/myorg/DEV"
    assert source.database == "NativeQueryReoprt"
    assert source.object_name == "PAYROLL_RECORDS"


def test_table_without_any_partition_still_yields_a_mapping():
    model = ParsedSemanticModelResponse(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        tables=[ParsedSemanticModelTable(name="Orphan")],
    )

    result = PhysicalSourceDiscoveryService().discover(model)

    assert [mapping.semantic_table for mapping in result.mappings] == ["Orphan"]
    assert result.mappings[0].source_ids == []


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


def test_native_query_resolves_database_qualified_object():
    model = _semantic_model(
        """
let
    Source = Sql.Database("sql.example.com", "warehouse"),
    Result = Value.NativeQuery(
        Source,
        "SELECT * FROM Analytics.dbo.FactSales"
    )
in
    Result
"""
    )

    result = PhysicalSourceDiscoveryService().discover(model)

    assert result.source_count == 1
    source = result.sources[0]
    assert source.database == "Analytics"
    assert source.schema_name == "dbo"
    assert source.object_name == "FactSales"


def test_kind_based_navigation_resolves_database_schema_and_table():
    model = _semantic_model(
        """
let
    Source = Sql.Database("sql.example.com"),
    Database = Source{[Name="Analytics",Kind="Database"]}[Data],
    Schema = Database{[Name="dbo",Kind="Schema"]}[Data],
    Table = Schema{[Name="FactSales",Kind="Table"]}[Data]
in
    Table
"""
    )

    result = PhysicalSourceDiscoveryService().discover(model)

    assert result.source_count == 1
    source = result.sources[0]
    assert source.database == "Analytics"
    assert source.schema_name == "dbo"
    assert source.object_name == "FactSales"
    assert source.object_kind == "table"


def test_kind_based_navigation_detects_view():
    model = _semantic_model(
        """
let
    Source = Sql.Database("sql.example.com"),
    Database = Source{[Name="Analytics",Kind="Database"]}[Data],
    Schema = Database{[Name="dbo",Kind="Schema"]}[Data],
    View = Schema{[Name="VwSalesSummary",Kind="View"]}[Data]
in
    View
"""
    )

    result = PhysicalSourceDiscoveryService().discover(model)

    assert result.source_count == 1
    source = result.sources[0]
    assert source.object_name == "VwSalesSummary"
    assert source.object_kind == "view"


def test_native_sql_navigation_leaves_object_kind_unresolved():
    model = _semantic_model(
        """
let
    Source = Sql.Database("sql.example.com", "warehouse"),
    Result = Value.NativeQuery(
        Source,
        "SELECT * FROM Analytics.dbo.FactSales"
    )
in
    Result
"""
    )

    result = PhysicalSourceDiscoveryService().discover(model)

    assert result.source_count == 1
    assert result.sources[0].object_kind is None


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


def test_gateway_sso_enabled_is_matched_to_query_source():
    model = _semantic_model('Snowflake.Databases("account.snowflakecomputing.com")')
    gateway = GatewayDatasource(
        id="datasource-1",
        gateway_id="gateway-1",
        datasource_type="Snowflake",
        connection_details='{"server":"account.snowflakecomputing.com"}',
        sso_enabled=True,
    )

    result = PhysicalSourceDiscoveryService().discover(
        model,
        gateway_datasources=[gateway],
    )

    query_source = next(
        source for source in result.sources if source.provider == "snowflake"
    )
    assert query_source.gateway_datasource_id == "datasource-1"
    assert query_source.sso_enabled is True


def test_gateway_only_source_carries_sso_enabled():
    gateway = GatewayDatasource(
        id="datasource-1",
        gateway_id="gateway-1",
        datasource_type="Snowflake",
        connection_details='{"server":"account.snowflakecomputing.com"}',
        sso_enabled=False,
    )

    result = PhysicalSourceDiscoveryService().discover(
        _semantic_model(""),
        gateway_datasources=[gateway],
    )

    gateway_source = next(
        source
        for source in result.sources
        if source.gateway_datasource_id == "datasource-1"
    )
    assert gateway_source.sso_enabled is False


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


def test_snowflake_second_argument_is_a_warehouse_not_a_database():
    # `Snowflake.Databases(server, warehouse)` -- reading COMPUTE_WH as the
    # database mislabels every table whose database is only reachable through
    # the navigation step.
    model = _semantic_model(
        """
let
    Source = Snowflake.Databases("acme.snowflakecomputing.com","COMPUTE_WH"),
    POC_DB_Database = Source{[Name="POC_DB",Kind="Database"]}[Data],
    HR_Schema = POC_DB_Database{[Name="HUMAN_RESOURCES",Kind="Schema"]}[Data],
    EMPLOYEES_Table = HR_Schema{[Name="EMPLOYEES",Kind="Table"]}[Data]
in
    EMPLOYEES_Table
"""
    )

    result = PhysicalSourceDiscoveryService().discover(model)

    source = next(source for source in result.sources if source.provider == "snowflake")
    assert source.database == "POC_DB"
    assert source.warehouse == "COMPUTE_WH"
    assert source.schema_name == "HUMAN_RESOURCES"
    assert source.object_name == "EMPLOYEES"


def test_navigated_database_is_used_when_a_native_query_omits_it():
    # A two-part name in the SQL leaves the database implicit, so it has to be
    # taken from the `Kind="Database"` navigation step.
    model = _semantic_model(
        """
let
    Source = Snowflake.Databases("acme.snowflakecomputing.com","COMPUTE_WH"),
    POC_DB_Database = Source{[Name="POC_DB",Kind="Database"]}[Data],
    RunQuery = Value.NativeQuery(
        POC_DB_Database,
        "SELECT EMPLOYEE_ID FROM HUMAN_RESOURCES.EMPLOYEES"
    )
in
    RunQuery
"""
    )

    result = PhysicalSourceDiscoveryService().discover(model)

    source = next(source for source in result.sources if source.provider == "snowflake")
    assert source.database == "POC_DB"
    assert source.schema_name == "HUMAN_RESOURCES"
    assert source.object_name == "EMPLOYEES"


def test_sql_database_second_argument_is_still_a_database():
    model = _semantic_model(
        'Sql.Database("sql.example.com", "WAREHOUSE")'
        '{[Schema="dbo",Item="FactSales"]}[Data]'
    )

    result = PhysicalSourceDiscoveryService().discover(model)

    source = next(source for source in result.sources if source.provider == "sqlserver")
    assert source.database == "WAREHOUSE"
    assert source.warehouse is None
