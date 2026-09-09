from typing import Any

from app.domain.lineage_ids import stable_lineage_id
from app.schemas.snowflake_lineage import (
    SnowflakeDependency,
    SnowflakeLineageSnapshot,
    SnowflakeLineageWarning,
    SnowflakeObjectReference,
)

_REQUIRED_COLUMNS = (
    "REFERENCED_DATABASE",
    "REFERENCED_SCHEMA",
    "REFERENCED_OBJECT_NAME",
    "REFERENCED_OBJECT_DOMAIN",
    "REFERENCING_DATABASE",
    "REFERENCING_SCHEMA",
    "REFERENCING_OBJECT_NAME",
    "REFERENCING_OBJECT_DOMAIN",
    "DEPENDENCY_TYPE",
)


class SnowflakeLineageService:
    def normalize_rows(
        self,
        *,
        account_identifier: str,
        rows: list[dict[str, Any]],
    ) -> SnowflakeLineageSnapshot:
        objects: dict[str, SnowflakeObjectReference] = {}
        dependencies: list[SnowflakeDependency] = []
        warnings: list[SnowflakeLineageWarning] = []
        seen_edges: set[tuple[str, str, str]] = set()

        for row_index, raw_row in enumerate(rows):
            row = {str(key).upper(): value for key, value in raw_row.items()}
            if not self._valid_row(row):
                warnings.append(
                    SnowflakeLineageWarning(
                        code="SNOWFLAKE_DEPENDENCY_ROW_INVALID",
                        message="Snowflake dependency row is incomplete or invalid.",
                        row_index=row_index,
                    )
                )
                continue

            source = self._object(
                account_identifier=account_identifier,
                database=str(row["REFERENCED_DATABASE"]),
                schema_name=str(row["REFERENCED_SCHEMA"]),
                object_name=str(row["REFERENCED_OBJECT_NAME"]),
                object_domain=str(row["REFERENCED_OBJECT_DOMAIN"]),
            )
            target = self._object(
                account_identifier=account_identifier,
                database=str(row["REFERENCING_DATABASE"]),
                schema_name=str(row["REFERENCING_SCHEMA"]),
                object_name=str(row["REFERENCING_OBJECT_NAME"]),
                object_domain=str(row["REFERENCING_OBJECT_DOMAIN"]),
            )
            dependency_type = str(row["DEPENDENCY_TYPE"])
            edge_key = (source.object_id, target.object_id, dependency_type.casefold())
            if edge_key in seen_edges:
                continue

            seen_edges.add(edge_key)
            objects.setdefault(source.object_id, source)
            objects.setdefault(target.object_id, target)
            dependencies.append(
                SnowflakeDependency(
                    source=source,
                    target=target,
                    dependency_type=dependency_type,
                )
            )

        ordered_objects = sorted(objects.values(), key=lambda item: item.qualified_name)
        dependencies.sort(
            key=lambda item: (item.source.qualified_name, item.target.qualified_name)
        )
        return SnowflakeLineageSnapshot(
            account_identifier=account_identifier,
            objects=ordered_objects,
            dependencies=dependencies,
            warnings=warnings,
            object_count=len(ordered_objects),
            dependency_count=len(dependencies),
        )

    @staticmethod
    def _valid_row(row: dict[str, Any]) -> bool:
        return all(
            isinstance(row.get(column), str) and row[column].strip()
            for column in _REQUIRED_COLUMNS
        )

    @staticmethod
    def _object(
        *,
        account_identifier: str,
        database: str,
        schema_name: str,
        object_name: str,
        object_domain: str,
    ) -> SnowflakeObjectReference:
        qualified_name = f"{database}.{schema_name}.{object_name}"
        return SnowflakeObjectReference(
            object_id=stable_lineage_id(
                "snowflake",
                account_identifier,
                database,
                schema_name,
                object_name,
                object_domain,
            ),
            database=database,
            schema_name=schema_name,
            object_name=object_name,
            object_domain=object_domain,
            qualified_name=qualified_name,
        )
