from collections import defaultdict

from app.domain.graph_algorithms import strongly_connected_components
from app.schemas.lineage_graph import LineageGraph
from app.schemas.lineage_validation import (
    LineageValidationIssue,
    LineageValidationResponse,
)


class LineageValidationService:
    def validate(self, graph: LineageGraph) -> LineageValidationResponse:
        issues: list[LineageValidationIssue] = []
        node_ids = [node.node_id for node in graph.nodes]
        edge_ids = [edge.edge_id for edge in graph.edges]
        node_id_set = set(node_ids)

        self._duplicates(node_ids, "node", issues)
        self._duplicates(edge_ids, "edge", issues)

        connected: set[str] = set()
        for edge in graph.edges:
            missing = [
                node_id
                for node_id in (edge.source_id, edge.target_id)
                if node_id not in node_id_set
            ]
            if missing:
                issues.append(
                    LineageValidationIssue(
                        severity="error",
                        code="EDGE_ENDPOINT_MISSING",
                        message="An edge references a node that is not in the graph.",
                        edge_id=edge.edge_id,
                    )
                )
                continue
            connected.update((edge.source_id, edge.target_id))
            if edge.source_id == edge.target_id:
                issues.append(
                    LineageValidationIssue(
                        severity="warning",
                        code="SELF_REFERENCING_EDGE",
                        message="An edge points back to the same node.",
                        node_id=edge.source_id,
                        edge_id=edge.edge_id,
                    )
                )

        for node in graph.nodes:
            if node.node_id not in connected:
                issues.append(
                    LineageValidationIssue(
                        severity="info",
                        code="ORPHAN_NODE",
                        message="The node has no incoming or outgoing edges.",
                        node_id=node.node_id,
                    )
                )

        for node in graph.nodes:
            if node.node_type != "query":
                continue
            has_source = any(
                edge.target_id == node.node_id
                and edge.edge_type == "reads_from"
                and edge.is_lineage
                for edge in graph.edges
            )
            if not has_source:
                issues.append(
                    LineageValidationIssue(
                        severity="warning",
                        code="QUERY_SOURCE_MISSING",
                        message="A query has no detected physical source.",
                        node_id=node.node_id,
                    )
                )

        for component in self._lineage_cycles(graph):
            issues.append(
                LineageValidationIssue(
                    severity="warning",
                    code="LINEAGE_CYCLE_DETECTED",
                    message=(
                        "A lineage cycle contains "
                        f"{len(component)} node{'s' if len(component) != 1 else ''}."
                    ),
                    node_id=min(component),
                )
            )

        error_count = sum(issue.severity == "error" for issue in issues)
        warning_count = sum(issue.severity == "warning" for issue in issues)
        info_count = sum(issue.severity == "info" for issue in issues)
        score = max(
            0.0,
            100.0 - error_count * 25.0 - warning_count * 5.0 - info_count,
        )
        return LineageValidationResponse(
            graph_id=graph.graph_id,
            valid=error_count == 0,
            quality_score=score,
            issues=issues,
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
        )

    @staticmethod
    def _duplicates(
        identifiers: list[str],
        item_type: str,
        issues: list[LineageValidationIssue],
    ) -> None:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for identifier in identifiers:
            if identifier in seen:
                duplicates.add(identifier)
            seen.add(identifier)
        for identifier in sorted(duplicates):
            issues.append(
                LineageValidationIssue(
                    severity="error",
                    code=f"DUPLICATE_{item_type.upper()}_ID",
                    message=f"The graph contains a duplicate {item_type} identifier.",
                    node_id=identifier if item_type == "node" else None,
                    edge_id=identifier if item_type == "edge" else None,
                )
            )

    @staticmethod
    def _lineage_cycles(graph: LineageGraph) -> list[set[str]]:
        adjacency: dict[str, set[str]] = defaultdict(set)
        for edge in graph.edges:
            if edge.is_lineage:
                adjacency[edge.source_id].add(edge.target_id)
                adjacency.setdefault(edge.target_id, set())

        components: list[set[str]] = []

        for component in strongly_connected_components(adjacency):
            member = next(iter(component))
            has_self_loop = len(component) == 1 and member in adjacency[member]
            if len(component) > 1 or has_self_loop:
                components.append(component)
        return components
