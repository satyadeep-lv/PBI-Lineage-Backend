from typing import Any

from app.clients.powerbi_client import PowerBIClient
from app.clients.xmla_client import XmlaClient
from app.core.exceptions import (
    ProviderResourceNotFoundError,
    UpstreamInvalidResponseError,
)
from app.schemas.xmla_metadata import (
    XmlaMetadataWarning,
    XmlaSemanticModelColumn,
    XmlaSemanticModelHierarchy,
    XmlaSemanticModelHierarchyLevel,
    XmlaSemanticModelMeasure,
    XmlaSemanticModelMetadataResponse,
    XmlaSemanticModelPartition,
    XmlaSemanticModelRelationship,
    XmlaSemanticModelTable,
)

MISSING = object()


class XmlaMetadataService:
    def __init__(
        self,
        *,
        xmla_client: XmlaClient | None = None,
        powerbi_client: PowerBIClient | None = None,
    ) -> None:
        self.client = xmla_client or XmlaClient()
        self.powerbi_client = powerbi_client or PowerBIClient()

    async def get_metadata(
        self,
        *,
        workspace_id: str,
        semantic_model_id: str,
        access_token: str,
        workspace_name: str | None = None,
        database_name: str | None = None,
    ) -> XmlaSemanticModelMetadataResponse:
        resolved_workspace_name = await self._resolve_workspace_name(
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            access_token=access_token,
        )
        resolved_database_name = await self._resolve_database_name(
            workspace_id=workspace_id,
            semantic_model_id=(semantic_model_id),
            database_name=database_name,
            access_token=access_token,
        )

        raw_metadata = await self.client.get_semantic_model_metadata(
            workspace_id=workspace_id,
            semantic_model_id=semantic_model_id,
            access_token=access_token,
            workspace_name=(resolved_workspace_name),
            database_name=(resolved_database_name),
        )

        xmla_endpoint = self.client.build_workspace_endpoint(
            workspace_id=workspace_id,
            workspace_name=(resolved_workspace_name),
        )

        return self._map_metadata(
            workspace_id=workspace_id,
            semantic_model_id=semantic_model_id,
            xmla_endpoint=xmla_endpoint,
            requested_database_name=(resolved_database_name),
            raw_metadata=raw_metadata,
        )

    async def _resolve_workspace_name(
        self,
        *,
        workspace_id: str,
        workspace_name: str | None,
        access_token: str,
    ) -> str:
        if workspace_name:
            return workspace_name

        raw_workspace = await self.powerbi_client.get_workspace(
            workspace_id=workspace_id,
            access_token=access_token,
        )
        resolved_workspace_name = raw_workspace.get("name")

        if (
            not isinstance(
                resolved_workspace_name,
                str,
            )
            or not resolved_workspace_name
        ):
            raise UpstreamInvalidResponseError("powerbi")

        return resolved_workspace_name

    async def _resolve_database_name(
        self,
        *,
        workspace_id: str,
        semantic_model_id: str,
        database_name: str | None,
        access_token: str,
    ) -> str:
        if database_name:
            return database_name

        raw_models = await self.powerbi_client.get_semantic_models_in_workspace(
            workspace_id=workspace_id,
            access_token=access_token,
        )
        target_model_id = semantic_model_id.lower()

        for raw_model in raw_models:
            model_id = raw_model.get("id")

            if isinstance(model_id, str) and model_id.lower() == target_model_id:
                model_name = raw_model.get("name")

                if (
                    not isinstance(
                        model_name,
                        str,
                    )
                    or not model_name
                ):
                    raise UpstreamInvalidResponseError("powerbi")

                return model_name

        raise ProviderResourceNotFoundError(
            "powerbi",
            "semantic model",
        )

    def _map_metadata(
        self,
        *,
        workspace_id: str,
        semantic_model_id: str,
        xmla_endpoint: str,
        requested_database_name: str | None,
        raw_metadata: dict[str, Any],
    ) -> XmlaSemanticModelMetadataResponse:
        if not isinstance(
            raw_metadata,
            dict,
        ):
            raise UpstreamInvalidResponseError("xmla")

        tables = [
            self._map_table(raw_table)
            for raw_table in _required_list(
                raw_metadata,
                "tables",
            )
        ]

        relationships = [
            self._map_relationship(raw_relationship)
            for raw_relationship in _optional_list(
                raw_metadata,
                "relationships",
            )
        ]

        warnings = [
            self._map_warning(raw_warning)
            for raw_warning in _optional_list(
                raw_metadata,
                "warnings",
            )
        ]

        return XmlaSemanticModelMetadataResponse(
            workspace_id=workspace_id,
            semantic_model_id=semantic_model_id,
            xmla_endpoint=xmla_endpoint,
            database_name=(
                _optional_string(
                    raw_metadata,
                    "database_name",
                    "databaseName",
                )
                or requested_database_name
            ),
            table_count=len(tables),
            column_count=sum(len(table.columns) for table in tables),
            measure_count=sum(len(table.measures) for table in tables),
            relationship_count=len(relationships),
            hierarchy_count=sum(len(table.hierarchies) for table in tables),
            partition_count=sum(len(table.partitions) for table in tables),
            tables=tables,
            relationships=relationships,
            warnings=warnings,
        )

    def _map_table(
        self,
        raw_table: Any,
    ) -> XmlaSemanticModelTable:
        table = _required_dict(raw_table)

        return XmlaSemanticModelTable(
            name=_required_string(
                table,
                "name",
            ),
            description=_optional_string(
                table,
                "description",
            ),
            is_hidden=_optional_bool(
                table,
                "is_hidden",
                "isHidden",
            ),
            columns=[
                self._map_column(raw_column)
                for raw_column in _optional_list(
                    table,
                    "columns",
                )
            ],
            measures=[
                self._map_measure(raw_measure)
                for raw_measure in _optional_list(
                    table,
                    "measures",
                )
            ],
            partitions=[
                self._map_partition(raw_partition)
                for raw_partition in _optional_list(
                    table,
                    "partitions",
                )
            ],
            hierarchies=[
                self._map_hierarchy(raw_hierarchy)
                for raw_hierarchy in _optional_list(
                    table,
                    "hierarchies",
                )
            ],
        )

    def _map_column(
        self,
        raw_column: Any,
    ) -> XmlaSemanticModelColumn:
        column = _required_dict(raw_column)

        return XmlaSemanticModelColumn(
            name=_required_string(
                column,
                "name",
            ),
            data_type=_optional_string(
                column,
                "data_type",
                "dataType",
            ),
            source_column=_optional_string(
                column,
                "source_column",
                "sourceColumn",
            ),
            expression=_optional_string(
                column,
                "expression",
            ),
            format_string=_optional_string(
                column,
                "format_string",
                "formatString",
            ),
            summarize_by=_optional_string(
                column,
                "summarize_by",
                "summarizeBy",
            ),
            sort_by_column=_optional_string(
                column,
                "sort_by_column",
                "sortByColumn",
            ),
            is_hidden=_optional_bool(
                column,
                "is_hidden",
                "isHidden",
            ),
            description=_optional_string(
                column,
                "description",
            ),
            lineage_tag=_optional_string(
                column,
                "lineage_tag",
                "lineageTag",
            ),
        )

    def _map_measure(
        self,
        raw_measure: Any,
    ) -> XmlaSemanticModelMeasure:
        measure = _required_dict(raw_measure)

        return XmlaSemanticModelMeasure(
            name=_required_string(
                measure,
                "name",
            ),
            expression=_optional_string(
                measure,
                "expression",
            ),
            format_string=_optional_string(
                measure,
                "format_string",
                "formatString",
            ),
            is_hidden=_optional_bool(
                measure,
                "is_hidden",
                "isHidden",
            ),
            description=_optional_string(
                measure,
                "description",
            ),
            lineage_tag=_optional_string(
                measure,
                "lineage_tag",
                "lineageTag",
            ),
        )

    def _map_partition(
        self,
        raw_partition: Any,
    ) -> XmlaSemanticModelPartition:
        partition = _required_dict(raw_partition)

        return XmlaSemanticModelPartition(
            name=_required_string(
                partition,
                "name",
            ),
            mode=_optional_string(
                partition,
                "mode",
            ),
            source_type=_optional_string(
                partition,
                "source_type",
                "sourceType",
            ),
            expression=_optional_string(
                partition,
                "expression",
            ),
            is_refreshable=_optional_bool(
                partition,
                "is_refreshable",
                "isRefreshable",
            ),
        )

    def _map_hierarchy(
        self,
        raw_hierarchy: Any,
    ) -> XmlaSemanticModelHierarchy:
        hierarchy = _required_dict(raw_hierarchy)

        return XmlaSemanticModelHierarchy(
            name=_required_string(
                hierarchy,
                "name",
            ),
            is_hidden=_optional_bool(
                hierarchy,
                "is_hidden",
                "isHidden",
            ),
            levels=[
                self._map_hierarchy_level(raw_level)
                for raw_level in _optional_list(
                    hierarchy,
                    "levels",
                )
            ],
        )

    def _map_hierarchy_level(
        self,
        raw_level: Any,
    ) -> XmlaSemanticModelHierarchyLevel:
        level = _required_dict(raw_level)

        return XmlaSemanticModelHierarchyLevel(
            name=_required_string(
                level,
                "name",
            ),
            column=_optional_string(
                level,
                "column",
            ),
            ordinal=_optional_int(
                level,
                "ordinal",
            ),
        )

    def _map_relationship(
        self,
        raw_relationship: Any,
    ) -> XmlaSemanticModelRelationship:
        relationship = _required_dict(raw_relationship)

        return XmlaSemanticModelRelationship(
            name=_optional_string(
                relationship,
                "name",
            ),
            from_table=_optional_string(
                relationship,
                "from_table",
                "fromTable",
            ),
            from_column=_optional_string(
                relationship,
                "from_column",
                "fromColumn",
            ),
            to_table=_optional_string(
                relationship,
                "to_table",
                "toTable",
            ),
            to_column=_optional_string(
                relationship,
                "to_column",
                "toColumn",
            ),
            is_active=_optional_bool(
                relationship,
                "is_active",
                "isActive",
            ),
            cardinality=_optional_string(
                relationship,
                "cardinality",
            ),
            cross_filter_direction=_optional_string(
                relationship,
                "cross_filter_direction",
                "crossFilterDirection",
            ),
            security_filtering_behavior=_optional_string(
                relationship,
                "security_filtering_behavior",
                "securityFilteringBehavior",
            ),
        )

    def _map_warning(
        self,
        raw_warning: Any,
    ) -> XmlaMetadataWarning:
        warning = _required_dict(raw_warning)

        return XmlaMetadataWarning(
            code=_required_string(
                warning,
                "code",
            ),
            message=_required_string(
                warning,
                "message",
            ),
            object_name=_optional_string(
                warning,
                "object_name",
                "objectName",
            ),
        )


def _value(
    payload: dict[str, Any],
    *keys: str,
) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]

    return MISSING


def _required_dict(
    value: Any,
) -> dict[str, Any]:
    if not isinstance(
        value,
        dict,
    ):
        raise UpstreamInvalidResponseError("xmla")

    return value


def _required_list(
    payload: dict[str, Any],
    key: str,
) -> list[Any]:
    value = _value(
        payload,
        key,
    )

    if not isinstance(
        value,
        list,
    ):
        raise UpstreamInvalidResponseError("xmla")

    return value


def _optional_list(
    payload: dict[str, Any],
    *keys: str,
) -> list[Any]:
    value = _value(
        payload,
        *keys,
    )

    if value is MISSING or value is None:
        return []

    if not isinstance(
        value,
        list,
    ):
        raise UpstreamInvalidResponseError("xmla")

    return value


def _required_string(
    payload: dict[str, Any],
    *keys: str,
) -> str:
    value = _value(
        payload,
        *keys,
    )

    if (
        not isinstance(
            value,
            str,
        )
        or not value
    ):
        raise UpstreamInvalidResponseError("xmla")

    return value


def _optional_string(
    payload: dict[str, Any],
    *keys: str,
) -> str | None:
    value = _value(
        payload,
        *keys,
    )

    if value is MISSING or value is None:
        return None

    if not isinstance(
        value,
        str,
    ):
        raise UpstreamInvalidResponseError("xmla")

    return value


def _optional_bool(
    payload: dict[str, Any],
    *keys: str,
) -> bool | None:
    value = _value(
        payload,
        *keys,
    )

    if value is MISSING or value is None:
        return None

    if not isinstance(
        value,
        bool,
    ):
        raise UpstreamInvalidResponseError("xmla")

    return value


def _optional_int(
    payload: dict[str, Any],
    *keys: str,
) -> int | None:
    value = _value(
        payload,
        *keys,
    )

    if value is MISSING or value is None:
        return None

    if not isinstance(
        value,
        int,
    ) or isinstance(
        value,
        bool,
    ):
        raise UpstreamInvalidResponseError("xmla")

    return value
