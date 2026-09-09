import pytest

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
from app.schemas.xmla_metadata import (
    XmlaSemanticModelColumn,
    XmlaSemanticModelHierarchy,
    XmlaSemanticModelHierarchyLevel,
    XmlaSemanticModelMeasure,
    XmlaSemanticModelMetadataResponse,
    XmlaSemanticModelPartition,
    XmlaSemanticModelRelationship,
    XmlaSemanticModelTable,
)
from app.services.semantic_model_metadata_service import (
    SemanticModelMetadataService,
)

WORKSPACE_ID = "workspace-123"
SEMANTIC_MODEL_ID = "model-123"


class _FakeDefinitionService:
    def __init__(
        self,
        response: ParsedSemanticModelResponse,
    ) -> None:
        self.response = response
        self.calls: list[dict] = []

    async def get_parsed_definition(
        self,
        **kwargs,
    ) -> ParsedSemanticModelResponse:
        self.calls.append(kwargs)

        return self.response


class _FakeXmlaMetadataService:
    def __init__(
        self,
        response: XmlaSemanticModelMetadataResponse,
    ) -> None:
        self.response = response
        self.calls: list[dict] = []

    async def get_metadata(
        self,
        **kwargs,
    ) -> XmlaSemanticModelMetadataResponse:
        self.calls.append(kwargs)

        return self.response


def _definition_response() -> ParsedSemanticModelResponse:
    return ParsedSemanticModelResponse(
        workspace_id=WORKSPACE_ID,
        semantic_model_id=SEMANTIC_MODEL_ID,
        format="TMDL",
        tables=[
            ParsedSemanticModelTable(
                name="Sales",
                source_path="definition/tables/Sales.tmdl",
                columns=[
                    ParsedSemanticModelColumn(
                        name="Amount",
                        source_path=("definition/tables/Sales.tmdl"),
                    ),
                    ParsedSemanticModelColumn(
                        name="Budget",
                        source_path=("definition/tables/Sales.tmdl"),
                    ),
                ],
                measures=[
                    ParsedSemanticModelMeasure(
                        name="Total Sales",
                        source_path=("definition/tables/Sales.tmdl"),
                    )
                ],
                hierarchies=[
                    ParsedSemanticModelHierarchy(
                        name="Calendar",
                        source_path=("definition/tables/Sales.tmdl"),
                        levels=[
                            ParsedSemanticModelHierarchyLevel(
                                name="Year",
                                source_path=("definition/tables/Sales.tmdl"),
                            )
                        ],
                    )
                ],
            )
        ],
        relationships=[
            ParsedSemanticModelRelationship(
                source_path="definition/model.tmdl",
                from_table="Sales",
                from_column="DateKey",
                to_table="Date",
                to_column="DateKey",
            )
        ],
    )


def _xmla_response(
    *,
    semantic_model_id: str = SEMANTIC_MODEL_ID,
) -> XmlaSemanticModelMetadataResponse:
    return XmlaSemanticModelMetadataResponse(
        workspace_id=WORKSPACE_ID,
        semantic_model_id=semantic_model_id,
        xmla_endpoint=("powerbi://api.powerbi.com/v1.0/myorg/Sales%20Workspace"),
        database_name="Sales Model",
        table_count=1,
        column_count=2,
        measure_count=1,
        relationship_count=1,
        hierarchy_count=1,
        partition_count=1,
        tables=[
            XmlaSemanticModelTable(
                name="sales",
                columns=[
                    XmlaSemanticModelColumn(
                        name="amount",
                    ),
                    XmlaSemanticModelColumn(
                        name="Margin",
                    ),
                ],
                measures=[
                    XmlaSemanticModelMeasure(
                        name="Total Sales",
                    )
                ],
                hierarchies=[
                    XmlaSemanticModelHierarchy(
                        name="Calendar",
                        levels=[XmlaSemanticModelHierarchyLevel(name="Year")],
                    )
                ],
                partitions=[XmlaSemanticModelPartition(name="Sales")],
            )
        ],
        relationships=[
            XmlaSemanticModelRelationship(
                name="Sales_Date",
                from_table="Sales",
                from_column="DateKey",
                to_table="Date",
                to_column="DateKey",
            )
        ],
    )


@pytest.mark.asyncio
async def test_get_metadata_preserves_sources_and_reconciles_objects():
    definition_service = _FakeDefinitionService(_definition_response())
    xmla_metadata_service = _FakeXmlaMetadataService(_xmla_response())
    service = SemanticModelMetadataService(
        definition_service=definition_service,
        xmla_metadata_service=xmla_metadata_service,
    )

    result = await service.get_metadata(
        workspace_id=WORKSPACE_ID,
        semantic_model_id=SEMANTIC_MODEL_ID,
        fabric_access_token="fabric-token",
        powerbi_access_token="powerbi-token",
        workspace_name="Sales Workspace",
        database_name="Sales Model",
    )

    assert result.definition.format == "TMDL"
    assert result.xmla.database_name == "Sales Model"
    assert result.reconciliation.matched_count == 6
    assert result.reconciliation.definition_only_count == 1
    assert result.reconciliation.xmla_only_count == 2
    assert [
        match.object_name
        for match in result.reconciliation.matches
        if match.status == "xmla_only"
    ] == ["Margin", "Sales"]
    assert [
        match.object_name
        for match in result.reconciliation.matches
        if match.status == "definition_only"
    ] == ["Budget"]
    assert definition_service.calls == [
        {
            "workspace_id": WORKSPACE_ID,
            "semantic_model_id": SEMANTIC_MODEL_ID,
            "access_token": "fabric-token",
            "definition_format": "TMDL",
        }
    ]
    assert xmla_metadata_service.calls == [
        {
            "workspace_id": WORKSPACE_ID,
            "semantic_model_id": SEMANTIC_MODEL_ID,
            "access_token": "powerbi-token",
            "workspace_name": "Sales Workspace",
            "database_name": "Sales Model",
        }
    ]


@pytest.mark.asyncio
async def test_get_metadata_rejects_mismatched_xmla_identity():
    service = SemanticModelMetadataService(
        definition_service=_FakeDefinitionService(_definition_response()),
        xmla_metadata_service=_FakeXmlaMetadataService(
            _xmla_response(
                semantic_model_id="different-model",
            )
        ),
    )

    with pytest.raises(UpstreamInvalidResponseError) as exc_info:
        await service.get_metadata(
            workspace_id=WORKSPACE_ID,
            semantic_model_id=SEMANTIC_MODEL_ID,
            fabric_access_token="fabric-token",
            powerbi_access_token="powerbi-token",
        )

    assert exc_info.value.provider == "xmla"
