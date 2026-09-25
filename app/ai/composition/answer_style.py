"""How Power AI writes, and what it is told about the screen in view.

Shared by the tool-calling loop and the grounded composer so an answer reads
the same whichever path produced it.
"""

from app.ai.models.context import ResolvedAIContext

ANSWER_STYLE = """
Write the way a senior Power BI developer would explain this to a colleague:
open with a direct, plain-English answer to the question in one or two
sentences, then give the supporting detail. When the question is about a
measure, column or table, cover every part the evidence supports, in this
order:

  What it is - what it calculates or holds, in business terms, and which
  table and semantic model (and workspace) it belongs to.
  DAX - the exact expression, verbatim, then what each part does.
  Semantic model lineage - the measures, columns and tables it reads.
  Database lineage - the database, schema, table/view and columns behind
  those, and any composite-model hop on the way.
  What builds on it - dependent measures and columns, and the tables
  affected.
  Visual impact - the report, page and visual that would change, and
  whether it uses the object directly or through a dependent measure.

For a report, say which semantic model powers it, what its pages show,
which measures (with their DAX) and columns its visuals use, and where that
data comes from in the database. Answer the question that was asked first;
skip a section only when the evidence has nothing for it, and say plainly
when something could not be checked.

Formatting: the answer is shown as plain text, so do not use Markdown
headings, bold, italics, tables or backticks. Put each section title on its
own line, use "- " for list items, and put each DAX expression on its own
lines indented by four spaces, copied exactly. Keep names exactly as they
appear in the evidence.
""".strip()


def context_brief(context: ResolvedAIContext) -> str:
    """What the user has open, so "this report" and "it" resolve."""
    lines: list[str] = []

    if context.workspace_name or context.workspace_id:
        lines.append(f"Workspace: {context.workspace_name or context.workspace_id}")

    if context.report_id:
        report = context.report_name or context.report_id
        detail = ""
        definition = context.report_definition
        if definition is not None:
            detail = (
                f" ({definition.page_count} pages, {definition.visual_count} visuals)"
            )
        lines.append(f"Report open: '{report}'{detail}")

    if context.semantic_model_id:
        model = context.semantic_model_name or context.semantic_model_id
        home = context.semantic_model_workspace_name
        lines.append(
            f"Semantic model: '{model}'"
            + (
                f" in workspace '{home}'"
                if home and home != context.workspace_name
                else ""
            )
        )

    if context.resolved_object is not None:
        selected = context.resolved_object
        lines.append(
            f"Selected {selected.object_type.replace('_', ' ')}: "
            f"{selected.qualified_name}"
        )

    if context.related_reports:
        names = ", ".join(
            f"'{report.report_name or report.report_id}'"
            for report in context.related_reports
        )
        lines.append(f"Other reports on this model: {names}")

    lines.extend(f"Note: {note}" for note in context.resolution_notes)

    if not lines:
        return "Nothing is open: no workspace, report or semantic model is in context."

    return "\n".join(lines)
