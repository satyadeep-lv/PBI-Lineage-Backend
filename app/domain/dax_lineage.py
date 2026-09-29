from collections import defaultdict

from app.schemas.dax_dependency import DaxDependencyAnalysisResponse, DaxObjectReference
from app.schemas.parsed_semantic_model import ParsedSemanticModelResponse
from app.schemas.physical_source import (
    PhysicalDataSource,
    PhysicalSourceDiscoveryResponse,
)


def expression_index(
    semantic_model: ParsedSemanticModelResponse,
) -> dict[str, str]:
    """Map each calculated object's qualified name (casefolded) to its DAX
    expression text, for owners produced by ``DaxDependencyService.analyze``.
    """
    expressions: dict[str, str] = {}
    for table in semantic_model.tables:
        if table.expression:
            expressions[table.name.casefold()] = table.expression
        for column in table.columns:
            if column.expression:
                expressions[f"{table.name}[{column.name}]".casefold()] = (
                    column.expression
                )
        for measure in table.measures:
            if measure.expression:
                expressions[f"{table.name}[{measure.name}]".casefold()] = (
                    measure.expression
                )
    return expressions


def terminal_dependencies(
    owner: DaxObjectReference,
    dax: DaxDependencyAnalysisResponse,
) -> list[tuple[DaxObjectReference, int]]:
    """Walk DAX dependency edges upstream from ``owner`` to its base (non-derived)
    semantic columns/tables, returning each terminal reference with its hop depth.
    """
    predecessors: dict[str, list[DaxObjectReference]] = defaultdict(list)
    for edge in dax.dependencies:
        predecessors[edge.target.qualified_name.casefold()].append(edge.source)

    terminals: dict[tuple[str, str], tuple[DaxObjectReference, int]] = {}

    def walk(
        current: DaxObjectReference,
        depth: int,
        path: frozenset[str],
    ) -> None:
        current_key = current.qualified_name.casefold()
        sources = predecessors.get(current_key, [])
        if not sources:
            if depth > 0:
                terminal_key = (current.object_type, current_key)
                existing = terminals.get(terminal_key)
                if existing is None or depth < existing[1]:
                    terminals[terminal_key] = (current, depth)
            return

        for source in sources:
            source_key = source.qualified_name.casefold()
            if source_key in path:
                continue
            walk(source, depth + 1, path | {source_key})

    owner_key = owner.qualified_name.casefold()
    walk(owner, 0, frozenset({owner_key}))
    return sorted(
        terminals.values(),
        key=lambda item: (
            item[1],
            item[0].qualified_name.casefold(),
            item[0].object_type,
        ),
    )


def physical_sources_by_table(
    physical: PhysicalSourceDiscoveryResponse,
) -> dict[str, list[PhysicalDataSource]]:
    """Group discovered physical sources by the semantic table their partition
    populates, using the query-to-source mappings already produced by
    ``PhysicalSourceDiscoveryService``.
    """
    source_by_id = {source.source_id: source for source in physical.sources}
    sources_by_table: dict[str, dict[str, PhysicalDataSource]] = defaultdict(dict)
    for mapping in physical.mappings:
        table_sources = sources_by_table[mapping.semantic_table.casefold()]
        for source_id in mapping.source_ids:
            source = source_by_id.get(source_id)
            if source is not None:
                table_sources.setdefault(source_id, source)
    return {
        table_name: sorted(values.values(), key=lambda item: item.source_id)
        for table_name, values in sources_by_table.items()
    }
