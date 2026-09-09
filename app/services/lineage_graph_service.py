from datetime import UTC, datetime
from typing import Any

from app.domain.lineage_ids import stable_lineage_id
from app.schemas.dax_dependency import DaxObjectReference
from app.schemas.lineage_graph import (
    LineageEdge,
    LineageGraph,
    LineageGraphBuildRequest,
    LineageNode,
)
from app.schemas.report_semantic_lineage import SemanticLineageObject
from app.services.dax_dependency_service import DaxDependencyService
from app.services.physical_source_service import PhysicalSourceDiscoveryService


class LineageGraphService:
    def build(self, request: LineageGraphBuildRequest) -> LineageGraph:
        self._validate_request_identity(request)
        semantic_model = request.semantic_model
        dax = request.dax_analysis or DaxDependencyService().analyze(semantic_model)
        physical = (
            request.physical_sources
            or PhysicalSourceDiscoveryService().discover(semantic_model)
        )
        nodes: dict[str, LineageNode] = {}
        edges: dict[tuple[str, str, str], LineageEdge] = {}
        warnings = [warning.message for warning in dax.warnings]
        warnings.extend(warning.message for warning in physical.warnings)

        model_node_id = self._semantic_id(
            semantic_model.workspace_id,
            semantic_model.semantic_model_id,
            "model",
        )
        self._add_node(
            nodes,
            LineageNode(
                node_id=model_node_id,
                node_type="semantic_model",
                name=semantic_model.semantic_model_id,
                qualified_name=semantic_model.semantic_model_id,
                workspace_id=semantic_model.workspace_id,
                semantic_model_id=semantic_model.semantic_model_id,
                properties={"format": semantic_model.format},
            ),
        )

        self._add_semantic_model_nodes(request, nodes, edges, model_node_id)
        self._add_dax_edges(request, dax, nodes, edges)
        self._add_physical_nodes(request, physical, nodes, edges)

        if request.report_lineage:
            self._add_report_nodes(request, nodes, edges)

        if request.snowflake_lineage:
            self._add_snowflake_nodes(request, nodes, edges)

        ordered_nodes = sorted(nodes.values(), key=lambda node: node.node_id)
        ordered_edges = sorted(edges.values(), key=lambda edge: edge.edge_id)
        report_id = request.report_lineage.report_id if request.report_lineage else None
        return LineageGraph(
            graph_id=stable_lineage_id(
                "graph",
                semantic_model.workspace_id,
                semantic_model.semantic_model_id,
                report_id,
            ),
            created_at=datetime.now(UTC),
            workspace_id=semantic_model.workspace_id,
            semantic_model_id=semantic_model.semantic_model_id,
            report_id=report_id,
            nodes=ordered_nodes,
            edges=ordered_edges,
            warnings=list(dict.fromkeys(warnings)),
            node_count=len(ordered_nodes),
            edge_count=len(ordered_edges),
        )

    @staticmethod
    def _validate_request_identity(request: LineageGraphBuildRequest) -> None:
        model = request.semantic_model
        evidence = (
            ("DAX analysis", request.dax_analysis),
            ("physical-source analysis", request.physical_sources),
        )
        for label, item in evidence:
            if item is None:
                continue
            if (
                item.workspace_id != model.workspace_id
                or item.semantic_model_id != model.semantic_model_id
            ):
                raise ValueError(
                    f"{label} does not identify the requested semantic model."
                )

        report = request.report_lineage
        if report is not None and (
            report.semantic_model_workspace_id != model.workspace_id
            or report.semantic_model_id != model.semantic_model_id
        ):
            raise ValueError(
                "Report lineage does not identify the requested semantic model."
            )

    def _add_semantic_model_nodes(
        self,
        request: LineageGraphBuildRequest,
        nodes: dict[str, LineageNode],
        edges: dict[tuple[str, str, str], LineageEdge],
        model_node_id: str,
    ) -> None:
        model = request.semantic_model

        for table in model.tables:
            table_id = self._semantic_id(
                model.workspace_id,
                model.semantic_model_id,
                "table",
                table.name,
            )
            self._add_node(
                nodes,
                LineageNode(
                    node_id=table_id,
                    node_type="semantic_table",
                    name=table.name,
                    qualified_name=table.name,
                    workspace_id=model.workspace_id,
                    semantic_model_id=model.semantic_model_id,
                    properties={
                        "source_path": table.source_path,
                        "is_calculated": table.expression is not None,
                    },
                ),
            )
            self._add_edge(edges, model_node_id, table_id, "contains", False)

            for column in table.columns:
                column_id = self._semantic_id(
                    model.workspace_id,
                    model.semantic_model_id,
                    "column",
                    table.name,
                    column.name,
                )
                self._add_node(
                    nodes,
                    LineageNode(
                        node_id=column_id,
                        node_type="semantic_column",
                        name=column.name,
                        qualified_name=f"{table.name}[{column.name}]",
                        workspace_id=model.workspace_id,
                        semantic_model_id=model.semantic_model_id,
                        properties={
                            "table_name": table.name,
                            "data_type": column.data_type,
                            "source_column": column.source_column,
                            "is_calculated": column.expression is not None,
                            "is_hidden": column.is_hidden,
                        },
                    ),
                )
                self._add_edge(edges, table_id, column_id, "contains", False)
                if column.expression is None:
                    self._add_edge(
                        edges,
                        table_id,
                        column_id,
                        "provides_data_to",
                        True,
                    )

            for measure in table.measures:
                measure_id = self._semantic_id(
                    model.workspace_id,
                    model.semantic_model_id,
                    "measure",
                    table.name,
                    measure.name,
                )
                self._add_node(
                    nodes,
                    LineageNode(
                        node_id=measure_id,
                        node_type="semantic_measure",
                        name=measure.name,
                        qualified_name=f"{table.name}[{measure.name}]",
                        workspace_id=model.workspace_id,
                        semantic_model_id=model.semantic_model_id,
                        properties={
                            "table_name": table.name,
                            "format_string": measure.format_string,
                            "is_hidden": measure.is_hidden,
                        },
                    ),
                )
                self._add_edge(edges, table_id, measure_id, "contains", False)

            for hierarchy in table.hierarchies:
                hierarchy_id = self._semantic_id(
                    model.workspace_id,
                    model.semantic_model_id,
                    "hierarchy",
                    table.name,
                    hierarchy.name,
                )
                self._add_node(
                    nodes,
                    LineageNode(
                        node_id=hierarchy_id,
                        node_type="semantic_hierarchy",
                        name=hierarchy.name,
                        qualified_name=f"{table.name}[{hierarchy.name}]",
                        workspace_id=model.workspace_id,
                        semantic_model_id=model.semantic_model_id,
                    ),
                )
                self._add_edge(edges, table_id, hierarchy_id, "contains", False)

                for level in hierarchy.levels:
                    level_id = self._semantic_id(
                        model.workspace_id,
                        model.semantic_model_id,
                        "hierarchy_level",
                        table.name,
                        hierarchy.name,
                        level.name,
                    )
                    self._add_node(
                        nodes,
                        LineageNode(
                            node_id=level_id,
                            node_type="semantic_hierarchy_level",
                            name=level.name,
                            qualified_name=(
                                f"{table.name}[{hierarchy.name}].[{level.name}]"
                            ),
                            workspace_id=model.workspace_id,
                            semantic_model_id=model.semantic_model_id,
                            properties={"column": level.column},
                        ),
                    )
                    self._add_edge(edges, hierarchy_id, level_id, "contains", False)

        for relationship in model.relationships:
            if not all(
                (
                    relationship.from_table,
                    relationship.from_column,
                    relationship.to_table,
                    relationship.to_column,
                )
            ):
                continue
            source_id = self._semantic_id(
                model.workspace_id,
                model.semantic_model_id,
                "column",
                relationship.from_table,
                relationship.from_column,
            )
            target_id = self._semantic_id(
                model.workspace_id,
                model.semantic_model_id,
                "column",
                relationship.to_table,
                relationship.to_column,
            )
            if source_id in nodes and target_id in nodes:
                self._add_edge(
                    edges,
                    source_id,
                    target_id,
                    "relates_to",
                    False,
                    {
                        "relationship": relationship.name,
                        "is_active": relationship.is_active,
                        "cardinality": relationship.cardinality,
                    },
                )

    def _add_dax_edges(
        self,
        request: LineageGraphBuildRequest,
        dax: Any,
        nodes: dict[str, LineageNode],
        edges: dict[tuple[str, str, str], LineageEdge],
    ) -> None:
        for dependency in dax.dependencies:
            source_id = self._dax_object_id(request, dependency.source)
            target_id = self._dax_object_id(request, dependency.target)
            if source_id in nodes and target_id in nodes:
                self._add_edge(
                    edges,
                    source_id,
                    target_id,
                    "dax_dependency",
                    True,
                    {"reference_text": dependency.reference_text},
                )

    def _add_physical_nodes(
        self,
        request: LineageGraphBuildRequest,
        physical: Any,
        nodes: dict[str, LineageNode],
        edges: dict[tuple[str, str, str], LineageEdge],
    ) -> None:
        model = request.semantic_model
        for source in physical.sources:
            self._add_node(
                nodes,
                LineageNode(
                    node_id=source.source_id,
                    node_type="physical_source",
                    name=source.object_name
                    or source.database
                    or source.path
                    or source.url
                    or source.provider,
                    qualified_name=self._physical_qualified_name(source),
                    workspace_id=model.workspace_id,
                    semantic_model_id=model.semantic_model_id,
                    properties=source.model_dump(
                        exclude={"source_id"}, exclude_none=True
                    ),
                ),
            )

        for mapping in physical.mappings:
            self._add_node(
                nodes,
                LineageNode(
                    node_id=mapping.query_id,
                    node_type="query",
                    name=mapping.partition_name,
                    qualified_name=(
                        f"{mapping.semantic_table}.{mapping.partition_name}"
                    ),
                    workspace_id=model.workspace_id,
                    semantic_model_id=model.semantic_model_id,
                    properties={"source_path": mapping.source_path},
                ),
            )
            table_id = self._semantic_id(
                model.workspace_id,
                model.semantic_model_id,
                "table",
                mapping.semantic_table,
            )
            if table_id in nodes:
                self._add_edge(edges, mapping.query_id, table_id, "populates", True)
            for source_id in mapping.source_ids:
                if source_id in nodes:
                    self._add_edge(
                        edges, source_id, mapping.query_id, "reads_from", True
                    )

    def _add_report_nodes(
        self,
        request: LineageGraphBuildRequest,
        nodes: dict[str, LineageNode],
        edges: dict[tuple[str, str, str], LineageEdge],
    ) -> None:
        lineage = request.report_lineage
        assert lineage is not None
        report_id = stable_lineage_id(
            "report",
            lineage.workspace_id,
            lineage.report_id,
        )
        self._add_node(
            nodes,
            LineageNode(
                node_id=report_id,
                node_type="report",
                name=lineage.report_id,
                qualified_name=lineage.report_id,
                workspace_id=lineage.workspace_id,
                report_id=lineage.report_id,
            ),
        )

        for match in lineage.field_matches:
            page_id = stable_lineage_id(
                "page",
                lineage.workspace_id,
                lineage.report_id,
                match.page_name,
            )
            visual_id = stable_lineage_id(
                "visual",
                lineage.workspace_id,
                lineage.report_id,
                match.page_name,
                match.visual_id,
            )
            self._add_node(
                nodes,
                LineageNode(
                    node_id=page_id,
                    node_type="report_page",
                    name=match.page_display_name,
                    qualified_name=f"{lineage.report_id}.{match.page_name}",
                    workspace_id=lineage.workspace_id,
                    report_id=lineage.report_id,
                    properties={"page_name": match.page_name},
                ),
            )
            self._add_node(
                nodes,
                LineageNode(
                    node_id=visual_id,
                    node_type="visual",
                    name=match.visual_title or match.visual_id,
                    qualified_name=(
                        f"{lineage.report_id}.{match.page_name}.{match.visual_id}"
                    ),
                    workspace_id=lineage.workspace_id,
                    report_id=lineage.report_id,
                    properties={
                        "visual_id": match.visual_id,
                        "visual_type": match.visual_type,
                    },
                ),
            )
            self._add_edge(edges, report_id, page_id, "contains", False)
            self._add_edge(edges, page_id, visual_id, "contains", False)

            if match.status != "matched" or match.semantic_object is None:
                continue
            semantic_id = self._lineage_object_id(request, match.semantic_object)
            if semantic_id in nodes:
                self._add_edge(
                    edges,
                    semantic_id,
                    visual_id,
                    "used_by_visual",
                    True,
                    {"confidence": match.match_confidence},
                )

    def _add_snowflake_nodes(
        self,
        request: LineageGraphBuildRequest,
        nodes: dict[str, LineageNode],
        edges: dict[tuple[str, str, str], LineageEdge],
    ) -> None:
        snapshot = request.snowflake_lineage
        assert snapshot is not None
        model = request.semantic_model

        for item in snapshot.objects:
            self._add_node(
                nodes,
                LineageNode(
                    node_id=item.object_id,
                    node_type="snowflake_object",
                    name=item.column_name or item.object_name,
                    qualified_name=item.qualified_name,
                    workspace_id=model.workspace_id,
                    semantic_model_id=model.semantic_model_id,
                    properties={
                        "account_identifier": snapshot.account_identifier,
                        "database": item.database,
                        "schema": item.schema_name,
                        "object_domain": item.object_domain,
                        "column_name": item.column_name,
                        "status": item.status,
                    },
                ),
            )

        for dependency in snapshot.dependencies:
            self._add_edge(
                edges,
                dependency.source.object_id,
                dependency.target.object_id,
                "snowflake_dependency",
                True,
                {
                    "dependency_type": dependency.dependency_type,
                    "distance": dependency.distance,
                    "process": dependency.process,
                },
            )

        snowflake_ids = {
            item.qualified_name.casefold(): item.object_id for item in snapshot.objects
        }
        for node in list(nodes.values()):
            if node.node_type != "physical_source":
                continue
            if str(node.properties.get("provider", "")).casefold() != "snowflake":
                continue
            physical_name = ".".join(
                str(node.properties.get(key, ""))
                for key in ("database", "schema_name", "object_name")
            ).casefold()
            snowflake_id = snowflake_ids.get(physical_name)
            if snowflake_id:
                self._add_edge(
                    edges,
                    snowflake_id,
                    node.node_id,
                    "maps_to_power_query_source",
                    True,
                )

    def _dax_object_id(
        self,
        request: LineageGraphBuildRequest,
        reference: DaxObjectReference,
    ) -> str:
        model = request.semantic_model
        object_kind = {
            "measure": "measure",
            "calculated_column": "column",
            "column": "column",
            "calculated_table": "table",
            "table": "table",
        }.get(reference.object_type, "unresolved")
        if object_kind == "table":
            return self._semantic_id(
                model.workspace_id,
                model.semantic_model_id,
                "table",
                reference.table_name or reference.object_name,
            )
        return self._semantic_id(
            model.workspace_id,
            model.semantic_model_id,
            object_kind,
            reference.table_name,
            reference.object_name,
        )

    def _lineage_object_id(
        self,
        request: LineageGraphBuildRequest,
        item: SemanticLineageObject,
    ) -> str:
        model = request.semantic_model
        if item.object_type == "hierarchy_level":
            return self._semantic_id(
                model.workspace_id,
                model.semantic_model_id,
                "hierarchy_level",
                item.table_name,
                item.hierarchy_name,
                item.level_name or item.object_name,
            )
        return self._semantic_id(
            model.workspace_id,
            model.semantic_model_id,
            item.object_type,
            item.table_name,
            item.object_name,
        )

    @staticmethod
    def _semantic_id(
        workspace_id: str,
        semantic_model_id: str,
        object_type: str,
        *parts: str | None,
    ) -> str:
        return stable_lineage_id(
            f"semantic_{object_type}",
            workspace_id,
            semantic_model_id,
            *parts,
        )

    @staticmethod
    def _physical_qualified_name(source: Any) -> str:
        return (
            ".".join(
                part
                for part in (
                    source.server,
                    source.database,
                    source.schema_name,
                    source.object_name,
                )
                if part
            )
            or source.path
            or source.url
            or source.account
            or source.provider
        )

    @staticmethod
    def _add_node(nodes: dict[str, LineageNode], node: LineageNode) -> None:
        nodes.setdefault(node.node_id, node)

    @staticmethod
    def _add_edge(
        edges: dict[tuple[str, str, str], LineageEdge],
        source_id: str,
        target_id: str,
        edge_type: str,
        is_lineage: bool,
        properties: dict[str, Any] | None = None,
    ) -> None:
        key = (source_id, target_id, edge_type)
        edges.setdefault(
            key,
            LineageEdge(
                edge_id=stable_lineage_id("edge", source_id, target_id, edge_type),
                source_id=source_id,
                target_id=target_id,
                edge_type=edge_type,
                is_lineage=is_lineage,
                properties=properties or {},
            ),
        )
