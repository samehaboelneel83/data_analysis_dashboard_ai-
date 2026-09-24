"""
Layer 1 — Connectors & Ingestion
Driver contract + Postgres reference implementation.

Design rules enforced here:
  1. Metadata plane (describe/profile/sample) is cheap and cacheable.
     Data plane (execute) is expensive and runs once.
  2. Statistics come from the engine's OWN catalog first (pg_stats).
     We only scan the source when the engine has nothing.
  3. No SQL string concatenation ever leaves this module unparsed.
     Every outbound query goes through the sqlglot guard.

Deps: sqlalchemy>=2.0  psycopg[binary]  pyarrow  sqlglot  connectorx
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

import pyarrow as pa
import sqlglot
from sqlglot import exp
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine


# ---------------------------------------------------------------- contracts

Incremental = Literal["cdc", "cursor", "none"]


@dataclass(frozen=True)
class Capabilities:
    """What a driver can do. Callers branch on these, not on isinstance()."""
    dialect: str | None            # sqlglot dialect name; None = no SQL engine
    pushdown: bool                 # can we send SQL, or must we materialize?
    incremental: Incremental
    has_constraints: bool          # real declared FKs, or must we infer?
    has_statistics: bool           # engine exposes precomputed stats cheaply
    metered: bool                  # billed per byte scanned -> throttle agent
    max_connections: int = 5


@dataclass(frozen=True)
class ObjectRef:
    schema: str | None
    name: str
    kind: Literal["table", "view", "materialized_view", "file"] = "table"

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.name}" if self.schema else self.name


@dataclass(frozen=True)
class ColumnSchema:
    name: str
    position: int
    arrow_type: pa.DataType
    native_type: str
    nullable: bool
    comment: str | None = None


@dataclass(frozen=True)
class TableSchema:
    ref: ObjectRef
    columns: list[ColumnSchema]
    primary_key: list[str] = field(default_factory=list)
    foreign_keys: list[dict[str, Any]] = field(default_factory=list)
    indexes: list[dict[str, Any]] = field(default_factory=list)
    comment: str | None = None
    row_count_estimate: int | None = None


@dataclass(frozen=True)
class ColumnStats:
    """One row per column. `exact=False` means these came from engine estimates."""
    column: str
    null_ratio: float | None = None
    distinct_count: int | None = None
    top_k: list[tuple[str, float]] = field(default_factory=list)
    min_value: str | None = None
    max_value: str | None = None
    avg_width: int | None = None
    exact: bool = False


@dataclass(frozen=True)
class Limits:
    max_rows: int = 10_000
    timeout_ms: int = 30_000
    max_bytes_scanned: int | None = None


@runtime_checkable
class SourceDriver(Protocol):
    caps: Capabilities

    # --- metadata plane: cheap, cached, scheduled -------------------------
    def list_objects(self) -> list[ObjectRef]: ...
    def describe(self, ref: ObjectRef) -> TableSchema: ...
    def profile(self, ref: ObjectRef) -> list[ColumnStats]: ...
    def sample(self, ref: ObjectRef, n: int = 1000) -> pa.Table: ...
    def fingerprint(self) -> str: ...

    # --- data plane: expensive, on demand ---------------------------------
    def execute(self, sql: str, limits: Limits) -> pa.Table: ...


# ---------------------------------------------------------------- sql guard

BLOCKED = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create,
    exp.Alter, exp.Grant, exp.Merge,
)


class UnsafeQuery(Exception):
    pass


def guard(sql: str, dialect: str, max_rows: int) -> str:
    """Parse -> reject writes -> force a LIMIT -> re-render.

    Never regex, never concatenate. If it doesn't parse, it doesn't run.
    """
    try:
        parsed = sqlglot.parse(sql, dialect=dialect)
    except Exception as e:
        raise UnsafeQuery(f"unparseable sql: {e}") from e

    if len(parsed) != 1:
        raise UnsafeQuery("exactly one statement allowed")

    stmt = parsed[0]
    if stmt is None:
        raise UnsafeQuery("empty statement")

    for node in stmt.walk():
        if isinstance(node, BLOCKED):
            raise UnsafeQuery(f"{type(node).__name__} is not permitted")

    if isinstance(stmt, exp.Select):
        existing = stmt.args.get("limit")
        if existing is None:
            stmt = stmt.limit(max_rows)
        else:
            try:
                if int(existing.expression.this) > max_rows:
                    stmt = stmt.limit(max_rows)
            except (AttributeError, ValueError):
                stmt = stmt.limit(max_rows)

    return stmt.sql(dialect=dialect)


# ---------------------------------------------------------------- postgres

_PG_TO_ARROW: dict[str, pa.DataType] = {
    "smallint": pa.int16(),
    "integer": pa.int32(),
    "bigint": pa.int64(),
    "real": pa.float32(),
    "double precision": pa.float64(),
    "boolean": pa.bool_(),
    "date": pa.date32(),
    "bytea": pa.binary(),
    "uuid": pa.string(),
    "text": pa.string(),
    "json": pa.string(),
    "jsonb": pa.string(),
}


def _pg_arrow_type(native: str) -> pa.DataType:
    n = native.lower()
    if n.startswith("numeric") or n.startswith("decimal"):
        # never collapse money to float64
        return pa.decimal128(38, 9)
    if "timestamp with time zone" in n:
        return pa.timestamp("us", tz="UTC")
    if n.startswith("timestamp"):
        return pa.timestamp("us")
    if n.startswith(("character varying", "varchar", "char")):
        return pa.string()
    if n == "geometry" or n == "geography":
        return pa.binary()          # keep WKB + SRID intact, do not stringify
    return _PG_TO_ARROW.get(n, pa.string())


class PostgresDriver:
    caps = Capabilities(
        dialect="postgres",
        pushdown=True,
        incremental="cursor",
        has_constraints=True,
        has_statistics=True,
        metered=False,
    )

    SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")

    def __init__(self, dsn: str, statement_timeout_ms: int = 30_000):
        self.engine: Engine = create_engine(
            dsn,
            pool_pre_ping=True,
            connect_args={
                "options": f"-c statement_timeout={statement_timeout_ms} "
                           f"-c idle_in_transaction_session_timeout={statement_timeout_ms}",
            },
        )

    # --- metadata plane ---------------------------------------------------

    def list_objects(self) -> list[ObjectRef]:
        insp = inspect(self.engine)
        out: list[ObjectRef] = []
        for schema in insp.get_schema_names():
            if schema in self.SYSTEM_SCHEMAS:
                continue
            out += [ObjectRef(schema, t, "table") for t in insp.get_table_names(schema)]
            out += [ObjectRef(schema, v, "view") for v in insp.get_view_names(schema)]
        return out

    def describe(self, ref: ObjectRef) -> TableSchema:
        """SQLAlchemy's Inspector already normalises this across dialects.
        Swapping to MySQL later means changing the stats query, not this."""
        insp = inspect(self.engine)
        cols = [
            ColumnSchema(
                name=c["name"],
                position=i,
                arrow_type=_pg_arrow_type(str(c["type"])),
                native_type=str(c["type"]),
                nullable=bool(c.get("nullable", True)),
                comment=c.get("comment"),
            )
            for i, c in enumerate(insp.get_columns(ref.name, schema=ref.schema))
        ]
        pk = insp.get_pk_constraint(ref.name, schema=ref.schema) or {}
        tbl_comment = insp.get_table_comment(ref.name, schema=ref.schema) or {}

        return TableSchema(
            ref=ref,
            columns=cols,
            primary_key=list(pk.get("constrained_columns") or []),
            foreign_keys=insp.get_foreign_keys(ref.name, schema=ref.schema),
            indexes=insp.get_indexes(ref.name, schema=ref.schema),
            comment=tbl_comment.get("text"),
            row_count_estimate=self._row_estimate(ref),
        )

    def _row_estimate(self, ref: ObjectRef) -> int | None:
        q = text("""
            select c.reltuples::bigint
            from pg_class c
            join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = :schema and c.relname = :name
        """)
        with self.engine.connect() as conn:
            row = conn.execute(q, {"schema": ref.schema or "public",
                                   "name": ref.name}).first()
        if not row or row[0] is None or row[0] < 0:
            return None
        return int(row[0])

    def profile(self, ref: ObjectRef) -> list[ColumnStats]:
        """Read the stats Postgres already computed during ANALYZE.

        Costs a catalog lookup, not a table scan. On a multi-TB table this
        returns in milliseconds. This is the single biggest reason the
        metadata plane stays cheap.
        """
        q = text("""
            select attname,
                   null_frac,
                   n_distinct,
                   most_common_vals::text  as mcv,
                   most_common_freqs,
                   histogram_bounds::text  as hist,
                   avg_width
            from pg_stats
            where schemaname = :schema and tablename = :name
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(q, {"schema": ref.schema or "public",
                                    "name": ref.name}).mappings().all()

        n_rows = self._row_estimate(ref) or 0
        stats: list[ColumnStats] = []

        for r in rows:
            # n_distinct: positive = absolute count, negative = fraction of rows
            nd = r["n_distinct"]
            if nd is None:
                distinct = None
            elif nd < 0:
                distinct = int(abs(nd) * n_rows) if n_rows else None
            else:
                distinct = int(nd)

            top_k: list[tuple[str, float]] = []
            vals = _parse_pg_array(r["mcv"])
            freqs = list(r["most_common_freqs"] or [])
            for v, f in zip(vals, freqs):
                top_k.append((v, float(f)))

            bounds = _parse_pg_array(r["hist"])

            stats.append(ColumnStats(
                column=r["attname"],
                null_ratio=float(r["null_frac"]) if r["null_frac"] is not None else None,
                distinct_count=distinct,
                top_k=top_k[:50],
                min_value=bounds[0] if bounds else None,
                max_value=bounds[-1] if bounds else None,
                avg_width=r["avg_width"],
                exact=False,
            ))

        return stats

    def sample(self, ref: ObjectRef, n: int = 1000) -> pa.Table:
        """TABLESAMPLE reads whole pages -- fast but page-biased.
        Views don't support it, so fall back to a plain limit."""
        table = f'"{ref.schema or "public"}"."{ref.name}"'
        if ref.kind == "table":
            sql = f"select * from {table} tablesample system (1) limit {int(n)}"
        else:
            sql = f"select * from {table} limit {int(n)}"
        return self.execute(sql, Limits(max_rows=n))

    def fingerprint(self) -> str:
        """Stable hash of the full schema shape. Changes => schema drift =>
        emit an event so orphaned semantic annotations get flagged."""
        import hashlib
        q = text("""
            select c.table_schema, c.table_name, c.column_name,
                   c.data_type, c.is_nullable
            from information_schema.columns c
            where c.table_schema not in ('pg_catalog','information_schema','pg_toast')
            order by 1,2,3
        """)
        h = hashlib.sha256()
        with self.engine.connect() as conn:
            for row in conn.execute(q):
                h.update("|".join(str(x) for x in row).encode())
        return h.hexdigest()

    # --- data plane -------------------------------------------------------

    def execute(self, sql: str, limits: Limits) -> pa.Table:
        safe = guard(sql, dialect="postgres", max_rows=limits.max_rows)
        with self.engine.connect() as conn:
            conn.execute(text(f"set local statement_timeout = {int(limits.timeout_ms)}"))
            result = conn.execute(text(safe))
            cols = list(result.keys())
            rows = result.fetchall()
        data = {c: [r[i] for r in rows] for i, c in enumerate(cols)}
        return pa.table(data)


def _parse_pg_array(raw: str | None) -> list[str]:
    """pg_stats anyarray columns cast to text arrive as '{a,b,"c,d"}'."""
    if not raw or not raw.startswith("{"):
        return []
    body, out, cur, in_q, i = raw[1:-1], [], "", False, 0
    while i < len(body):
        ch = body[i]
        if ch == '"' and (i == 0 or body[i - 1] != "\\"):
            in_q = not in_q
        elif ch == "," and not in_q:
            out.append(cur)
            cur = ""
        else:
            cur += ch
        i += 1
    if cur:
        out.append(cur)
    return [v.strip().strip('"') for v in out]
