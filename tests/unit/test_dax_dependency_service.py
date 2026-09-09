from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelMeasure,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)
from app.services.dax_dependency_service import DaxDependencyService


def _model() -> ParsedSemanticModelResponse:
    return ParsedSemanticModelResponse(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        tables=[
            ParsedSemanticModelTable(
                name="Sales",
                columns=[
                    ParsedSemanticModelColumn(
                        name="Amount",
                    ),
                    ParsedSemanticModelColumn(
                        name="Taxed Amount",
                        expression="'Sales'[Amount] * 1.2",
                    ),
                ],
                measures=[
                    ParsedSemanticModelMeasure(
                        name="Total Sales",
                        expression="SUM('Sales'[Amount])",
                    ),
                    ParsedSemanticModelMeasure(
                        name="Sales With Tax",
                        expression="[Total Sales] * 1.2",
                    ),
                ],
            ),
            ParsedSemanticModelTable(
                name="Top Sales",
                expression="FILTER('Sales', 'Sales'[Amount] > 100)",
            ),
        ],
    )


def test_analyze_extracts_measure_column_and_table_dependencies():
    result = DaxDependencyService().analyze(_model())

    edges = {
        (
            edge.source.qualified_name,
            edge.target.qualified_name,
        )
        for edge in result.dependencies
    }

    assert ("Sales[Amount]", "Sales[Total Sales]") in edges
    assert ("Sales[Total Sales]", "Sales[Sales With Tax]") in edges
    assert ("Sales[Amount]", "Sales[Taxed Amount]") in edges
    assert ("Sales", "Top Sales") in edges
    assert result.object_count == 4
    assert result.cycle_count == 0


def test_analyze_ignores_comments_and_string_literals():
    model = _model()
    model.tables[0].measures[
        0
    ].expression = 'IF(TRUE(), "[Fake Measure]", SUM([Amount])) // [Another Fake]'

    result = DaxDependencyService().analyze(model)

    assert not any(
        warning.reference_text in {"[Fake Measure]", "[Another Fake]"}
        for warning in result.warnings
    )


def test_analyze_detects_measure_cycles():
    model = ParsedSemanticModelResponse(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        tables=[
            ParsedSemanticModelTable(
                name="Metrics",
                measures=[
                    ParsedSemanticModelMeasure(
                        name="A",
                        expression="[B] + 1",
                    ),
                    ParsedSemanticModelMeasure(
                        name="B",
                        expression="[A] + 1",
                    ),
                ],
            )
        ],
    )

    result = DaxDependencyService().analyze(model)

    assert result.cycle_count == 1
    assert result.cycles[0].members == ["Metrics[A]", "Metrics[B]"]


def test_analyze_reports_unresolved_references():
    model = _model()
    model.tables[0].measures[0].expression = "[Missing Measure]"

    result = DaxDependencyService().analyze(model)

    assert result.warnings[0].code == "DAX_REFERENCE_UNRESOLVED"
    assert result.warnings[0].reference_text == "[Missing Measure]"
