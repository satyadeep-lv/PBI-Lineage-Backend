from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.normalized_report_definition import (
    NormalizedReportDefinitionResponse,
)
from app.schemas.parsed_semantic_model import ParsedSemanticModelResponse
from app.schemas.physical_source import PhysicalSourceDiscoveryResponse
from app.schemas.xmla_metadata import XmlaSemanticModelMetadataResponse


class ResolvedObject(BaseModel):
    """An object reference resolved against authorized, fetched evidence.

    Never built from a client-supplied ID/name alone — only populated once
    AIContextResolver has matched it against the caller's own authorized
    semantic model / report data.
    """

    object_type: Literal[
        "measure",
        "calculated_column",
        "column",
        "table",
    ]
    table_name: str
    object_name: str
    qualified_name: str


class ResolvedReport(BaseModel):
    """A report bound to the semantic model in view, with its definition.

    Fetched with the caller's own token, so it is only ever a report the
    caller can already open. Used to say which visuals an object reaches.
    """

    workspace_id: str
    workspace_name: str | None = None
    report_id: str
    report_name: str | None = None
    definition: NormalizedReportDefinitionResponse


class ResolvedAIContext(BaseModel):
    """Authenticated, access-checked context for one AI request.

    Frontend-supplied IDs are never trusted directly; every field here was
    either validated against the caller's own Power BI/Fabric access
    (workspace/report/semantic_model_id) or resolved from evidence fetched
    using that access (parsed_semantic_model, resolved_object).
    """

    workspace_id: str | None = None
    workspace_name: str | None = None
    report_id: str | None = None
    report_name: str | None = None
    semantic_model_id: str | None = None
    semantic_model_name: str | None = None
    # Where the model was actually read from, which is not always the
    # report's own workspace.
    semantic_model_workspace_id: str | None = None
    semantic_model_workspace_name: str | None = None

    parsed_semantic_model: ParsedSemanticModelResponse | None = None
    report_definition: NormalizedReportDefinitionResponse | None = None

    # Physical sources with composite-model hops already followed to the
    # real database, so the AI names the same tables the explorer does.
    physical_sources: PhysicalSourceDiscoveryResponse | None = None

    # Other reports bound to the same model, for visual impact when the
    # question is about an object rather than one report.
    related_reports: list[ResolvedReport] = Field(default_factory=list)

    # Populated only when a caller explicitly supplies live XMLA metadata
    # (e.g. a future opt-in resolver step, or a test) — not fetched by
    # default, since XMLA is an optional, Windows/MSOLAP-only integration.
    xmla_metadata: XmlaSemanticModelMetadataResponse | None = None

    resolved_object: ResolvedObject | None = None

    resolution_notes: list[str] = Field(default_factory=list)

    # What the best-effort enrichment could not establish (a model name, the
    # reports bound to a model). Shown to the reader so an answer can say
    # what it did not check; never a reason to refuse one.
    coverage_notes: list[str] = Field(default_factory=list)
