import re
from dataclasses import dataclass

from app.domain.graph_algorithms import strongly_connected_components
from app.schemas.dax_dependency import (
    DaxDependencyAnalysisResponse,
    DaxDependencyCycle,
    DaxDependencyEdge,
    DaxDependencyWarning,
    DaxObjectReference,
)
from app.schemas.parsed_semantic_model import ParsedSemanticModelResponse

_QUALIFIED_REFERENCE = re.compile(
    r"(?P<table>'(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_ .]*)"
    r"\s*\[(?P<object>(?:[^\]]|\]\])+)\]"
)
_UNQUALIFIED_REFERENCE = re.compile(
    r"(?<![A-Za-z0-9_'\]])\[(?P<object>(?:[^\]]|\]\])+)\]"
)
_QUOTED_TABLE = re.compile(r"'(?P<table>(?:[^']|'')+)'(?!\s*\[)")


@dataclass(frozen=True)
class _ExpressionOwner:
    reference: DaxObjectReference
    expression: str


class DaxDependencyService:
    def analyze(
        self,
        semantic_model: ParsedSemanticModelResponse,
    ) -> DaxDependencyAnalysisResponse:
        symbols = _DaxSymbols(semantic_model)
        owners = symbols.expression_owners()
        dependencies: list[DaxDependencyEdge] = []
        warnings: list[DaxDependencyWarning] = []
        seen_edges: set[tuple[str, str]] = set()

        for owner in owners:
            for reference_text, table_name, object_name in self._extract_references(
                owner.expression
            ):
                resolved = symbols.resolve(
                    table_name=table_name,
                    object_name=object_name,
                    current_table=owner.reference.table_name,
                )

                if resolved is None:
                    warnings.append(
                        DaxDependencyWarning(
                            code="DAX_REFERENCE_UNRESOLVED",
                            message="DAX reference could not be resolved.",
                            object_name=owner.reference.qualified_name,
                            reference_text=reference_text,
                        )
                    )
                    continue

                edge_key = (
                    resolved.qualified_name.casefold(),
                    owner.reference.qualified_name.casefold(),
                )

                if edge_key in seen_edges:
                    continue

                seen_edges.add(edge_key)
                dependencies.append(
                    DaxDependencyEdge(
                        source=resolved,
                        target=owner.reference,
                        reference_text=reference_text,
                    )
                )

            for reference_text, table_name in self._extract_table_references(
                owner.expression,
                symbols.table_names,
            ):
                resolved = symbols.resolve_table(table_name)

                if resolved is None:
                    continue

                edge_key = (
                    resolved.qualified_name.casefold(),
                    owner.reference.qualified_name.casefold(),
                )

                if edge_key in seen_edges:
                    continue

                seen_edges.add(edge_key)
                dependencies.append(
                    DaxDependencyEdge(
                        source=resolved,
                        target=owner.reference,
                        reference_text=reference_text,
                    )
                )

        dependencies.sort(
            key=lambda edge: (
                edge.target.qualified_name.casefold(),
                edge.source.qualified_name.casefold(),
            )
        )
        objects = symbols.calculated_objects()
        cycles = self._find_cycles(objects, dependencies)

        return DaxDependencyAnalysisResponse(
            workspace_id=semantic_model.workspace_id,
            semantic_model_id=semantic_model.semantic_model_id,
            objects=objects,
            dependencies=dependencies,
            cycles=cycles,
            warnings=warnings,
            object_count=len(objects),
            dependency_count=len(dependencies),
            cycle_count=len(cycles),
        )

    @staticmethod
    def _extract_references(
        expression: str,
    ) -> list[tuple[str, str | None, str]]:
        cleaned = _strip_dax_comments_and_strings(expression)
        references: list[tuple[str, str | None, str]] = []
        occupied: list[tuple[int, int]] = []

        for match in _QUALIFIED_REFERENCE.finditer(cleaned):
            table_name = _clean_dax_identifier(match.group("table"))
            object_name = match.group("object").replace("]]", "]").strip()
            references.append((match.group(0), table_name, object_name))
            occupied.append(match.span())

        for match in _UNQUALIFIED_REFERENCE.finditer(cleaned):
            if any(start <= match.start() < end for start, end in occupied):
                continue

            object_name = match.group("object").replace("]]", "]").strip()
            references.append((match.group(0), None, object_name))

        return references

    @staticmethod
    def _extract_table_references(
        expression: str,
        table_names: list[str],
    ) -> list[tuple[str, str]]:
        cleaned = _strip_dax_comments_and_strings(expression)
        references: list[tuple[str, str]] = []
        seen: set[str] = set()

        for match in _QUOTED_TABLE.finditer(cleaned):
            table_name = match.group("table").replace("''", "'")
            key = table_name.casefold()

            if key not in seen:
                seen.add(key)
                references.append((match.group(0), table_name))

        for table_name in table_names:
            if table_name.casefold() in seen:
                continue

            pattern = re.compile(
                rf"(?<![A-Za-z0-9_']){re.escape(table_name)}"
                r"(?![A-Za-z0-9_']|\s*\[|\s*\()",
                re.IGNORECASE,
            )
            match = pattern.search(cleaned)

            if match:
                seen.add(table_name.casefold())
                references.append((match.group(0), table_name))

        return references

    @staticmethod
    def _find_cycles(
        objects: list[DaxObjectReference],
        dependencies: list[DaxDependencyEdge],
    ) -> list[DaxDependencyCycle]:
        object_ids = {
            item.qualified_name.casefold(): item.qualified_name for item in objects
        }
        adjacency: dict[str, set[str]] = {object_id: set() for object_id in object_ids}

        for edge in dependencies:
            source = edge.source.qualified_name.casefold()
            target = edge.target.qualified_name.casefold()

            if source in object_ids and target in object_ids:
                adjacency[source].add(target)

        cycles: list[DaxDependencyCycle] = []

        for component in strongly_connected_components(adjacency):
            has_self_loop = (
                len(component) == 1
                and next(iter(component)) in adjacency[next(iter(component))]
            )

            if len(component) > 1 or has_self_loop:
                cycles.append(
                    DaxDependencyCycle(
                        members=sorted(
                            (object_ids[item] for item in component),
                            key=str.casefold,
                        )
                    )
                )

        cycles.sort(key=lambda cycle: cycle.members[0].casefold())
        return cycles


class _DaxSymbols:
    def __init__(
        self,
        semantic_model: ParsedSemanticModelResponse,
    ) -> None:
        self.semantic_model = semantic_model
        self.table_names = [table.name for table in semantic_model.tables]
        self.tables: dict[str, DaxObjectReference] = {}
        self.columns: dict[tuple[str, str], DaxObjectReference] = {}
        self.measures: dict[tuple[str, str], DaxObjectReference] = {}
        self.measures_by_name: dict[str, list[DaxObjectReference]] = {}
        self._owners: list[_ExpressionOwner] = []
        self._index()

    def _index(self) -> None:
        for table in self.semantic_model.tables:
            table_reference = _reference(
                "calculated_table" if table.expression else "table",
                table.name,
                table.name,
            )
            self.tables[table.name.casefold()] = table_reference

            if table.expression:
                self._owners.append(_ExpressionOwner(table_reference, table.expression))

            for column in table.columns:
                column_reference = _reference(
                    "calculated_column" if column.expression else "column",
                    table.name,
                    column.name,
                )
                self.columns[(table.name.casefold(), column.name.casefold())] = (
                    column_reference
                )

                if column.expression:
                    self._owners.append(
                        _ExpressionOwner(column_reference, column.expression)
                    )

            for measure in table.measures:
                measure_reference = _reference(
                    "measure",
                    table.name,
                    measure.name,
                )
                self.measures[(table.name.casefold(), measure.name.casefold())] = (
                    measure_reference
                )
                self.measures_by_name.setdefault(
                    measure.name.casefold(),
                    [],
                ).append(measure_reference)

                if measure.expression:
                    self._owners.append(
                        _ExpressionOwner(measure_reference, measure.expression)
                    )

    def expression_owners(self) -> list[_ExpressionOwner]:
        return list(self._owners)

    def calculated_objects(self) -> list[DaxObjectReference]:
        return sorted(
            (owner.reference for owner in self._owners),
            key=lambda item: item.qualified_name.casefold(),
        )

    def resolve(
        self,
        *,
        table_name: str | None,
        object_name: str,
        current_table: str | None,
    ) -> DaxObjectReference | None:
        object_key = object_name.casefold()

        if table_name:
            key = (table_name.casefold(), object_key)
            measure = self.measures.get(key)
            column = self.columns.get(key)
            return measure or column

        measures = self.measures_by_name.get(object_key, [])

        if len(measures) == 1:
            return measures[0]

        if current_table:
            return self.columns.get((current_table.casefold(), object_key))

        return None

    def resolve_table(
        self,
        table_name: str,
    ) -> DaxObjectReference | None:
        return self.tables.get(table_name.casefold())


def _reference(
    object_type: str,
    table_name: str,
    object_name: str,
) -> DaxObjectReference:
    qualified_name = (
        table_name
        if object_type in {"table", "calculated_table"}
        else f"{table_name}[{object_name}]"
    )
    return DaxObjectReference(
        object_type=object_type,
        table_name=table_name,
        object_name=object_name,
        qualified_name=qualified_name,
    )


def _clean_dax_identifier(value: str) -> str:
    cleaned = value.strip()

    if cleaned.startswith("'") and cleaned.endswith("'"):
        cleaned = cleaned[1:-1].replace("''", "'")

    return cleaned


def _strip_dax_comments_and_strings(expression: str) -> str:
    result: list[str] = []
    index = 0
    state = "code"

    while index < len(expression):
        character = expression[index]
        next_character = expression[index + 1] if index + 1 < len(expression) else ""

        if state == "code":
            if character == "/" and next_character == "/":
                result.extend("  ")
                index += 2
                state = "line_comment"
                continue
            if character == "/" and next_character == "*":
                result.extend("  ")
                index += 2
                state = "block_comment"
                continue
            if character == '"':
                result.append(" ")
                index += 1
                state = "string"
                continue

            result.append(character)
            index += 1
            continue

        if state == "line_comment":
            if character in "\r\n":
                result.append(character)
                state = "code"
            else:
                result.append(" ")
            index += 1
            continue

        if state == "block_comment":
            if character == "*" and next_character == "/":
                result.extend("  ")
                index += 2
                state = "code"
            else:
                result.append(character if character in "\r\n" else " ")
                index += 1
            continue

        if character == '"' and next_character == '"':
            result.extend("  ")
            index += 2
            continue
        if character == '"':
            result.append(" ")
            index += 1
            state = "code"
            continue

        result.append(character if character in "\r\n" else " ")
        index += 1

    return "".join(result)
