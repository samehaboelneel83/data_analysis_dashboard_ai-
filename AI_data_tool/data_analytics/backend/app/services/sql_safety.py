"""SQL safety: the three rules every query Datalytics sends to a customer's
database goes through (owner request, 2026-10-10: "I need to avoid SQL
injection").

1. **Values** are written as literals that cannot end early on ANY supported
   database (`encode_literal`). Doubling single quotes is the standard escape,
   but MySQL/MariaDB and ClickHouse also treat a backslash as an escape inside
   a string: the old encoder turned the value  \\' OR 1=1 #  into
   '\\'' OR 1=1 #'  -- on MySQL that is the string ' followed by real SQL.
   Backslashes are doubled there too, and a character no string may carry (NUL)
   or a number that is not a number (NaN, infinity) is refused.

2. **Names** (tables, columns, aliases) are checked against the database's own
   catalogue by the callers, then quoted with the dialect's quote character
   doubled inside (`quote_ident`), so even a real column called  a"b  stays
   one name.

3. **Hand-written SQL** (the SQL tab, a custom-SQL import, a saved live
   dataset) must be exactly ONE read (`ensure_read_only`): a SELECT, a WITH ...
   SELECT or a UNION of them. Writes, DDL, `SELECT ... INTO`, procedure calls
   and a second statement after a semicolon are refused before the query
   reaches the database. Read-only database accounts remain the strongest
   protection; this makes the app safe even on a connection that can write.

Values are literals rather than bound parameters on purpose: the builder's SQL
is shown to the person, saved as the dataset's query and later wrapped by
DirectQuery and re-imports as text, so it has to be complete, readable SQL.
The encoder is per dialect for exactly that reason.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache

#: Families whose string literals treat a backslash as an escape character.
#: Unknown families are treated the same way (the safe side: doubling a
#: backslash on a database that does not need it changes a value, never the
#: query's shape).
_BACKSLASH_FAMILIES = {"mysql", "mariadb", "clickhouse"}
#: Families known to follow the SQL standard: a backslash is an ordinary
#: character, only the quote is doubled.
_STANDARD_FAMILIES = {"postgresql", "postgres", "duckdb", "sqlserver", "mssql", "oracle", "sqlite"}

_SQLGLOT = {"postgresql": "postgres", "postgres": "postgres", "duckdb": "duckdb",
            "mysql": "mysql", "mariadb": "mysql", "sqlserver": "tsql", "mssql": "tsql",
            "oracle": "oracle", "sqlite": "sqlite", "clickhouse": "clickhouse"}


class UnsafeQuery(ValueError):
    """A query or value that will not be sent to the database. The message is
    written for the person who has to fix it."""


def sqlglot_dialect(family: str | None) -> str:
    return _SQLGLOT.get((family or "").lower(), "postgres")


def encode_literal(value, family: str | None) -> str:
    """`value` as an SQL literal for this database family."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return repr(int(value))
    if isinstance(value, float):
        if not math.isfinite(value):
            raise UnsafeQuery("A filter value must be a real number (not NaN or infinity)")
        return repr(value)
    text = str(value)
    if "\x00" in text:
        raise UnsafeQuery("A filter value contains a character databases cannot store (NUL)")
    fam = (family or "").lower()
    if fam not in _STANDARD_FAMILIES:
        text = text.replace("\\", "\\\\")
    return "'" + text.replace("'", "''") + "'"


def like_pattern(value, family: str | None) -> str:
    """A LIKE literal matching rows that CONTAIN `value` as typed: % and _ in
    the person's text are matched literally (they were wildcards before, so
    "50%" matched "500"), with ESCAPE spelled out so every dialect agrees."""
    text = "" if value is None else str(value)
    # '!' as the LIKE escape: unlike a backslash it means nothing to any
    # dialect's string literal, so the two escaping layers cannot interfere.
    text = text.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return f"{encode_literal('%' + text + '%', family)} ESCAPE '!'"


def quote_ident(family: str | None, name: str) -> str:
    """A table/column/alias name quoted for the dialect, the quote character
    doubled inside so the name can never end early."""
    name = str(name)
    if "\x00" in name:
        raise UnsafeQuery("A name contains a character databases cannot store (NUL)")
    fam = (family or "").lower()
    if fam in ("mysql", "mariadb", "clickhouse"):
        return "`" + name.replace("`", "``") + "`"
    if fam in ("sqlserver", "mssql"):
        return "[" + name.replace("]", "]]") + "]"
    return '"' + name.replace('"', '""') + '"'


# ── hand-written SQL: one read, nothing else ─────────────────────────────────

_WRITE_WORDS = re.compile(
    r"\b(insert|update|delete|merge|upsert|drop|create|alter|truncate|rename|grant|revoke|"
    r"exec|execute|call|copy|attach|detach|vacuum|pragma|load|unload|lock|set|use|begin|commit|"
    r"rollback|savepoint|declare|into|outfile|dumpfile)\b", re.I)
_QUOTED_AND_COMMENTS = r"\"(?:[^\"]|\"\")*\"|`[^`]*`|\[[^\]]*\]|--[^\n]*|/\*.*?\*/|#[^\n]*"
#: Strings read both ways -- a backslash escaping the next character (MySQL)
#: and a backslash as an ordinary character (the SQL standard) -- because the
#: text checks must not be fooled by whichever reading the database does NOT use.
_STRINGS_AND_COMMENTS = re.compile(r"'(?:[^'\\]|\\.|'')*'|" + _QUOTED_AND_COMMENTS, re.S)
_STD_STRINGS_AND_COMMENTS = re.compile(r"'(?:[^']|'')*'|" + _QUOTED_AND_COMMENTS, re.S)


def has_second_statement(text: str) -> bool:
    """True when a ';' outside strings and comments starts another statement."""
    return any(";" in rx.sub(" ", text) for rx in (_STRINGS_AND_COMMENTS, _STD_STRINGS_AND_COMMENTS))


def _fallback_check(text: str) -> str | None:
    """For SQL the parser cannot read (dialect corners): a conservative word
    check with strings, quoted names and comments removed."""
    if has_second_statement(text):
        return "Write exactly one statement (no ';' in the middle)."
    bare = _STRINGS_AND_COMMENTS.sub(" ", text)
    first = re.match(r"\s*\(*\s*(\w+)", bare)
    if not first or first.group(1).lower() not in ("select", "with"):
        return "Only a query that reads data (SELECT or WITH ... SELECT) can be used."
    hit = _WRITE_WORDS.search(bare)
    if hit:
        return f"Only reading is allowed: '{hit.group(1).upper()}' is not."
    return None


@lru_cache(maxsize=512)
def _read_only_problem(text: str, family: str) -> str | None:
    import sqlglot
    from sqlglot import exp

    try:
        trees = [t for t in sqlglot.parse(text, dialect=sqlglot_dialect(family))
                 if t is not None and not isinstance(t, exp.Semicolon)]
    except Exception:                                               # noqa: BLE001
        return _fallback_check(text)
    if len(trees) != 1:
        return "Write exactly one statement (no ';' followed by another one)."
    tree = trees[0]
    while isinstance(tree, (exp.Subquery, exp.Paren)) and isinstance(tree.this, exp.Expression):
        tree = tree.this
    if not isinstance(tree, (exp.Select, exp.Union)):
        return "Only a query that reads data (SELECT or WITH ... SELECT) can be used."
    banned = [exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command,
              exp.Merge, exp.TruncateTable, exp.Into, exp.Pragma, exp.Copy, exp.Grant,
              exp.Transaction, exp.Set, exp.Use]
    for node in tree.walk():
        if isinstance(node, tuple(banned)):
            return "Only reading is allowed: this query would change the database."
    # The parser can read a dialect corner as a harmless function call or name;
    # the word check runs too, on what is left once strings and comments go.
    if has_second_statement(text):
        return "Write exactly one statement (no ';' in the middle)."
    return None


def ensure_read_only(sql: str | None, family: str | None) -> str:
    """The query, trimmed, when it is exactly one read; raises UnsafeQuery
    with a plain reason otherwise."""
    text = (sql or "").strip()
    while text.endswith(";"):
        text = text[:-1].rstrip()
    if not text:
        raise UnsafeQuery("The query is empty.")
    why = _read_only_problem(text, (family or "").lower())
    if why:
        raise UnsafeQuery(why)
    return text
