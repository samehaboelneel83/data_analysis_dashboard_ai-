"""A database whose tables predate Alembic must still reach the ORM schema.

Such a database has app tables but no `alembic_version`: one first built from
postgres/init.sql (docker-compose mounted it into docker-entrypoint-initdb.d
until commit 5ffbb917, so older volumes are like this), or any database that
existed before Alembic was adopted. app.main._run_alembic then STAMPS head
without running a revision, and trusts create_all + _migrate to bring the
schema to head-equivalence in the same boot -- and on every boot after, since
the stamp is permanent. A fresh install no longer takes this path (an empty
database gets `upgrade head`), but these databases still do.

create_all only adds missing TABLES. So for every table init.sql creates, each
ORM column has to come from init.sql itself or from an ALTER ... ADD COLUMN in
_migrate. A column that only an Alembic revision adds is silently missing on
that path, and the first query touching it 500s (seen 2026-10-14: a fresh
stack's POST /api/v1/demo/seed failed on datasets.aggregate_of_dataset_id).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import app.models.models  # noqa: F401  -- registers every table on Base.metadata
from app.core.database import Base
from app.main import _migrate

INIT_SQL = Path(__file__).resolve().parents[2] / "postgres" / "init.sql"

pytestmark = pytest.mark.skipif(
    not INIT_SQL.exists(),
    reason="postgres/init.sql is not mounted here (e.g. inside the backend container)",
)

_CREATE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?\"?(\w+)\"?\s*\((.*?)\);",
    re.IGNORECASE | re.DOTALL,
)
_ADD_COL = re.compile(
    r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?\"?(\w+)\"?\s+ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?\"?(\w+)\"?",
    re.IGNORECASE,
)
_NOT_A_COLUMN = {"primary", "foreign", "unique", "constraint", "check", "exclude"}


def _init_sql_tables() -> dict[str, set[str]]:
    sql = re.sub(r"--[^\n]*", "", INIT_SQL.read_text(encoding="utf-8"))
    tables: dict[str, set[str]] = {}
    for name, body in _CREATE.findall(sql):
        cols = tables.setdefault(name.lower(), set())
        depth, start, parts = 0, 0, []
        for i, ch in enumerate(body):  # split on top-level commas only
            depth += ch == "("
            depth -= ch == ")"
            if ch == "," and depth == 0:
                parts.append(body[start:i])
                start = i + 1
        parts.append(body[start:])
        for part in parts:
            first = part.strip().split(None, 1)
            if first and first[0].strip('"').lower() not in _NOT_A_COLUMN:
                cols.add(first[0].strip('"').lower())
    # init.sql may also ALTER its own tables further down.
    for table, col in _ADD_COL.findall(sql):
        tables.setdefault(table.lower(), set()).add(col.lower())
    return tables


class _RecordingConn:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, stmt) -> None:  # noqa: ANN001
        self.statements.append(str(stmt))


async def _migrate_added_columns() -> set[tuple[str, str]]:
    conn = _RecordingConn()
    await _migrate(conn)
    return {
        (t.lower(), c.lower())
        for s in conn.statements
        for t, c in _ADD_COL.findall(s)
    }


def test_init_sql_parses_into_known_tables():
    """Guard the parser: if it finds nothing, every other check passes vacuously."""
    tables = _init_sql_tables()
    assert "datasets" in tables, "parser found no `datasets` table in init.sql"
    assert {"id", "name"} <= tables["datasets"]
    shared = set(tables) & set(Base.metadata.tables)
    assert len(shared) >= 5, f"expected init.sql to share many tables with the ORM, got {sorted(shared)}"


async def test_every_orm_column_reachable_from_init_sql_path():
    tables = _init_sql_tables()
    added = await _migrate_added_columns()

    missing = []
    for name, table in sorted(Base.metadata.tables.items()):
        if name not in tables:
            continue  # create_all builds a table init.sql never made, in full
        for col in table.columns:
            c = col.name.lower()
            if c not in tables[name] and (name, c) not in added:
                missing.append(f"{name}.{col.name}")

    assert not missing, (
        "These ORM columns are missing on a database first created from "
        "postgres/init.sql (the docker-compose fresh-volume path): _run_alembic "
        "stamps head there, and neither init.sql nor app.main._migrate adds "
        "them. Add an `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` line to "
        "_migrate (or the column to init.sql) for each:\n  "
        + "\n  ".join(missing)
    )


_INDEX = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?\w+\s+ON\s+\"?(\w+)\"?\s*\(([^)]*)\)",
    re.IGNORECASE,
)


async def test_migrate_never_indexes_a_column_before_adding_it():
    """`_migrate` runs its statements in order on a pre-Alembic database. An
    index on a column that a LATER statement adds fails ("column does not
    exist") and aborts startup: the backend exited on an init.sql-built
    database because `ix_reports_org_published` came before the ALTER that
    adds `reports.published` (2026-10-15). A fresh install never noticed --
    Alembic had already made the column."""
    conn = _RecordingConn()
    await _migrate(conn)
    added_at = {}
    for i, stmt in enumerate(conn.statements):
        for table, col in _ADD_COL.findall(stmt):
            added_at.setdefault((table.lower(), col.lower()), i)

    wrong = []
    for i, stmt in enumerate(conn.statements):
        for table, cols in _INDEX.findall(stmt):
            for col in cols.split(","):
                name = col.strip().split()[0].strip('"').lower() if col.strip() else ""
                j = added_at.get((table.lower(), name))
                if j is not None and j > i:
                    wrong.append(f"{stmt!r} runs before {conn.statements[j]!r}")
    assert not wrong, "Index created before its column exists:\n  " + "\n  ".join(wrong)

