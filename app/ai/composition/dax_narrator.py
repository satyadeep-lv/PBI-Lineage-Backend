"""Describe a DAX expression in plain language, deterministically.

This is not a model call and never guesses business meaning: it describes
only what the expression structurally does, in terms of the names already in
it. A language model can phrase it better, but this always works -- including
when no AI provider is configured or reachable -- so the plain-language line
is never the part of an answer that goes missing.

Anything it cannot recognise degrades to naming what the expression reads
rather than inventing a description.
"""

import re

_AGGREGATIONS = {
    "SUM": "Adds up",
    "AVERAGE": "Averages",
    "MIN": "Takes the smallest",
    "MAX": "Takes the largest",
    "COUNT": "Counts the values in",
    "COUNTA": "Counts the non-empty values in",
    "DISTINCTCOUNT": "Counts how many distinct values there are in",
    "SUMX": "Adds up, row by row,",
    "AVERAGEX": "Averages, row by row,",
}

_FIELD = re.compile(
    r"""(?:'(?P<qtable>[^']+)'|(?P<table>[A-Za-z_][\w]*))?\s*
        \[(?P<field>[^\]]+)\]""",
    re.VERBOSE,
)
_FUNCTION_CALL = re.compile(
    r"^\s*(?P<name>[A-Z][A-Z0-9._]*)\s*\((?P<args>.*)\)\s*$", re.IGNORECASE | re.DOTALL
)


def describe(expression: str | None, *, object_name: str) -> str | None:
    """One sentence describing what `expression` computes."""
    if not expression or not expression.strip():
        return None

    text = " ".join(expression.split())
    described = _describe_expression(text)

    if described is None:
        references = _referenced_names(text)
        if not references:
            return None
        joined = _join(references)
        return f"{object_name} is calculated with DAX from {joined}."

    return f"{object_name} {described}."


def _describe_expression(text: str) -> str | None:
    call = _FUNCTION_CALL.match(text)

    if call is not None:
        name = call.group("name").upper()
        arguments = _split_arguments(call.group("args"))

        if name in _AGGREGATIONS and arguments:
            return f"{_AGGREGATIONS[name].lower()} {_readable(arguments[-1])}"

        if name == "COUNTROWS" and arguments:
            return f"counts the rows in {_readable(arguments[0])}"

        if name == "DIVIDE" and len(arguments) >= 2:
            return (
                f"divides {_noun_phrase(arguments[0])} by {_noun_phrase(arguments[1])}"
            )

        if name == "CALCULATE" and arguments:
            base = _verb_phrase(arguments[0])
            filters = [_condition(argument) for argument in arguments[1:]]
            if filters:
                return f"{base}, restricted to {_join(filters)}"
            return base

        if name == "IF" and len(arguments) >= 3:
            return (
                f"returns {_readable(arguments[1])} when "
                f"{_condition(arguments[0])}, and {_readable(arguments[2])} "
                "otherwise"
            )

        if name == "SWITCH" and len(arguments) >= 3:
            return _describe_switch(arguments)

    for operator, joined, continued in _OPERATORS:
        parts = _split_top_level(text, operator)
        if len(parts) != 2:
            continue
        left = _describe_expression(parts[0])
        right = _readable(parts[1])
        if left is not None:
            # e.g. DIVIDE(a, b) * 100 -> "divides a by b, then multiplies
            # the result by 100" rather than "is divides a by b ...".
            return f"{left}, then {continued} {right}"
        return f"equals {_readable(parts[0])} {joined} {right}"

    return None


_OPERATORS = (
    (" - ", "minus", "subtracts"),
    (" + ", "plus", "adds"),
    (" * ", "multiplied by", "multiplies the result by"),
    (" / ", "divided by", "divides the result by"),
)


_NOUN_FORMS = {
    "SUM": "the total of {0}",
    "AVERAGE": "the average of {0}",
    "MIN": "the smallest {0}",
    "MAX": "the largest {0}",
    "COUNT": "the count of {0}",
    "COUNTA": "the count of {0}",
    "COUNTROWS": "the number of {0} rows",
    "DISTINCTCOUNT": "the number of distinct {0}",
}


def _noun_phrase(fragment: str) -> str:
    """A noun form, for places a verb phrase would not read as English.

    "divides counts the rows in X by ..." is not a sentence; "divides the
    number of X rows by ..." is.
    """
    fragment = fragment.strip()
    call = _FUNCTION_CALL.match(fragment)

    if call is None:
        return _readable(fragment)

    name = call.group("name").upper()
    arguments = _split_arguments(call.group("args"))

    if name in _NOUN_FORMS and arguments:
        inner = _readable(arguments[-1]).strip("'\"")
        return _NOUN_FORMS[name].format(inner)

    if name == "CALCULATE" and arguments:
        base = _noun_phrase(arguments[0])
        filters = [_condition(argument) for argument in arguments[1:]]
        if filters:
            return f"{base} restricted to {_join(filters)}"
        return base

    return _readable(fragment)


_MAX_LISTED_CASES = 3


def _describe_switch(arguments: list[str]) -> str:
    """Narrate SWITCH, including the `SWITCH(TRUE(), ...)` banding idiom.

    Saying only "checks TRUE() against N cases" tells a reader nothing; the
    useful part is which field is being banded and what the bands are.
    """
    is_true_form = arguments[0].strip().upper().rstrip("()") == "TRUE"
    cases = arguments[1:] if is_true_form else arguments[1:]

    pairs: list[tuple[str, str]] = []
    index = 0
    while index + 1 < len(cases):
        pairs.append((cases[index], cases[index + 1]))
        index += 2
    default = cases[index] if index < len(cases) else None

    if not pairs:
        return f"picks a result based on {_readable(arguments[0])}"

    listed = pairs[:_MAX_LISTED_CASES]
    clauses = [
        f"{_readable(result)} when {_condition(condition)}"
        for condition, result in listed
    ]

    if len(pairs) > len(listed):
        clauses.append(f"and {len(pairs) - len(listed)} more cases")

    sentence = f"returns {_join(clauses)}"

    if default is not None:
        sentence = f"{sentence}, and {_readable(default)} otherwise"

    if not is_true_form:
        sentence = f"{sentence}, matching on {_readable(arguments[0])}"

    return sentence


def _verb_phrase(fragment: str) -> str:
    """A phrase that can follow the object's name directly."""
    described = _describe_expression(fragment.strip())

    if described is not None:
        return described

    return f"equals {_readable(fragment)}"


def _condition(fragment: str) -> str:
    """Keep a filter readable, including its comparison."""
    fragment = fragment.strip()
    match = _COMPARISON.match(fragment)

    if match is None:
        return _readable(fragment)

    names = _referenced_names(match.group("left"))
    left = names[0] if names else match.group("left").strip()

    return f"{left} {match.group('operator')} {match.group('right').strip()}"


_COMPARISON = re.compile(
    r"^(?P<left>.+?)\s*(?P<operator><>|>=|<=|=|>|<)\s*(?P<right>.+)$"
)


def _readable(fragment: str) -> str:
    fragment = fragment.strip()
    nested = _describe_expression(fragment)

    if nested is not None:
        # "equals X" is a copula for a whole sentence; inside a larger phrase
        # only the X part belongs.
        return nested.removeprefix("equals ")

    references = _referenced_names(fragment)

    if len(references) == 1 and _FIELD.fullmatch(fragment.strip()):
        return references[0]

    if references:
        return _join(references)

    return fragment


def _referenced_names(text: str) -> list[str]:
    names: list[str] = []

    for match in _FIELD.finditer(text):
        field = match.group("field").strip()
        if field and field not in names:
            names.append(field)

    return names


def _join(values: list[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    return f"{', '.join(values[:-1])} and {values[-1]}"


def _split_arguments(text: str) -> list[str]:
    return _split_top_level(text, ",")


def _split_top_level(text: str, separator: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    quoted: str | None = None
    index = 0

    while index < len(text):
        character = text[index]

        if quoted is not None:
            current.append(character)
            if character == quoted:
                quoted = None
            index += 1
            continue

        if character in "'\"":
            quoted = character
            current.append(character)
            index += 1
            continue

        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1

        if depth == 0 and text.startswith(separator, index):
            parts.append("".join(current))
            current = []
            index += len(separator)
            continue

        current.append(character)
        index += 1

    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]
