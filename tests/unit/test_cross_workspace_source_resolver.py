import asyncio

import pytest

from app.core.exceptions import AppException
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelExpression,
    ParsedSemanticModelPartition,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)
from app.schemas.semantic_model import SemanticModel, SemanticModelListResponse
from app.schemas.workspace import Workspace, WorkspaceListResponse
from app.services.cross_workspace_source_resolver import (
    CrossWorkspaceSourceResolver,
)
from app.services.physical_source_service import PhysicalSourceDiscoveryService

PRIMARY_WORKSPACE = "11111111-1111-1111-1111-111111111111"
PRIMARY_MODEL = "22222222-2222-2222-2222-222222222222"
UPSTREAM_WORKSPACE = "33333333-3333-3333-3333-333333333333"
UPSTREAM_MODEL = "44444444-4444-4444-4444-444444444444"

SHARED_EXPRESSION = (
    "let\n"
    "    Source = AnalysisServices.Database("
    '"powerbi://api.powerbi.com/v1.0/myorg/DEV", "Upstream Model"),\n'
    "    Cubes = Table.Combine(Source[Data])\n"
    "in\n"
    "    Cubes"
)


def _composite_model(*, source_lineage_tag: str | None = "tag-employees"):
    return ParsedSemanticModelResponse(
        workspace_id=PRIMARY_WORKSPACE,
        semantic_model_id=PRIMARY_MODEL,
        format="TMDL",
        expressions=[
            ParsedSemanticModelExpression(
                name="DirectQuery to AS - Upstream Model",
                expression=SHARED_EXPRESSION,
            )
        ],
        tables=[
            ParsedSemanticModelTable(
                name="EMPLOYEES",
                source_lineage_tag=source_lineage_tag,
                partitions=[
                    ParsedSemanticModelPartition(
                        name="EMPLOYEES",
                        source_type="entity",
                        mode="directQuery",
                        entity_name="EMPLOYEES",
                        expression_source="DirectQuery to AS - Upstream Model",
                    )
                ],
            )
        ],
    )


def _upstream_model(*, table_name: str = "EMPLOYEES"):
    return ParsedSemanticModelResponse(
        workspace_id=UPSTREAM_WORKSPACE,
        semantic_model_id=UPSTREAM_MODEL,
        format="TMDL",
        tables=[
            ParsedSemanticModelTable(
                name=table_name,
                lineage_tag="tag-employees",
                partitions=[
                    ParsedSemanticModelPartition(
                        name=table_name,
                        source_type="m",
                        mode="import",
                        expression=(
                            'Snowflake.Databases("acme.snowflakecomputing.com",'
                            '"COMPUTE_WH")'
                            '{[Name="POC_DB",Kind="Database"]}[Data]'
                            '{[Name="HUMAN_RESOURCES",Kind="Schema"]}[Data]'
                            '{[Name="EMPLOYEES",Kind="Table"]}[Data]'
                        ),
                    )
                ],
            )
        ],
    )


class _Workspaces:
    def __init__(self, workspaces=None):
        self.workspaces = (
            workspaces
            if workspaces is not None
            else [Workspace(id=UPSTREAM_WORKSPACE, name="DEV")]
        )

    async def list_workspaces(self, *, access_token, top, skip):
        return WorkspaceListResponse(
            workspaces=self.workspaces,
            count=len(self.workspaces),
            top=top,
            skip=skip,
        )


class _Models:
    def __init__(self, models=None):
        self.models = (
            models
            if models is not None
            else [SemanticModel(id=UPSTREAM_MODEL, name="Upstream Model")]
        )

    async def list_semantic_models(self, *, workspace_id, access_token):
        return SemanticModelListResponse(
            workspace_id=workspace_id,
            semantic_models=self.models,
            count=len(self.models),
        )


class _Definitions:
    def __init__(self, model=None, error: Exception | None = None):
        self.model = model if model is not None else _upstream_model()
        self.error = error
        self.calls = 0

    async def get_parsed_definition(
        self,
        *,
        workspace_id,
        semantic_model_id,
        access_token,
        definition_format,
    ):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.model


async def _resolve(primary, *, workspaces=None, models=None, definitions=None):
    physical = PhysicalSourceDiscoveryService().discover(primary)
    key = (PRIMARY_WORKSPACE, PRIMARY_MODEL)
    resolver = CrossWorkspaceSourceResolver(
        workspace_service=workspaces or _Workspaces(),
        semantic_model_service=models or _Models(),
        semantic_model_definition_service=definitions or _Definitions(),
    )
    resolved, warnings = await resolver.resolve(
        physical_by_model={key: physical},
        models_by_key={key: primary},
        powerbi_access_token="token",
        fabric_access_token="token",
        definition_format="TMDL",
    )
    return resolved[key], warnings


@pytest.mark.asyncio
async def test_composite_model_resolves_to_the_upstream_database():
    resolved, warnings = await _resolve(_composite_model())

    assert warnings == []
    assert [source.provider for source in resolved.sources] == ["snowflake"]
    source = resolved.sources[0]
    assert source.server == "acme.snowflakecomputing.com"
    assert source.database == "POC_DB"
    assert source.schema_name == "HUMAN_RESOURCES"
    assert source.object_name == "EMPLOYEES"
    assert source.via_workspace_name == "DEV"
    assert source.via_semantic_model_name == "Upstream Model"
    assert source.via_semantic_table == "EMPLOYEES"
    assert resolved.mappings[0].source_ids == [source.source_id]


@pytest.mark.asyncio
async def test_upstream_table_is_matched_by_lineage_tag_after_a_rename():
    # The upstream table was renamed, so only `sourceLineageTag` still links
    # the two sides together.
    definitions = _Definitions(model=_upstream_model(table_name="STAFF"))

    resolved, warnings = await _resolve(
        _composite_model(),
        definitions=definitions,
    )

    assert warnings == []
    assert resolved.sources[0].via_semantic_table == "STAFF"
    assert resolved.sources[0].database == "POC_DB"


@pytest.mark.asyncio
async def test_entity_name_is_used_when_no_lineage_tag_is_available():
    resolved, warnings = await _resolve(
        _composite_model(source_lineage_tag=None),
    )

    assert warnings == []
    assert resolved.sources[0].object_name == "EMPLOYEES"


@pytest.mark.asyncio
async def test_hop_is_kept_with_a_warning_when_the_workspace_is_not_visible():
    resolved, warnings = await _resolve(
        _composite_model(),
        workspaces=_Workspaces(workspaces=[]),
    )

    assert [warning.code for warning in warnings] == [
        "CROSS_WORKSPACE_WORKSPACE_NOT_FOUND"
    ]
    # The row survives, still pointing at the Power BI model, rather than
    # vanishing from the dataset.
    assert [source.provider for source in resolved.sources] == ["analysis_services"]
    assert resolved.mappings[0].source_ids == [resolved.sources[0].source_id]


@pytest.mark.asyncio
async def test_unreadable_upstream_definition_degrades_to_a_warning():
    resolved, warnings = await _resolve(
        _composite_model(),
        definitions=_Definitions(
            error=AppException(
                code="FORBIDDEN",
                message="no access",
                status_code=403,
            )
        ),
    )

    assert [warning.code for warning in warnings] == [
        "CROSS_WORKSPACE_DEFINITION_UNAVAILABLE"
    ]
    assert "no access" in warnings[0].message
    assert [source.provider for source in resolved.sources] == ["analysis_services"]


@pytest.mark.asyncio
async def test_unmatched_table_reports_which_model_was_searched():
    definitions = _Definitions(model=_upstream_model(table_name="SOMETHING_ELSE"))
    definitions.model.tables[0].lineage_tag = "tag-other"

    resolved, warnings = await _resolve(
        _composite_model(),
        definitions=definitions,
    )

    assert [warning.code for warning in warnings] == [
        "CROSS_WORKSPACE_TABLE_NOT_MATCHED"
    ]
    assert "Upstream Model" in warnings[0].message
    assert [source.provider for source in resolved.sources] == ["analysis_services"]


@pytest.mark.asyncio
async def test_upstream_model_is_fetched_once_for_repeated_tables():
    primary = _composite_model()
    primary.tables.append(
        ParsedSemanticModelTable(
            name="PAYROLL_RECORDS",
            source_lineage_tag="tag-employees",
            partitions=[
                ParsedSemanticModelPartition(
                    name="PAYROLL_RECORDS",
                    source_type="entity",
                    mode="directQuery",
                    entity_name="PAYROLL_RECORDS",
                    expression_source="DirectQuery to AS - Upstream Model",
                )
            ],
        )
    )
    definitions = _Definitions()

    await _resolve(primary, definitions=definitions)

    assert definitions.calls == 1


@pytest.mark.asyncio
async def test_models_without_a_composite_hop_are_left_untouched():
    primary = ParsedSemanticModelResponse(
        workspace_id=PRIMARY_WORKSPACE,
        semantic_model_id=PRIMARY_MODEL,
        format="TMDL",
        tables=[
            ParsedSemanticModelTable(
                name="SALES",
                partitions=[
                    ParsedSemanticModelPartition(
                        name="SALES",
                        source_type="m",
                        expression=(
                            'Sql.Database("server", "DB")'
                            '{[Schema="dbo",Item="SALES"]}[Data]'
                        ),
                    )
                ],
            )
        ],
    )
    definitions = _Definitions()

    resolved, warnings = await _resolve(primary, definitions=definitions)

    assert warnings == []
    assert definitions.calls == 0
    assert resolved.sources[0].database == "DB"


@pytest.mark.asyncio
async def test_models_resolving_concurrently_share_one_upstream_fetch():
    # Two primary models point at the same upstream. They are now resolved
    # concurrently, so the second must await the first one's fetch instead of
    # starting its own.
    class _SlowDefinitions(_Definitions):
        async def get_parsed_definition(self, **kwargs):
            self.calls += 1
            await asyncio.sleep(0.01)
            return self.model

    definitions = _SlowDefinitions()
    second_key = (PRIMARY_WORKSPACE, "55555555-5555-5555-5555-555555555555")
    first_key = (PRIMARY_WORKSPACE, PRIMARY_MODEL)
    primary = _composite_model()
    discovery = PhysicalSourceDiscoveryService()

    resolver = CrossWorkspaceSourceResolver(
        workspace_service=_Workspaces(),
        semantic_model_service=_Models(),
        semantic_model_definition_service=definitions,
    )
    resolved, warnings = await resolver.resolve(
        physical_by_model={
            first_key: discovery.discover(primary),
            second_key: discovery.discover(primary),
        },
        models_by_key={first_key: primary, second_key: primary},
        powerbi_access_token="token",
        fabric_access_token="token",
        definition_format="TMDL",
    )

    assert definitions.calls == 1
    assert warnings == []
    for key in (first_key, second_key):
        assert [source.database for source in resolved[key].sources] == ["POC_DB"]


@pytest.mark.asyncio
async def test_a_composite_cycle_terminates_instead_of_deadlocking():
    # The upstream model points straight back at the primary one. Awaiting the
    # still-pending fetch would deadlock, so the walk has to stop.
    upstream = _upstream_model()
    upstream.expressions.append(
        ParsedSemanticModelExpression(
            name="DirectQuery to AS - Upstream Model",
            expression=SHARED_EXPRESSION,
        )
    )
    upstream.tables[0].partitions = [
        ParsedSemanticModelPartition(
            name="EMPLOYEES",
            source_type="entity",
            mode="directQuery",
            entity_name="EMPLOYEES",
            expression_source="DirectQuery to AS - Upstream Model",
        )
    ]

    resolved, _ = await asyncio.wait_for(
        _resolve(_composite_model(), definitions=_Definitions(model=upstream)),
        timeout=5,
    )

    # Nothing resolves past the cycle, and the hop is kept rather than lost.
    assert [source.provider for source in resolved.sources] == ["analysis_services"]
