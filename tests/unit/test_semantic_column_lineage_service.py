import pytest

from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelMeasure,
    ParsedSemanticModelPartition,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)
from app.schemas.xmla_metadata import (
    XmlaCalcDependency,
    XmlaSemanticModelColumn,
    XmlaSemanticModelMeasure,
    XmlaSemanticModelMetadataResponse,
    XmlaSemanticModelPartition,
    XmlaSemanticModelTable,
)
from app.services.semantic_column_lineage_service import SemanticColumnLineageService
from app.services.xmla_metadata_service import XmlaMetadataService

_NATIVE_QUERY_EXPRESSION = """
let
    Source = Sql.Database("sql.example.com", "warehouse"),
    Result = Value.NativeQuery(
        Source,
        "SELECT s.SalesAmount AS Amount, s.Region FROM dbo.Sales s"
    )
in
    Result
"""


def _model() -> ParsedSemanticModelResponse:
    return ParsedSemanticModelResponse(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        tables=[
            ParsedSemanticModelTable(
                name="Sales",
                partitions=[
                    ParsedSemanticModelPartition(
                        name="Sales",
                        source_type="m",
                        expression=_NATIVE_QUERY_EXPRESSION,
                    )
                ],
                columns=[
                    ParsedSemanticModelColumn(name="Amount", source_column="Amount"),
                    ParsedSemanticModelColumn(name="Territory"),
                ],
                measures=[
                    ParsedSemanticModelMeasure(
                        name="Total Sales",
                        expression="SUM(Sales[Amount])",
                    ),
                ],
            ),
        ],
    )


def test_resolves_measure_to_native_query_aliased_column():
    response = SemanticColumnLineageService().build_lineage_from_model(_model())

    row = next(
        row
        for row in response.rows
        if row.semantic_object_name == "Total Sales"
        and row.referenced_semantic_column == "Amount"
    )

    assert row.dependency_depth == 1
    assert row.is_direct_dependency is True
    assert len(row.physical_columns) == 1
    physical = row.physical_columns[0]
    assert physical.resolution_method == "native_query_select"
    assert physical.column_name == "SalesAmount"
    assert physical.fully_qualified_name == "warehouse.dbo.Sales.SalesAmount"


def test_falls_back_to_same_name_assumed_when_not_aliased_in_native_query():
    model = _model()
    model.tables[0].measures.append(
        ParsedSemanticModelMeasure(
            name="Territory Count",
            expression="DISTINCTCOUNT(Sales[Territory])",
        )
    )

    response = SemanticColumnLineageService().build_lineage_from_model(model)

    row = next(
        row
        for row in response.rows
        if row.semantic_object_name == "Territory Count"
        and row.referenced_semantic_column == "Territory"
    )

    assert len(row.physical_columns) == 1
    physical = row.physical_columns[0]
    assert physical.resolution_method == "same_name_assumed"
    assert physical.column_name == "Territory"


def test_computed_native_query_column_resolves_to_every_physical_column():
    model = ParsedSemanticModelResponse(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        tables=[
            ParsedSemanticModelTable(
                name="Employee",
                partitions=[
                    ParsedSemanticModelPartition(
                        name="Employee",
                        source_type="m",
                        expression="""
let
    Source = Sql.Database("sql.example.com", "warehouse"),
    Result = Value.NativeQuery(
        Source,
        "SELECT FIRST_NAME || ' ' || LAST_NAME AS FullName FROM dbo.Employee"
    )
in
    Result
""",
                    )
                ],
                columns=[
                    ParsedSemanticModelColumn(name="FullName"),
                ],
                measures=[
                    ParsedSemanticModelMeasure(
                        name="Employee Count",
                        expression="DISTINCTCOUNT(Employee[FullName])",
                    ),
                ],
            ),
        ],
    )

    response = SemanticColumnLineageService().build_lineage_from_model(model)

    row = next(
        row
        for row in response.rows
        if row.semantic_object_name == "Employee Count"
        and row.referenced_semantic_column == "FullName"
    )

    assert [c.column_name for c in row.physical_columns] == [
        "FIRST_NAME",
        "LAST_NAME",
    ]
    assert all(
        c.resolution_method == "native_query_select" for c in row.physical_columns
    )
    assert row.physical_columns[0].fully_qualified_name == (
        "warehouse.dbo.Employee.FIRST_NAME"
    )


@pytest.mark.asyncio
async def test_build_lineage_from_xmla_resolves_measure_via_calc_dependency(
    monkeypatch,
):
    metadata = XmlaSemanticModelMetadataResponse(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        xmla_endpoint="powerbi://api.powerbi.com/v1.0/myorg/Sales",
        table_count=1,
        column_count=1,
        measure_count=1,
        relationship_count=0,
        hierarchy_count=0,
        partition_count=1,
        tables=[
            XmlaSemanticModelTable(
                name="Sales",
                columns=[
                    XmlaSemanticModelColumn(name="Amount", source_column="Amount"),
                ],
                measures=[
                    XmlaSemanticModelMeasure(
                        name="Total Sales",
                        expression="SUM(Sales[Amount])",
                    ),
                ],
                partitions=[
                    XmlaSemanticModelPartition(
                        name="Sales",
                        mode="Import",
                        source_type="M",
                        expression=(
                            'let Source = Sql.Database("sql.example.com",'
                            ' "warehouse"), Result = Value.NativeQuery(Source,'
                            ' "SELECT s.SalesAmount AS Amount FROM dbo.Sales s")'
                            " in Result"
                        ),
                    )
                ],
            ),
        ],
        calc_dependencies=[
            XmlaCalcDependency(
                object_type="MEASURE",
                table="Sales",
                object="Total Sales",
                expression="SUM(Sales[Amount])",
                referenced_object_type="COLUMN",
                referenced_table="Sales",
                referenced_object="Amount",
            ),
        ],
    )

    async def fake_get_metadata(self, **kwargs) -> XmlaSemanticModelMetadataResponse:
        assert kwargs["workspace_id"] == "workspace-1"
        assert kwargs["semantic_model_id"] == "model-1"
        assert kwargs["access_token"] == "token"
        return metadata

    monkeypatch.setattr(XmlaMetadataService, "get_metadata", fake_get_metadata)

    response = await SemanticColumnLineageService().build_lineage_from_xmla(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        access_token="token",
    )

    row = next(
        row
        for row in response.rows
        if row.semantic_object_name == "Total Sales"
        and row.referenced_semantic_column == "Amount"
    )

    assert row.dependency_depth == 1
    assert len(row.physical_columns) == 1
    physical = row.physical_columns[0]
    assert physical.resolution_method == "native_query_select"
    assert physical.column_name == "SalesAmount"
    assert physical.fully_qualified_name == "warehouse.dbo.Sales.SalesAmount"
    assert response.warnings == []


def test_object_and_row_counts():
    response = SemanticColumnLineageService().build_lineage_from_model(_model())

    assert response.object_count == 1
    assert response.row_count == len(response.rows)
    assert response.workspace_id == "workspace-1"
    assert response.semantic_model_id == "model-1"
