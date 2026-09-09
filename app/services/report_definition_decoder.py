import base64
import binascii
import json
from typing import Any

from app.core.exceptions import (
    UpstreamInvalidResponseError,
)
from app.schemas.report_definition import (
    ReportDefinition,
)

MAX_DECODED_PART_BYTES = 10 * 1024 * 1024

MAX_TOTAL_JSON_BYTES = 50 * 1024 * 1024


class ReportDefinitionDecoder:
    @staticmethod
    def _is_structural_json(
        path: str,
    ) -> bool:
        if path == "definition.pbir":
            return True

        if path == "report.json":
            return True

        if path == "semanticModelDiagramLayout.json":
            return True

        return path.startswith("definition/") and path.endswith(".json")

    def decode(
        self,
        definition: ReportDefinition,
    ) -> dict[str, Any]:
        decoded: dict[
            str,
            Any,
        ] = {}

        total_decoded_bytes = 0

        for part in definition.parts:
            if not self._is_structural_json(part.path):
                continue

            if part.payload_type != "InlineBase64":
                raise (UpstreamInvalidResponseError("fabric"))

            raw_bytes = self._decode_base64(part.payload)

            if len(raw_bytes) > MAX_DECODED_PART_BYTES:
                raise (UpstreamInvalidResponseError("fabric"))

            total_decoded_bytes += len(raw_bytes)

            if total_decoded_bytes > MAX_TOTAL_JSON_BYTES:
                raise (UpstreamInvalidResponseError("fabric"))

            decoded[part.path] = self._decode_json(raw_bytes)

        return decoded

    @staticmethod
    def _decode_base64(
        payload: str,
    ) -> bytes:
        try:
            return base64.b64decode(
                payload,
                validate=True,
            )

        except (
            binascii.Error,
            ValueError,
        ) as exc:
            raise (UpstreamInvalidResponseError("fabric")) from exc

    @staticmethod
    def _decode_json(
        payload: bytes,
    ) -> Any:
        try:
            text = payload.decode("utf-8-sig")

            return json.loads(text)

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise (UpstreamInvalidResponseError("fabric")) from exc
