import base64
import binascii
import re

from app.schemas.parsed_semantic_model import (
    ParsedSemanticModelColumn,
    ParsedSemanticModelExpression,
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

# Trailing metadata on a shared `expression` block. Everything else inside
# one is M code and must be kept verbatim -- including lines such as
# `Source = AnalysisServices.Database(...)`, which look like a property
# assignment but are the part that actually names the upstream model.
EXPRESSION_METADATA_KEYS = frozenset(
    {
        "lineageTag",
        "queryGroup",
        "description",
        "displayFolder",
    }
)
EXPRESSION_METADATA_PREFIXES = (
    "annotation ",
    "extendedProperty ",
    "changedProperty ",
)


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

        for table in result.tables:
            for measure in table.measures:
                measure.expression = self._strip_code_fence(measure.expression)
            for column in table.columns:
                column.expression = self._strip_code_fence(column.expression)

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
        current_expression = None
        partition_source_started = False

        for raw_line in text.splitlines():
            line = raw_line.strip()

            if not line or line.startswith("//"):
                continue

            if current_table is None and line.startswith("expression "):
                name, expression = self._split_assignment(
                    line.removeprefix("expression ").strip()
                )
                current_expression = ParsedSemanticModelExpression(
                    name=self._clean_name(name),
                    source_path=source_path,
                    expression=expression,
                )
                result.expressions.append(current_expression)
                current_column = None
                current_measure = None
                current_hierarchy = None
                current_partition = None
                current_relationship = None
                partition_source_started = False
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
                current_expression = None
                partition_source_started = False
                continue

            if line.startswith("relationship "):
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
                current_expression = None
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

            if current_expression is not None:
                if key == "lineageTag":
                    current_expression.lineage_tag = value
                elif not (
                    key in EXPRESSION_METADATA_KEYS
                    or line.startswith(EXPRESSION_METADATA_PREFIXES)
                ):
                    current_expression.expression = self._append_expression(
                        current_expression.expression,
                        line,
                    )
            elif current_partition:
                if key == "mode" and not partition_source_started:
                    current_partition.mode = value
                elif (
                    key
                    in {
                        "entityName",
                        "expressionSource",
                        "schemaName",
                    }
                    and not partition_source_started
                ):
                    self._apply_entity_partition_property(
                        current_partition,
                        key,
                        value,
                    )
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
                    and not self._is_metadata_line(line)
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

                if (
                    not applied
                    and not self._is_metadata_line(line)
                    and not self._looks_like_property_key(key)
                ):
                    current_measure.expression = self._append_expression(
                        current_measure.expression,
                        line,
                    )
            elif current_hierarchy and current_hierarchy.levels:
                if key == "column":
                    current_hierarchy.levels[-1].column = self._clean_name(value)
            elif current_relationship:
                self._apply_relationship_property(current_relationship, key, value)
            elif current_table is not None and key in {
                "lineageTag",
                "sourceLineageTag",
            }:
                if key == "lineageTag":
                    current_table.lineage_tag = value
                else:
                    current_table.source_lineage_tag = value
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
    def _strip_code_fence(expression: str | None) -> str | None:
        """Drop the ``` delimiters TMDL wraps a multi-line value in.

        They are a block marker, not part of the DAX, but they survived into
        every multi-line measure -- so the expression shown to a user began
        and ended with a code fence.
        """
        if expression is None:
            return None

        text = expression.strip()

        if not text.startswith("```"):
            return expression

        text = text.removeprefix("```")
        if text.endswith("```"):
            text = text[: -len("```")]

        return text.strip() or expression

    @staticmethod
    def _is_metadata_line(line: str) -> bool:
        """TMDL metadata that trails a measure or calculated column.

        `PROPERTY_KEY_PATTERN` only matches a single bare word, so keys such
        as `annotation PBI_FormatHint` were not recognised as properties and
        were appended to the DAX instead -- every measure in a real model
        came back with `annotation PBI_FormatHint = {...}` stuck on the end
        of its expression. DAX has no such construct, so matching the prefix
        cannot swallow real expression text.
        """
        return line.startswith(EXPRESSION_METADATA_PREFIXES)

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

    def _apply_entity_partition_property(
        self,
        partition: ParsedSemanticModelPartition,
        key: str,
        value: str,
    ) -> None:
        if key == "entityName":
            partition.entity_name = self._clean_name(value)
        elif key == "expressionSource":
            partition.expression_source = self._clean_name(value)
        elif key == "schemaName":
            partition.schema_name = self._clean_name(value)

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

        if key == "lineageTag":
            column.lineage_tag = value.strip()
            return True

        if key == "sourceLineageTag":
            column.source_lineage_tag = value.strip()
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
