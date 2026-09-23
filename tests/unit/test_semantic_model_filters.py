from app.domain.semantic_model_filters import (
    exclude_auto_date_tables,
    is_auto_date_table,
)
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelRelationship,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)


def test_is_auto_date_table():
    assert is_auto_date_table("LocalDateTable_cbf3fa13-bd1b-43ab-8e76-07ea3b691590")
    assert is_auto_date_table("DateTableTemplate_aa8673b2-0821-4f03-b137-f500b1def215")
    assert not is_auto_date_table("Sales Story")
    assert not is_auto_date_table("DateDimension")


def test_exclude_auto_date_tables_drops_tables_and_their_relationships():
    model = ParsedSemanticModelResponse(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        tables=[
            ParsedSemanticModelTable(name="Sales Story"),
            ParsedSemanticModelTable(name="LocalDateTable_ae43a320-f9ba-4c88-a75c"),
            ParsedSemanticModelTable(name="DateTableTemplate_aa8673b2-0821-4f03"),
        ],
        relationships=[
            ParsedSemanticModelRelationship(
                name="real",
                from_table="Sales Story",
                to_table="Sales Story",
            ),
            ParsedSemanticModelRelationship(
                name="auto",
                from_table="Sales Story",
                to_table="LocalDateTable_ae43a320-f9ba-4c88-a75c",
            ),
        ],
    )

    result = exclude_auto_date_tables(model)

    assert [table.name for table in result.tables] == ["Sales Story"]
    assert [relationship.name for relationship in result.relationships] == ["real"]


def test_exclude_auto_date_tables_returns_model_unchanged_when_nothing_to_drop():
    model = ParsedSemanticModelResponse(
        workspace_id="workspace-1",
        semantic_model_id="model-1",
        tables=[ParsedSemanticModelTable(name="Sales Story")],
    )

    assert exclude_auto_date_tables(model) is model
