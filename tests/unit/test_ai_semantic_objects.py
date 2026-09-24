import pytest

from app.ai.context.semantic_objects import find_semantic_object, split_qualified_name
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelMeasure,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)


def _model() -> ParsedSemanticModelResponse:
    return ParsedSemanticModelResponse(
        workspace_id="ws",
        semantic_model_id="model",
        tables=[
            ParsedSemanticModelTable(
                name="Sales",
                columns=[
                    ParsedSemanticModelColumn(name="Date"),
                    ParsedSemanticModelColumn(name="Margin", expression="1"),
                ],
                measures=[ParsedSemanticModelMeasure(name="Total Revenue")],
            ),
            ParsedSemanticModelTable(
                name="Calendar",
                columns=[ParsedSemanticModelColumn(name="Date")],
            ),
        ],
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Sales[Total Revenue]", ("Sales", "Total Revenue")),
        ("'Sales Fact'[Net]", ("Sales Fact", "Net")),
        ("[Total Revenue]", (None, "Total Revenue")),
        ("Total Revenue", (None, "Total Revenue")),
    ],
)
def test_split_qualified_name(value, expected):
    assert split_qualified_name(value) == expected


def test_the_qualified_form_screens_send_resolves_exactly():
    # Measure impact sends `Table[Measure]`, which fuzzy search only scored
    # as a substring match.
    found = find_semantic_object(_model(), "sales[total revenue]")

    assert found is not None
    assert found.object_type == "measure"
    assert found.qualified_name == "Sales[Total Revenue]"


def test_a_calculated_column_and_a_table_are_told_apart():
    model = _model()

    assert find_semantic_object(model, "Margin").object_type == "calculated_column"
    assert find_semantic_object(model, "Calendar").object_type == "table"


def test_a_column_name_in_several_tables_is_not_silently_picked():
    model = _model()

    assert find_semantic_object(model, "Date") is None
    assert find_semantic_object(model, "Calendar[Date]").table_name == "Calendar"
    assert (
        find_semantic_object(model, "Date", table_name="Sales").qualified_name
        == "Sales[Date]"
    )


def test_an_unknown_name_resolves_to_nothing():
    assert find_semantic_object(_model(), "Nope") is None
