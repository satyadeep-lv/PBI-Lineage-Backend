"""Exact lookup of a named object inside an already-authorized model.

Screens name objects two ways -- a bare `Total Revenue`, or a qualified
`Sales[Total Revenue]` -- and fuzzy search scores the qualified form as a mere
substring match, which ties with unrelated objects. An exact match is tried
first so a precise name always resolves to exactly that object.
"""

import re

from app.ai.models.context import ResolvedObject
from app.schemas.parsed_semantic_model import ParsedSemanticModelResponse

_QUALIFIED_NAME = re.compile(
    r"^\s*'?(?P<table>[^'\[\]]+?)'?\s*\[(?P<name>[^\]]+)\]\s*$"
)
_BRACKETED_NAME = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*$")

_TYPE_PRIORITY = {"measure": 0, "calculated_column": 1, "column": 2, "table": 3}


def split_qualified_name(value: str) -> tuple[str | None, str]:
    """`'Sales'[Net]` -> ("Sales", "Net"); `[Net]` and `Net` -> (None, "Net")."""
    qualified = _QUALIFIED_NAME.match(value)
    if qualified:
        return qualified.group("table").strip(), qualified.group("name").strip()

    bracketed = _BRACKETED_NAME.match(value)
    if bracketed:
        return None, bracketed.group("name").strip()

    return None, value.strip()


def find_semantic_object(
    model: ParsedSemanticModelResponse,
    name: str,
    *,
    table_name: str | None = None,
    object_type: str | None = None,
) -> ResolvedObject | None:
    """The one object `name` identifies exactly, or None.

    A declared `object_type` breaks ties between a measure and a column of
    the same name; otherwise measures win, matching how Power BI resolves an
    unqualified `[Name]` reference.
    """
    parsed_table, object_name = split_qualified_name(name)
    wanted_table = (table_name or parsed_table or "").casefold()
    wanted_name = object_name.casefold()

    if not wanted_name:
        return None

    candidates: list[ResolvedObject] = []

    for table in model.tables:
        if wanted_table and table.name.casefold() != wanted_table:
            continue

        for measure in table.measures:
            if measure.name.casefold() == wanted_name:
                candidates.append(_object("measure", table.name, measure.name))

        for column in table.columns:
            if column.name.casefold() == wanted_name:
                kind = "calculated_column" if column.expression else "column"
                candidates.append(_object(kind, table.name, column.name))

        if not parsed_table and table.name.casefold() == wanted_name:
            candidates.append(_object("table", table.name, table.name))

    if not candidates:
        return None

    if object_type:
        typed = [
            item
            for item in candidates
            if item.object_type == object_type
            or (object_type == "column" and item.object_type == "calculated_column")
        ]
        candidates = typed or candidates

    candidates.sort(key=lambda item: _TYPE_PRIORITY[item.object_type])
    best = [
        item
        for item in candidates
        if _TYPE_PRIORITY[item.object_type] == _TYPE_PRIORITY[candidates[0].object_type]
    ]

    if len(best) > 1:
        # `Date` in three tables is a question, not an answer; the caller's
        # fuzzy search reports the ambiguity instead of a silent pick.
        return None

    return best[0]


def _object(object_type: str, table_name: str, object_name: str) -> ResolvedObject:
    qualified = table_name if object_type == "table" else f"{table_name}[{object_name}]"
    return ResolvedObject(
        object_type=object_type,
        table_name=table_name,
        object_name=object_name,
        qualified_name=qualified,
    )
