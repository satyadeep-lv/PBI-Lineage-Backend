from collections import defaultdict, deque

from app.schemas.impact_analysis import ImpactAnalysisResponse, ImpactedNode
from app.schemas.lineage_graph import LineageEdge, LineageGraph


class ImpactAnalysisService:
    def analyze(
        self,
        graph: LineageGraph,
        *,
        node_id: str,
        max_depth: int = 10,
        include_non_lineage: bool = False,
    ) -> ImpactAnalysisResponse:
        if max_depth < 1 or max_depth > 100:
            raise ValueError("max_depth must be between 1 and 100.")

        nodes = {node.node_id: node for node in graph.nodes}
        source_node = nodes.get(node_id)
        if source_node is None:
            raise KeyError(node_id)

        adjacency: dict[str, list[LineageEdge]] = defaultdict(list)
        for edge in graph.edges:
            if edge.is_lineage or include_non_lineage:
                adjacency[edge.source_id].append(edge)

        queue = deque([(node_id, 0, [node_id], [])])
        visited = {node_id}
        impacted: list[ImpactedNode] = []
        truncated = False

        while queue:
            current_id, depth, node_path, edge_path = queue.popleft()
            outgoing = adjacency.get(current_id, [])
            if depth >= max_depth:
                if any(edge.target_id not in visited for edge in outgoing):
                    truncated = True
                continue

            for edge in outgoing:
                target = nodes.get(edge.target_id)
                if target is None or target.node_id in visited:
                    continue
                visited.add(target.node_id)
                next_node_path = [*node_path, target.node_id]
                next_edge_path = [*edge_path, edge.edge_id]
                impacted.append(
                    ImpactedNode(
                        node=target,
                        distance=depth + 1,
                        path_node_ids=next_node_path,
                        path_edge_ids=next_edge_path,
                    )
                )
                queue.append(
                    (target.node_id, depth + 1, next_node_path, next_edge_path)
                )

        impacted.sort(key=lambda item: (item.distance, item.node.qualified_name))
        return ImpactAnalysisResponse(
            graph_id=graph.graph_id,
            source_node=source_node,
            max_depth=max_depth,
            impacted_nodes=impacted,
            impacted_count=len(impacted),
            truncated=truncated,
        )
