import asyncio
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.schemas.normalized_report_definition import (
    NormalizedReportDefinitionResponse,
    VisualFieldReference,
)
from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelHierarchy,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
)
from app.schemas.report_semantic_lineage import (
    ReportSemanticLineageResponse,
    SemanticLineageCandidate,
    SemanticLineageDiagnosticsSummary,
    SemanticLineageFieldMatch,
    SemanticLineageObject,
)
from app.services.report_definition_service import (
    ReportDefinitionService,
)
from app.services.semantic_model_definition_service import (
    SemanticModelDefinitionService,
)

MAX_CANDIDATE_SUGGESTIONS = 5


@dataclass(frozen=True)
class _LineageMatchResult:
    semantic_object: SemanticLineageObject | None = None
    reason: str | None = None
    match_confidence: float = 0.0
    candidate_suggestions: tuple[SemanticLineageCandidate, ...] = ()


class ReportSemanticLineageService:
    def __init__(self) -> None:
        self.report_definition_service = ReportDefinitionService()
        self.semantic_model_definition_service = SemanticModelDefinitionService()

    async def build_lineage(
        self,
        *,
        workspace_id: str,
        report_id: str,
        semantic_model_workspace_id: str,
        semantic_model_id: str,
        access_token: str,
        report_definition_format: str | None = "PBIR",
        semantic_model_definition_format: str = "TMDL",
    ) -> ReportSemanticLineageResponse:
        report_task = self.report_definition_service.get_normalized_definition(
            workspace_id=workspace_id,
            report_id=report_id,
            access_token=access_token,
            definition_format=(report_definition_format),
        )

        semantic_model_task = (
            self.semantic_model_definition_service.get_parsed_definition(
                workspace_id=(semantic_model_workspace_id),
                semantic_model_id=semantic_model_id,
                access_token=access_token,
                definition_format=(semantic_model_definition_format),
            )
        )

        report, semantic_model = await asyncio.gather(
            report_task,
            semantic_model_task,
        )

        return self.match(
            report=report,
            semantic_model=semantic_model,
            semantic_model_workspace_id=(semantic_model_workspace_id),
        )

    def match(
        self,
        *,
        report: NormalizedReportDefinitionResponse,
        semantic_model: ParsedSemanticModelResponse,
        semantic_model_workspace_id: str,
    ) -> ReportSemanticLineageResponse:
        index = _SemanticModelIndex(semantic_model)

        field_matches: list[SemanticLineageFieldMatch] = []

        for page in report.pages:
            for visual in page.visuals:
                for field_reference in visual.field_references:
                    match_result = index.find(field_reference)

                    status = (
                        "matched"
                        if (match_result.semantic_object is not None)
                        else "unmatched"
                    )

                    field_matches.append(
                        SemanticLineageFieldMatch(
                            page_name=page.name,
                            page_display_name=(page.display_name),
                            visual_id=visual.id,
                            visual_title=(visual.title),
                            visual_type=(visual.visual_type),
                            field_reference=(field_reference),
                            status=status,
                            semantic_object=(match_result.semantic_object),
                            reason=(match_result.reason),
                            match_confidence=(match_result.match_confidence),
                            candidate_suggestions=list(
                                match_result.candidate_suggestions
                            ),
                        )
                    )

        matched_count = sum(
            1 for field_match in field_matches if field_match.status == "matched"
        )

        warnings = list(report.warnings)
        warnings.extend(self._semantic_model_warnings(semantic_model))

        return ReportSemanticLineageResponse(
            workspace_id=report.workspace_id,
            report_id=report.report_id,
            semantic_model_workspace_id=(semantic_model_workspace_id),
            semantic_model_id=(semantic_model.semantic_model_id),
            total_field_reference_count=len(field_matches),
            matched_field_reference_count=(matched_count),
            unmatched_field_reference_count=(len(field_matches) - matched_count),
            field_matches=field_matches,
            diagnostics_summary=(self._build_diagnostics_summary(field_matches)),
            warnings=warnings,
        )

    @staticmethod
    def _build_diagnostics_summary(
        field_matches: list[SemanticLineageFieldMatch],
    ) -> SemanticLineageDiagnosticsSummary:
        status_counts = {
            "matched": 0,
            "unmatched": 0,
        }
        object_type_counts: dict[str, int] = {}
        match_counts: dict[
            str,
            dict[str, int],
        ] = {}
        reason_counts: dict[str, int] = {}

        for field_match in field_matches:
            status_counts[field_match.status] += 1

            object_type = field_match.field_reference.object_type
            object_type_counts[object_type] = (
                object_type_counts.get(
                    object_type,
                    0,
                )
                + 1
            )

            match_counts.setdefault(
                object_type,
                {
                    "matched": 0,
                    "unmatched": 0,
                },
            )[field_match.status] += 1

            if field_match.reason:
                reason_counts[field_match.reason] = (
                    reason_counts.get(
                        field_match.reason,
                        0,
                    )
                    + 1
                )

        return SemanticLineageDiagnosticsSummary(
            status_counts=status_counts,
            field_reference_object_type_counts=dict(sorted(object_type_counts.items())),
            match_counts_by_object_type={
                object_type: counts
                for object_type, counts in sorted(match_counts.items())
            },
            reason_counts=dict(sorted(reason_counts.items())),
        )

    @staticmethod
    def _semantic_model_warnings(
        semantic_model: ParsedSemanticModelResponse,
    ) -> list[str]:
        warnings: list[str] = []

        for warning in semantic_model.warnings:
            message = f"{warning.code}: {warning.message}"

            if warning.path:
                message = f"{message} ({warning.path})"

            warnings.append(message)

        return warnings


class _SemanticModelIndex:
    def __init__(
        self,
        semantic_model: ParsedSemanticModelResponse,
    ) -> None:
        self.tables = {_key(table.name): table for table in semantic_model.tables}
        self.columns = self._build_column_index(semantic_model)
        self.measures = self._build_measure_index(semantic_model)
        self.hierarchies = self._build_hierarchy_index(semantic_model)
        self.hierarchy_levels = self._build_hierarchy_level_index(semantic_model)
        self.objects_by_type = self._build_objects_by_type()

    def find(
        self,
        reference: VisualFieldReference,
    ) -> _LineageMatchResult:
        table_name = reference.table_name
        object_name = reference.object_name

        if not table_name:
            return self._unmatched_result(
                reference,
                "missing_table_name",
            )

        table_key = _key(table_name)

        if table_key not in self.tables:
            return self._unmatched_result(
                reference,
                "table_not_found",
            )

        if reference.object_type == "column":
            if not object_name:
                return self._unmatched_result(
                    reference,
                    "missing_object_name",
                )

            result = self.columns.get(
                (
                    table_key,
                    _key(object_name),
                )
            )

            return self._matched_or_unmatched_result(
                reference=reference,
                semantic_object=result,
                reason="object_not_found",
            )

        if reference.object_type == "measure":
            if not object_name:
                return self._unmatched_result(
                    reference,
                    "missing_object_name",
                )

            result = self.measures.get(
                (
                    table_key,
                    _key(object_name),
                )
            )

            return self._matched_or_unmatched_result(
                reference=reference,
                semantic_object=result,
                reason="object_not_found",
            )

        if reference.object_type == "hierarchy":
            hierarchy_name = reference.hierarchy_name or object_name

            if not hierarchy_name:
                return self._unmatched_result(
                    reference,
                    "missing_object_name",
                )

            result = self.hierarchies.get(
                (
                    table_key,
                    _key(hierarchy_name),
                )
            )

            return self._matched_or_unmatched_result(
                reference=reference,
                semantic_object=result,
                reason="hierarchy_not_found",
            )

        if reference.object_type == "hierarchy_level":
            hierarchy_name = reference.hierarchy_name
            level_name = reference.level_name or object_name

            if not hierarchy_name:
                return self._unmatched_result(
                    reference,
                    "missing_hierarchy_name",
                )

            if not level_name:
                return self._unmatched_result(
                    reference,
                    "missing_level_name",
                )

            if (
                table_key,
                _key(hierarchy_name),
            ) not in self.hierarchies:
                return self._unmatched_result(
                    reference,
                    "hierarchy_not_found",
                )

            result = self.hierarchy_levels.get(
                (
                    table_key,
                    _key(hierarchy_name),
                    _key(level_name),
                )
            )

            return self._matched_or_unmatched_result(
                reference=reference,
                semantic_object=result,
                reason="hierarchy_level_not_found",
            )

        return self._unmatched_result(
            reference,
            "unsupported_object_type",
        )

    def _matched_or_unmatched_result(
        self,
        *,
        reference: VisualFieldReference,
        semantic_object: SemanticLineageObject | None,
        reason: str,
    ) -> _LineageMatchResult:
        if semantic_object is not None:
            return _LineageMatchResult(
                semantic_object=semantic_object,
                match_confidence=1.0,
            )

        return self._unmatched_result(
            reference,
            reason,
        )

    def _unmatched_result(
        self,
        reference: VisualFieldReference,
        reason: str,
    ) -> _LineageMatchResult:
        return _LineageMatchResult(
            reason=reason,
            candidate_suggestions=tuple(self._candidate_suggestions(reference)),
        )

    def _candidate_suggestions(
        self,
        reference: VisualFieldReference,
    ) -> list[SemanticLineageCandidate]:
        requested_name = self._reference_object_name(reference)

        if not requested_name:
            return []

        objects = self.objects_by_type.get(
            reference.object_type,
            [],
        )

        suggestions: dict[
            tuple[str, str, str, str, str],
            SemanticLineageCandidate,
        ] = {}

        for semantic_object in objects:
            candidate = self._candidate_for_object(
                reference=reference,
                requested_name=requested_name,
                semantic_object=semantic_object,
            )

            if candidate is None:
                continue

            identity = self._semantic_object_identity(candidate.semantic_object)
            current = suggestions.get(identity)

            if current is None or candidate.confidence > current.confidence:
                suggestions[identity] = candidate

        return sorted(
            suggestions.values(),
            key=self._candidate_sort_key,
        )[:MAX_CANDIDATE_SUGGESTIONS]

    def _candidate_for_object(
        self,
        *,
        reference: VisualFieldReference,
        requested_name: str,
        semantic_object: SemanticLineageObject,
    ) -> SemanticLineageCandidate | None:
        requested_table_key = (
            _key(reference.table_name) if reference.table_name else None
        )
        candidate_table_key = _key(semantic_object.table_name)

        table_matches = requested_table_key == candidate_table_key
        object_matches = _key(requested_name) == _key(semantic_object.object_name)
        object_similarity = _similarity(
            requested_name,
            semantic_object.object_name,
        )

        if table_matches and object_similarity >= 0.6:
            return SemanticLineageCandidate(
                semantic_object=semantic_object,
                confidence=round(
                    min(
                        0.9,
                        0.55 + object_similarity * 0.35,
                    ),
                    2,
                ),
                reason="same_table_similar_object",
            )

        if object_matches:
            return SemanticLineageCandidate(
                semantic_object=semantic_object,
                confidence=0.75,
                reason="same_object_name",
            )

        if not reference.table_name:
            return None

        table_similarity = _similarity(
            reference.table_name,
            semantic_object.table_name,
        )

        if table_similarity >= 0.75 and object_similarity >= 0.5:
            return SemanticLineageCandidate(
                semantic_object=semantic_object,
                confidence=round(
                    min(
                        0.7,
                        0.35 + (table_similarity + object_similarity) / 2 * 0.35,
                    ),
                    2,
                ),
                reason="similar_table_and_object",
            )

        return None

    def _build_objects_by_type(
        self,
    ) -> dict[
        str,
        list[SemanticLineageObject],
    ]:
        objects_by_type: dict[
            str,
            dict[
                tuple[str, str, str, str, str],
                SemanticLineageObject,
            ],
        ] = {}

        for index in (
            self.columns,
            self.measures,
            self.hierarchies,
            self.hierarchy_levels,
        ):
            for semantic_object in index.values():
                objects_by_type.setdefault(
                    semantic_object.object_type,
                    {},
                )[self._semantic_object_identity(semantic_object)] = semantic_object

        return {
            object_type: sorted(
                values.values(),
                key=self._semantic_object_sort_key,
            )
            for object_type, values in (objects_by_type.items())
        }

    @staticmethod
    def _reference_object_name(
        reference: VisualFieldReference,
    ) -> str | None:
        if reference.object_type == "hierarchy":
            return reference.hierarchy_name or reference.object_name

        if reference.object_type == "hierarchy_level":
            return reference.level_name or reference.object_name

        return reference.object_name

    @staticmethod
    def _semantic_object_identity(
        semantic_object: SemanticLineageObject,
    ) -> tuple[str, str, str, str, str]:
        return (
            semantic_object.object_type,
            _key(semantic_object.table_name),
            _key(semantic_object.object_name),
            _key(semantic_object.hierarchy_name or ""),
            _key(semantic_object.level_name or ""),
        )

    @staticmethod
    def _semantic_object_sort_key(
        semantic_object: SemanticLineageObject,
    ) -> tuple[str, str, str, str]:
        return (
            _key(semantic_object.table_name),
            _key(semantic_object.hierarchy_name or ""),
            _key(semantic_object.object_name),
            _key(semantic_object.level_name or ""),
        )

    @staticmethod
    def _candidate_sort_key(
        candidate: SemanticLineageCandidate,
    ) -> tuple[float, str, str, str, str]:
        semantic_object = candidate.semantic_object

        return (
            -candidate.confidence,
            _key(semantic_object.table_name),
            _key(semantic_object.hierarchy_name or ""),
            _key(semantic_object.object_name),
            _key(semantic_object.level_name or ""),
        )

    @staticmethod
    def _build_column_index(
        semantic_model: ParsedSemanticModelResponse,
    ) -> dict[
        tuple[str, str],
        SemanticLineageObject,
    ]:
        index: dict[
            tuple[str, str],
            SemanticLineageObject,
        ] = {}

        for table in semantic_model.tables:
            for column in table.columns:
                lineage_object = SemanticLineageObject(
                    object_type="column",
                    table_name=table.name,
                    object_name=column.name,
                    source_path=(column.source_path or table.source_path),
                )

                index[
                    (
                        _key(table.name),
                        _key(column.name),
                    )
                ] = lineage_object

                if column.source_column:
                    index.setdefault(
                        (
                            _key(table.name),
                            _key(column.source_column),
                        ),
                        lineage_object,
                    )

        return index

    @staticmethod
    def _build_measure_index(
        semantic_model: ParsedSemanticModelResponse,
    ) -> dict[
        tuple[str, str],
        SemanticLineageObject,
    ]:
        index: dict[
            tuple[str, str],
            SemanticLineageObject,
        ] = {}

        for table in semantic_model.tables:
            for measure in table.measures:
                index[
                    (
                        _key(table.name),
                        _key(measure.name),
                    )
                ] = SemanticLineageObject(
                    object_type="measure",
                    table_name=table.name,
                    object_name=measure.name,
                    source_path=(measure.source_path or table.source_path),
                )

        return index

    @staticmethod
    def _build_hierarchy_index(
        semantic_model: ParsedSemanticModelResponse,
    ) -> dict[
        tuple[str, str],
        SemanticLineageObject,
    ]:
        index: dict[
            tuple[str, str],
            SemanticLineageObject,
        ] = {}

        for table in semantic_model.tables:
            for hierarchy in table.hierarchies:
                index[
                    (
                        _key(table.name),
                        _key(hierarchy.name),
                    )
                ] = SemanticLineageObject(
                    object_type="hierarchy",
                    table_name=table.name,
                    object_name=hierarchy.name,
                    source_path=(hierarchy.source_path or table.source_path),
                    hierarchy_name=hierarchy.name,
                )

        return index

    @staticmethod
    def _build_hierarchy_level_index(
        semantic_model: ParsedSemanticModelResponse,
    ) -> dict[
        tuple[str, str, str],
        SemanticLineageObject,
    ]:
        index: dict[
            tuple[str, str, str],
            SemanticLineageObject,
        ] = {}

        for table in semantic_model.tables:
            _SemanticModelIndex._index_table_hierarchies(
                index=index,
                table=table,
            )

        return index

    @staticmethod
    def _index_table_hierarchies(
        *,
        index: dict[
            tuple[str, str, str],
            SemanticLineageObject,
        ],
        table: ParsedSemanticModelTable,
    ) -> None:
        for hierarchy in table.hierarchies:
            _SemanticModelIndex._index_hierarchy_levels(
                index=index,
                table=table,
                hierarchy=hierarchy,
            )

    @staticmethod
    def _index_hierarchy_levels(
        *,
        index: dict[
            tuple[str, str, str],
            SemanticLineageObject,
        ],
        table: ParsedSemanticModelTable,
        hierarchy: ParsedSemanticModelHierarchy,
    ) -> None:
        for level in hierarchy.levels:
            lineage_object = SemanticLineageObject(
                object_type="hierarchy_level",
                table_name=table.name,
                object_name=level.name,
                source_path=(
                    level.source_path or hierarchy.source_path or table.source_path
                ),
                hierarchy_name=hierarchy.name,
                level_name=level.name,
            )

            index[
                (
                    _key(table.name),
                    _key(hierarchy.name),
                    _key(level.name),
                )
            ] = lineage_object


def _key(
    value: str,
) -> str:
    return value.strip().casefold()


def _similarity(
    left: str,
    right: str,
) -> float:
    return SequenceMatcher(
        None,
        _key(left),
        _key(right),
    ).ratio()
