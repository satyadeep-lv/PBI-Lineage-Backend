import json
from collections import defaultdict, deque

from app.domain.lineage_ids import stable_lineage_id
from app.schemas.lineage_graph import LineageGraph, LineageNodeType
from app.schemas.lineage_search import (
    LineageNavigationResponse,
    LineageSearchResponse,
    LineageSearchResult,
)


class LineageSearchService:
    def search(
        self,
        graph: LineageGraph,
        *,
        query: str,
        node_types: list[LineageNodeType] | None = None,
        workspace_id: str | None = None,
        semantic_model_id: str | None = None,
        report_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> LineageSearchResponse:
        normalized_query = query.strip().casefold()
        if not normalized_query:
            raise ValueError("query cannot be empty.")
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500.")
        if offset < 0:
            raise ValueError("offset cannot be negative.")

        allowed_types = set(node_types or [])
        matches: list[LineageSearchResult] = []
        for node in graph.nodes:
            if allowed_types and node.node_type not in allowed_types:
                continue
            if workspace_id and node.workspace_id != workspace_id:
                continue
            if semantic_model_id and node.semantic_model_id != semantic_model_id:
                continue
            if report_id and node.report_id != report_id:
                continue

            result = self._match(node, normalized_query)
            if result:
                matches.append(result)

        matches.sort(
            key=lambda item: (
                -item.score,
                item.node.qualified_name.casefold(),
                item.node.node_id,
            )
        )
        total = len(matches)
        return LineageSearchResponse(
            graph_id=graph.graph_id,
            query=query.strip(),
            results=matches[offset : offset + limit],
            total=total,
            limit=limit,
            offset=offset,
            node_types=list(node_types or []),
        )

    @staticmethod
    def _match(node, query: str) -> LineageSearchResult | None:
        name = node.name.casefold()
        qualified_name = node.qualified_name.casefold()
        matched_fields: list[str] = []
        score = 0.0

        if name == query:
            matched_fields.append("name")
            score = 1.0
        elif name.startswith(query):
            matched_fields.append("name")
            score = 0.9
        elif query in name:
            matched_fields.append("name")
            score = 0.8

        if query in qualified_name:
            matched_fields.append("qualified_name")
            score = max(score, 0.7)

        properties = json.dumps(
            node.properties,
            sort_keys=True,
            default=str,
        ).casefold()
        if query in properties:
            matched_fields.append("properties")
            score = max(score, 0.5)

        if not matched_fields:
            return None
        return LineageSearchResult(
            node=node,
            score=score,
            matched_fields=matched_fields,
        )


class LineageNavigationService:
    def navigate(
        self,
        graph: LineageGraph,
        *,
        node_id: str,
        direction: str = "both",
        depth: int = 1,
        include_non_lineage: bool = True,
    ) -> LineageNavigationResponse:
        if direction not in {"upstream", "downstream", "both"}:
            raise ValueError("direction must be upstream, downstream, or both.")
        if depth < 1 or depth > 20:
            raise ValueError("depth must be between 1 and 20.")

        nodes = {node.node_id: node for node in graph.nodes}
        if node_id not in nodes:
            raise KeyError(node_id)

        outgoing = defaultdict(list)
        incoming = defaultdict(list)
        for edge in graph.edges:
            if edge.is_lineage or include_non_lineage:
                outgoing[edge.source_id].append(edge)
                incoming[edge.target_id].append(edge)

        visited = {node_id}
        selected_edge_ids: set[str] = set()
        queue = deque([(node_id, 0)])
        while queue:
            current_id, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            candidates = []
            if direction in {"downstream", "both"}:
                candidates.extend(
                    (edge, edge.target_id) for edge in outgoing[current_id]
                )
            if direction in {"upstream", "both"}:
                candidates.extend(
                    (edge, edge.source_id) for edge in incoming[current_id]
                )
            for edge, neighbor_id in candidates:
                if neighbor_id not in nodes:
                    continue
                selected_edge_ids.add(edge.edge_id)
                if neighbor_id in visited:
                    continue
                visited.add(neighbor_id)
                queue.append((neighbor_id, current_depth + 1))

        selected_nodes = sorted(
            (nodes[selected_id] for selected_id in visited),
            key=lambda item: item.node_id,
        )
        selected_edges = sorted(
            (
                edge
                for edge in graph.edges
                if edge.edge_id in selected_edge_ids
                and edge.source_id in visited
                and edge.target_id in visited
            ),
            key=lambda item: item.edge_id,
        )
        subgraph = LineageGraph(
            graph_id=stable_lineage_id(
                "navigation",
                graph.graph_id,
                node_id,
                direction,
                str(depth),
            ),
            created_at=graph.created_at,
            workspace_id=graph.workspace_id,
            semantic_model_id=graph.semantic_model_id,
            report_id=graph.report_id,
            nodes=selected_nodes,
            edges=selected_edges,
            node_count=len(selected_nodes),
            edge_count=len(selected_edges),
        )
        return LineageNavigationResponse(
            graph_id=graph.graph_id,
            root_node_id=node_id,
            direction=direction,
            depth=depth,
            graph=subgraph,
        )
