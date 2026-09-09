import asyncio
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.core.exceptions import UpstreamInvalidResponseError
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelHierarchy,
    ParsedSemanticModelHierarchyLevel,
    ParsedSemanticModelMeasure,
    ParsedSemanticModelRelationship,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)
from app.schemas.semantic_model_metadata import (
    SemanticModelMetadataMatch,
    SemanticModelMetadataReconciliation,
    SemanticModelMetadataResponse,
)
from app.schemas.xmla_metadata import (
    XmlaSemanticModelColumn,
    XmlaSemanticModelHierarchy,
    XmlaSemanticModelHierarchyLevel,
    XmlaSemanticModelMeasure,
    XmlaSemanticModelMetadataResponse,
    XmlaSemanticModelRelationship,
    XmlaSemanticModelTable,
)
from app.services.semantic_model_definition_service import (
    SemanticModelDefinitionService,
)
from app.services.xmla_metadata_service import (
    XmlaMetadataService,
)

MetadataObjectType = Literal[
    "table",
    "column",
    "measure",
    "hierarchy",
    "hierarchy_level",
    "partition",
    "relationship",
]

DefinitionNamedObject = (
    ParsedSemanticModelColumn
    | ParsedSemanticModelMeasure
    | ParsedSemanticModelHierarchy
    | ParsedSemanticModelHierarchyLevel
)

XmlaNamedObject = (
    XmlaSemanticModelColumn
    | XmlaSemanticModelMeasure
    | XmlaSemanticModelHierarchy
    | XmlaSemanticModelHierarchyLevel
)


@dataclass(frozen=True)
class _MetadataCandidate:
    object_name: str
    key: str
    table_name: str | None = None
    source_path: str | None = None


class SemanticModelMetadataService:
    def __init__(
        self,
        *,
        definition_service: (SemanticModelDefinitionService | None) = None,
        xmla_metadata_service: (XmlaMetadataService | None) = None,
    ) -> None:
        self.definition_service = definition_service or SemanticModelDefinitionService()
        self.xmla_metadata_service = xmla_metadata_service or XmlaMetadataService()

    async def get_metadata(
        self,
        *,
        workspace_id: str,
        semantic_model_id: str,
        fabric_access_token: str,
        powerbi_access_token: str,
        workspace_name: str | None = None,
        database_name: str | None = None,
        definition_format: str = "TMDL",
    ) -> SemanticModelMetadataResponse:
        definition, xmla = await asyncio.gather(
            self.definition_service.get_parsed_definition(
                workspace_id=workspace_id,
                semantic_model_id=semantic_model_id,
                access_token=fabric_access_token,
                definition_format=definition_format,
            ),
            self.xmla_metadata_service.get_metadata(
                workspace_id=workspace_id,
                semantic_model_id=semantic_model_id,
                access_token=powerbi_access_token,
                workspace_name=workspace_name,
                database_name=database_name,
            ),
        )

        self._validate_source_identity(
            source=definition,
            workspace_id=workspace_id,
            semantic_model_id=semantic_model_id,
            provider="fabric",
        )
        self._validate_source_identity(
            source=xmla,
            workspace_id=workspace_id,
            semantic_model_id=semantic_model_id,
            provider="xmla",
        )

        return SemanticModelMetadataResponse(
            workspace_id=workspace_id,
            semantic_model_id=semantic_model_id,
            definition=definition,
            xmla=xmla,
            reconciliation=self._reconcile(
                definition=definition,
                xmla=xmla,
            ),
        )

    def _validate_source_identity(
        self,
        *,
        source: (ParsedSemanticModelResponse | XmlaSemanticModelMetadataResponse),
        workspace_id: str,
        semantic_model_id: str,
        provider: str,
    ) -> None:
        if (
            source.workspace_id != workspace_id
            or source.semantic_model_id != semantic_model_id
        ):
            raise UpstreamInvalidResponseError(provider)

    def _reconcile(
        self,
        *,
        definition: ParsedSemanticModelResponse,
        xmla: XmlaSemanticModelMetadataResponse,
    ) -> SemanticModelMetadataReconciliation:
        matches: list[SemanticModelMetadataMatch] = []

        self._append_matches(
            matches=matches,
            object_type="table",
            definition_candidates=[
                _MetadataCandidate(
                    object_name=table.name,
                    key=self._key(table.name),
                    source_path=table.source_path,
                )
                for table in definition.tables
            ],
            xmla_candidates=[
                _MetadataCandidate(
                    object_name=table.name,
                    key=self._key(table.name),
                )
                for table in xmla.tables
            ],
        )

        for definition_table in definition.tables:
            xmla_table = self._find_table(
                tables=xmla.tables,
                name=definition_table.name,
            )
            self._append_table_object_matches(
                matches=matches,
                definition_table=definition_table,
                xmla_table=xmla_table,
            )

        definition_table_keys = {self._key(table.name) for table in definition.tables}
        for xmla_table in xmla.tables:
            if self._key(xmla_table.name) not in definition_table_keys:
                self._append_table_object_matches(
                    matches=matches,
                    definition_table=None,
                    xmla_table=xmla_table,
                )

        self._append_matches(
            matches=matches,
            object_type="relationship",
            definition_candidates=[
                self._relationship_candidate(
                    relationship,
                    source_path=relationship.source_path,
                )
                for relationship in definition.relationships
            ],
            xmla_candidates=[
                self._relationship_candidate(relationship)
                for relationship in xmla.relationships
            ],
        )

        matched_count = sum(match.status == "matched" for match in matches)
        definition_only_count = sum(
            match.status == "definition_only" for match in matches
        )
        xmla_only_count = sum(match.status == "xmla_only" for match in matches)

        return SemanticModelMetadataReconciliation(
            matched_count=matched_count,
            definition_only_count=definition_only_count,
            xmla_only_count=xmla_only_count,
            matches=matches,
        )

    def _append_table_object_matches(
        self,
        *,
        matches: list[SemanticModelMetadataMatch],
        definition_table: ParsedSemanticModelTable | None,
        xmla_table: XmlaSemanticModelTable | None,
    ) -> None:
        table_name = (
            definition_table.name if definition_table is not None else xmla_table.name
        )
        definition_columns = (
            definition_table.columns if definition_table is not None else []
        )
        xmla_columns = xmla_table.columns if xmla_table is not None else []
        definition_measures = (
            definition_table.measures if definition_table is not None else []
        )
        xmla_measures = xmla_table.measures if xmla_table is not None else []
        definition_hierarchies = (
            definition_table.hierarchies if definition_table is not None else []
        )
        xmla_hierarchies = xmla_table.hierarchies if xmla_table is not None else []
        xmla_partitions = xmla_table.partitions if xmla_table is not None else []

        self._append_named_matches(
            matches=matches,
            object_type="column",
            table_name=table_name,
            definition_objects=definition_columns,
            xmla_objects=xmla_columns,
        )
        self._append_named_matches(
            matches=matches,
            object_type="measure",
            table_name=table_name,
            definition_objects=definition_measures,
            xmla_objects=xmla_measures,
        )
        self._append_hierarchy_matches(
            matches=matches,
            table_name=table_name,
            definition_hierarchies=definition_hierarchies,
            xmla_hierarchies=xmla_hierarchies,
        )
        self._append_matches(
            matches=matches,
            object_type="partition",
            definition_candidates=[],
            xmla_candidates=[
                _MetadataCandidate(
                    object_name=partition.name,
                    key=self._key(table_name, partition.name),
                    table_name=table_name,
                )
                for partition in xmla_partitions
            ],
        )

    def _append_named_matches(
        self,
        *,
        matches: list[SemanticModelMetadataMatch],
        object_type: MetadataObjectType,
        table_name: str,
        definition_objects: Sequence[DefinitionNamedObject],
        xmla_objects: Sequence[XmlaNamedObject],
        key_scope: str | None = None,
    ) -> None:
        scope = key_scope or table_name

        self._append_matches(
            matches=matches,
            object_type=object_type,
            definition_candidates=[
                _MetadataCandidate(
                    object_name=item.name,
                    key=self._key(scope, item.name),
                    table_name=table_name,
                    source_path=item.source_path,
                )
                for item in definition_objects
            ],
            xmla_candidates=[
                _MetadataCandidate(
                    object_name=item.name,
                    key=self._key(scope, item.name),
                    table_name=table_name,
                )
                for item in xmla_objects
            ],
        )

    def _append_hierarchy_matches(
        self,
        *,
        matches: list[SemanticModelMetadataMatch],
        table_name: str,
        definition_hierarchies: Sequence[ParsedSemanticModelHierarchy],
        xmla_hierarchies: Sequence[XmlaSemanticModelHierarchy],
    ) -> None:
        self._append_named_matches(
            matches=matches,
            object_type="hierarchy",
            table_name=table_name,
            definition_objects=definition_hierarchies,
            xmla_objects=xmla_hierarchies,
        )

        definition_by_key = {
            self._key(hierarchy.name): hierarchy for hierarchy in definition_hierarchies
        }
        xmla_by_key = {
            self._key(hierarchy.name): hierarchy for hierarchy in xmla_hierarchies
        }

        hierarchy_keys = list(definition_by_key)
        hierarchy_keys.extend(
            key for key in xmla_by_key if key not in definition_by_key
        )

        for key in hierarchy_keys:
            definition_hierarchy = definition_by_key.get(key)
            xmla_hierarchy = xmla_by_key.get(key)
            hierarchy_name = (
                definition_hierarchy.name
                if definition_hierarchy is not None
                else xmla_hierarchy.name
            )
            self._append_named_matches(
                matches=matches,
                object_type="hierarchy_level",
                table_name=table_name,
                definition_objects=(
                    definition_hierarchy.levels
                    if definition_hierarchy is not None
                    else []
                ),
                xmla_objects=(
                    xmla_hierarchy.levels if xmla_hierarchy is not None else []
                ),
                key_scope=(f"{table_name}\u001f{hierarchy_name}"),
            )

    def _append_matches(
        self,
        *,
        matches: list[SemanticModelMetadataMatch],
        object_type: MetadataObjectType,
        definition_candidates: list[_MetadataCandidate],
        xmla_candidates: list[_MetadataCandidate],
    ) -> None:
        xmla_by_key: dict[
            str,
            list[_MetadataCandidate],
        ] = defaultdict(list)
        for candidate in xmla_candidates:
            xmla_by_key[candidate.key].append(candidate)

        for definition_candidate in definition_candidates:
            xmla_matches = xmla_by_key.get(
                definition_candidate.key,
            )
            xmla_candidate = xmla_matches.pop(0) if xmla_matches else None
            matches.append(
                SemanticModelMetadataMatch(
                    object_type=object_type,
                    object_name=definition_candidate.object_name,
                    table_name=definition_candidate.table_name,
                    status=(
                        "matched" if xmla_candidate is not None else "definition_only"
                    ),
                    definition_source_path=(definition_candidate.source_path),
                    xmla_object_name=(
                        xmla_candidate.object_name
                        if xmla_candidate is not None
                        else None
                    ),
                )
            )

        for remaining_candidates in xmla_by_key.values():
            for xmla_candidate in remaining_candidates:
                matches.append(
                    SemanticModelMetadataMatch(
                        object_type=object_type,
                        object_name=xmla_candidate.object_name,
                        table_name=xmla_candidate.table_name,
                        status="xmla_only",
                        xmla_object_name=(xmla_candidate.object_name),
                    )
                )

    def _find_table(
        self,
        *,
        tables: Sequence[XmlaSemanticModelTable],
        name: str,
    ) -> XmlaSemanticModelTable | None:
        target_key = self._key(name)

        return next(
            (table for table in tables if self._key(table.name) == target_key),
            None,
        )

    def _relationship_candidate(
        self,
        relationship: (ParsedSemanticModelRelationship | XmlaSemanticModelRelationship),
        *,
        source_path: str | None = None,
    ) -> _MetadataCandidate:
        object_name = relationship.name or self._relationship_identity(relationship)

        return _MetadataCandidate(
            object_name=object_name,
            key=self._relationship_identity(relationship),
            source_path=source_path,
        )

    def _relationship_identity(
        self,
        relationship: (ParsedSemanticModelRelationship | XmlaSemanticModelRelationship),
    ) -> str:
        fields = (
            relationship.from_table,
            relationship.from_column,
            relationship.to_table,
            relationship.to_column,
        )

        if any(fields):
            return self._key(*[value or "" for value in fields])

        return self._key(relationship.name or "")

    @staticmethod
    def _key(*parts: str) -> str:
        return "\u001f".join(part.strip().casefold() for part in parts)
