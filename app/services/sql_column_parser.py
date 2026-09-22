import re
from dataclasses import dataclass, field

_SELECT_FROM_PATTERN = re.compile(
    r"\bselect\b(?:\s+(?:top\s*\(?\s*\d+\s*\)?|distinct|all)\b)*\s*"
    r"(?P<columns>.+?)\bfrom\b",
    re.IGNORECASE | re.DOTALL,
)
_LEADING_DISTINCT_ALL = re.compile(r"^\s*(?:distinct|all)\s+", re.IGNORECASE)
_AS_KEYWORD_PATTERN = re.compile(r"\bAS\b", re.IGNORECASE)
_IDENTIFIER_SEGMENT = r"\[[^\]]+\]|\"[^\"]+\"|`[^`]+`|[A-Za-z_][A-Za-z0-9_$#]*"
_IDENTIFIER_SEGMENT_PATTERN = re.compile(_IDENTIFIER_SEGMENT)
_IDENTIFIER_CHAIN = re.compile(
    rf"(?:(?:{_IDENTIFIER_SEGMENT})\s*\.\s*)*(?:{_IDENTIFIER_SEGMENT})"
)
_STAR_PROJECTION = re.compile(rf"^\s*(?:(?:{_IDENTIFIER_SEGMENT})\s*\.\s*)?\*\s*$")
_SIMPLE_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_$#]*")

# Keywords and built-in function names that must never be mistaken for a
# column reference when scanning an arbitrary SQL expression for identifiers.
_SQL_KEYWORDS = frozenset(
    {
        "SELECT",
        "DISTINCT",
        "ALL",
        "FROM",
        "WHERE",
        "JOIN",
        "LEFT",
        "RIGHT",
        "FULL",
        "INNER",
        "OUTER",
        "ON",
        "AS",
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
        "END",
        "AND",
        "OR",
        "NOT",
        "NULL",
        "IS",
        "IN",
        "LIKE",
        "BETWEEN",
        "GROUP",
        "BY",
        "ORDER",
        "HAVING",
        "LIMIT",
        "OFFSET",
        "QUALIFY",
        "OVER",
        "PARTITION",
        "ROW",
        "ROWS",
        "RANGE",
        "CURRENT",
        "PRECEDING",
        "FOLLOWING",
        "ASC",
        "DESC",
        "TRUE",
        "FALSE",
        "CAST",
        "CONVERT",
        "TRY_CAST",
        "DATE",
        "DATE_TRUNC",
        "TO_DATE",
        "TO_TIMESTAMP",
        "SUM",
        "AVG",
        "MIN",
        "MAX",
        "COUNT",
        "COUNT_DISTINCT",
        "COALESCE",
        "NVL",
        "IFNULL",
        "IFF",
        "ROUND",
        "ABS",
        "UPPER",
        "LOWER",
        "TRIM",
        "LTRIM",
        "RTRIM",
        "CONCAT",
        "SUBSTR",
        "SUBSTRING",
        "REPLACE",
        "REGEXP_REPLACE",
        "TOP",
    }
)


@dataclass(frozen=True)
class SqlSelectColumn:
    """One projected column of a ``SELECT`` list.

    ``source_identifiers`` lists every physical column the projected
    expression reads from (in order, deduplicated) — a plain pass-through
    column has exactly one; a computed expression such as
    ``FIRST_NAME || ' ' || LAST_NAME AS FULL_NAME`` has every column it
    combines (``["FIRST_NAME", "LAST_NAME"]``), not just the alias.
    """

    output_name: str
    source_identifiers: list[str] = field(default_factory=list)
    raw_expression: str = ""


def parse_select_columns(query: str) -> list[SqlSelectColumn]:
    """Best-effort extraction of a native SQL query's outermost ``SELECT``
    projection list. This is not a general SQL parser: ``SELECT *`` and
    subqueries nested in the column list are skipped rather than guessed, and
    a computed expression with no identifiable column reference falls back
    to assuming a physical column with the same name as its alias.
    """
    match = _SELECT_FROM_PATTERN.search(query)
    if not match:
        return []

    columns: list[SqlSelectColumn] = []
    for item in _split_top_level_commas(match.group("columns")):
        item = _LEADING_DISTINCT_ALL.sub("", item.strip()).strip()
        if not item or _STAR_PROJECTION.match(item):
            continue
        columns.append(_parse_column_item(item))
    return columns


def _parse_column_item(item: str) -> SqlSelectColumn:
    alias, expression = _split_alias(item)
    identifiers = _extract_source_identifiers(expression)

    if not alias:
        segments = _IDENTIFIER_SEGMENT_PATTERN.findall(expression)
        alias = _unquote(segments[-1]) if segments else expression.strip()

    if not identifiers and _SIMPLE_IDENTIFIER.fullmatch(alias):
        identifiers = [alias]

    return SqlSelectColumn(
        output_name=alias,
        source_identifiers=identifiers,
        raw_expression=expression,
    )


def _split_alias(item: str) -> tuple[str | None, str]:
    """Split ``expr AS alias`` or ``expr alias`` into ``(alias, expr)``.

    Returns ``(None, item)`` when no alias is present, so the caller derives
    the output name from the expression itself.
    """
    as_index = _find_top_level_as(item)
    if as_index is not None:
        expression = item[:as_index].strip()
        alias_text = item[as_index + 2 :].strip()
        if _SIMPLE_IDENTIFIER.fullmatch(_unquote(alias_text)):
            return _unquote(alias_text), expression
        return None, item

    implicit = _implicit_alias_split(item)
    if implicit is not None:
        return implicit

    return None, item


def _implicit_alias_split(item: str) -> tuple[str, str] | None:
    stripped = item.rstrip()
    last_match = None
    for candidate in _IDENTIFIER_CHAIN.finditer(stripped):
        if candidate.end() == len(stripped):
            last_match = candidate

    if last_match is None:
        return None

    before = stripped[: last_match.start()].rstrip()
    if not before or before.endswith("."):
        return None

    segments = _IDENTIFIER_SEGMENT_PATTERN.findall(last_match.group(0))
    candidate_name = _unquote(segments[-1]) if segments else None
    if not candidate_name or not _SIMPLE_IDENTIFIER.fullmatch(candidate_name):
        return None
    if candidate_name.upper() in _SQL_KEYWORDS:
        return None

    return candidate_name, before


def _extract_source_identifiers(expression: str) -> list[str]:
    """Find every real column reference in a SQL expression, skipping SQL
    keywords, function names, and numeric literals.
    """
    cleaned = _strip_string_literals(expression)
    identifiers: list[str] = []
    seen: set[str] = set()

    for match in _IDENTIFIER_CHAIN.finditer(cleaned):
        raw = match.group(0)
        segments = _IDENTIFIER_SEGMENT_PATTERN.findall(raw)
        if not segments:
            continue
        token = _unquote(segments[-1])

        following = cleaned[match.end() : match.end() + 1]
        if following == "(" and len(segments) == 1:
            continue
        if token.upper() in _SQL_KEYWORDS:
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?", token):
            continue

        key = token.casefold()
        if key not in seen:
            seen.add(key)
            identifiers.append(token)

    return identifiers


def _strip_string_literals(expression: str) -> str:
    return re.sub(r"'(?:''|[^'])*'", " ", expression)


def _unquote(token: str) -> str:
    if len(token) >= 2 and token[0] == "[" and token[-1] == "]":
        return token[1:-1]
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ('"', "`"):
        return token[1:-1]
    return token


def split_dotted_identifier(identifier: str) -> list[str]:
    """Split a possibly-quoted ``db.schema.table``-style identifier into its
    parts, treating ``[...]``/``"..."``/`` `...` `` spans (which may contain a
    literal ``.``) as opaque.
    """
    identifier = identifier.strip().strip(",;")
    if not identifier or identifier.startswith("("):
        return []

    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    bracket = False

    for character in identifier:
        if bracket:
            current.append(character)
            if character == "]":
                bracket = False
            continue
        if quote:
            current.append(character)
            if character == quote:
                quote = None
            continue
        if character in ('"', "`"):
            quote = character
            current.append(character)
            continue
        if character == "[":
            bracket = True
            current.append(character)
            continue
        if character == ".":
            parts.append(_unquote("".join(current).strip()))
            current = []
            continue
        current.append(character)

    if current:
        parts.append(_unquote("".join(current).strip()))

    return [part for part in parts if part]


def _top_level_mask(text: str) -> list[bool]:
    """True at each index that is outside parentheses, brackets, and string
    literals, so callers can find top-level commas/keywords without
    mis-splitting on a nested subquery, function call, or literal value.
    """
    mask = [False] * len(text)
    depth = 0
    index = 0
    length = len(text)

    while index < length:
        character = text[index]

        if character == "(":
            depth += 1
            index += 1
            continue
        if character == ")":
            depth = max(0, depth - 1)
            index += 1
            continue
        if character == "[":
            end = text.find("]", index + 1)
            index = length if end < 0 else end + 1
            continue
        if character == "'":
            index += 1
            while index < length:
                if text[index] == "'" and text[index + 1 : index + 2] == "'":
                    index += 2
                    continue
                if text[index] == "'":
                    index += 1
                    break
                index += 1
            continue
        if character == '"':
            end = text.find('"', index + 1)
            index = length if end < 0 else end + 1
            continue

        if depth == 0:
            mask[index] = True
        index += 1

    return mask


def _split_top_level_commas(text: str) -> list[str]:
    mask = _top_level_mask(text)
    parts: list[str] = []
    start = 0
    for index, character in enumerate(text):
        if character == "," and mask[index]:
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return parts


def _find_top_level_as(text: str) -> int | None:
    mask = _top_level_mask(text)
    last_start: int | None = None
    for match in _AS_KEYWORD_PATTERN.finditer(text):
        if mask[match.start()]:
            last_start = match.start()
    return last_start
