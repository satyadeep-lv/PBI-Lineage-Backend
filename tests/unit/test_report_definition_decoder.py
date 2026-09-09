import base64
import json

import pytest

from app.core.exceptions import (
    UpstreamInvalidResponseError,
)
from app.schemas.report_definition import (
    ReportDefinition,
    ReportDefinitionPart,
)
from app.services.report_definition_decoder import (
    ReportDefinitionDecoder,
)


def _encode(
    value: object,
) -> str:
    payload = json.dumps(value).encode("utf-8")

    return base64.b64encode(payload).decode("ascii")


def test_decode_definition_pbir():
    decoder = ReportDefinitionDecoder()

    definition = ReportDefinition(
        format="PBIR",
        parts=[
            ReportDefinitionPart(
                path="definition.pbir",
                payload=_encode({"version": "4.0"}),
                payload_type="InlineBase64",
            )
        ],
    )

    result = decoder.decode(definition)

    assert result["definition.pbir"]["version"] == "4.0"


def test_static_resource_is_ignored():
    decoder = ReportDefinitionDecoder()

    definition = ReportDefinition(
        format="PBIR",
        parts=[
            ReportDefinitionPart(
                path=("StaticResources/RegisteredResources/logo.png"),
                payload="not-base64",
                payload_type=("InlineBase64"),
            )
        ],
    )

    result = decoder.decode(definition)

    assert result == {}


def test_invalid_base64_raises():
    decoder = ReportDefinitionDecoder()

    definition = ReportDefinition(
        format="PBIR",
        parts=[
            ReportDefinitionPart(
                path="definition.pbir",
                payload="invalid!!!",
                payload_type="InlineBase64",
            )
        ],
    )

    with pytest.raises(UpstreamInvalidResponseError):
        decoder.decode(definition)
