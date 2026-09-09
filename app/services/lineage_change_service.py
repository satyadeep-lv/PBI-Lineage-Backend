from app.schemas.lineage_change import LineageChangeSet
from app.schemas.lineage_graph import LineageGraph


class LineageChangeService:
    def compare(
        self,
        *,
        graph_id: str,
        from_version: int,
        from_graph: LineageGraph,
        to_version: int,
        to_graph: LineageGraph,
    ) -> LineageChangeSet:
        from_nodes = {node.node_id: node for node in from_graph.nodes}
        to_nodes = {node.node_id: node for node in to_graph.nodes}
        from_edges = {edge.edge_id: edge for edge in from_graph.edges}
        to_edges = {edge.edge_id: edge for edge in to_graph.edges}

        added_nodes = sorted(to_nodes.keys() - from_nodes.keys())
        removed_nodes = sorted(from_nodes.keys() - to_nodes.keys())
        changed_nodes = sorted(
            node_id
            for node_id in from_nodes.keys() & to_nodes.keys()
            if from_nodes[node_id].model_dump(mode="json")
            != to_nodes[node_id].model_dump(mode="json")
        )
        added_edges = sorted(to_edges.keys() - from_edges.keys())
        removed_edges = sorted(from_edges.keys() - to_edges.keys())
        changed_edges = sorted(
            edge_id
            for edge_id in from_edges.keys() & to_edges.keys()
            if from_edges[edge_id].model_dump(mode="json")
            != to_edges[edge_id].model_dump(mode="json")
        )
        has_changes = any(
            (
                added_nodes,
                removed_nodes,
                changed_nodes,
                added_edges,
                removed_edges,
                changed_edges,
            )
        )
        return LineageChangeSet(
            graph_id=graph_id,
            from_version=from_version,
            to_version=to_version,
            added_node_ids=added_nodes,
            removed_node_ids=removed_nodes,
            changed_node_ids=changed_nodes,
            added_edge_ids=added_edges,
            removed_edge_ids=removed_edges,
            changed_edge_ids=changed_edges,
            has_changes=has_changes,
        )
