"""Best-effort reading of Snowflake SQL for column transformations.

Given the SQL that defines an object -- a view's DDL, or the INSERT / CTAS /
MERGE / UPDATE / COPY that loaded a table -- find the expression that
produces one column, follow it through CTEs and FROM-subqueries, and name the
real tables it reads. It replaces the legacy TRACE_COLUMN_LINEAGE
procedure's regex heuristics and is deliberately not a full SQL engine: the
text is tokenised once, clauses are found by keyword at the right paren
depth, and anything unrecognised degrades to "not found" rather than raising.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

_MAX_SQL_CHARS = 1_000_000
_MAX_DEPTH = 12
_MAX_STEPS = 20

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
_NUMBER = re.compile(r"(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_POSITIONAL = re.compile(r"\$\d+")
_STAGE = re.compile(r"@[^\s,;()]*")
_OPERATORS = ("::", "=>", "->", "||", "<=", ">=", "<>", "!=")

# Words that end a select list, a FROM clause or an expression, and so can
# never be an implicit alias or a column reference.
_CLAUSE_WORDS = frozenset(
    {
        "FROM", "WHERE", "GROUP", "HAVING", "QUALIFY", "ORDER", "LIMIT",
        "OFFSET", "FETCH", "WINDOW", "UNION", "INTERSECT", "EXCEPT", "MINUS",
        "ON", "USING", "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "OUTER",
        "CROSS", "NATURAL", "ASOF", "LATERAL", "MATCH_CONDITION", "SAMPLE",
        "TABLESAMPLE", "AT", "BEFORE", "CHANGES", "PIVOT", "UNPIVOT", "WHEN",
        "THEN", "ELSE", "SET", "VALUES", "SELECT", "WITH", "AS", "INTO",
    }
)  # fmt: skip
_KEYWORDS = _CLAUSE_WORDS | frozenset(
    {
        "CASE", "END", "AND", "OR", "NOT", "NULL", "IS", "IN", "LIKE", "ILIKE",
        "RLIKE", "REGEXP", "BETWEEN", "EXISTS", "DISTINCT", "ALL", "ANY",
        "SOME", "OVER", "PARTITION", "BY", "ASC", "DESC", "NULLS", "FIRST",
        "LAST", "ROWS", "RANGE", "UNBOUNDED", "PRECEDING", "FOLLOWING",
        "CURRENT", "ROW", "WITHIN", "FILTER", "IGNORE", "RESPECT", "TRUE",
        "FALSE", "INTERVAL", "CAST", "TRY_CAST", "BOTH", "LEADING", "TRAILING",
        "FOR", "ESCAPE", "COLLATE", "DATE", "TIME", "TIMESTAMP", "TOP",
        "CURRENT_DATE", "CURRENT_TIME", "CURRENT_TIMESTAMP", "CURRENT_USER",
        "CURRENT_ROLE", "LOCALTIME", "LOCALTIMESTAMP", "SYSDATE",
    }
)  # fmt: skip
# The first argument of these is a date part (DATEADD(day, 1, d)), not a column.
_DATE_PART_FUNCTIONS = frozenset(
    {
        "DATEADD", "DATEDIFF", "DATE_TRUNC", "DATE_PART", "TIMEADD", "TIMEDIFF",
        "TIMESTAMPADD", "TIMESTAMPDIFF", "LAST_DAY", "TIME_SLICE", "EXTRACT",
    }
)  # fmt: skip
_CREATE_MODIFIERS = frozenset(
    {
        "OR", "REPLACE", "ALTER", "SECURE", "RECURSIVE", "LOCAL", "GLOBAL",
        "TEMP", "TEMPORARY", "VOLATILE", "TRANSIENT", "ICEBERG", "HYBRID",
        "EVENT",
    }
)  # fmt: skip
_SET_OPERATORS = frozenset({"UNION", "INTERSECT", "EXCEPT", "MINUS"})
_JOIN_WORDS = frozenset(
    {"JOIN", "INNER", "LEFT", "RIGHT", "FULL", "OUTER", "CROSS", "NATURAL", "ASOF"}
)


@dataclass(frozen=True)
class SqlObjectName:
    parts: tuple[str, ...]

    def resolve(
        self,
        database: str | None,
        schema: str | None,
    ) -> tuple[str | None, str | None, str]:
        """(database, schema, name), missing leading parts from the defaults."""
        parts = self.parts[-3:]
        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
        if len(parts) == 2:
            return database, parts[0], parts[1]
        return database, schema, parts[0] if parts else ""


@dataclass(frozen=True)
class SqlStatementInfo:
    kind: str
    target: SqlObjectName | None = None
    target_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class SqlColumnSource:
    table: SqlObjectName
    column: str
    certain: bool = True


@dataclass(frozen=True)
class SqlColumnTransformation:
    column: str
    expression: str | None
    kind: str
    steps: tuple[str, ...] = ()
    referenced_columns: tuple[str, ...] = ()
    source_columns: tuple[SqlColumnSource, ...] = ()
    stage: str | None = None
    branch_count: int = 1


@dataclass(frozen=True)
class _Token:
    kind: str  # word, quoted, string, number, positional, stage, op
    text: str
    start: int
    end: int
    depth: int

    @property
    def upper(self) -> str:
        return self.text.upper() if self.kind == "word" else ""

    def is_name(self) -> bool:
        return self.kind == "quoted" or (
            self.kind == "word" and self.upper not in _KEYWORDS
        )


def normalize_identifier(raw: str) -> str:
    """Unquoted names are stored upper-case; quoted ones exactly."""
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        return raw[1:-1].replace('""', '"')
    return raw.upper()


def split_identifier(raw: str) -> tuple[str, ...]:
    """`"My Db".sch."T.x"` -> ("My Db", "SCH", "T.x")."""
    parts: list[str] = []
    current: list[str] = []
    quoted = False
    index = 0
    while index < len(raw):
        character = raw[index]
        if character == '"':
            if quoted and raw[index + 1 : index + 2] == '"':
                current.append('""')
                index += 2
                continue
            quoted = not quoted
            current.append(character)
        elif character == "." and not quoted:
            parts.append("".join(current))
            current = []
        else:
            current.append(character)
        index += 1
    parts.append("".join(current))
    return tuple(normalize_identifier(part) for part in parts if part.strip())


def collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def strip_comments(sql: str) -> str:
    return _text(sql, _tokenize(sql))


def _tokenize(sql: str) -> list[_Token]:
    sql = sql[:_MAX_SQL_CHARS]
    tokens: list[_Token] = []
    depth = 0
    index = 0
    length = len(sql)
    while index < length:
        character = sql[index]
        if character.isspace():
            index += 1
            continue
        if sql.startswith("--", index) or sql.startswith("//", index):
            end = sql.find("\n", index)
            index = length if end < 0 else end + 1
            continue
        if sql.startswith("/*", index):
            end = sql.find("*/", index + 2)
            index = length if end < 0 else end + 2
            continue
        start = index
        if character == "'":
            index += 1
            while index < length:
                if sql[index] == "\\":
                    index += 2
                    continue
                if sql[index] == "'":
                    if sql[index + 1 : index + 2] == "'":
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            tokens.append(_Token("string", sql[start:index], start, index, depth))
            continue
        if sql.startswith("$$", index):
            end = sql.find("$$", index + 2)
            index = length if end < 0 else end + 2
            tokens.append(_Token("string", sql[start:index], start, index, depth))
            continue
        if character == '"':
            index += 1
            while index < length:
                if sql[index] == '"':
                    if sql[index + 1 : index + 2] == '"':
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            tokens.append(_Token("quoted", sql[start:index], start, index, depth))
            continue
        match = (
            _WORD.match(sql, index)
            or _POSITIONAL.match(sql, index)
            or _NUMBER.match(sql, index)
        )
        if match is not None:
            text = match.group(0)
            kind = (
                "word"
                if text[0].isalpha() or text[0] == "_"
                else "positional"
                if text[0] == "$"
                else "number"
            )
            index = match.end()
            tokens.append(_Token(kind, text, start, index, depth))
            continue
        if character == "@":
            match = _STAGE.match(sql, index)
            index = match.end() if match else index + 1
            tokens.append(_Token("stage", sql[start:index], start, index, depth))
            continue
        operator = next(
            (item for item in _OPERATORS if sql.startswith(item, index)), None
        )
        text = operator or character
        if text == ")":
            depth = max(0, depth - 1)
        tokens.append(_Token("op", text, start, start + len(text), depth))
        if text == "(":
            depth += 1
        index += len(text)
    return tokens


def _text(sql: str, tokens: Sequence[_Token]) -> str:
    """The original SQL a token run spans, comments removed, whitespace collapsed."""
    pieces: list[str] = []
    previous: _Token | None = None
    for token in tokens:
        if previous is not None and token.start > previous.end:
            # Only whitespace and comments sit between tokens.
            pieces.append(" ")
        pieces.append(token.text)
        previous = token
    return collapse_whitespace("".join(pieces))


def _matching(tokens: Sequence[_Token], index: int) -> int:
    """Index of the ")" closing the "(" at `index` (or the last token)."""
    depth = tokens[index].depth
    for position in range(index + 1, len(tokens)):
        if tokens[position].text == ")" and tokens[position].depth == depth:
            return position
    return len(tokens) - 1


def _name_chain(tokens: Sequence[_Token], index: int) -> tuple[tuple[str, ...], int]:
    """A dotted name starting at `index`: its normalised parts, next index."""
    parts: list[str] = []
    while index < len(tokens) and tokens[index].kind in ("word", "quoted"):
        parts.append(normalize_identifier(tokens[index].text))
        if (
            index + 2 < len(tokens)
            and tokens[index + 1].text == "."
            and tokens[index + 2].kind in ("word", "quoted")
        ):
            index += 2
            continue
        index += 1
        break
    return tuple(parts), index


def _split(tokens: Sequence[_Token], depth: int) -> list[list[_Token]]:
    """Split on commas at `depth`."""
    parts: list[list[_Token]] = [[]]
    for token in tokens:
        if token.text == "," and token.depth == depth:
            parts.append([])
        else:
            parts[-1].append(token)
    return [part for part in parts if part]


def _column_list(tokens: Sequence[_Token], index: int) -> tuple[tuple[str, ...], int]:
    """`(C1, C2 COMMENT 'x', ...)` at `index`: first name of each item."""
    end = _matching(tokens, index)
    names = tuple(
        normalize_identifier(item[0].text)
        for item in _split(tokens[index + 1 : end], tokens[index].depth + 1)
        if item[0].kind in ("word", "quoted")
    )
    return names, end + 1


def _query_start(tokens: Sequence[_Token], index: int, depth: int) -> int | None:
    """The first top-level `AS` that is followed by a query."""
    for position in range(index, len(tokens) - 1):
        token = tokens[position]
        following = tokens[position + 1]
        if (
            token.depth == depth
            and token.upper == "AS"
            and (following.upper in ("SELECT", "WITH") or following.text == "(")
        ):
            return position + 1
    return None


@dataclass
class _Statement:
    info: SqlStatementInfo
    tokens: list[_Token]
    body: int | None = None  # index where the defining query starts
    after_target: int = 0  # index just past the target name and column list


def _statement(sql: str) -> _Statement:
    tokens = _tokenize(sql)
    while tokens and tokens[0].text in (";",):
        tokens = tokens[1:]
    if not tokens:
        return _Statement(SqlStatementInfo("OTHER"), tokens)
    first = tokens[0].upper
    depth = tokens[0].depth

    if first == "CREATE":
        index = 1
        while index < len(tokens) and tokens[index].upper in _CREATE_MODIFIERS:
            index += 1
        words = [token.upper for token in tokens[index : index + 2]]
        kind = None
        if words[:2] == ["MATERIALIZED", "VIEW"]:
            kind, index = "CREATE_MATERIALIZED_VIEW", index + 2
        elif words[:2] == ["DYNAMIC", "TABLE"]:
            kind, index = "CREATE_DYNAMIC_TABLE", index + 2
        elif words[:2] == ["EXTERNAL", "TABLE"]:
            kind, index = "CREATE_EXTERNAL_TABLE", index + 2
        elif words[:1] == ["VIEW"]:
            kind, index = "CREATE_VIEW", index + 1
        elif words[:1] == ["TABLE"]:
            kind, index = "CREATE_TABLE", index + 1
        if kind is None:
            return _Statement(SqlStatementInfo("OTHER"), tokens)
        if [token.upper for token in tokens[index : index + 3]] == [
            "IF",
            "NOT",
            "EXISTS",
        ]:
            index += 3
        parts, index = _name_chain(tokens, index)
        columns: tuple[str, ...] = ()
        if index < len(tokens) and tokens[index].text == "(":
            columns, index = _column_list(tokens, index)
        body = _query_start(tokens, index, depth)
        if kind == "CREATE_TABLE":
            if any(
                token.upper == "CLONE" and token.depth == depth
                for token in tokens[index:]
            ):
                kind = "CREATE_TABLE_CLONE"
            elif body is not None:
                kind = "CREATE_TABLE_AS_SELECT"
        return _Statement(
            SqlStatementInfo(kind, SqlObjectName(parts) if parts else None, columns),
            tokens,
            body,
            index,
        )

    if first == "INSERT":
        index = 1
        if index < len(tokens) and tokens[index].upper == "OVERWRITE":
            index += 1
        if index < len(tokens) and tokens[index].upper in ("ALL", "FIRST"):
            into = next(
                (
                    position
                    for position in range(index, len(tokens))
                    if tokens[position].upper == "INTO"
                ),
                None,
            )
            parts = _name_chain(tokens, into + 1)[0] if into is not None else ()
            return _Statement(
                SqlStatementInfo(
                    "MULTI_TABLE_INSERT", SqlObjectName(parts) if parts else None
                ),
                tokens,
            )
        if index < len(tokens) and tokens[index].upper == "INTO":
            index += 1
        parts, index = _name_chain(tokens, index)
        columns = ()
        if (
            index < len(tokens)
            and tokens[index].text == "("
            and not (
                index + 1 < len(tokens)
                and tokens[index + 1].upper in ("SELECT", "WITH")
            )
        ):
            columns, index = _column_list(tokens, index)
        values = index < len(tokens) and tokens[index].upper == "VALUES"
        return _Statement(
            SqlStatementInfo(
                "INSERT_VALUES" if values else "INSERT",
                SqlObjectName(parts) if parts else None,
                columns,
            ),
            tokens,
            None if values else index,
            index,
        )

    if first in ("MERGE", "COPY") and len(tokens) > 1 and tokens[1].upper == "INTO":
        if tokens[2:3] and tokens[2].kind == "stage":
            return _Statement(SqlStatementInfo("OTHER"), tokens)
        parts, index = _name_chain(tokens, 2)
        columns = ()
        if first == "COPY" and index < len(tokens) and tokens[index].text == "(":
            columns, index = _column_list(tokens, index)
        return _Statement(
            SqlStatementInfo(first, SqlObjectName(parts) if parts else None, columns),
            tokens,
            None,
            index,
        )

    if first == "UPDATE":
        parts, index = _name_chain(tokens, 1)
        return _Statement(
            SqlStatementInfo("UPDATE", SqlObjectName(parts) if parts else None),
            tokens,
            None,
            index,
        )

    if first in ("SELECT", "WITH") or tokens[0].text == "(":
        return _Statement(SqlStatementInfo("SELECT"), tokens, 0, 0)
    return _Statement(SqlStatementInfo("OTHER"), tokens)


def describe_statement(sql: str) -> SqlStatementInfo:
    return _statement(sql).info


# -- queries ------------------------------------------------------------------


@dataclass
class _Item:
    tokens: list[_Token]
    alias: str | None = None
    star: bool = False
    star_qualifier: str | None = None
    excluded: frozenset[str] = frozenset()
    renamed: dict[str, str] = field(default_factory=dict)

    def output(self) -> str | None:
        if self.alias is not None:
            return self.alias
        reference = _reference(self.tokens)
        return reference[-1] if reference else None


@dataclass
class _Source:
    kind: str  # table, cte, subquery, other
    name: SqlObjectName | None = None
    alias: str | None = None
    query: "_Query | None" = None
    columns: tuple[str, ...] = ()

    def matches(self, qualifier: tuple[str, ...]) -> bool:
        if self.alias is not None:
            return qualifier == (self.alias,)
        if self.name is None:
            return False
        return self.name.parts[-len(qualifier) :] == qualifier

    @property
    def label(self) -> str:
        if self.alias is not None:
            return self.alias
        return ".".join(self.name.parts) if self.name is not None else self.kind


@dataclass
class _Select:
    items: list[_Item]
    sources: list[_Source]


@dataclass
class _Query:
    branches: list[_Select]
    operators: list[str]


_QUERY_END_WORDS = frozenset(
    {"WHERE", "GROUP", "HAVING", "QUALIFY", "ORDER", "LIMIT", "OFFSET", "FETCH",
     "WINDOW"}
)  # fmt: skip


def _reference(tokens: Sequence[_Token]) -> tuple[str, ...] | None:
    """`a.b.c` (names only) as normalised parts, else None."""
    if not tokens or len(tokens) % 2 == 0:
        return None
    parts: list[str] = []
    for position, token in enumerate(tokens):
        if position % 2:
            if token.text != ".":
                return None
        elif not token.is_name():
            return None
        else:
            parts.append(normalize_identifier(token.text))
    return tuple(parts)


def _unwrap(tokens: list[_Token]) -> list[_Token]:
    while tokens and tokens[0].text == "(" and _matching(tokens, 0) == len(tokens) - 1:
        tokens = tokens[1:-1]
    while tokens and tokens[-1].text == ";":
        tokens = tokens[:-1]
    return tokens


def _parse_query(
    tokens: list[_Token],
    ctes: dict[str, "_Query"],
    budget: int,
) -> _Query | None:
    tokens = _unwrap(tokens)
    if not tokens or budget <= 0:
        return None
    depth = tokens[0].depth
    scope = dict(ctes)
    index = 0
    if tokens[0].upper == "WITH":
        index = 1
        if index < len(tokens) and tokens[index].upper == "RECURSIVE":
            index += 1
        while index < len(tokens) and tokens[index].kind in ("word", "quoted"):
            name = normalize_identifier(tokens[index].text)
            index += 1
            columns: tuple[str, ...] = ()
            if index < len(tokens) and tokens[index].text == "(":
                columns, index = _column_list(tokens, index)
            if index < len(tokens) and tokens[index].upper == "AS":
                index += 1
            if index < len(tokens) and tokens[index].upper in ("MATERIALIZED",):
                index += 1
            if index >= len(tokens) or tokens[index].text != "(":
                break
            end = _matching(tokens, index)
            body = _parse_query(tokens[index + 1 : end], scope, budget - 1)
            if body is not None:
                if columns:
                    body = _Query(
                        [_renamed(branch, columns) for branch in body.branches],
                        body.operators,
                    )
                scope[name] = body
            index = end + 1
            if (
                index < len(tokens)
                and tokens[index].text == ","
                and (tokens[index].depth == depth)
            ):
                index += 1
                continue
            break

    branches: list[_Select] = []
    operators: list[str] = []
    start = index
    position = index
    parts: list[list[_Token]] = []
    while position < len(tokens):
        token = tokens[position]
        if token.depth == depth and token.upper in _SET_OPERATORS:
            parts.append(tokens[start:position])
            operator = token.upper
            position += 1
            if position < len(tokens) and tokens[position].upper in ("ALL", "DISTINCT"):
                operator += " " + tokens[position].upper
                position += 1
            operators.append(operator)
            start = position
            continue
        position += 1
    parts.append(tokens[start:])

    for part in parts:
        if not part:
            continue
        if part[0].text == "(":
            inner = _parse_query(part[: _matching(part, 0) + 1], scope, budget - 1)
            if inner is not None:
                branches.extend(inner.branches)
        elif part[0].upper == "SELECT":
            branches.append(_parse_select(part, scope, budget))
    return _Query(branches, operators) if branches else None


def _renamed(select: _Select, columns: tuple[str, ...]) -> _Select:
    """A CTE's or subquery's column list renames its items by position."""
    items = list(select.items)
    for position, name in enumerate(columns):
        if position < len(items) and not items[position].star:
            items[position] = _Item(items[position].tokens, alias=name)
    return _Select(items, select.sources)


def _parse_select(
    tokens: list[_Token],
    ctes: dict[str, _Query],
    budget: int,
) -> _Select:
    depth = tokens[0].depth
    index = 1
    while index < len(tokens) and tokens[index].upper in ("DISTINCT", "ALL"):
        index += 1
    if index < len(tokens) and tokens[index].upper == "TOP":
        index += 2
    end = next(
        (
            position
            for position in range(index, len(tokens))
            if tokens[position].depth == depth
            and (
                tokens[position].upper == "FROM"
                or tokens[position].upper in _QUERY_END_WORDS
            )
        ),
        len(tokens),
    )
    items = [_parse_item(part) for part in _split(tokens[index:end], depth)]
    sources: list[_Source] = []
    if end < len(tokens) and tokens[end].upper == "FROM":
        stop = next(
            (
                position
                for position in range(end + 1, len(tokens))
                if tokens[position].depth == depth
                and tokens[position].upper in _QUERY_END_WORDS
            ),
            len(tokens),
        )
        sources = _parse_sources(tokens[end + 1 : stop], depth, ctes, budget)
    return _Select([item for item in items if item is not None], sources)


def _parse_item(tokens: list[_Token]) -> _Item | None:
    if not tokens:
        return None
    depth = tokens[0].depth
    star_at = next(
        (
            position
            for position, token in enumerate(tokens[:3])
            if token.text == "*" and token.depth == depth
        ),
        None,
    )
    if star_at is not None and (
        star_at == 0 or (star_at == 2 and tokens[1].text == ".")
    ):
        qualifier = normalize_identifier(tokens[0].text) if star_at == 2 else None
        excluded: set[str] = set()
        renamed: dict[str, str] = {}
        rest = tokens[star_at + 1 :]
        position = 0
        while position < len(rest):
            word = rest[position].upper
            if word in ("EXCLUDE", "RENAME", "REPLACE", "ILIKE"):
                position += 1
                if position < len(rest) and rest[position].text == "(":
                    end = _matching(rest, position)
                    group = _split(rest[position + 1 : end], rest[position].depth + 1)
                    position = end + 1
                else:
                    group = (
                        [rest[position : position + 3]]
                        if word == "RENAME"
                        else [rest[position : position + 1]]
                    )
                    position += 3 if word == "RENAME" else 1
                for item in group:
                    if word == "EXCLUDE" and item[0].kind in ("word", "quoted"):
                        excluded.add(normalize_identifier(item[0].text))
                    elif word == "RENAME" and len(item) >= 3:
                        renamed[normalize_identifier(item[-1].text)] = (
                            normalize_identifier(item[0].text)
                        )
                continue
            position += 1
        return _Item(
            [],
            star=True,
            star_qualifier=qualifier,
            excluded=frozenset(excluded),
            renamed=renamed,
        )

    if (
        len(tokens) >= 3
        and tokens[-2].upper == "AS"
        and tokens[-2].depth == depth
        and tokens[-1].kind in ("word", "quoted")
    ):
        return _Item(tokens[:-2], alias=normalize_identifier(tokens[-1].text))
    if len(tokens) >= 2:
        last, previous = tokens[-1], tokens[-2]
        if (
            last.depth == depth
            and last.is_name()
            and previous.text not in (".", "::", ":")
            and (previous.kind != "op" or previous.text == ")")
        ):
            return _Item(tokens[:-1], alias=normalize_identifier(last.text))
    return _Item(tokens)


def _parse_sources(
    tokens: list[_Token],
    depth: int,
    ctes: dict[str, _Query],
    budget: int,
) -> list[_Source]:
    sources: list[_Source] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        word = token.upper
        if (
            token.depth != depth
            or token.text == ","
            or word in _JOIN_WORDS
            or (word == "LATERAL")
        ):
            index += 1
            continue
        if word in ("ON", "WHERE"):
            index += 1
            while index < len(tokens) and not (
                tokens[index].depth == depth
                and (tokens[index].text == "," or tokens[index].upper in _JOIN_WORDS)
            ):
                index += 1
            continue
        if word in ("USING", "MATCH_CONDITION") and index + 1 < len(tokens):
            index = (
                _matching(tokens, index + 1) + 1
                if tokens[index + 1].text == "("
                else index + 1
            )
            continue

        if token.text == "(":
            end = _matching(tokens, index)
            query = _parse_query(tokens[index + 1 : end], ctes, budget - 1)
            alias, columns, index = _alias(tokens, end + 1, depth)
            if query is not None and columns:
                query = _Query(
                    [_renamed(branch, columns) for branch in query.branches],
                    query.operators,
                )
            sources.append(
                _Source("subquery", alias=alias, query=query, columns=columns)
            )
            continue
        if token.kind == "stage":
            alias, _, index = _alias(tokens, index + 1, depth)
            sources.append(_Source("other", alias=alias))
            continue
        if token.kind in ("word", "quoted"):
            parts, after = _name_chain(tokens, index)
            if after < len(tokens) and tokens[after].text == "(":
                # TABLE(...), FLATTEN(...), GENERATOR(...): a function, not a table.
                alias, _, index = _alias(tokens, _matching(tokens, after) + 1, depth)
                sources.append(_Source("other", alias=alias))
                continue
            index = after
            while index + 1 < len(tokens) and tokens[index].upper in (
                "AT", "BEFORE", "CHANGES", "SAMPLE", "TABLESAMPLE", "END",
            ) and tokens[index + 1].text == "(":  # fmt: skip
                index = _matching(tokens, index + 1) + 1
            alias, _, index = _alias(tokens, index, depth)
            name = SqlObjectName(parts)
            if len(parts) == 1 and parts[0] in ctes:
                sources.append(
                    _Source("cte", name=name, alias=alias, query=ctes[parts[0]])
                )
            else:
                sources.append(_Source("table", name=name, alias=alias))
            continue
        index += 1
    return sources


def _alias(
    tokens: Sequence[_Token],
    index: int,
    depth: int,
) -> tuple[str | None, tuple[str, ...], int]:
    if index < len(tokens) and tokens[index].upper == "AS":
        index += 1
    alias = None
    if index < len(tokens) and tokens[index].is_name() and tokens[index].depth == depth:
        alias = normalize_identifier(tokens[index].text)
        index += 1
    columns: tuple[str, ...] = ()
    if alias is not None and index < len(tokens) and tokens[index].text == "(":
        columns, index = _column_list(tokens, index)
    return alias, columns, index


# -- resolution ---------------------------------------------------------------


@dataclass
class _Result:
    """How one expression produces a column."""

    text: str  # the expression as written
    computed: bool = False
    expression: str | None = None  # outermost computed expression met
    reference: str | None = None  # innermost reference, for pass-through
    referenced: list[str] = field(default_factory=list)
    sources: list[SqlColumnSource] = field(default_factory=list)


def _references(tokens: Sequence[_Token]) -> list[list[_Token]]:
    """Column references inside an expression, as token runs."""
    found: list[list[_Token]] = []
    skip_type = False
    date_part_at: int | None = None
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.text == "::" or (
            token.upper == "AS" and index > 0 and _inside_cast(tokens, index)
        ):
            skip_type = True
            index += 1
            continue
        if token.text == ":":
            # A JSON path: v:a.b[0] -- only `v` is a column.
            index += 1
            while index < len(tokens) and (
                tokens[index].kind in ("word", "quoted", "number")
                or tokens[index].text in (".", "[", "]")
            ):
                index += 1
            continue
        if token.kind == "positional":
            found.append([token])
            index += 1
            continue
        if token.kind not in ("word", "quoted"):
            if token.text != "(":
                skip_type = False
            index += 1
            continue
        if skip_type:
            skip_type = False
            index += 1
            if index < len(tokens) and tokens[index].text == "(":
                index = _matching(tokens, index) + 1
            continue
        start = index
        parts, index = _name_chain(tokens, index)
        following = tokens[index] if index < len(tokens) else None
        if following is not None and following.text == "(":
            # A function call; some take a date part first.
            if tokens[start].upper in _DATE_PART_FUNCTIONS:
                date_part_at = index + 1
            continue
        if following is not None and following.text in ("=>", "->"):
            continue
        if start == date_part_at:
            continue
        if (
            len(parts) == 1
            and tokens[start].kind == "word"
            and (tokens[start].upper in _KEYWORDS)
        ):
            continue
        if (
            index < len(tokens)
            and tokens[index].text == "."
            and (index + 1 < len(tokens) and tokens[index + 1].kind == "positional")
        ):
            found.append(tokens[start : index + 2])
            index += 2
            continue
        found.append(list(tokens[start:index]))
    return found


def _inside_cast(tokens: Sequence[_Token], index: int) -> bool:
    depth = tokens[index].depth
    for position in range(index - 1, -1, -1):
        token = tokens[position]
        if token.text == "(" and token.depth == depth - 1:
            return position > 0 and tokens[position - 1].upper in ("CAST", "TRY_CAST")
    return False


class _Resolver:
    def __init__(self, sql: str) -> None:
        self.sql = sql
        self.steps: list[str] = []

    def column(
        self,
        query: _Query,
        column: str | None,
        position: int | None,
        depth: int,
    ) -> list[tuple[_Result, str]] | None:
        """Per branch, the result producing the column, with its operator."""
        if depth > _MAX_DEPTH or not query.branches:
            return None
        results: list[tuple[_Result, str]] = []
        operators = ["", *query.operators]
        index = position
        if index is not None and any(
            item.star for item in query.branches[0].items[: index + 1]
        ):
            index = None
        if index is None and column is not None:
            index = next(
                (
                    _last_index(branch, column)
                    for branch in query.branches
                    if _last_index(branch, column) is not None
                ),
                None,
            )
        for number, branch in enumerate(query.branches):
            operator = operators[number] if number < len(operators) else ""
            if index is not None and index < len(branch.items):
                item = branch.items[index]
                if not item.star:
                    results.append((self.item(branch, item, index, depth), operator))
                    continue
            if column is not None:
                starred = self.star(branch, column, depth)
                if starred is not None:
                    results.append((starred, operator))
        return results or None

    def item(self, select: _Select, item: _Item, index: int, depth: int) -> _Result:
        return self.tokens(select, item.tokens, depth, before=index)

    def tokens(
        self,
        select: _Select,
        tokens: Sequence[_Token],
        depth: int,
        before: int | None = None,
    ) -> _Result:
        text = _text(self.sql, tokens)
        reference = _reference(tokens)
        if reference is not None:
            return self.follow(select, reference, text, depth, before)
        if len(tokens) in (1, 3) and tokens[-1].kind == "positional":
            # A staged file's column, $2 or t.$2, loaded as is.
            return _Result(text, reference=text, referenced=[text])
        result = _Result(text, computed=True, expression=text)
        for run in _references(tokens):
            run_text = _text(self.sql, run)
            result.referenced.append(run_text)
            if run[-1].kind == "positional":
                continue
            parts = _reference(run)
            if parts is None:
                continue
            followed = self.follow(select, parts, run_text, depth, before)
            result.sources.extend(followed.sources)
        return result

    def follow(
        self,
        select: _Select,
        parts: tuple[str, ...],
        text: str,
        depth: int,
        before: int | None = None,
    ) -> _Result:
        """Resolve a column reference in a select's scope to its definition."""
        name = parts[-1]
        qualifier = parts[:-1]
        if qualifier:
            candidates = [
                source for source in select.sources if source.matches(qualifier)
            ]
        else:
            candidates = list(select.sources)
            providers = [
                source
                for source in candidates
                if source.kind in ("cte", "subquery") and _outputs(source, name)
            ]
            if providers:
                candidates = providers[:1]
            else:
                if before is not None:
                    # Snowflake lets a later item reuse an earlier alias.
                    for position, item in enumerate(select.items[:before]):
                        if item.alias == name and not item.star:
                            return self.item(select, item, position, depth + 1)
                candidates = [source for source in candidates if source.kind == "table"]
        if not candidates:
            return _Result(text, reference=text, referenced=[text])
        if len(candidates) > 1:
            return _Result(
                text,
                reference=text,
                referenced=[text],
                sources=[
                    SqlColumnSource(source.name, name, certain=False)
                    for source in candidates
                    if source.name is not None
                ],
            )
        source = candidates[0]
        if source.kind == "table" and source.name is not None:
            return _Result(
                text,
                reference=text,
                referenced=[text],
                sources=[SqlColumnSource(source.name, name)],
            )
        if source.query is None:
            return _Result(text, reference=text, referenced=[text])
        step_at = len(self.steps)
        inner = self.column(source.query, name, None, depth + 1)
        if not inner:
            return _Result(text, reference=text, referenced=[text])
        combined = _combine(inner)
        if len(self.steps) < _MAX_STEPS:
            definition = " ".join(result.text for result, _ in inner)
            self.steps.insert(step_at, f"{name} = {definition} [in {source.label}]")
        if combined.computed:
            return _Result(
                text,
                computed=True,
                expression=combined.expression,
                referenced=combined.referenced,
                sources=combined.sources,
            )
        return _Result(
            text,
            reference=combined.reference,
            referenced=combined.referenced,
            sources=combined.sources,
        )

    def star(self, select: _Select, column: str, depth: int) -> _Result | None:
        for item in select.items:
            if not item.star or column in item.excluded:
                continue
            original = item.renamed.get(column, column)
            eligible = [
                source
                for source in select.sources
                if item.star_qualifier is None or source.matches((item.star_qualifier,))
            ]
            providers = [
                source
                for source in eligible
                if source.kind in ("cte", "subquery") and _outputs(source, original)
            ]
            text = f"{item.star_qualifier}.*" if item.star_qualifier else "*"
            if providers:
                return self.follow(_Select([], providers[:1]), (original,), text, depth)
            tables = [source for source in eligible if source.kind == "table"]
            if tables:
                return _Result(
                    text,
                    reference=original,
                    referenced=[text],
                    sources=[
                        SqlColumnSource(source.name, original, certain=len(tables) == 1)
                        for source in tables
                        if source.name is not None
                    ],
                )
        return None


def _last_index(select: _Select, column: str) -> int | None:
    index = None
    for position, item in enumerate(select.items):
        if not item.star and item.output() == column:
            index = position
    return index


def _outputs(source: _Source, column: str) -> bool:
    if source.query is None or not source.query.branches:
        return False
    first = source.query.branches[0]
    if _last_index(first, column) is not None:
        return True
    # A star over something unknown may well include the column.
    return any(item.star and column not in item.excluded for item in first.items)


def _combine(results: list[tuple[_Result, str]]) -> _Result:
    if len(results) == 1:
        return results[0][0]
    computed = any(result.computed for result, _ in results)
    shown: list[str] = []
    for result, operator in results:
        value = (result.expression if result.computed else result.reference) or ""
        if value and value not in [item for item in shown[1::2]]:
            shown.extend([operator, value] if shown else ["", value])
    text = " ".join(part for part in shown if part)
    combined = _Result(
        text,
        computed=computed,
        expression=text if computed else None,
        reference=None if computed else text,
    )
    for result, _ in results:
        combined.referenced.extend(result.referenced)
        combined.sources.extend(result.sources)
    return combined


def _transformation(
    column: str,
    resolver: _Resolver,
    result: _Result,
    *,
    stage: str | None = None,
    branch_count: int = 1,
) -> SqlColumnTransformation:
    return SqlColumnTransformation(
        column=column,
        expression=result.expression if result.computed else result.reference,
        kind="EXPRESSION" if result.computed else "PASS_THROUGH",
        steps=tuple(resolver.steps[:_MAX_STEPS]),
        referenced_columns=tuple(dict.fromkeys(result.referenced)),
        source_columns=tuple(dict.fromkeys(result.sources)),
        stage=stage,
        branch_count=branch_count,
    )


def extract_column_transformation(
    sql: str,
    column: str,
    *,
    table_columns: Sequence[str] | None = None,
) -> SqlColumnTransformation | None:
    """How the statement produces `column` (its stored name), or None.

    `table_columns` -- the target table's columns in order -- lets an INSERT
    or COPY without a column list be matched by position.
    """
    wanted = normalize_identifier(column) if column.startswith('"') else column
    try:
        return _extract(sql, wanted, table_columns)
    except RecursionError:
        return None


def _extract(
    sql: str,
    column: str,
    table_columns: Sequence[str] | None,
) -> SqlColumnTransformation | None:
    statement = _statement(sql)
    info = statement.info
    tokens = statement.tokens
    resolver = _Resolver(sql)

    if info.kind == "CREATE_TABLE_CLONE":
        clone = next(
            (
                index
                for index, token in enumerate(tokens)
                if token.upper == "CLONE" and token.depth == tokens[0].depth
            ),
            None,
        )
        parts = _name_chain(tokens, clone + 1)[0] if clone is not None else ()
        if not parts:
            return None
        return SqlColumnTransformation(
            column=column,
            expression=None,
            kind="CLONE",
            source_columns=(SqlColumnSource(SqlObjectName(parts), column),),
        )

    if info.kind == "CREATE_EXTERNAL_TABLE":
        return _external_column(sql, tokens, column)

    if info.kind in ("MERGE", "UPDATE"):
        return _assignment(statement, column, table_columns, resolver)

    if info.kind == "COPY":
        return _copy(statement, column, table_columns, resolver)

    if statement.body is None or info.kind in (
        "OTHER",
        "INSERT_VALUES",
        "MULTI_TABLE_INSERT",
        "CREATE_TABLE",
    ):
        return None
    query = _parse_query(list(tokens[statement.body :]), {}, _MAX_DEPTH)
    if query is None:
        return None
    position = _position(info, column, table_columns)
    results = resolver.column(query, column, position, 0)
    if not results:
        return None
    return _transformation(
        column, resolver, _combine(results), branch_count=len(results)
    )


def _position(
    info: SqlStatementInfo,
    column: str,
    table_columns: Sequence[str] | None,
) -> int | None:
    if info.target_columns:
        return (
            info.target_columns.index(column) if column in info.target_columns else None
        )
    if info.kind in ("INSERT", "COPY") and table_columns and column in table_columns:
        return list(table_columns).index(column)
    return None


def _external_column(
    sql: str,
    tokens: list[_Token],
    column: str,
) -> SqlColumnTransformation | None:
    opening = next(
        (index for index, token in enumerate(tokens) if token.text == "("),
        None,
    )
    if opening is None:
        return None
    end = _matching(tokens, opening)
    for item in _split(tokens[opening + 1 : end], tokens[opening].depth + 1):
        if not item or normalize_identifier(item[0].text) != column:
            continue
        for index, token in enumerate(item):
            if (
                token.upper == "AS"
                and index + 1 < len(item)
                and item[index + 1].text == "("
            ):
                close = _matching(item, index + 1)
                expression = _text(sql, item[index + 2 : close])
                return SqlColumnTransformation(
                    column=column,
                    expression=expression,
                    kind="EXPRESSION",
                    referenced_columns=tuple(
                        _text(sql, run) for run in _references(item[index + 2 : close])
                    ),
                )
    return None


def _target_source(statement: _Statement) -> tuple[_Source | None, int]:
    """The statement's own target as a source (with any alias)."""
    target = statement.info.target
    index = statement.after_target
    if target is None:
        return None, index
    alias, _, index = _alias(statement.tokens, index, statement.tokens[0].depth)
    return _Source("table", name=target, alias=alias), index


def _assignment(
    statement: _Statement,
    column: str,
    table_columns: Sequence[str] | None,
    resolver: _Resolver,
) -> SqlColumnTransformation | None:
    tokens = statement.tokens
    depth = tokens[0].depth
    target, index = _target_source(statement)
    sources = [target] if target is not None else []
    branches: list[tuple[str, list[_Token]]] = []

    if statement.info.kind == "UPDATE":
        stops = ("FROM", "WHERE")
        set_at = next(
            (i for i in range(index, len(tokens)) if tokens[i].upper == "SET"), None
        )
        if set_at is None:
            return None
        end = next(
            (
                i
                for i in range(set_at + 1, len(tokens))
                if tokens[i].depth == depth and tokens[i].upper in stops
            ),
            len(tokens),
        )
        if end < len(tokens) and tokens[end].upper == "FROM":
            stop = next(
                (
                    i
                    for i in range(end + 1, len(tokens))
                    if tokens[i].depth == depth and tokens[i].upper == "WHERE"
                ),
                len(tokens),
            )
            sources.extend(
                _parse_sources(tokens[end + 1 : stop], depth, {}, _MAX_DEPTH)
            )
        branches.extend(
            ("", value)
            for value in _set_values(tokens[set_at + 1 : end], depth, column)
        )
    else:
        using = next(
            (i for i in range(index, len(tokens)) if tokens[i].upper == "USING"), None
        )
        on = next(
            (
                i
                for i in range((using or index) + 1, len(tokens))
                if tokens[i].depth == depth and tokens[i].upper == "ON"
            ),
            len(tokens),
        )
        if using is not None:
            sources.extend(
                _parse_sources(tokens[using + 1 : on], depth, {}, _MAX_DEPTH)
            )
        whens = [
            i
            for i in range(on, len(tokens))
            if tokens[i].depth == depth and tokens[i].upper == "WHEN"
        ]
        for number, start in enumerate(whens):
            clause = tokens[
                start : whens[number + 1] if number + 1 < len(whens) else len(tokens)
            ]
            words = [token.upper for token in clause]
            label = "WHEN NOT MATCHED" if "NOT" in words[1:3] else "WHEN MATCHED"
            if "UPDATE" in words and "SET" in words:
                set_at = words.index("SET")
                branches.extend(
                    (label, value)
                    for value in _set_values(clause[set_at + 1 :], depth, column)
                )
            elif "INSERT" in words and "VALUES" in words:
                insert_at = words.index("INSERT")
                columns: tuple[str, ...] = ()
                if clause[insert_at + 1].text == "(":
                    columns, _ = _column_list(clause, insert_at + 1)
                values_at = words.index("VALUES")
                if values_at + 1 >= len(clause) or clause[values_at + 1].text != "(":
                    continue
                close = _matching(clause, values_at + 1)
                values = _split(clause[values_at + 2 : close], depth + 1)
                names = list(columns) or list(table_columns or [])
                if column in names and names.index(column) < len(values):
                    branches.append((label, values[names.index(column)]))

    if not branches:
        return None
    scope = _Select([], sources)
    results = [(resolver.tokens(scope, value, 0), label) for label, value in branches]
    distinct: list[tuple[_Result, str]] = []
    for result, label in results:
        shown = result.expression if result.computed else result.reference
        if shown not in [
            (item.expression if item.computed else item.reference)
            for item, _ in distinct
        ]:
            distinct.append((result, label))
    if len(distinct) == 1:
        combined = distinct[0][0]
    else:
        combined = _combine([(result, "") for result, _ in distinct])
        # Each branch as written: "s.amt", not what s.amt resolves to.
        text = "; ".join(f"{label}: {result.text}" for result, label in distinct)
        combined = _Result(
            text,
            computed=True,
            expression=text,
            referenced=combined.referenced,
            sources=combined.sources,
        )
    return _transformation(column, resolver, combined, branch_count=len(distinct))


def _set_values(
    tokens: Sequence[_Token],
    depth: int,
    column: str,
) -> list[list[_Token]]:
    values: list[list[_Token]] = []
    for assignment in _split(tokens, depth):
        equals = next(
            (i for i, token in enumerate(assignment) if token.text == "="), None
        )
        if equals is None:
            continue
        target = _reference(assignment[:equals])
        if target and target[-1] == column:
            values.append(assignment[equals + 1 :])
    return values


def _copy(
    statement: _Statement,
    column: str,
    table_columns: Sequence[str] | None,
    resolver: _Resolver,
) -> SqlColumnTransformation | None:
    tokens = statement.tokens
    index = statement.after_target
    if index >= len(tokens) or tokens[index].upper != "FROM":
        return None
    if index + 1 < len(tokens) and tokens[index + 1].kind == "stage":
        return SqlColumnTransformation(
            column=column,
            expression=None,
            kind="STAGE_LOAD",
            stage=tokens[index + 1].text,
        )
    if index + 1 >= len(tokens) or tokens[index + 1].text != "(":
        return None
    end = _matching(tokens, index + 1)
    inner = tokens[index + 2 : end]
    stage = next((token.text for token in inner if token.kind == "stage"), None)
    query = _parse_query(list(inner), {}, _MAX_DEPTH)
    if query is None:
        return None
    position = _position(statement.info, column, table_columns)
    results = resolver.column(query, column, position, 0)
    if not results:
        return None
    return _transformation(column, resolver, _combine(results), stage=stage)


def referenced_tables(sql: str) -> tuple[SqlObjectName, ...]:
    """Every real table the statement reads, CTE names excluded."""
    statement = _statement(sql)
    tokens = statement.tokens
    found: list[SqlObjectName] = []

    def visit_sources(sources: Sequence[_Source], budget: int) -> None:
        for source in sources:
            if source.kind == "table" and source.name is not None:
                found.append(source.name)
            elif source.query is not None and budget > 0:
                visit_query(source.query, budget - 1)

    def visit_query(query: _Query, budget: int) -> None:
        for branch in query.branches:
            visit_sources(branch.sources, budget)

    info = statement.info
    if info.kind == "CREATE_TABLE_CLONE":
        clone = next(
            (index for index, token in enumerate(tokens) if token.upper == "CLONE"),
            None,
        )
        parts = _name_chain(tokens, clone + 1)[0] if clone is not None else ()
        return (SqlObjectName(parts),) if parts else ()
    if statement.body is not None:
        query = _parse_query(list(tokens[statement.body :]), {}, _MAX_DEPTH)
        if query is not None:
            visit_query(query, _MAX_DEPTH)
            for cte in _cte_queries(tokens[statement.body :]):
                visit_query(cte, _MAX_DEPTH)
    elif info.kind in ("MERGE", "UPDATE") and tokens:
        depth = tokens[0].depth
        keyword = "USING" if info.kind == "MERGE" else "FROM"
        start = next(
            (
                index
                for index, token in enumerate(tokens)
                if token.depth == depth and token.upper == keyword
            ),
            None,
        )
        if start is not None:
            stop = next(
                (
                    index
                    for index in range(start + 1, len(tokens))
                    if tokens[index].depth == depth
                    and tokens[index].upper in ("ON", "WHERE")
                ),
                len(tokens),
            )
            visit_sources(
                _parse_sources(tokens[start + 1 : stop], depth, {}, _MAX_DEPTH),
                _MAX_DEPTH,
            )
    target = info.target.parts if info.target is not None else None
    return tuple(dict.fromkeys(name for name in found if name.parts != target))


def _cte_queries(tokens: Sequence[_Token]) -> list[_Query]:
    """CTE bodies, which a query reads even if its final select does not."""
    tokens = _unwrap(list(tokens))
    if not tokens or tokens[0].upper != "WITH":
        return []
    queries: list[_Query] = []
    for index, token in enumerate(tokens):
        if token.text == "(" and index > 0 and tokens[index - 1].upper == "AS":
            if token.depth == tokens[0].depth:
                query = _parse_query(
                    list(tokens[index + 1 : _matching(tokens, index)]), {}, _MAX_DEPTH
                )
                if query is not None:
                    queries.append(query)
    return queries


def table_column_type(ddl: str, column: str) -> str | None:
    """A plain CREATE TABLE column's declared type, e.g. NUMBER(38,0)."""
    statement = _statement(ddl)
    tokens = statement.tokens
    opening = next(
        (index for index, token in enumerate(tokens) if token.text == "("), None
    )
    if opening is None:
        return None
    wanted = normalize_identifier(column) if column.startswith('"') else column.upper()
    end = _matching(tokens, opening)
    stops = {
        "NOT", "NULL", "DEFAULT", "COLLATE", "COMMENT", "PRIMARY", "UNIQUE",
        "REFERENCES", "CONSTRAINT", "AUTOINCREMENT", "IDENTITY", "WITH",
        "MASKING", "TAG", "AS",
    }  # fmt: skip
    for item in _split(tokens[opening + 1 : end], tokens[opening].depth + 1):
        if len(item) < 2 or normalize_identifier(item[0].text) != wanted:
            continue
        type_tokens: list[_Token] = []
        for token in item[1:]:
            if token.upper in stops and token.depth == item[0].depth:
                break
            type_tokens.append(token)
        return _text(ddl, type_tokens).replace(" (", "(") or None
    return None
