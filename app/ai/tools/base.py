from collections.abc import Callable
from dataclasses import dataclass

from app.ai.models.context import ResolvedAIContext
from app.ai.models.evidence import EvidenceItem

ToolHandler = Callable[[ResolvedAIContext], list[EvidenceItem]]

#: Context fields a tool may require before it is safe/meaningful to call.
ToolRequirement = str


@dataclass(frozen=True)
class Tool:
    """One explicitly registered, read-only capability.

    Agents look tools up by name from the registry — there is no dynamic
    method invocation and no way to reach arbitrary application code from a
    tool name. A tool that is missing the context it needs simply returns
    no evidence instead of running or raising.
    """

    name: str
    description: str
    requires_context: frozenset[ToolRequirement]
    handler: ToolHandler

    def is_available(self, context: ResolvedAIContext) -> bool:
        checks: dict[str, bool] = {
            "semantic_model": context.parsed_semantic_model is not None,
            "report_definition": context.report_definition is not None,
            "resolved_object": context.resolved_object is not None,
        }
        return all(
            checks.get(requirement, False) for requirement in self.requires_context
        )

    def run(self, context: ResolvedAIContext) -> list[EvidenceItem]:
        if not self.is_available(context):
            return []
        return self.handler(context)
