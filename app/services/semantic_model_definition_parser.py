import base64
import binascii
import re

from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelHierarchy,
    ParsedSemanticModelHierarchyLevel,
    ParsedSemanticModelMeasure,
    ParsedSemanticModelPartition,
    ParsedSemanticModelRelationship,
    ParsedSemanticModelResponse,
    ParsedSemanticModelTable,
    ParsedSemanticModelWarning,
)
from app.schemas.semantic_model_definition import SemanticModelDefinitionResponse

FIELD_REFERENCE_PATTERN = re.compile(r"^'?(?P<table>[^'\[]+)'?\[(?P<field>[^\]]+)\]$")
TMDL_FIELD_REFERENCE_PATTERN = re.compile(
    r"^(?P<table>'(?:[^']|'')+'|[^.]+)\."
    r"(?P<field>'(?:[^']|'')+'|[^.]+)$"
)

PROPERTY_KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


class SemanticModelDefinitionParser:
    def parse(
        self,
        raw: SemanticModelDefinitionResponse,
    ) -> ParsedSemanticModelResponse:
        result = ParsedSemanticModelResponse(
            workspace_id=raw.workspace_id,
            semantic_model_id=raw.semantic_model_id,
            format=raw.definition.format,
        )

        if (raw.definition.format or "").upper() != "TMDL":
            result.warnings.append(
                ParsedSemanticModelWarning(
                    code="UNSUPPORTED_FORMAT",
                    message="Only TMDL parsing is supported in this phase.",
                )
            )
            return result

        for part in raw.definition.parts:
            if part.payload_type != "InlineBase64":
                result.warnings.append(
                    ParsedSemanticModelWarning(
                        code="UNSUPPORTED_PAYLOAD_TYPE",
                        message="Only InlineBase64 payloads are supported.",
                        path=part.path,
                    )
                )
                continue

            try:
                text = base64.b64decode(
                    part.payload,
                    validate=True,
                ).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError):
                result.warnings.append(
                    ParsedSemanticModelWarning(
                        code="INVALID_BASE64_PAYLOAD",
                        message="Definition part payload could not be decoded.",
                        path=part.path,
                    )
                )
                continue

            self._parse_tmdl_part(
                text=text,
                source_path=part.path,
                result=result,
            )

        return result

    def _parse_tmdl_part(
        self,
        *,
        text: str,
        source_path: str,
        result: ParsedSemanticModelResponse,
    ) -> None:
        current_table = None
        current_column = None
        current_measure = None
        current_hierarchy = None
        current_partition = None
        current_relationship = None
        partition_source_started = False

        for raw_line in text.splitlines():
            line = raw_line.strip()

            if not line or line.startswith("//"):
                continue

            if line.startswith("table "):
                declaration = line.removeprefix("table ")
                table_name, expression = self._split_assignment(declaration)
                if "=" in declaration and expression is None:
                    expression = ""
                current_table = ParsedSemanticModelTable(
                    name=self._clean_name(table_name),
                    source_path=source_path,
                    expression=expression,
                )
                result.tables.append(current_table)
                current_column = None
                current_measure = None
                current_hierarchy = None
                current_partition = None
                current_relationship = None
                partition_source_started = False
                continue

            if line.startswith("relationship"):
                name = self._clean_optional_name(line.removeprefix("relationship"))
                current_relationship = ParsedSemanticModelRelationship(
                    name=name,
                    source_path=source_path,
                )
                result.relationships.append(current_relationship)
                current_table = None
                current_column = None
                current_measure = None
                current_hierarchy = None
                current_partition = None
                partition_source_started = False
                continue

            if current_table and line.startswith("column "):
                declaration = line.removeprefix("column ")
                column_name, expression = self._split_assignment(declaration)
                if "=" in declaration and expression is None:
                    expression = ""
                current_column = ParsedSemanticModelColumn(
                    name=self._clean_name(column_name),
                    source_path=source_path,
                    expression=expression,
                )
                current_table.columns.append(current_column)
                current_measure = None
                current_hierarchy = None
                current_partition = None
                partition_source_started = False
                continue

            if current_table and line.startswith("measure "):
                name, expression = self._split_assignment(
                    line.removeprefix("measure ").strip()
                )
                current_measure = ParsedSemanticModelMeasure(
                    name=self._clean_name(name),
                    source_path=source_path,
                    expression=expression,
                )
                current_table.measures.append(current_measure)
                current_column = None
                current_hierarchy = None
                current_partition = None
                partition_source_started = False
                continue

            if current_table and line.startswith("hierarchy "):
                current_hierarchy = ParsedSemanticModelHierarchy(
                    name=self._clean_name(line.removeprefix("hierarchy ")),
                    source_path=source_path,
                )
                current_table.hierarchies.append(current_hierarchy)
                current_column = None
                current_measure = None
                current_partition = None
                partition_source_started = False
                continue

            if current_table and line.startswith("partition "):
                name, source_type = self._split_assignment(
                    line.removeprefix("partition ").strip()
                )
                current_partition = ParsedSemanticModelPartition(
                    name=self._clean_name(name),
                    source_path=source_path,
                    source_type=source_type,
                )
                current_table.partitions.append(current_partition)
                current_column = None
                current_measure = None
                current_hierarchy = None
                partition_source_started = False
                continue

            if current_hierarchy and line.startswith("level "):
                current_hierarchy.levels.append(
                    ParsedSemanticModelHierarchyLevel(
                        name=self._clean_name(line.removeprefix("level ")),
                        source_path=source_path,
                    )
                )
                continue

            key, value = self._split_property(line)

            if current_partition:
                if key == "mode" and not partition_source_started:
                    current_partition.mode = value
                elif key == "source":
                    current_partition.expression = value
                    partition_source_started = True
                    self._apply_calculated_partition(
                        current_table,
                        current_partition,
                    )
                elif partition_source_started:
                    current_partition.expression = self._append_expression(
                        current_partition.expression,
                        line,
                    )
                    self._apply_calculated_partition(
                        current_table,
                        current_partition,
                    )
            elif current_column:
                applied = self._apply_column_property(
                    current_column,
                    key,
                    value,
                )

                if (
                    not applied
                    and not self._looks_like_property_key(key)
                    and current_column.expression is not None
                ):
                    current_column.expression = self._append_expression(
                        current_column.expression,
                        line,
                    )
            elif current_measure:
                applied = self._apply_measure_property(
                    current_measure,
                    key,
                    value,
                )

                if not applied and not self._looks_like_property_key(key):
                    current_measure.expression = self._append_expression(
                        current_measure.expression,
                        line,
                    )
            elif current_hierarchy and current_hierarchy.levels:
                if key == "column":
                    current_hierarchy.levels[-1].column = self._clean_name(value)
            elif current_relationship:
                self._apply_relationship_property(current_relationship, key, value)
            elif (
                current_table
                and current_table.expression is not None
                and not self._looks_like_property_key(key)
            ):
                current_table.expression = self._append_expression(
                    current_table.expression,
                    line,
                )

    @staticmethod
    def _split_assignment(value: str) -> tuple[str, str | None]:
        if "=" not in value:
            return value, None

        name, expression = value.split("=", 1)
        return (
            name.strip(),
            expression.strip() or None,
        )

    @staticmethod
    def _split_property(line: str) -> tuple[str, str]:
        separators = (
            ":",
            "=",
        )

        for separator in separators:
            if separator in line:
                key, value = line.split(
                    separator,
                    1,
                )

                return key.strip(), value.strip()

        return "", ""

    @staticmethod
    def _clean_name(value: str) -> str:
        cleaned = value.strip()

        if len(cleaned) >= 2 and cleaned.startswith("'") and cleaned.endswith("'"):
            cleaned = cleaned[1:-1]

        return cleaned.replace(
            "''",
            "'",
        )

    def _clean_optional_name(
        self,
        value: str,
    ) -> str | None:
        cleaned = self._clean_name(value)

        return cleaned or None

    @staticmethod
    def _append_expression(
        current: str | None,
        line: str,
    ) -> str:
        if not current:
            return line

        return f"{current}\n{line}"

    @staticmethod
    def _to_bool(value: str) -> bool | None:
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
        return None

    @staticmethod
    def _looks_like_property_key(
        key: str,
    ) -> bool:
        return bool(key and PROPERTY_KEY_PATTERN.match(key))

    @staticmethod
    def _parse_field_reference(value: str) -> tuple[str | None, str | None]:
        match = FIELD_REFERENCE_PATTERN.match(value.strip())

        if not match:
            match = TMDL_FIELD_REFERENCE_PATTERN.match(value.strip())

        if not match:
            return None, None

        return (
            SemanticModelDefinitionParser._clean_name(match.group("table")),
            SemanticModelDefinitionParser._clean_name(match.group("field")),
        )

    def _apply_column_property(
        self,
        column: ParsedSemanticModelColumn,
        key: str,
        value: str,
    ) -> bool:
        if key == "dataType":
            column.data_type = value
            return True

        if key == "sourceColumn":
            column.source_column = self._clean_name(value)
            return True

        if key == "expression":
            column.expression = value
            return True

        if key == "isHidden":
            column.is_hidden = self._to_bool(value)
            return True

        return False

    def _apply_measure_property(
        self,
        measure: ParsedSemanticModelMeasure,
        key: str,
        value: str,
    ) -> bool:
        if key == "expression":
            measure.expression = value
            return True

        if key == "formatString":
            measure.format_string = self._clean_name(value)
            return True

        if key == "isHidden":
            measure.is_hidden = self._to_bool(value)
            return True

        return False

    def _apply_relationship_property(
        self,
        relationship: ParsedSemanticModelRelationship,
        key: str,
        value: str,
    ) -> None:
        if key == "fromColumn":
            relationship.from_table, relationship.from_column = (
                self._parse_field_reference(value)
            )
        elif key == "toColumn":
            relationship.to_table, relationship.to_column = self._parse_field_reference(
                value
            )
        elif key == "isActive":
            relationship.is_active = self._to_bool(value)
        elif key == "cardinality":
            relationship.cardinality = value
        elif key in {"crossFilteringBehavior", "crossFilterDirection"}:
            relationship.cross_filter_direction = value

    @staticmethod
    def _apply_calculated_partition(
        table: ParsedSemanticModelTable | None,
        partition: ParsedSemanticModelPartition,
    ) -> None:
        if (
            table is not None
            and (partition.source_type or "").casefold() == "calculated"
        ):
            table.expression = partition.expression
