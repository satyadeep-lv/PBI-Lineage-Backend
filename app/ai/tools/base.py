from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.ai.models.context import ResolvedAIContext
from app.ai.models.evidence import EvidenceItem

ToolHandler = Callable[[ResolvedAIContext, Mapping[str, Any]], list[EvidenceItem]]

#: Context fields a tool may require before it is safe/meaningful to call.
ToolRequirement = str


@dataclass(frozen=True)
class Tool:
    """One explicitly registered, read-only capability.

    Tools are looked up by name from the registry -- there is no dynamic
    method invocation, so a tool name from a model can never reach arbitrary
    application code. A tool that is missing the context it needs returns no
    evidence rather than running or raising.

    Arguments are the model's only influence on what a tool does, and they
    are resolved strictly inside `ResolvedAIContext`, which was built from
    the caller's own authorized fetch. Naming an object the caller cannot
    see therefore returns nothing; it cannot widen access.
    """

    name: str
    description: str
    requires_context: frozenset[ToolRequirement]
    handler: ToolHandler
    parameters: dict[str, Any] = field(default_factory=dict)

    def is_available(self, context: ResolvedAIContext) -> bool:
        checks: dict[str, bool] = {
            "semantic_model": context.parsed_semantic_model is not None,
            "report_definition": context.report_definition is not None,
            "resolved_object": context.resolved_object is not None,
        }
        return all(
            checks.get(requirement, False) for requirement in self.requires_context
        )

    def run(
        self,
        context: ResolvedAIContext,
        arguments: Mapping[str, Any] | None = None,
    ) -> list[EvidenceItem]:
        if not self.is_available(context):
            return []
        return self.handler(context, arguments or {})

    def schema(self) -> dict[str, Any]:
        """The tool as a provider-neutral JSON-Schema definition."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
            or {"type": "object", "properties": {}, "additionalProperties": False},
        }
