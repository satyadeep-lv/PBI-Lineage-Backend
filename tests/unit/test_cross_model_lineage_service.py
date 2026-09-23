import pytest

from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)
from app.schemas.scanner import (
    ScannerResultResponse,
    ScannerResultSummary,
    ScannerScanResponse,
)
from app.schemas.semantic_model import SemanticModel, SemanticModelListResponse
from app.services.cross_model_lineage_service import (
    CrossModelLineageService,
    build_lineage_tag_index,
)

PRIMARY_WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"
PRIMARY_DATASET_ID = "22222222-2222-2222-2222-222222222222"
UPSTREAM_WORKSPACE_ID = "33333333-3333-3333-3333-333333333333"
UPSTREAM_DATASET_ID = "44444444-4444-4444-4444-444444444444"
SCAN_ID = "55555555-5555-5555-5555-555555555555"


class _ScannerService:
    def __init__(self, scan_result_payload: dict) -> None:
        self.scan_result_payload = scan_result_payload

    async def start_scan(self, *, access_token, request):
        return ScannerScanResponse(
            scan_id=SCAN_ID,
            created_at="2026-01-01T00:00:00Z",
            status="NotStarted",
        )

    async def get_scan_status(self, *, access_token, scan_id):
        return ScannerScanResponse(
            scan_id=scan_id,
            created_at="2026-01-01T00:00:00Z",
            status="Succeeded",
        )

    async def get_scan_result(self, *, access_token, scan_id):
        return ScannerResultResponse(
            scan_id=scan_id,
            sections=sorted(self.scan_result_payload),
            summary=ScannerResultSummary(),
            payload=self.scan_result_payload,
        )


class _SemanticModelService:
    async def list_semantic_models(self, *, workspace_id, access_token):
        return SemanticModelListResponse(
            workspace_id=workspace_id,
            semantic_models=[
                SemanticModel(id=UPSTREAM_DATASET_ID, name="NativeQueryReoprt"),
            ],
            count=1,
        )


class _SemanticModelDefinitionService:
    async def get_parsed_definition(
        self,
        *,
        workspace_id,
        semantic_model_id,
        access_token,
        definition_format,
    ):
        return ParsedSemanticModelResponse(
            workspace_id=workspace_id,
            semantic_model_id=semantic_model_id,
            format="TMDL",
            tables=[
                ParsedSemanticModelTable(
                    name="Employees",
                    columns=[
                        ParsedSemanticModelColumn(
                            name="EmployeeId",
                            lineage_tag="tag-employee-id",
                        )
                    ],
                )
            ],
        )


@pytest.mark.asyncio
async def test_discover_finds_upstream_dataset_and_fetches_its_model():
    scan_payload = {
        "workspaces": [
            {
                "id": PRIMARY_WORKSPACE_ID,
                "datasets": [
                    {
                        "id": PRIMARY_DATASET_ID,
                        "upstreamDatasets": [
                            {
                                "targetDatasetId": UPSTREAM_DATASET_ID,
                                "groupId": UPSTREAM_WORKSPACE_ID,
                            }
                        ],
                    }
                ],
            }
        ]
    }
    service = CrossModelLineageService(
        scanner_service=_ScannerService(scan_payload),
        semantic_model_service=_SemanticModelService(),
        semantic_model_definition_service=_SemanticModelDefinitionService(),
    )

    result = await service.discover(
        primary_dataset_ids={PRIMARY_DATASET_ID},
        primary_workspace_ids={PRIMARY_WORKSPACE_ID},
        powerbi_access_token="powerbi-token",
        fabric_access_token="fabric-token",
        semantic_model_definition_format="TMDL",
    )

    assert result.warnings == []
    ref = result.upstream_refs[UPSTREAM_DATASET_ID]
    assert ref.workspace_id == UPSTREAM_WORKSPACE_ID
    assert ref.name == "NativeQueryReoprt"
    assert result.upstream_models[UPSTREAM_DATASET_ID].tables[0].name == "Employees"


@pytest.mark.asyncio
async def test_discover_returns_empty_when_no_upstream_datasets():
    scan_payload = {
        "workspaces": [
            {
                "id": PRIMARY_WORKSPACE_ID,
                "datasets": [{"id": PRIMARY_DATASET_ID, "upstreamDatasets": []}],
            }
        ]
    }
    service = CrossModelLineageService(
        scanner_service=_ScannerService(scan_payload),
        semantic_model_service=_SemanticModelService(),
        semantic_model_definition_service=_SemanticModelDefinitionService(),
    )

    result = await service.discover(
        primary_dataset_ids={PRIMARY_DATASET_ID},
        primary_workspace_ids={PRIMARY_WORKSPACE_ID},
        powerbi_access_token="powerbi-token",
        fabric_access_token="fabric-token",
        semantic_model_definition_format="TMDL",
    )

    assert result.upstream_refs == {}
    assert result.upstream_models == {}
    assert result.warnings == []


@pytest.mark.asyncio
async def test_discover_excludes_upstream_ref_that_is_actually_a_primary_dataset():
    scan_payload = {
        "workspaces": [
            {
                "id": PRIMARY_WORKSPACE_ID,
                "datasets": [
                    {
                        "id": PRIMARY_DATASET_ID,
                        "upstreamDatasets": [
                            {
                                "targetDatasetId": PRIMARY_DATASET_ID,
                                "groupId": PRIMARY_WORKSPACE_ID,
                            }
                        ],
                    }
                ],
            }
        ]
    }
    service = CrossModelLineageService(
        scanner_service=_ScannerService(scan_payload),
        semantic_model_service=_SemanticModelService(),
        semantic_model_definition_service=_SemanticModelDefinitionService(),
    )

    result = await service.discover(
        primary_dataset_ids={PRIMARY_DATASET_ID},
        primary_workspace_ids={PRIMARY_WORKSPACE_ID},
        powerbi_access_token="powerbi-token",
        fabric_access_token="fabric-token",
        semantic_model_definition_format="TMDL",
    )

    assert result.upstream_refs == {}


def test_build_lineage_tag_index_matches_columns_across_models():
    primary = {
        PRIMARY_DATASET_ID: ParsedSemanticModelResponse(
            workspace_id=PRIMARY_WORKSPACE_ID,
            semantic_model_id=PRIMARY_DATASET_ID,
            tables=[
                ParsedSemanticModelTable(
                    name="Employees",
                    columns=[
                        ParsedSemanticModelColumn(
                            name="EmployeeId",
                            source_lineage_tag="tag-employee-id",
                        )
                    ],
                )
            ],
        )
    }
    upstream = {
        UPSTREAM_DATASET_ID: ParsedSemanticModelResponse(
            workspace_id=UPSTREAM_WORKSPACE_ID,
            semantic_model_id=UPSTREAM_DATASET_ID,
            tables=[
                ParsedSemanticModelTable(
                    name="Employees",
                    columns=[
                        ParsedSemanticModelColumn(
                            name="EmployeeId",
                            lineage_tag="tag-employee-id",
                        )
                    ],
                )
            ],
        )
    }

    index = build_lineage_tag_index(primary_models=primary, upstream_models=upstream)

    matches = index["tag-employee-id"]
    assert len(matches) == 1
    dataset_id, semantic_object = matches[0]
    assert dataset_id == UPSTREAM_DATASET_ID
    assert semantic_object.table_name == "Employees"
    assert semantic_object.object_name == "EmployeeId"
