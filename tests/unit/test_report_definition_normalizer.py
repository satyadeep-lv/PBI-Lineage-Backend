import base64
import json

from app.schemas.report_definition import (
    ReportDefinition,
    ReportDefinitionPart,
    ReportDefinitionResponse,
)
from app.services.report_definition_normalizer import (
    ReportDefinitionNormalizer,
)


def _encode(
    value: object,
) -> str:
    return base64.b64encode(json.dumps(value).encode("utf-8")).decode("ascii")


def _part(
    path: str,
    value: object,
) -> ReportDefinitionPart:
    return ReportDefinitionPart(
        path=path,
        payload=_encode(value),
        payload_type="InlineBase64",
    )


def test_normalize_pbir_report():
    raw = ReportDefinitionResponse(
        workspace_id="workspace-1",
        report_id="report-1",
        definition=ReportDefinition(
            format="PBIR",
            parts=[
                _part(
                    "definition.pbir",
                    {
                        "version": "4.0",
                        "datasetReference": {
                            "byConnection": {
                                "connectionString": ("semanticmodelid=[model-123]")
                            }
                        },
                    },
                ),
                _part(
                    ("definition/pages/pages.json"),
                    {
                        "pageOrder": ["page-1"],
                        "activePageName": ("page-1"),
                    },
                ),
                _part(
                    ("definition/pages/page-1/page.json"),
                    {
                        "name": "page-1",
                        "displayName": ("Executive Summary"),
                        "displayOption": ("FitToPage"),
                        "width": 1280,
                        "height": 720,
                    },
                ),
                _part(
                    ("definition/pages/page-1/visuals/visual-1/visual.json"),
                    {
                        "name": "visual-1",
                        "position": {
                            "x": 10,
                            "y": 20,
                            "width": 300,
                            "height": 200,
                            "tabOrder": 0,
                        },
                        "visual": {
                            "visualType": "barChart",
                            "query": {},
                            "visualContainerObjects": {
                                "title": [
                                    {
                                        "properties": {
                                            "show": {
                                                "expr": {"Literal": {"Value": ("true")}}
                                            },
                                            "text": {
                                                "expr": {
                                                    "Literal": {
                                                        "Value": ("'Revenue by Region'")
                                                    }
                                                }
                                            },
                                        }
                                    }
                                ]
                            },
                        },
                    },
                ),
            ],
        ),
    )

    result = ReportDefinitionNormalizer().normalize(raw)

    assert result.format == "PBIR"

    assert result.definition_version == "4.0"

    assert result.semantic_model is not None

    assert result.semantic_model.semantic_model_id == "model-123"

    assert result.page_count == 1
    assert result.visual_count == 1

    page = result.pages[0]

    assert page.display_name == "Executive Summary"

    assert page.order == 0
    assert page.is_active is True

    visual = page.visuals[0]

    assert visual.id == "visual-1"

    assert visual.internal_name == "visual-1"

    assert visual.title == "Revenue by Region"

    assert visual.title_visible is True

    assert visual.title_is_dynamic is False

    assert visual.visual_type == "barChart"

    assert visual.has_query is True


def test_semantic_model_by_path():
    raw = ReportDefinitionResponse(
        workspace_id="workspace-1",
        report_id="report-1",
        definition=ReportDefinition(
            format="PBIR",
            parts=[
                _part(
                    "definition.pbir",
                    {
                        "version": "4.0",
                        "datasetReference": {
                            "byPath": {"path": ("../Sales.SemanticModel")}
                        },
                    },
                ),
                _part(
                    ("definition/pages/pages.json"),
                    {"pageOrder": []},
                ),
            ],
        ),
    )

    result = ReportDefinitionNormalizer().normalize(raw)

    assert result.semantic_model.mode == "by_path"

    assert result.semantic_model.path == "../Sales.SemanticModel"


def test_visual_without_title():
    normalizer = ReportDefinitionNormalizer()

    visual = normalizer._normalize_visual(
        visual_folder="visual-1",
        payload={
            "name": "visual-1",
            "position": {
                "x": 0,
                "y": 0,
                "width": 100,
                "height": 100,
            },
            "visual": {
                "visualType": "card",
            },
        },
    )

    assert visual.id == "visual-1"

    assert visual.internal_name == "visual-1"

    assert visual.title is None

    assert visual.title_visible is None

    assert visual.title_is_dynamic is False


def test_visual_title_can_be_hidden():
    normalizer = ReportDefinitionNormalizer()

    visual = normalizer._normalize_visual(
        visual_folder="visual-1",
        payload={
            "name": "visual-1",
            "position": {
                "x": 0,
                "y": 0,
                "width": 100,
                "height": 100,
            },
            "visual": {
                "visualType": "card",
                "visualContainerObjects": {
                    "title": [
                        {
                            "properties": {
                                "show": {"expr": {"Literal": {"Value": ("false")}}},
                                "text": {
                                    "expr": {"Literal": {"Value": ("'Total Revenue'")}}
                                },
                            }
                        }
                    ]
                },
            },
        },
    )

    assert visual.title == "Total Revenue"

    assert visual.title_visible is False


def test_dynamic_visual_title():
    normalizer = ReportDefinitionNormalizer()

    visual = normalizer._normalize_visual(
        visual_folder="visual-1",
        payload={
            "name": "visual-1",
            "position": {
                "x": 0,
                "y": 0,
                "width": 100,
                "height": 100,
            },
            "visual": {
                "visualType": "card",
                "visualContainerObjects": {
                    "title": [
                        {
                            "properties": {
                                "text": {
                                    "expr": {"Measure": {"Property": ("Dynamic Title")}}
                                }
                            }
                        }
                    ]
                },
            },
        },
    )

    assert visual.title is None

    assert visual.title_is_dynamic is True


def test_normalized_visual_contains_field_references():
    visual_definition = {
        "name": "visual-123",
        "visual": {
            "visualType": "card",
            "query": {
                "queryState": {
                    "Values": {
                        "projections": [
                            {
                                "field": {
                                    "Measure": {
                                        "Expression": {
                                            "SourceRef": {"Entity": "Sales"}
                                        },
                                        "Property": "Revenue",
                                    }
                                },
                                "queryRef": "Sales.Revenue",
                            }
                        ]
                    }
                }
            },
        },
    }

    normalizer = ReportDefinitionNormalizer()

    normalized = normalizer._normalize_visual(
        visual_folder="visual-123",
        payload=visual_definition,
    )

    assert normalized.has_query is True
    assert len(normalized.field_references) == 1

    field = normalized.field_references[0]

    assert field.object_type == "measure"
    assert field.table_name == "Sales"
    assert field.object_name == "Revenue"
    assert field.usage == "projection"
    assert field.role == "Values"
    assert field.query_ref == "Sales.Revenue"
