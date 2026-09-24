"""The read-only tools a model may call, and nothing else.

Modelled on the reference implementation's agent tool set: a small number of
broad, self-describing capabilities the model chooses between, rather than a
single intent guessed from keywords. Every tool is read-only and bounded to
the caller's already-authorized context.
"""

from app.ai.tools import agent_tools
from app.ai.tools.base import Tool

_OBJECT_NAME = {
    "type": "string",
    "description": (
        "Name of a measure, column or table in the semantic model in "
        "context. Omit to use the object the user currently has selected."
    ),
}
_TABLE_NAME = {
    "type": "string",
    "description": "Table to disambiguate with, when the name is not unique.",
}


def _schema(properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="explain_object",
        description=(
            "Explain one measure or calculated column: its exact DAX, a "
            "plain-language reading of it, the semantic objects and database "
            "tables it reads from, and what downstream depends on it. Use "
            "this for any 'what is X', 'explain X' or 'how is X calculated' "
            "question."
        ),
        requires_context=frozenset({"semantic_model"}),
        handler=agent_tools.explain_object,
        parameters=_schema({"object_name": _OBJECT_NAME, "table_name": _TABLE_NAME}),
    ),
    Tool(
        name="object_lineage",
        description=(
            "Trace what an object reads from (upstream) or what would break "
            "if it changed (downstream). Use for impact and dependency "
            "questions."
        ),
        requires_context=frozenset({"semantic_model"}),
        handler=agent_tools.object_lineage,
        parameters=_schema(
            {
                "object_name": _OBJECT_NAME,
                "table_name": _TABLE_NAME,
                "direction": {
                    "type": "string",
                    "enum": ["upstream", "downstream"],
                    "description": "Defaults to upstream.",
                },
            }
        ),
    ),
    Tool(
        name="model_overview",
        description=(
            "List what the semantic model in context contains: its tables, "
            "the measures in each, and how many columns. Use this for "
            "inventory or orientation questions such as 'what measures are "
            "there' or 'what am I looking at'."
        ),
        requires_context=frozenset({"semantic_model"}),
        handler=agent_tools.model_overview,
        parameters=_schema({}),
    ),
    Tool(
        name="search_model",
        description=(
            "Find measures, columns or tables whose name contains a term. "
            "Use this first when the exact object name is not known."
        ),
        requires_context=frozenset({"semantic_model"}),
        handler=agent_tools.search_model,
        parameters=_schema(
            {
                "query": {
                    "type": "string",
                    "description": (
                        "A short entity term such as NET_SALES or Revenue -- "
                        "not the user's whole sentence."
                    ),
                }
            },
            required=["query"],
        ),
    ),
    Tool(
        name="physical_sources",
        description=(
            "List the databases, schemas and tables the semantic model "
            "ultimately reads from, including across a composite model."
        ),
        requires_context=frozenset({"semantic_model"}),
        handler=agent_tools.physical_sources,
        parameters=_schema({}),
    ),
    Tool(
        name="report_overview",
        description=(
            "Summarise the report in context: its format, pages, and how "
            "many visuals it has."
        ),
        requires_context=frozenset({"report_definition"}),
        handler=agent_tools.report_overview,
        parameters=_schema({}),
    ),
    Tool(
        name="report_visuals",
        description=(
            "List the report's visuals and the semantic fields each one "
            "uses. Call this only when the user explicitly asks about "
            "visuals, pages, charts, cards or slicers."
        ),
        requires_context=frozenset({"report_definition"}),
        handler=agent_tools.report_visuals,
        parameters=_schema({}),
    ),
)

TOOL_REGISTRY: dict[str, Tool] = {tool.name: tool for tool in _TOOLS}


def available_tools(context) -> list[Tool]:
    """Only the tools whose required context is actually present."""
    return [tool for tool in _TOOLS if tool.is_available(context)]


def tool_schemas(context) -> list[dict]:
    return [tool.schema() for tool in available_tools(context)]
