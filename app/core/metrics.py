import re
from collections import defaultdict
from threading import RLock
from time import monotonic, perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_GROUNDING_COUNTER_NAMES = (
    "ai_requests_total",
    "ai_grounded_answers_total",
    "ai_insufficient_evidence_total",
    "ai_conflicting_evidence_total",
    "ai_grounding_validation_failed_total",
    "ai_deterministic_fallback_total",
    "ai_provider_failure_total",
)


class MetricsRegistry:
    def __init__(self) -> None:
        self.started_at = monotonic()
        self._lock = RLock()
        self._request_counts: dict[tuple[str, str, str], int] = defaultdict(int)
        self._duration_sums: dict[tuple[str, str], float] = defaultdict(float)
        self._duration_counts: dict[tuple[str, str], int] = defaultdict(int)
        self._in_progress = 0
        self._grounding_counts: dict[str, int] = defaultdict(int)

    def record_grounding_event(self, name: str) -> None:
        """Increment one of the fixed, known Power AI grounding counters.

        Unknown names are ignored rather than creating unbounded label
        cardinality, matching this registry's existing low-cardinality design.
        """
        if name not in _GROUNDING_COUNTER_NAMES:
            return
        with self._lock:
            self._grounding_counts[name] += 1

    def request_started(self) -> None:
        with self._lock:
            self._in_progress += 1

    def request_finished(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        status_class = f"{status_code // 100}xx"
        with self._lock:
            self._in_progress = max(0, self._in_progress - 1)
            self._request_counts[(method, route, status_class)] += 1
            self._duration_sums[(method, route)] += duration_seconds
            self._duration_counts[(method, route)] += 1

    def render_prometheus(self) -> str:
        with self._lock:
            request_counts = dict(self._request_counts)
            duration_sums = dict(self._duration_sums)
            duration_counts = dict(self._duration_counts)
            in_progress = self._in_progress
        lines = [
            "# HELP pbi_lineage_http_requests_total Completed HTTP requests.",
            "# TYPE pbi_lineage_http_requests_total counter",
        ]
        for (method, route, status_class), count in sorted(request_counts.items()):
            lines.append(
                "pbi_lineage_http_requests_total"
                f'{{method="{_escape(method)}",route="{_escape(route)}",'
                f'status="{status_class}"}} {count}'
            )
        lines.extend(
            [
                (
                    "# HELP pbi_lineage_http_request_duration_seconds "
                    "HTTP request duration."
                ),
                "# TYPE pbi_lineage_http_request_duration_seconds summary",
            ]
        )
        for (method, route), total in sorted(duration_sums.items()):
            labels = f'method="{_escape(method)}",route="{_escape(route)}"'
            lines.append(
                f"pbi_lineage_http_request_duration_seconds_sum{{{labels}}} {total:.6f}"
            )
            lines.append(
                "pbi_lineage_http_request_duration_seconds_count"
                f"{{{labels}}} {duration_counts[(method, route)]}"
            )
        lines.extend(
            [
                "# HELP pbi_lineage_http_requests_in_progress Current HTTP requests.",
                "# TYPE pbi_lineage_http_requests_in_progress gauge",
                f"pbi_lineage_http_requests_in_progress {in_progress}",
                "# HELP pbi_lineage_process_uptime_seconds Process uptime.",
                "# TYPE pbi_lineage_process_uptime_seconds gauge",
                (
                    "pbi_lineage_process_uptime_seconds "
                    f"{monotonic() - self.started_at:.3f}"
                ),
            ]
        )
        lines.extend(self._render_grounding_counters())
        return "\n".join(lines) + "\n"

    def _render_grounding_counters(self) -> list[str]:
        with self._lock:
            counts = dict(self._grounding_counts)
        lines: list[str] = []
        for name in _GROUNDING_COUNTER_NAMES:
            lines.append(f"# HELP {name} Power AI grounding outcome counter.")
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {counts.get(name, 0)}")
        return lines


metrics_registry = MetricsRegistry()


class MetricsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = perf_counter()
        status_code = 500
        metrics_registry.request_started()

        async def capture_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            route = _normalized_route(
                scope.get("path", "__unmatched__"),
                scope.get("path_params", {}),
            )
            metrics_registry.request_finished(
                method=scope.get("method", "UNKNOWN"),
                route=route,
                status_code=status_code,
                duration_seconds=perf_counter() - started,
            )


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


_UUID_SEGMENT = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
_LINEAGE_ID_SEGMENT = re.compile(r"^[a-z_]+:[0-9a-f]{16,64}$")


def _normalized_route(path: str, path_params: dict[str, object]) -> str:
    parameter_values = {str(value): name for name, value in path_params.items()}
    segments = []
    for segment in path.split("/"):
        if segment in parameter_values:
            segments.append(f"{{{parameter_values[segment]}}}")
        elif _UUID_SEGMENT.fullmatch(segment):
            segments.append("{uuid}")
        elif _LINEAGE_ID_SEGMENT.fullmatch(segment):
            segments.append("{lineage_id}")
        else:
            segments.append(segment)
    return "/".join(segments)
