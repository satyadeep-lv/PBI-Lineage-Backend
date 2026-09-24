from datetime import UTC, datetime

from app.ai.composition.dax_narrator import describe
from app.ai.models.context import ResolvedAIContext
from app.ai.models.enums import VerificationStatus
from app.ai.models.evidence import EvidenceConflict, EvidenceItem
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelMeasure,
)


def _find_measure(
    context: ResolvedAIContext,
) -> tuple[str, ParsedSemanticModelMeasure] | None:
    resolved = context.resolved_object
    model = context.parsed_semantic_model

    if resolved is None or model is None or resolved.object_type != "measure":
        return None

    for table in model.tables:
        if table.name.casefold() != resolved.table_name.casefold():
            continue

        for measure in table.measures:
            if measure.name.casefold() == resolved.object_name.casefold():
                return table.name, measure

    return None


def _find_column(
    context: ResolvedAIContext,
) -> tuple[str, ParsedSemanticModelColumn] | None:
    resolved = context.resolved_object
    model = context.parsed_semantic_model

    if resolved is None or model is None:
        return None

    if resolved.object_type not in ("column", "calculated_column"):
        return None

    for table in model.tables:
        if table.name.casefold() != resolved.table_name.casefold():
            continue

        for column in table.columns:
            if column.name.casefold() == resolved.object_name.casefold():
                return table.name, column

    return None


def get_measure_definition(context: ResolvedAIContext) -> list[EvidenceItem]:
    found = _find_measure(context)

    if found is None:
        return []

    table_name, measure = found

    if measure.expression is None:
        return []

    return [
        EvidenceItem(
            evidence_id="",
            object_type="measure",
            object_id=f"{table_name}[{measure.name}]",
            object_name=measure.name,
            fact_type="definition",
            source_type="tmdl",
            value=measure.expression,
            plain_language=describe(
                measure.expression,
                object_name=measure.name,
            ),
            workspace_id=context.workspace_id,
            semantic_model_id=context.semantic_model_id,
            verification_status=VerificationStatus.VERIFIED,
            retrieved_at=datetime.now(UTC),
            source_reference=measure.source_path,
        )
    ]


def get_calculated_column_definition(
    context: ResolvedAIContext,
) -> list[EvidenceItem]:
    found = _find_column(context)

    if found is None:
        return []

    table_name, column = found

    if column.expression is None:
        return []

    return [
        EvidenceItem(
            evidence_id="",
            object_type="calculated_column",
            object_id=f"{table_name}[{column.name}]",
            object_name=column.name,
            fact_type="definition",
            source_type="tmdl",
            value=column.expression,
            plain_language=describe(
                column.expression,
                object_name=column.name,
            ),
            workspace_id=context.workspace_id,
            semantic_model_id=context.semantic_model_id,
            verification_status=VerificationStatus.VERIFIED,
            retrieved_at=datetime.now(UTC),
            source_reference=column.source_path,
        )
    ]


def detect_measure_conflict(
    context: ResolvedAIContext,
) -> EvidenceConflict | None:
    """TMDL-vs-XMLA DAX conflict check for the resolved measure.

    Opt-in only: `context.xmla_metadata` is never populated by the default
    resolver flow (XMLA needs a Windows/MSOLAP-configured host), so this
    never blocks or slows the primary TMDL-only evidence path. It only
    fires when a caller explicitly supplies XMLA metadata.
    """
    found = _find_measure(context)

    if found is None or context.xmla_metadata is None:
        return None

    table_name, tmdl_measure = found

    xmla_measure = None
    for xmla_table in context.xmla_metadata.tables:
        if xmla_table.name.casefold() != table_name.casefold():
            continue

        for measure in xmla_table.measures:
            if measure.name.casefold() == tmdl_measure.name.casefold():
                xmla_measure = measure
                break

    if (
        xmla_measure is None
        or xmla_measure.expression is None
        or tmdl_measure.expression is None
    ):
        return None

    if _normalize_dax(xmla_measure.expression) == _normalize_dax(
        tmdl_measure.expression
    ):
        return None

    return EvidenceConflict(
        field="definition",
        definition_value=tmdl_measure.expression,
        runtime_value=xmla_measure.expression,
        object_name=f"{table_name}[{tmdl_measure.name}]",
    )


def _normalize_dax(expression: str) -> str:
    return " ".join(expression.split()).strip().casefold()
