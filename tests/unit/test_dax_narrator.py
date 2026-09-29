import pytest

from app.ai.composition.dax_narrator import describe


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        (
            "SUM ( 'Sales Story'[NET_SALES] )",
            "Total Revenue adds up NET_SALES.",
        ),
        (
            "DISTINCTCOUNT ( 'Sales Story'[ORDER_ID] )",
            "Total Revenue counts how many distinct values there are in ORDER_ID.",
        ),
        (
            "DIVIDE ( [Total Revenue], [Orders] )",
            "Total Revenue divides Total Revenue by Orders.",
        ),
        (
            "[Total Revenue] - [Revenue Target]",
            "Total Revenue equals Total Revenue minus Revenue Target.",
        ),
        (
            "CALCULATE ( [Total Revenue], 'Sales Story'[IS_RETURNED] = 1 )",
            "Total Revenue equals Total Revenue, restricted to IS_RETURNED = 1.",
        ),
        (
            "CALCULATE ( DISTINCTCOUNT ( 'S'[ORDER_ID] ), 'S'[IS_RETURNED] = 1 )",
            "Total Revenue counts how many distinct values there are in "
            "ORDER_ID, restricted to IS_RETURNED = 1.",
        ),
        (
            "DIVIDE([Total Profit], [Total Revenue], 0) * 100",
            "Total Revenue divides Total Profit by Total Revenue, then "
            "multiplies the result by 100.",
        ),
    ],
)
def test_describes_common_dax_shapes(expression, expected):
    assert describe(expression, object_name="Total Revenue") == expected


def test_switch_true_banding_names_the_field_and_the_bands():
    # `SWITCH(TRUE(), ...)` is the standard banding idiom; saying only
    # "checks TRUE() against N cases" tells a reader nothing.
    described = describe(
        'SWITCH(TRUE(), \'S\'[REVENUE_RANK] <= 2, "Tier 1", "Tier 2")',
        object_name="Region Tier",
    )

    assert described == (
        'Region Tier returns "Tier 1" when REVENUE_RANK <= 2, and "Tier 2" otherwise.'
    )


def test_nested_aggregations_read_as_nouns_inside_divide():
    described = describe(
        "DIVIDE(COUNTROWS('Customers'), COUNTROWS('Orders'))",
        object_name="Ratio",
    )

    assert described == (
        "Ratio divides the number of Customers rows by the number of Orders rows."
    )


def test_an_unrecognised_shape_names_what_it_reads_rather_than_guessing():
    described = describe(
        "SOMEFUTUREFUNCTION('S'[REVENUE_RANK], 'S'[REGION])",
        object_name="Mystery",
    )

    assert described is not None
    # No invented business meaning -- just the fields it actually reads.
    assert "REVENUE_RANK" in described and "REGION" in described


def test_no_description_without_an_expression():
    assert describe(None, object_name="X") is None
    assert describe("   ", object_name="X") is None


def test_a_bare_literal_yields_no_invented_description():
    assert describe("42", object_name="X") is None
