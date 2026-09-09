import re
from typing import Any

from app.core.exceptions import (
    UpstreamInvalidResponseError,
)
from app.schemas.normalized_report_definition import (
    NormalizedReportDefinitionResponse,
    NormalizedReportPage,
    NormalizedReportVisual,
    NormalizedVisualPosition,
    SemanticModelReference,
)
from app.schemas.report_definition import (
    ReportDefinitionResponse,
)
from app.services.report_definition_decoder import (
    ReportDefinitionDecoder,
)
from app.services.visual_field_reference_extractor import (
    extract_visual_field_references,
)

PAGE_PATTERN = re.compile(
    r"^definition/pages/"
    r"([^/]+)/page\.json$"
)

VISUAL_PATTERN = re.compile(
    r"^definition/pages/"
    r"([^/]+)/visuals/"
    r"([^/]+)/visual\.json$"
)

SEMANTIC_MODEL_ID_PATTERN = re.compile(
    r"(?:^|;)\s*"
    r"semanticmodelid\s*="
    r"\s*([^;]+)",
    re.IGNORECASE,
)


class ReportDefinitionNormalizer:
    def __init__(self) -> None:
        self.decoder = ReportDefinitionDecoder()

    @staticmethod
    def _detect_format(
        *,
        raw: ReportDefinitionResponse,
        decoded: dict[str, Any],
    ) -> str:
        reported_format = raw.definition.format

        has_pbir = any(path.startswith("definition/") for path in decoded)

        has_legacy = "report.json" in decoded

        if reported_format == "PBIR" or has_pbir:
            return "PBIR"

        if (
            reported_format
            in {
                "PBIR-Legacy",
                "PBIRLegacy",
            }
            or has_legacy
        ):
            return "PBIR-Legacy"

        return "Unknown"

    @staticmethod
    def _get_definition_properties(
        decoded: dict[str, Any],
    ) -> dict[str, Any]:
        definition = decoded.get("definition.pbir")

        if not isinstance(
            definition,
            dict,
        ):
            raise (UpstreamInvalidResponseError("fabric"))

        return definition

    @staticmethod
    def _extract_semantic_model(
        definition: dict[str, Any],
    ) -> SemanticModelReference | None:
        dataset_reference = definition.get("datasetReference")

        if not isinstance(
            dataset_reference,
            dict,
        ):
            return None

        by_path = dataset_reference.get("byPath")

        if isinstance(
            by_path,
            dict,
        ):
            path = by_path.get("path")

            if isinstance(
                path,
                str,
            ):
                return SemanticModelReference(
                    mode="by_path",
                    path=path,
                )

        by_connection = dataset_reference.get("byConnection")

        if isinstance(
            by_connection,
            dict,
        ):
            connection_string = by_connection.get("connectionString")

            semantic_model_id = ReportDefinitionNormalizer._extract_semantic_model_id(
                connection_string
            )

            return SemanticModelReference(
                mode="by_connection",
                semantic_model_id=(semantic_model_id),
            )

        return SemanticModelReference(mode="unknown")

    @staticmethod
    def _extract_semantic_model_id(
        connection_string: Any,
    ) -> str | None:
        if not isinstance(
            connection_string,
            str,
        ):
            return None

        match = SEMANTIC_MODEL_ID_PATTERN.search(connection_string)

        if match is None:
            return None

        value = match.group(1).strip().strip("[]")

        return value or None

    def _normalize_pbir_pages(
        self,
        *,
        decoded: dict[str, Any],
        warnings: list[str],
    ) -> list[NormalizedReportPage]:
        page_order, active_page = self._get_pages_metadata(decoded)

        pages: list[NormalizedReportPage] = []

        for path, payload in decoded.items():
            match = PAGE_PATTERN.match(path)

            if match is None:
                continue

            page_folder = match.group(1)

            if not isinstance(
                payload,
                dict,
            ):
                raise (UpstreamInvalidResponseError("fabric"))

            page = self._normalize_page(
                page_folder=page_folder,
                payload=payload,
                decoded=decoded,
                page_order=page_order,
                active_page=active_page,
                warnings=warnings,
            )

            pages.append(page)

        pages.sort(key=self._page_sort_key)

        return pages

    @staticmethod
    def _get_pages_metadata(
        decoded: dict[str, Any],
    ) -> tuple[
        list[str],
        str | None,
    ]:
        metadata = decoded.get("definition/pages/pages.json")

        if not isinstance(
            metadata,
            dict,
        ):
            return [], None

        raw_order = metadata.get("pageOrder")

        page_order = []

        if isinstance(
            raw_order,
            list,
        ):
            page_order = [
                item
                for item in raw_order
                if isinstance(
                    item,
                    str,
                )
            ]

        active_page = metadata.get("activePageName")

        if not isinstance(
            active_page,
            str,
        ):
            active_page = None

        return (
            page_order,
            active_page,
        )

    def _normalize_page(
        self,
        *,
        page_folder: str,
        payload: dict[str, Any],
        decoded: dict[str, Any],
        page_order: list[str],
        active_page: str | None,
        warnings: list[str],
    ) -> NormalizedReportPage:
        payload_name = self._get_string(
            payload,
            "name",
        )

        page_name = payload_name or page_folder

        if payload_name and payload_name != page_folder:
            warnings.append(
                "Page folder identifier "
                f"'{page_folder}' differs "
                f"from page name "
                f"'{payload_name}'."
            )

        display_name = (
            self._get_string(
                payload,
                "displayName",
            )
            or page_name
        )

        order = None

        if page_name in page_order:
            order = page_order.index(page_name)

        visuals = self._normalize_visuals(
            page_folder=page_folder,
            decoded=decoded,
        )

        return NormalizedReportPage(
            name=page_name,
            display_name=display_name,
            order=order,
            is_active=(page_name == active_page),
            display_option=(
                self._get_string(
                    payload,
                    "displayOption",
                )
            ),
            width=self._get_number(
                payload,
                "width",
            ),
            height=self._get_number(
                payload,
                "height",
            ),
            visuals=visuals,
            visual_count=len(visuals),
        )

    def _normalize_visuals(
        self,
        *,
        page_folder: str,
        decoded: dict[str, Any],
    ) -> list[NormalizedReportVisual]:
        visuals: list[NormalizedReportVisual] = []

        for path, payload in decoded.items():
            match = VISUAL_PATTERN.match(path)

            if match is None:
                continue

            matched_page = match.group(1)

            if matched_page != page_folder:
                continue

            visual_folder = match.group(2)

            if not isinstance(
                payload,
                dict,
            ):
                raise (UpstreamInvalidResponseError("fabric"))

            visuals.append(
                self._normalize_visual(
                    visual_folder=(visual_folder),
                    payload=payload,
                )
            )

        visuals.sort(key=self._visual_sort_key)

        return visuals

    def _normalize_visual(
        self,
        *,
        visual_folder: str,
        payload: dict[str, Any],
    ) -> NormalizedReportVisual:
        internal_name = (
            self._get_string(
                payload,
                "name",
            )
            or visual_folder
        )

        visual_config = payload.get("visual")

        visual_type = None
        has_query = False

        title = None
        title_visible = None
        title_is_dynamic = False

        if isinstance(
            visual_config,
            dict,
        ):
            visual_type = self._get_string(
                visual_config,
                "visualType",
            )

            has_query = visual_config.get("query") is not None

            (
                title,
                title_visible,
                title_is_dynamic,
            ) = self._extract_visual_title(visual_config)

        is_hidden = payload.get(
            "isHidden",
            False,
        )

        if not isinstance(
            is_hidden,
            bool,
        ):
            is_hidden = False

        return NormalizedReportVisual(
            id=visual_folder,
            internal_name=internal_name,
            title=title,
            title_visible=title_visible,
            title_is_dynamic=(title_is_dynamic),
            visual_type=visual_type,
            parent_group_name=(
                self._get_string(
                    payload,
                    "parentGroupName",
                )
            ),
            is_hidden=is_hidden,
            has_query=has_query,
            position=(self._normalize_position(payload.get("position"))),
            field_references=(extract_visual_field_references(payload)),
        )

    def _normalize_position(
        self,
        value: Any,
    ) -> NormalizedVisualPosition | None:
        if not isinstance(
            value,
            dict,
        ):
            return None

        return NormalizedVisualPosition(
            x=self._get_number(
                value,
                "x",
            ),
            y=self._get_number(
                value,
                "y",
            ),
            width=self._get_number(
                value,
                "width",
            ),
            height=self._get_number(
                value,
                "height",
            ),
            z=self._get_number(
                value,
                "z",
            ),
            tab_order=self._get_number(
                value,
                "tabOrder",
            ),
        )

    @classmethod
    def _extract_visual_title(
        cls,
        visual_config: dict[str, Any],
    ) -> tuple[
        str | None,
        bool | None,
        bool,
    ]:
        container_objects = visual_config.get("visualContainerObjects")

        if not isinstance(
            container_objects,
            dict,
        ):
            return None, None, False

        title_objects = container_objects.get("title")

        if not isinstance(
            title_objects,
            list,
        ):
            return None, None, False

        title_visible: bool | None = None
        title_is_dynamic = False

        for title_object in title_objects:
            if not isinstance(
                title_object,
                dict,
            ):
                continue

            properties = title_object.get("properties")

            if not isinstance(
                properties,
                dict,
            ):
                continue

            if "show" in properties:
                visible = cls._extract_literal_bool(properties.get("show"))

                if visible is not None:
                    title_visible = visible

            if "text" not in properties:
                continue

            title = cls._extract_literal_string(properties.get("text"))

            if title is not None:
                return (
                    title,
                    title_visible,
                    False,
                )

            #
            # A title expression exists,
            # but it isn't a static Literal.
            #
            title_is_dynamic = True

        return (
            None,
            title_visible,
            title_is_dynamic,
        )

    @staticmethod
    def _extract_literal_string(
        value: Any,
    ) -> str | None:
        if not isinstance(
            value,
            dict,
        ):
            return None

        expression = value.get("expr")

        if not isinstance(
            expression,
            dict,
        ):
            return None

        literal = expression.get("Literal")

        if not isinstance(
            literal,
            dict,
        ):
            return None

        raw_value = literal.get("Value")

        if not isinstance(
            raw_value,
            str,
        ):
            return None

        raw_value = raw_value.strip()

        if (
            len(raw_value) >= 2
            and raw_value.startswith("'")
            and raw_value.endswith("'")
        ):
            return raw_value[1:-1].replace(
                "''",
                "'",
            )

        return raw_value or None

    @staticmethod
    def _extract_literal_bool(
        value: Any,
    ) -> bool | None:
        if not isinstance(
            value,
            dict,
        ):
            return None

        expression = value.get("expr")

        if not isinstance(
            expression,
            dict,
        ):
            return None

        literal = expression.get("Literal")

        if not isinstance(
            literal,
            dict,
        ):
            return None

        raw_value = literal.get("Value")

        if not isinstance(
            raw_value,
            str,
        ):
            return None

        normalized = raw_value.strip().lower()

        if normalized == "true":
            return True

        if normalized == "false":
            return False

        return None

    @staticmethod
    def _get_string(
        value: dict[str, Any],
        key: str,
    ) -> str | None:
        result = value.get(key)

        if isinstance(result, str) and result:
            return result

        return None

    @staticmethod
    def _get_number(
        value: dict[str, Any],
        key: str,
    ) -> float | None:
        result = value.get(key)

        if isinstance(
            result,
            bool,
        ):
            return None

        if isinstance(
            result,
            (int, float),
        ):
            return float(result)

        return None

    @staticmethod
    def _page_sort_key(
        page: NormalizedReportPage,
    ) -> tuple[int, int, str]:
        if page.order is None:
            return (
                1,
                0,
                page.name,
            )

        return (
            0,
            page.order,
            page.name,
        )

    @staticmethod
    def _visual_sort_key(
        visual: NormalizedReportVisual,
    ) -> tuple[
        int,
        float,
        str,
    ]:
        if visual.position is None or visual.position.tab_order is None:
            return (
                1,
                0,
                visual.id,
            )

        return (
            0,
            visual.position.tab_order,
            visual.id,
        )

    def normalize(
        self,
        raw: ReportDefinitionResponse,
    ) -> NormalizedReportDefinitionResponse:
        decoded = self.decoder.decode(raw.definition)

        warnings: list[str] = []

        format_name = self._detect_format(
            raw=raw,
            decoded=decoded,
        )

        definition_properties = self._get_definition_properties(decoded)

        definition_version = self._get_string(
            definition_properties,
            "version",
        )

        semantic_model = self._extract_semantic_model(definition_properties)

        if format_name == "PBIR":
            pages = self._normalize_pbir_pages(
                decoded=decoded,
                warnings=warnings,
            )

        elif format_name == "PBIR-Legacy":
            pages = []

            warnings.append(
                "PBIR-Legacy report.json "
                "was decoded but deep visual "
                "normalization is not performed."
            )

        else:
            pages = []

            warnings.append("Report definition format could not be identified.")

        visual_count = sum(page.visual_count for page in pages)

        return NormalizedReportDefinitionResponse(
            workspace_id=raw.workspace_id,
            report_id=raw.report_id,
            format=format_name,
            definition_version=(definition_version),
            semantic_model=semantic_model,
            pages=pages,
            page_count=len(pages),
            visual_count=visual_count,
            source_part_count=len(raw.definition.parts),
            decoded_json_part_count=len(decoded),
            warnings=warnings,
        )
