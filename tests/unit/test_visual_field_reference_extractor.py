from app.services.visual_field_reference_extractor import (
    extract_visual_field_references,
)


def test_extracts_column_projection():
    visual_definition = {
        "visual": {
            "query": {
                "queryState": {
                    "Category": {
                        "projections": [
                            {
                                "field": {
                                    "Column": {
                                        "Expression": {
                                            "SourceRef": {"Entity": "Product"}
                                        },
                                        "Property": "Brand",
                                    }
                                },
                                "queryRef": "Product.Brand",
                                "active": True,
                            }
                        ]
                    }
                }
            }
        }
    }

    result = extract_visual_field_references(visual_definition)

    assert len(result) == 1

    reference = result[0]

    assert reference.object_type == "column"
    assert reference.table_name == "Product"
    assert reference.object_name == "Brand"
    assert reference.usage == "projection"
    assert reference.role == "Category"
    assert reference.query_ref == "Product.Brand"
    assert reference.active is True


def test_extracts_measure_projection():
    visual_definition = {
        "visual": {
            "query": {
                "queryState": {
                    "Y": {
                        "projections": [
                            {
                                "field": {
                                    "Measure": {
                                        "Expression": {
                                            "SourceRef": {"Entity": "Sales"}
                                        },
                                        "Property": "Sales Amount",
                                    }
                                },
                                "queryRef": ("Measure Table.Sales Amount"),
                            }
                        ]
                    }
                }
            }
        }
    }

    result = extract_visual_field_references(visual_definition)

    assert len(result) == 1

    reference = result[0]

    assert reference.object_type == "measure"
    assert reference.table_name == "Sales"
    assert reference.object_name == "Sales Amount"
    assert reference.query_ref == "Measure Table.Sales Amount"


def test_non_data_visual_returns_empty_list():
    visual_definition = {
        "name": "textbox-123",
        "visual": {
            "visualType": "textbox",
        },
    }

    result = extract_visual_field_references(visual_definition)

    assert result == []
