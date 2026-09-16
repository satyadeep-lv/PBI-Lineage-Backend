"""Shared fixtures for Power AI tests. Not a test module itself."""

from app.schemas.normalized_report_definition import (
    NormalizedReportDefinitionResponse,
    NormalizedReportPage,
    NormalizedReportVisual,
    SemanticModelReference,
    VisualFieldReference,
)
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelMeasure,
    ParsedSemanticModelPartition,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)

WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"
SEMANTIC_MODEL_ID = "22222222-2222-2222-2222-222222222222"
REPORT_ID = "33333333-3333-3333-3333-333333333333"

GROSS_MARGIN_DAX = "DIVIDE([Gross Profit], [Net Sales])"


def sample_semantic_model() -> ParsedSemanticModelResponse:
    return ParsedSemanticModelResponse(
        workspace_id=WORKSPACE_ID,
        semantic_model_id=SEMANTIC_MODEL_ID,
        format="TMDL",
        tables=[
            ParsedSemanticModelTable(
                name="Sales",
                partitions=[
                    ParsedSemanticModelPartition(
                        name="Sales",
                        source_type="m",
                        expression=(
                            'let Source = Sql.Database("sql.example.com", '
                            '"warehouse"), Sales = Source{[Schema="dbo",'
                            'Item="FactSales"]}[Data] in Sales'
                        ),
                    )
                ],
                columns=[
                    ParsedSemanticModelColumn(
                        name="NetSalesAmount",
                        data_type="decimal",
                        source_column="NetSalesAmount",
                    ),
                    ParsedSemanticModelColumn(
                        name="CostAmount",
                        data_type="decimal",
                        source_column="CostAmount",
                    ),
                ],
                measures=[
                    ParsedSemanticModelMeasure(
                        name="Net Sales",
                        source_path="definition/tables/Sales.tmdl",
                        expression="SUM(Sales[NetSalesAmount])",
                    ),
                    ParsedSemanticModelMeasure(
                        name="Gross Profit",
                        source_path="definition/tables/Sales.tmdl",
                        expression="[Net Sales] - SUM(Sales[CostAmount])",
                    ),
                    ParsedSemanticModelMeasure(
                        name="Gross Margin %",
                        source_path="definition/tables/Sales.tmdl",
                        expression=GROSS_MARGIN_DAX,
                    ),
                ],
            ),
        ],
        relationships=[],
    )


def sample_report_definition() -> NormalizedReportDefinitionResponse:
    return NormalizedReportDefinitionResponse(
        workspace_id=WORKSPACE_ID,
        report_id=REPORT_ID,
        format="PBIR",
        semantic_model=SemanticModelReference(
            mode="by_connection",
            semantic_model_id=SEMANTIC_MODEL_ID,
        ),
        pages=[
            NormalizedReportPage(
                name="page1",
                display_name="Overview",
                visuals=[
                    NormalizedReportVisual(
                        id="visual1",
                        internal_name="visual1",
                        title="Margin Card",
                        visual_type="card",
                        field_references=[
                            VisualFieldReference(
                                object_type="measure",
                                table_name="Sales",
                                object_name="Gross Margin %",
                                usage="projection",
                            ),
                        ],
                    )
                ],
                visual_count=1,
            )
        ],
        page_count=1,
        visual_count=1,
        source_part_count=1,
        decoded_json_part_count=1,
        warnings=[],
    )
