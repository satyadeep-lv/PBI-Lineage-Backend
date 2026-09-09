from __future__ import annotations

from typing import Any, Literal

from app.schemas.normalized_report_definition import (
    VisualFieldReference,
)

FieldUsage = Literal[
    "projection",
    "sort",
    "filter",
]


def extract_visual_field_references(
    visual_definition: dict[str, Any],
) -> list[VisualFieldReference]:
    """
    Extract semantic-model object references used by a PBIR visual.

    Extracts:
    - query projections
    - sort fields
    - visual-level filter fields

    Intentionally does not extract:
    - filter values
    - slicer selections
    - literal values
    - formatting/configuration literals
    """

    references: list[VisualFieldReference] = []

    visual = visual_definition.get("visual")

    if not isinstance(visual, dict):
        return []

    query = visual.get("query")

    if isinstance(query, dict):
        references.extend(_extract_projection_references(query))

        references.extend(_extract_sort_references(query))

    #
    # PBIR visual-level filters are stored at the
    # visual container/root level.
    #
    filter_config = visual_definition.get("filterConfig")

    if isinstance(filter_config, dict):
        references.extend(_extract_filter_references(filter_config))

    return _deduplicate_references(references)


def _extract_projection_references(
    query: dict[str, Any],
) -> list[VisualFieldReference]:
    references: list[VisualFieldReference] = []

    query_state = query.get("queryState")

    if not isinstance(query_state, dict):
        return references

    for role, role_definition in query_state.items():
        if not isinstance(
            role_definition,
            dict,
        ):
            continue

        projections = role_definition.get("projections")

        if not isinstance(projections, list):
            continue

        for projection in projections:
            if not isinstance(projection, dict):
                continue

            field = projection.get("field")

            if not isinstance(field, dict):
                continue

            references.extend(
                _parse_field_expression(
                    field=field,
                    usage="projection",
                    role=str(role),
                    query_ref=_optional_string(projection.get("queryRef")),
                    active=_optional_bool(projection.get("active")),
                )
            )

    return references


def _extract_sort_references(
    query: dict[str, Any],
) -> list[VisualFieldReference]:
    references: list[VisualFieldReference] = []

    sort_definition = query.get("sortDefinition")

    if not isinstance(
        sort_definition,
        dict,
    ):
        return references

    sort_items = sort_definition.get("sort")

    if not isinstance(sort_items, list):
        return references

    for sort_item in sort_items:
        if not isinstance(sort_item, dict):
            continue

        field = sort_item.get("field")

        if not isinstance(field, dict):
            continue

        references.extend(
            _parse_field_expression(
                field=field,
                usage="sort",
            )
        )

    return references


def _extract_filter_references(
    filter_config: dict[str, Any],
) -> list[VisualFieldReference]:
    references: list[VisualFieldReference] = []

    filters = filter_config.get("filters")

    if not isinstance(filters, list):
        return references

    for filter_item in filters:
        if not isinstance(
            filter_item,
            dict,
        ):
            continue

        #
        # Important:
        #
        # Only inspect the field metadata.
        #
        # Do NOT recursively parse the complete
        # filter object because it can contain
        # selected values/literals.
        #
        field = filter_item.get("field")

        if not isinstance(field, dict):
            continue

        references.extend(
            _parse_field_expression(
                field=field,
                usage="filter",
            )
        )

    return references


def _parse_field_expression(
    field: dict[str, Any],
    usage: FieldUsage,
    role: str | None = None,
    query_ref: str | None = None,
    active: bool | None = None,
    aggregation_function: (int | str | None) = None,
) -> list[VisualFieldReference]:
    """
    Parse PBIR semantic expressions.

    Supported:
    - Column
    - Measure
    - Aggregation
    - Hierarchy
    - HierarchyLevel

    Unknown expression wrappers are traversed
    defensively without inspecting Literal values.
    """

    column = field.get("Column")

    if isinstance(column, dict):
        reference = _parse_column(
            column=column,
            usage=usage,
            role=role,
            query_ref=query_ref,
            active=active,
            aggregation_function=(aggregation_function),
        )

        return [reference] if reference is not None else []

    measure = field.get("Measure")

    if isinstance(measure, dict):
        reference = _parse_measure(
            measure=measure,
            usage=usage,
            role=role,
            query_ref=query_ref,
            active=active,
        )

        return [reference] if reference is not None else []

    aggregation = field.get("Aggregation")

    if isinstance(aggregation, dict):
        expression = aggregation.get("Expression")

        if not isinstance(expression, dict):
            return []

        return _parse_field_expression(
            field=expression,
            usage=usage,
            role=role,
            query_ref=query_ref,
            active=active,
            aggregation_function=(aggregation.get("Function")),
        )

    hierarchy_level = field.get("HierarchyLevel")

    if isinstance(
        hierarchy_level,
        dict,
    ):
        reference = _parse_hierarchy_level(
            hierarchy_level=hierarchy_level,
            usage=usage,
            role=role,
            query_ref=query_ref,
            active=active,
        )

        return [reference] if reference is not None else []

    hierarchy = field.get("Hierarchy")

    if isinstance(hierarchy, dict):
        reference = _parse_hierarchy(
            hierarchy=hierarchy,
            usage=usage,
            role=role,
            query_ref=query_ref,
            active=active,
        )

        return [reference] if reference is not None else []

    #
    # Handle semantic-expression wrappers that
    # contain Column/Measure deeper inside them.
    #
    references: list[VisualFieldReference] = []

    for key, value in field.items():
        #
        # Never inspect literal values.
        #
        if key == "Literal":
            continue

        if isinstance(value, dict):
            references.extend(
                _parse_field_expression(
                    field=value,
                    usage=usage,
                    role=role,
                    query_ref=query_ref,
                    active=active,
                    aggregation_function=(aggregation_function),
                )
            )

        elif isinstance(value, list):
            for item in value:
                if not isinstance(item, dict):
                    continue

                references.extend(
                    _parse_field_expression(
                        field=item,
                        usage=usage,
                        role=role,
                        query_ref=query_ref,
                        active=active,
                        aggregation_function=(aggregation_function),
                    )
                )

    return references


def _parse_column(
    column: dict[str, Any],
    usage: FieldUsage,
    role: str | None,
    query_ref: str | None,
    active: bool | None,
    aggregation_function: (int | str | None),
) -> VisualFieldReference | None:
    table_name = _extract_entity(column.get("Expression"))

    object_name = _optional_string(column.get("Property"))

    if table_name is None and object_name is None:
        return None

    return VisualFieldReference(
        object_type="column",
        table_name=table_name,
        object_name=object_name,
        usage=usage,
        role=role,
        query_ref=query_ref,
        active=active,
        aggregation_function=(aggregation_function),
    )


def _parse_measure(
    measure: dict[str, Any],
    usage: FieldUsage,
    role: str | None,
    query_ref: str | None,
    active: bool | None,
) -> VisualFieldReference | None:
    table_name = _extract_entity(measure.get("Expression"))

    object_name = _optional_string(measure.get("Property"))

    if table_name is None and object_name is None:
        return None

    return VisualFieldReference(
        object_type="measure",
        table_name=table_name,
        object_name=object_name,
        usage=usage,
        role=role,
        query_ref=query_ref,
        active=active,
    )


def _parse_hierarchy(
    hierarchy: dict[str, Any],
    usage: FieldUsage,
    role: str | None,
    query_ref: str | None,
    active: bool | None,
) -> VisualFieldReference | None:
    table_name = _extract_entity(hierarchy.get("Expression"))

    hierarchy_name = _optional_string(hierarchy.get("Hierarchy"))

    if table_name is None and hierarchy_name is None:
        return None

    return VisualFieldReference(
        object_type="hierarchy",
        table_name=table_name,
        object_name=hierarchy_name,
        hierarchy_name=hierarchy_name,
        usage=usage,
        role=role,
        query_ref=query_ref,
        active=active,
    )


def _parse_hierarchy_level(
    hierarchy_level: dict[str, Any],
    usage: FieldUsage,
    role: str | None,
    query_ref: str | None,
    active: bool | None,
) -> VisualFieldReference | None:
    expression = hierarchy_level.get("Expression")

    table_name: str | None = None
    hierarchy_name: str | None = None

    if isinstance(expression, dict):
        hierarchy = expression.get("Hierarchy")

        if isinstance(hierarchy, dict):
            table_name = _extract_entity(hierarchy.get("Expression"))

            hierarchy_name = _optional_string(hierarchy.get("Hierarchy"))

    level_name = _optional_string(hierarchy_level.get("Level"))

    if table_name is None and hierarchy_name is None and level_name is None:
        return None

    return VisualFieldReference(
        object_type="hierarchy_level",
        table_name=table_name,
        object_name=level_name,
        hierarchy_name=hierarchy_name,
        level_name=level_name,
        usage=usage,
        role=role,
        query_ref=query_ref,
        active=active,
    )


def _extract_entity(
    expression: Any,
) -> str | None:
    """
    Extract SourceRef.Entity from a PBIR
    semantic expression.

    queryRef is deliberately not used for
    semantic object identity.
    """

    if isinstance(expression, dict):
        source_ref = expression.get("SourceRef")

        if isinstance(source_ref, dict):
            entity = source_ref.get("Entity")

            if isinstance(entity, str) and entity:
                return entity

        for value in expression.values():
            entity = _extract_entity(value)

            if entity is not None:
                return entity

    elif isinstance(expression, list):
        for item in expression:
            entity = _extract_entity(item)

            if entity is not None:
                return entity

    return None


def _deduplicate_references(
    references: list[VisualFieldReference],
) -> list[VisualFieldReference]:
    result: list[VisualFieldReference] = []

    seen: set[tuple[Any, ...]] = set()

    for reference in references:
        key = (
            reference.object_type,
            reference.table_name,
            reference.object_name,
            reference.usage,
            reference.role,
            reference.query_ref,
            reference.active,
            reference.hierarchy_name,
            reference.level_name,
            reference.aggregation_function,
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(reference)

    return result


def _optional_string(
    value: Any,
) -> str | None:
    if isinstance(value, str):
        return value

    return None


def _optional_bool(
    value: Any,
) -> bool | None:
    if isinstance(value, bool):
        return value

    return None
