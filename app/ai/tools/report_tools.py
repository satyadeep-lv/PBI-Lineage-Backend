from datetime import UTC, datetime

from app.ai.models.context import ResolvedAIContext
from app.ai.models.enums import VerificationStatus
from app.ai.models.evidence import EvidenceItem


def get_report_summary(context: ResolvedAIContext) -> list[EvidenceItem]:
    report = context.report_definition

    if report is None:
        return []

    semantic_model_reference = None
    if report.semantic_model is not None:
        semantic_model_reference = (
            report.semantic_model.semantic_model_id or report.semantic_model.path
        )

    return [
        EvidenceItem(
            evidence_id="",
            object_type="report",
            object_id=report.report_id,
            object_name=report.report_id,
            fact_type="definition",
            source_type="pbir",
            value={
                "format": report.format,
                "page_count": report.page_count,
                "visual_count": report.visual_count,
                "semantic_model_reference": semantic_model_reference,
            },
            workspace_id=report.workspace_id,
            report_id=report.report_id,
            verification_status=VerificationStatus.VERIFIED,
            retrieved_at=datetime.now(UTC),
            source_reference=f"report:{report.report_id}",
        )
    ]


def get_report_pages(context: ResolvedAIContext) -> list[EvidenceItem]:
    report = context.report_definition

    if report is None:
        return []

    now = datetime.now(UTC)

    return [
        EvidenceItem(
            evidence_id="",
            object_type="report_page",
            object_id=page.name,
            object_name=page.display_name,
            fact_type="relationship",
            source_type="pbir",
            value={
                "visual_count": page.visual_count,
                "order": page.order,
                "is_active": page.is_active,
            },
            workspace_id=report.workspace_id,
            report_id=report.report_id,
            verification_status=VerificationStatus.VERIFIED,
            retrieved_at=now,
            source_reference=f"report_page:{report.report_id}.{page.name}",
        )
        for page in report.pages
    ]


def get_report_visuals(context: ResolvedAIContext) -> list[EvidenceItem]:
    report = context.report_definition

    if report is None:
        return []

    now = datetime.now(UTC)
    items: list[EvidenceItem] = []

    for page in report.pages:
        for visual in page.visuals:
            field_summaries = [
                {
                    "object_type": reference.object_type,
                    "table_name": reference.table_name,
                    "object_name": reference.object_name,
                    "usage": reference.usage,
                }
                for reference in visual.field_references
            ]
            fields = sorted(
                {
                    f"{reference.table_name}[{reference.object_name}]"
                    if reference.table_name
                    else str(reference.object_name)
                    for reference in visual.field_references
                    if reference.object_name
                }
            )
            label = visual.title or f"untitled {visual.visual_type or ''} visual"
            items.append(
                EvidenceItem(
                    evidence_id="",
                    object_type="visual",
                    object_id=visual.id,
                    object_name=visual.title or visual.internal_name,
                    fact_type="usage",
                    source_type="pbir",
                    value={
                        "visual_type": visual.visual_type,
                        "page": page.name,
                        "fields": field_summaries,
                    },
                    display_value=(
                        f"'{label}'"
                        + (f" ({visual.visual_type})" if visual.visual_type else "")
                        + f" on page '{page.display_name}'"
                        + (
                            f" uses {', '.join(fields)}"
                            if fields
                            else " uses no fields"
                        )
                    ),
                    workspace_id=report.workspace_id,
                    report_id=report.report_id,
                    verification_status=VerificationStatus.VERIFIED,
                    retrieved_at=now,
                    source_reference=(
                        f"visual:{report.report_id}.{page.name}.{visual.id}"
                    ),
                )
            )

    return items
