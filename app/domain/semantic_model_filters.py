"""Filters for Power BI's own generated model objects.

Power BI Desktop's Auto Date/Time feature silently adds a hidden date table
per date column (``LocalDateTable_<guid>``) plus one template
(``DateTableTemplate_<guid>``). They are calculated tables with no physical
source, so they carry no lineage — but they can easily outnumber the real
tables in a model and drown the useful rows in every explorer dataset.
"""

from app.schemas.parsed_semantic_model import ParsedSemanticModelResponse

AUTO_DATE_TABLE_PREFIXES = (
    "localdatetable_",
    "datetabletemplate_",
)


def is_auto_date_table(table_name: str) -> bool:
    return table_name.casefold().startswith(AUTO_DATE_TABLE_PREFIXES)


def exclude_auto_date_tables(
    model: ParsedSemanticModelResponse,
) -> ParsedSemanticModelResponse:
    """Drop Auto Date/Time tables, and any relationship that used one."""

    kept_tables = [
        table for table in model.tables if not is_auto_date_table(table.name)
    ]

    if len(kept_tables) == len(model.tables):
        return model

    dropped = {
        table.name.casefold()
        for table in model.tables
        if is_auto_date_table(table.name)
    }
    kept_relationships = [
        relationship
        for relationship in model.relationships
        if (relationship.from_table or "").casefold() not in dropped
        and (relationship.to_table or "").casefold() not in dropped
    ]

    return model.model_copy(
        update={
            "tables": kept_tables,
            "relationships": kept_relationships,
        }
    )
