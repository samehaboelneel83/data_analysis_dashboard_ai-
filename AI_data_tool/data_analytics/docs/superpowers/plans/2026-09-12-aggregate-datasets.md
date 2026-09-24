# Aggregate Datasets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an author create a scheduled, governed aggregate dataset from a DirectQuery dataset, so dashboards read thousands of pre-summed rows instead of scanning millions.

**Architecture:** An aggregate is an ordinary import-mode `Dataset` whose `source_query` is a compiled `GROUP BY` over the source's base query and whose `aggregate_of_dataset_id` points at the DirectQuery source. The existing scheduler refreshes it like any import dataset. Row-level and column security are never copied: the two resolvers in `core/rls.py` follow `aggregate_of_dataset_id` and apply the *source's* rules at read time, which works because creation refuses any grain that does not contain every RLS column.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, pandas; React 18 + TypeScript + Vitest. Backend tests run with `./.venv/Scripts/python.exe -m pytest` from `backend/`; frontend with `npx vitest run` from `frontend/`.

**Spec:** `docs/superpowers/specs/2026-09-12-aggregate-datasets-design.md`

## Global Constraints

- Backend `.py` files are **CRLF**; many frontend `.tsx` are too. Any scripted multi-line edit must detect the newline (`nl = "\r\n" if "\r\n" in s else "\n"`) and assert the anchor exists before writing.
- A service module must never import FastAPI (`tests/test_layer_conformance.py`). Status codes belong in `core/` or `routers/`.
- Every widget-path error carries a code (`core/widget_errors.py`); this feature's own errors are ordinary router `HTTPException`s on non-widget endpoints and need no code.
- Only `sum`, `count`, `min`, `max` are permitted aggregations. `row_count` is a reserved output name and is always present.
- Column names, never values or SQL text, may be stored about a customer's data.
- `ARCHITECTURE.md` and `ARCHITECTURE.html` pin counts of backend test modules, Alembic revisions and frontend tests; `tests/test_architecture_doc.py` fails if a new test file or revision is added without bumping both files (Task 7).
- The full backend suite takes ~26 minutes and reads the working tree live; do not edit backend files while it runs.

---

### Task 1: Model and migration

**Files:**
- Create: `backend/alembic/versions/0029_aggregate_datasets.py`
- Modify: `backend/app/models/models.py` (class `Dataset`, next to `refresh_interval_minutes` ≈ line 47)
- Modify: `backend/app/schemas/schemas.py` (class `DatasetOut`)
- Test: `backend/tests/test_aggregate_model.py`

**Interfaces:**
- Produces: `Dataset.aggregate_of_dataset_id: int | None` (FK `datasets.id`, `ondelete="CASCADE"`), `Dataset.aggregate_spec: dict | None` shaped `{"grain": [str], "measures": [{"column": str, "agg": str, "name": str}]}`; both exposed on `DatasetOut`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_aggregate_model.py
"""An aggregate dataset remembers its source, and dies with it.

`aggregate_of_dataset_id` is how read-time security finds the source's rules
(Task 3). A dangling pointer would mean rules that cannot be found -- so the
foreign key cascades: delete the source, the aggregate goes too.
"""
import pytest
from sqlalchemy import select

from app.models.models import Dataset


@pytest.mark.asyncio
async def test_an_aggregate_points_at_its_source_and_keeps_its_spec(db_session, two_orgs):
    org = two_orgs["a"]["org"]
    src = Dataset(name="orders", org_id=org.id, mode="directquery", source_table="orders")
    db_session.add(src)
    await db_session.flush()
    spec = {"grain": ["region"], "measures": [{"column": "amount", "agg": "sum", "name": "amount_sum"}]}
    agg = Dataset(name="orders by region", org_id=org.id, mode="import",
                  aggregate_of_dataset_id=src.id, aggregate_spec=spec)
    db_session.add(agg)
    await db_session.commit()
    await db_session.refresh(agg)
    assert agg.aggregate_of_dataset_id == src.id
    assert agg.aggregate_spec == spec


@pytest.mark.asyncio
async def test_deleting_the_source_deletes_the_aggregate(db_session, two_orgs):
    org = two_orgs["a"]["org"]
    src = Dataset(name="orders", org_id=org.id, mode="directquery", source_table="orders")
    db_session.add(src)
    await db_session.flush()
    agg = Dataset(name="agg", org_id=org.id, mode="import", aggregate_of_dataset_id=src.id,
                  aggregate_spec={"grain": [], "measures": []})
    db_session.add(agg)
    await db_session.commit()
    agg_id = agg.id
    await db_session.delete(src)
    await db_session.commit()
    db_session.expire_all()
    assert (await db_session.execute(select(Dataset).where(Dataset.id == agg_id))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_the_fields_are_exposed_on_the_api(client, auth_headers, db_session, two_orgs):
    org = two_orgs["a"]["org"]
    src = Dataset(name="orders", org_id=org.id, mode="directquery", source_table="orders")
    db_session.add(src)
    await db_session.flush()
    agg = Dataset(name="agg", org_id=org.id, mode="import", aggregate_of_dataset_id=src.id,
                  aggregate_spec={"grain": ["region"], "measures": []})
    db_session.add(agg)
    await db_session.commit()
    r = await client.get(f"/api/v1/datasets/{agg.id}", headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.json()["aggregate_of_dataset_id"] == src.id
    assert r.json()["aggregate_spec"]["grain"] == ["region"]
```

- [ ] **Step 2: Run it to verify it fails**

Run (from `backend/`): `./.venv/Scripts/python.exe -m pytest tests/test_aggregate_model.py -q`
Expected: FAIL — `TypeError: 'aggregate_of_dataset_id' is an invalid keyword argument for Dataset`

- [ ] **Step 3: Add the columns to the model**

In `backend/app/models/models.py`, class `Dataset`, directly after the line `last_refreshed_at        = Column(DateTime(timezone=True), nullable=True)`:

```python
    # An aggregate dataset: a scheduled GROUP BY over a DirectQuery source
    # (services/aggregates.py). The pointer is how read-time security finds
    # the SOURCE's rules -- they are never copied -- so it cascades: an
    # aggregate must not outlive the rules that govern it. `aggregate_spec`
    # is what was asked for ({"grain": [...], "measures": [...]}), kept so the
    # SQL can be recompiled and the UI can show it.
    aggregate_of_dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"),
                                     nullable=True, index=True)
    aggregate_spec          = Column(JSON, nullable=True)
```

In `backend/app/schemas/schemas.py`, class `DatasetOut`, add two fields beside `refresh_interval_minutes` (find it with `grep -n refresh_interval_minutes app/schemas/schemas.py`):

```python
    aggregate_of_dataset_id: int | None = None
    aggregate_spec: dict | None = None
```

- [ ] **Step 4: Write the migration**

```python
# backend/alembic/versions/0029_aggregate_datasets.py
"""Aggregate datasets: a scheduled GROUP BY over a DirectQuery source.

Revision ID: 0029_aggregate_datasets
Revises: 0028_query_run_shape
"""
from alembic import op
import sqlalchemy as sa

revision = "0029_aggregate_datasets"
down_revision = "0028_query_run_shape"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column(
        "aggregate_of_dataset_id", sa.Integer(),
        sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=True))
    op.create_index("ix_datasets_aggregate_of_dataset_id", "datasets", ["aggregate_of_dataset_id"])
    op.add_column("datasets", sa.Column("aggregate_spec", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("datasets", "aggregate_spec")
    op.drop_index("ix_datasets_aggregate_of_dataset_id", table_name="datasets")
    op.drop_column("datasets", "aggregate_of_dataset_id")
```

- [ ] **Step 5: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_aggregate_model.py tests/test_layer_conformance.py -q`
Expected: PASS. (The test suite runs on SQLite via `create_all`; the cascade test relies on SQLite foreign keys being enabled in `conftest.py` — if the cascade test fails with the aggregate still present, check that `PRAGMA foreign_keys=ON` is set there, as other cascade tests in the suite rely on it.)

- [ ] **Step 6: Apply to the dev database and commit**

```bash
MSYS_NO_PATHCONV=1 docker exec datalytics_backend alembic upgrade head
git add backend/alembic/versions/0029_aggregate_datasets.py backend/app/models/models.py backend/app/schemas/schemas.py backend/tests/test_aggregate_model.py
git commit -m "Aggregate datasets: model, migration, API fields"
```

---

### Task 2: Compile and validate an aggregate

**Files:**
- Create: `backend/app/services/aggregates.py`
- Test: `backend/tests/test_aggregates_compile.py`

**Interfaces:**
- Consumes: `app.services.direct_query._base_query_sql(dataset, rls_where="") -> str`, `app.services.direct_query._quote(identifier) -> str`, `app.services.sql_expr.expression_columns(expr, known_columns) -> set[str]` (raises `ExpressionTranslationError`).
- Produces:
  - `ALLOWED_AGGS = frozenset({"sum", "count", "min", "max"})`, `ROW_COUNT = "row_count"`
  - `class AggregateSpecError(ValueError)`
  - `normalise_spec(spec: dict, known_columns: set[str]) -> dict` — validates and fills measure names; raises `AggregateSpecError`
  - `compile_aggregate_sql(dataset, spec: dict) -> str`
  - `rls_columns_outside_grain(rules: list, grain: list[str], known_columns: set[str]) -> list[tuple[int, str]]` — `(role_id, column)` pairs; an untranslatable rule is reported as `(role_id, "<untranslatable>")`
  - `derived_measure_names(spec: dict, source_column: str) -> list[str]`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_aggregates_compile.py
"""Compiling an aggregate: the SQL is pinned, and everything it refuses is named.

Nothing user-supplied reaches the SQL as text. Grain and measure columns are
validated against the source's real columns, aggregations against a fixed
allowlist, and identifiers are quoted with the same function DirectQuery
uses. `row_count` is reserved and always present so averages can be computed
as sum / row_count on the aggregate.
"""
import pytest

from app.services import aggregates
from app.services.aggregates import AggregateSpecError

COLS = {"region", "product", "order_date", "amount", "units", "tenant"}


class _DS:
    source_table = "orders"
    source_query = None


class TestNormalise:
    def test_fills_default_measure_names(self):
        spec = aggregates.normalise_spec(
            {"grain": ["region"], "measures": [{"column": "amount", "agg": "sum"}]}, COLS)
        assert spec["measures"] == [{"column": "amount", "agg": "sum", "name": "amount_sum"}]

    def test_keeps_an_explicit_name(self):
        spec = aggregates.normalise_spec(
            {"grain": ["region"], "measures": [{"column": "amount", "agg": "sum", "name": "revenue"}]}, COLS)
        assert spec["measures"][0]["name"] == "revenue"

    @pytest.mark.parametrize("bad, message", [
        ({"grain": [], "measures": [{"column": "amount", "agg": "sum"}]}, "grain"),
        ({"grain": ["nope"], "measures": [{"column": "amount", "agg": "sum"}]}, "nope"),
        ({"grain": ["region"], "measures": []}, "measure"),
        ({"grain": ["region"], "measures": [{"column": "nope", "agg": "sum"}]}, "nope"),
        ({"grain": ["region"], "measures": [{"column": "amount", "agg": "avg"}]}, "avg"),
        ({"grain": ["region"], "measures": [{"column": "amount", "agg": "sum", "name": "row_count"}]}, "row_count"),
        ({"grain": ["region"], "measures": [{"column": "amount", "agg": "sum", "name": "region"}]}, "region"),
        ({"grain": ["region", "region"], "measures": [{"column": "amount", "agg": "sum"}]}, "twice"),
        ({"grain": ["region"], "measures": [{"column": "amount", "agg": "sum", "name": "x"},
                                            {"column": "units", "agg": "sum", "name": "x"}]}, "twice"),
    ])
    def test_refuses_and_names_the_problem(self, bad, message):
        with pytest.raises(AggregateSpecError, match=message):
            aggregates.normalise_spec(bad, COLS)


class TestCompile:
    def test_the_sql_is_exactly_this(self):
        spec = aggregates.normalise_spec(
            {"grain": ["region", "order_date"],
             "measures": [{"column": "amount", "agg": "sum"}, {"column": "units", "agg": "max"},
                          {"column": "product", "agg": "count"}]}, COLS)
        sql = aggregates.compile_aggregate_sql(_DS(), spec)
        assert sql == (
            'SELECT "region", "order_date", '
            'SUM("amount") AS "amount_sum", MAX("units") AS "units_max", COUNT("product") AS "product_count", '
            'COUNT(*) AS "row_count" '
            'FROM (SELECT * FROM "orders") AS src '
            'GROUP BY "region", "order_date"')

    def test_a_source_query_is_wrapped_not_edited(self):
        class Q:
            source_table = None
            source_query = "SELECT * FROM orders WHERE deleted = false;"
        spec = aggregates.normalise_spec({"grain": ["region"], "measures": [{"column": "amount", "agg": "sum"}]}, COLS)
        sql = aggregates.compile_aggregate_sql(Q(), spec)
        assert 'FROM (SELECT * FROM orders WHERE deleted = false) AS src' in sql

    def test_identifiers_with_quotes_are_escaped(self):
        cols = COLS | {'we"ird'}
        spec = aggregates.normalise_spec({"grain": ['we"ird'], "measures": [{"column": "amount", "agg": "sum"}]}, cols)
        assert '"we""ird"' in aggregates.compile_aggregate_sql(_DS(), spec)


class _Rule:
    def __init__(self, role_id, expr):
        self.role_id, self.filter_expr = role_id, expr


class TestGrainCoversRules:
    def test_a_rule_column_missing_from_the_grain_is_named(self):
        bad = aggregates.rls_columns_outside_grain(
            [_Rule(5, "tenant == 'acme'"), _Rule(6, "region == 'EMEA' and product == 'x'")],
            grain=["region"], known_columns=COLS)
        assert bad == [(5, "tenant"), (6, "product")]

    def test_a_grain_that_covers_every_rule_passes(self):
        assert aggregates.rls_columns_outside_grain(
            [_Rule(5, "tenant == 'acme'")], grain=["tenant", "region"], known_columns=COLS) == []

    def test_an_untranslatable_rule_is_reported_not_ignored(self):
        bad = aggregates.rls_columns_outside_grain(
            [_Rule(5, "region.str.startswith('E')")], grain=["region"], known_columns=COLS)
        assert bad == [(5, "<untranslatable>")]


class TestDerivedMeasures:
    def test_measures_built_on_a_column_are_named(self):
        spec = {"grain": ["region"], "measures": [
            {"column": "amount", "agg": "sum", "name": "amount_sum"},
            {"column": "amount", "agg": "max", "name": "biggest"},
            {"column": "units", "agg": "sum", "name": "units_sum"}]}
        assert aggregates.derived_measure_names(spec, "amount") == ["amount_sum", "biggest"]
        assert aggregates.derived_measure_names(spec, "units") == ["units_sum"]
        assert aggregates.derived_measure_names(spec, "region") == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_aggregates_compile.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.aggregates'`

- [ ] **Step 3: Write the module**

```python
# backend/app/services/aggregates.py
"""Compiling an aggregate dataset from a DirectQuery source.

An aggregate is a GROUP BY run where the data lives, on a schedule, so a
dashboard reads thousands of pre-summed rows instead of scanning millions.
This module turns an author's request -- a grain and some measures -- into
that SQL, and decides what it will not compile.

Two rules that are not negotiable:

  * Nothing user-supplied reaches the SQL as text. Grain and measure columns
    are validated against the source's real columns; aggregations against
    ALLOWED_AGGS; identifiers go through the same quoting DirectQuery uses.
  * Only additive aggregations. A widget on the aggregate will aggregate
    again, and only sum / count / min / max survive that at a coarser grain.
    `row_count` is always present so an average is sum / row_count.

The governance decision -- the grain must cover every column an RLS rule
reads, so the SOURCE's rules can be applied to the aggregate at read time
without ever being copied -- is checked here (`rls_columns_outside_grain`)
and enforced by the router at creation and by the scheduler at every refresh.
"""
from __future__ import annotations

import re

from .direct_query import _base_query_sql, _quote
from .sql_expr import ExpressionTranslationError, expression_columns

ALLOWED_AGGS = frozenset({"sum", "count", "min", "max"})
ROW_COUNT = "row_count"
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_ ]{0,120}$")


class AggregateSpecError(ValueError):
    """The request cannot be compiled; the message says which part and why."""


def normalise_spec(spec: dict, known_columns: set[str]) -> dict:
    """Validate a spec and fill in measure names. Returns a new dict."""
    grain = [str(g) for g in (spec.get("grain") or [])]
    measures_in = spec.get("measures") or []
    if not grain:
        raise AggregateSpecError("an aggregate needs at least one grain column")
    if not measures_in:
        raise AggregateSpecError("an aggregate needs at least one measure")
    seen: set[str] = set()
    for g in grain:
        if g not in known_columns:
            raise AggregateSpecError(f"grain column {g!r} is not a column of the source")
        if g in seen:
            raise AggregateSpecError(f"grain column {g!r} is listed twice")
        seen.add(g)
    measures: list[dict] = []
    names: set[str] = set(grain) | {ROW_COUNT}
    for m in measures_in:
        col = str(m.get("column") or "")
        agg = str(m.get("agg") or "").lower()
        if col not in known_columns:
            raise AggregateSpecError(f"measure column {col!r} is not a column of the source")
        if agg not in ALLOWED_AGGS:
            raise AggregateSpecError(
                f"aggregation {agg!r} is not allowed; only sum, count, min and max "
                "re-aggregate correctly at a coarser grain")
        name = str(m.get("name") or f"{col}_{agg}")
        if not _NAME.match(name):
            raise AggregateSpecError(f"measure name {name!r} is not a plain identifier")
        if name == ROW_COUNT:
            raise AggregateSpecError(f"{ROW_COUNT!r} is reserved; it is always included")
        if name in names:
            raise AggregateSpecError(f"output name {name!r} is used twice")
        names.add(name)
        measures.append({"column": col, "agg": agg, "name": name})
    return {"grain": grain, "measures": measures}


def compile_aggregate_sql(dataset, spec: dict) -> str:
    """The GROUP BY, over the source's base query with NO RLS predicate: the
    aggregate holds every row's contribution, and RLS is applied when it is
    read, on grain columns that are guaranteed to be there."""
    grain_sql = ", ".join(_quote(g) for g in spec["grain"])
    measure_sql = ", ".join(
        f'{m["agg"].upper()}({_quote(m["column"])}) AS {_quote(m["name"])}' for m in spec["measures"])
    base = _base_query_sql(dataset).strip().rstrip(";")
    return (f"SELECT {grain_sql}, {measure_sql}, COUNT(*) AS {_quote(ROW_COUNT)} "
            f"FROM ({base}) AS src GROUP BY {grain_sql}")


def rls_columns_outside_grain(rules, grain: list[str], known_columns: set[str]) -> list[tuple[int, str]]:
    """(role_id, column) for every RLS rule column the grain does not carry.

    Empty means the grain can govern the aggregate exactly as the source is
    governed. An untranslatable rule cannot be checked and is reported as
    `<untranslatable>` -- fail closed, never silently pass."""
    g = set(grain)
    bad: list[tuple[int, str]] = []
    for rule in rules:
        try:
            cols = expression_columns(rule.filter_expr, known_columns)
        except ExpressionTranslationError:
            bad.append((rule.role_id, "<untranslatable>"))
            continue
        for c in sorted(cols):
            if c not in g:
                bad.append((rule.role_id, c))
    return bad


def derived_measure_names(spec: dict, source_column: str) -> list[str]:
    """The aggregate's output columns built from one source column -- what a
    column rule on the source must also deny on the aggregate."""
    return [m["name"] for m in spec.get("measures") or [] if m.get("column") == source_column]
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_aggregates_compile.py tests/test_layer_conformance.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/aggregates.py backend/tests/test_aggregates_compile.py
git commit -m "Aggregate datasets: compile a GROUP BY, refuse what cannot be governed"
```

---

### Task 3: Security resolves through the source

**Files:**
- Modify: `backend/app/core/rls.py` (`resolve_rls_expr` ≈ line 149, `resolve_denied_columns` ≈ line 231)
- Test: `backend/tests/test_aggregate_security.py`

**Interfaces:**
- Consumes: Task 1 columns; Task 2 `derived_measure_names`.
- Produces: `core.rls._aggregate_source(db, dataset_id) -> tuple[int, dict | None]` — `(source_id_or_self, aggregate_spec_or_None)`; `resolve_rls_expr` and `resolve_denied_columns` unchanged in signature, now following the link.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_aggregate_security.py
"""An aggregate is governed by its source's rules, applied at read time.

Rules are never copied (materialize refused to copy them, and was right:
copies drift, and aggregation can delete the rule's column). Instead the
two resolvers follow `aggregate_of_dataset_id` and hand back the SOURCE's
rule for the caller's role. The rule references grain columns, which exist
on the aggregate with the same names, so it applies unchanged.

The value test is the whole point: a restricted user reading the aggregate
sees only their rows and their totals. Sabotage the redirect and they see
everyone's -- that is what the test must catch.
"""
import pandas as pd
import pytest

from app.core.security import create_access_token, hash_password
from app.models.models import (ColumnSecurityRule, Dataset, DatasetColumn, Role,
                               RowSecurityRule, User)

BAR = {"widget_type": "bar",
       "config": {"dimension": "region", "measure": "amount_sum", "aggregation": "sum"},
       "calculated_columns": [], "parameters": {}}


async def _restricted(db_session, org, dataset, expr, denied=None):
    role = Role(org_id=org.id, name=f"R-{expr[:8]}", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{role.id}@example.com",
                password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=dataset.id, filter_expr=expr))
    if denied:
        db_session.add(ColumnSecurityRule(role_id=role.id, dataset_id=dataset.id, denied_columns=denied))
    await db_session.commit()
    await db_session.refresh(user)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


@pytest.fixture
async def source_and_aggregate(db_session, two_orgs, tmp_path):
    """A DirectQuery source (rules live here) and an aggregate file over
    tenant x region -- the file is what a refresh would have written."""
    org = two_orgs["a"]["org"]
    src = Dataset(name="orders", org_id=org.id, mode="directquery", source_table="orders")
    db_session.add(src)
    await db_session.flush()
    for c in ("tenant", "region", "amount"):
        db_session.add(DatasetColumn(dataset_id=src.id, name=c, dtype="categorical"))
    path = tmp_path / "agg.csv"
    pd.DataFrame([
        {"tenant": "acme", "region": "N", "amount_sum": 10.0, "row_count": 2},
        {"tenant": "acme", "region": "S", "amount_sum": 20.0, "row_count": 3},
        {"tenant": "globex", "region": "N", "amount_sum": 99.0, "row_count": 9},
    ]).to_csv(path, index=False)
    agg = Dataset(name="orders by tenant/region", org_id=org.id, mode="import", filename=str(path),
                  aggregate_of_dataset_id=src.id,
                  aggregate_spec={"grain": ["tenant", "region"],
                                  "measures": [{"column": "amount", "agg": "sum", "name": "amount_sum"}]})
    db_session.add(agg)
    await db_session.flush()
    for c in ("tenant", "region", "amount_sum", "row_count"):
        db_session.add(DatasetColumn(dataset_id=agg.id, name=c, dtype="categorical"))
    await db_session.commit()
    return org, src, agg


@pytest.mark.asyncio
async def test_a_restricted_user_sees_only_their_tenant_on_the_aggregate(
        client, db_session, two_orgs, source_and_aggregate):
    org, src, agg = source_and_aggregate
    headers = await _restricted(db_session, org, src, "tenant == 'acme'")
    r = await client.post(f"/api/v1/datasets/{agg.id}/widget-data", json=BAR, headers=headers)
    assert r.status_code == 200, r.text
    rows = {x["name"]: x["value"] for x in r.json()["rows"]}
    assert rows == {"N": 10.0, "S": 20.0}, rows        # globex's 99 never appears
    assert r.json()["total"] == 2


@pytest.mark.asyncio
async def test_an_admin_sees_everything(client, auth_headers, source_and_aggregate):
    _, _, agg = source_and_aggregate
    r = await client.post(f"/api/v1/datasets/{agg.id}/widget-data", json=BAR, headers=auth_headers["a"])
    assert r.status_code == 200
    assert {x["name"]: x["value"] for x in r.json()["rows"]} == {"N": 109.0, "S": 20.0}


@pytest.mark.asyncio
async def test_a_denied_source_column_denies_the_measures_built_on_it(
        client, db_session, source_and_aggregate):
    """A role that may not see `amount` may not see `amount_sum` either;
    `row_count` stays."""
    org, src, agg = source_and_aggregate
    headers = await _restricted(db_session, org, src, "tenant == 'acme'", denied=["amount"])
    r = await client.post(f"/api/v1/datasets/{agg.id}/widget-data", json=BAR, headers=headers)
    # The measure the widget asks for no longer exists for this role.
    assert r.status_code in (200, 403), r.text
    if r.status_code == 200:
        assert r.json()["rows"] == [] or all("amount_sum" not in x for x in r.json()["rows"])
    count_widget = dict(BAR, config={"dimension": "region", "measure": "row_count", "aggregation": "sum"})
    r2 = await client.post(f"/api/v1/datasets/{agg.id}/widget-data", json=count_widget, headers=headers)
    assert r2.status_code == 200, r2.text
    assert {x["name"]: x["value"] for x in r2.json()["rows"]} == {"N": 2, "S": 3}


@pytest.mark.asyncio
async def test_a_rule_the_grain_cannot_express_fails_closed(
        client, db_session, source_and_aggregate):
    """A rule added to the source later, on a column the aggregate lacks:
    zero rows for that role, never everyone's rows."""
    org, src, agg = source_and_aggregate
    headers = await _restricted(db_session, org, src, "product == 'widget'")
    r = await client.post(f"/api/v1/datasets/{agg.id}/widget-data", json=BAR, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["rows"] == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_aggregate_security.py -q`
Expected: `test_a_restricted_user_sees_only_their_tenant_on_the_aggregate` FAILS with `rows == {"N": 109.0, "S": 20.0}` (the restricted user sees globex's 99, because the rule is on the source and the aggregate has none). The admin test passes already.

- [ ] **Step 3: Follow the link in both resolvers**

In `backend/app/core/rls.py`, add above `resolve_rls_expr`:

```python
async def _aggregate_source(db: AsyncSession, dataset_id: int) -> tuple[int, dict | None]:
    """The dataset whose rules govern `dataset_id`, and the aggregate spec if
    there is one.

    An aggregate dataset (services/aggregates.py) carries no rules of its own:
    it points at its DirectQuery source, and the source's rules are applied to
    it at read time. Rules are never copied -- a copy would drift the moment
    the source's changed. Every other dataset governs itself.
    """
    from ..models.models import Dataset
    row = (await db.execute(
        select(Dataset.aggregate_of_dataset_id, Dataset.aggregate_spec)
        .where(Dataset.id == dataset_id))).first()
    if row is None or row[0] is None:
        return dataset_id, None
    return int(row[0]), row[1]
```

In `resolve_rls_expr`, immediately after the `if current_user.role.is_org_admin: return None` line:

```python
    dataset_id, _spec = await _aggregate_source(db, dataset_id)
```

In `resolve_denied_columns`, immediately after its `if current_user.role.is_org_admin: return []` line:

```python
    dataset_id, spec = await _aggregate_source(db, dataset_id)
```

and replace its final `return denied` with:

```python
    if spec:
        # A source column denied to this role denies, on the aggregate, the
        # column itself (if it is in the grain) and every measure built on it.
        # `row_count` is never denied: it reveals nothing about any column.
        from ..services.aggregates import derived_measure_names
        expanded = list(denied)
        for c in list(denied):
            expanded.extend(derived_measure_names(spec, c))
        denied = [c for c in dict.fromkeys(expanded) if c != "row_count"]
    return denied
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_aggregate_security.py tests/test_rls_fail_closed.py tests/test_column_security*.py -q`
Expected: PASS

- [ ] **Step 5: Prove the value test discriminates**

Temporarily change `dataset_id, _spec = await _aggregate_source(db, dataset_id)` in `resolve_rls_expr` to `_spec = None`, run `tests/test_aggregate_security.py`, confirm `test_a_restricted_user_sees_only_their_tenant_on_the_aggregate` FAILS showing the 109.0, then restore the line and confirm PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/rls.py backend/tests/test_aggregate_security.py
git commit -m "Aggregate datasets: row and column security resolve through the source"
```

---

### Task 4: Create, list, preflight

**Files:**
- Modify: `backend/app/routers/datasets.py` (add three endpoints directly above `@router.post("/{dataset_id}/rebuild", ...)`)
- Modify: `backend/app/schemas/schemas.py` (add `AggregateCreateRequest` after `MaterializeRequest` ≈ line 178)
- Test: `backend/tests/test_aggregate_endpoints.py`

**Interfaces:**
- Consumes: Task 2 (`normalise_spec`, `compile_aggregate_sql`, `rls_columns_outside_grain`, `AggregateSpecError`), `services.dataset_refresh.rewrite_dataset_file(cfg, filename, source_table, source_query) -> (df, type_map)`, `services.dataset_refresh.write_materialization(db, dataset_id, csv_path, "full", row_count, columns, None)`, `upload_store.allocate_path(org_id, name)`, `_refuse_if_ungovernable` is NOT used (the point is to govern), but the export policy copy it returns is reproduced: read `_dataset_export_policy`-style inheritance by copying `column_meta["__exports_disabled__"]` if present on the source.
- Produces:
  - `POST /api/v1/datasets/{id}/aggregates` body `{"name": str, "grain": [str], "measures": [{"column","agg","name"?}], "refresh_interval_minutes": int | null}` → `DatasetOut` (201)
  - `GET /api/v1/datasets/{id}/aggregates` → `[{"dataset": DatasetOut, "last_error": str | null, "attempts": int}]`
  - `GET /api/v1/datasets/{id}/aggregate-preflight` → `{"rls_columns": [str], "grain_candidates": [str], "measure_candidates": [str]}`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_aggregate_endpoints.py
"""Creating an aggregate: refuse what cannot be governed, run the first
refresh, and tell the UI what the grain must contain.
"""
import pandas as pd
import pytest

from app.models.models import DataSource, Dataset, DatasetColumn, Role, RowSecurityRule
from app.services import dataset_refresh


@pytest.fixture
async def source(db_session, two_orgs):
    org = two_orgs["a"]["org"]
    ds_src = DataSource(name="Warehouse", type="postgresql", org_id=org.id,
                        config={"host": "h", "port": 5432, "database": "d",
                                "username": "u", "password": "p"})
    db_session.add(ds_src)
    await db_session.flush()
    src = Dataset(name="orders", org_id=org.id, mode="directquery", source_table="orders",
                  data_source_id=ds_src.id)
    db_session.add(src)
    await db_session.flush()
    for c, t in (("tenant", "categorical"), ("region", "categorical"),
                 ("amount", "numeric"), ("units", "numeric")):
        db_session.add(DatasetColumn(dataset_id=src.id, name=c, dtype=t))
    role = Role(org_id=org.id, name="Tenant", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=src.id, filter_expr="tenant == 'acme'"))
    await db_session.commit()
    return src


@pytest.fixture
def fake_refresh(monkeypatch):
    """The customer's database is not reachable from a unit test. The refresh
    writes what a real one would: a CSV plus its parquet sidecar."""
    calls = []

    def _rewrite(cfg, filename, source_table, source_query):
        calls.append(source_query)
        df = pd.DataFrame([{"tenant": "acme", "region": "N", "amount_sum": 10.0, "row_count": 2}])
        df.to_csv(filename, index=False)
        from app.services.frame_cache import write_parquet_sidecar
        write_parquet_sidecar(filename)
        from app.services.ingest import detect_types
        return df, detect_types(df)

    monkeypatch.setattr(dataset_refresh, "rewrite_dataset_file", _rewrite)
    return calls


BODY = {"name": "orders by tenant/region", "grain": ["tenant", "region"],
        "measures": [{"column": "amount", "agg": "sum"}], "refresh_interval_minutes": 60}


@pytest.mark.asyncio
async def test_creates_runs_the_first_refresh_and_returns_the_dataset(
        client, auth_headers, source, fake_refresh):
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["aggregate_of_dataset_id"] == source.id
    assert body["mode"] == "import"
    assert body["refresh_interval_minutes"] == 60
    assert body["row_count"] == 1
    assert fake_refresh and 'GROUP BY "tenant", "region"' in fake_refresh[0]
    assert {c["name"] for c in body["columns"]} == {"tenant", "region", "amount_sum", "row_count"}


@pytest.mark.asyncio
async def test_refuses_a_grain_that_does_not_cover_an_rls_column(client, auth_headers, source, fake_refresh):
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates",
                          json=dict(BODY, grain=["region"]), headers=auth_headers["a"])
    assert r.status_code == 400, r.text
    assert "tenant" in r.json()["detail"] and "Tenant" in r.json()["detail"]
    assert fake_refresh == []                      # nothing ran


@pytest.mark.asyncio
async def test_refuses_a_bad_spec_with_its_reason(client, auth_headers, source, fake_refresh):
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates",
                          json=dict(BODY, measures=[{"column": "amount", "agg": "avg"}]),
                          headers=auth_headers["a"])
    assert r.status_code == 400
    assert "avg" in r.json()["detail"]


@pytest.mark.asyncio
async def test_only_a_directquery_dataset_can_be_aggregated(client, auth_headers, db_session, two_orgs, tmp_path):
    p = tmp_path / "i.csv"
    pd.DataFrame({"a": [1]}).to_csv(p, index=False)
    imp = Dataset(name="imported", org_id=two_orgs["a"]["org"].id, mode="import", filename=str(p))
    db_session.add(imp)
    await db_session.commit()
    r = await client.post(f"/api/v1/datasets/{imp.id}/aggregates", json=BODY, headers=auth_headers["a"])
    assert r.status_code == 400
    assert "DirectQuery" in r.json()["detail"]


@pytest.mark.asyncio
async def test_lists_the_aggregates_of_a_source(client, auth_headers, source, fake_refresh):
    await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    r = await client.get(f"/api/v1/datasets/{source.id}/aggregates", headers=auth_headers["a"])
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["dataset"]["name"] == BODY["name"]
    assert r.json()[0]["last_error"] is None


@pytest.mark.asyncio
async def test_preflight_names_the_columns_the_grain_must_contain(client, auth_headers, source):
    r = await client.get(f"/api/v1/datasets/{source.id}/aggregate-preflight", headers=auth_headers["a"])
    assert r.status_code == 200
    assert r.json()["rls_columns"] == ["tenant"]
    assert set(r.json()["measure_candidates"]) == {"amount", "units"}
    assert "tenant" in r.json()["grain_candidates"]


@pytest.mark.asyncio
async def test_another_org_cannot_see_or_create(client, auth_headers, source):
    assert (await client.get(f"/api/v1/datasets/{source.id}/aggregates", headers=auth_headers["b"])).status_code == 404
    assert (await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["b"])).status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_aggregate_endpoints.py -q`
Expected: FAIL — 404s / 405s on the three routes.

- [ ] **Step 3: The request schema**

In `backend/app/schemas/schemas.py`, after class `MaterializeRequest`:

```python
class AggregateMeasure(BaseModel):
    column: str
    agg: str
    name: str | None = None


class AggregateCreateRequest(BaseModel):
    """Create a scheduled aggregate of a DirectQuery dataset. `grain` must
    contain every column any row-level security rule on the source reads;
    the endpoint refuses otherwise and names the role and column."""
    name: str
    grain: list[str]
    measures: list[AggregateMeasure]
    refresh_interval_minutes: int | None = None
```

- [ ] **Step 4: The endpoints**

In `backend/app/routers/datasets.py`, add `AggregateCreateRequest` to the schemas import, then insert directly above `@router.post("/{dataset_id}/rebuild", response_model=DatasetOut)`:

```python
async def _source_rules(db: AsyncSession, dataset_id: int):
    """Every row-level rule on a dataset, with the role's name for messages."""
    from ..models.models import Role, RowSecurityRule
    rows = (await db.execute(
        select(RowSecurityRule, Role.name)
        .join(Role, Role.id == RowSecurityRule.role_id)
        .where(RowSecurityRule.dataset_id == dataset_id))).all()
    return [(rule, role_name) for rule, role_name in rows]


def _uncovered_message(bad: list[tuple[int, str]], rules) -> str:
    names = {rule.role_id: role_name for rule, role_name in rules}
    role_id, col = bad[0]
    who = names.get(role_id, f"role {role_id}")
    if col == "<untranslatable>":
        return (f"The row-level security rule for role '{who}' cannot be checked "
                "against a grain; fix or remove that rule first.")
    return (f"The grain must include '{col}': the row-level security rule for "
            f"role '{who}' reads it, and an aggregate without it could not be "
            "governed the way the source is.")


@router.get("/{dataset_id}/aggregate-preflight")
async def aggregate_preflight(
    dataset_id: int,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """What the Aggregates tab needs before an author chooses anything: the
    columns every RLS rule reads (the grain must include them), and which
    columns can be grain or measure."""
    from ..services.aggregates import rls_columns_outside_grain
    ds = (await db.execute(select(Dataset).options(selectinload(Dataset.columns))
                           .where(Dataset.id == dataset_id))).scalar_one_or_none()
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_capability(db, current_user, dataset_id, "data")
    known = {c.name for c in ds.columns}
    rules = await _source_rules(db, dataset_id)
    # Every rule column, found by asking which are outside an EMPTY grain.
    rls_cols = sorted({c for _, c in rls_columns_outside_grain([r for r, _ in rules], [], known)
                       if c != "<untranslatable>"})
    numeric = [c.name for c in ds.columns if c.dtype in ("numeric", "number", "float", "integer")]
    return {"rls_columns": rls_cols,
            "grain_candidates": sorted(known),
            "measure_candidates": sorted(numeric)}


@router.post("/{dataset_id}/aggregates", response_model=DatasetOut, status_code=201)
async def create_aggregate(
    dataset_id: int, req: AggregateCreateRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """A scheduled GROUP BY over a DirectQuery dataset, saved as a new dataset.

    Governed, not copied: the new dataset carries no rules; the resolvers in
    core/rls.py apply the SOURCE's rules to it at read time, which is only
    sound if the grain contains every column those rules read -- hence the
    refusal below, and the same check on every refresh (refresh_scheduler).
    The first refresh runs here, synchronously, so the response carries a
    real row count -- or the source's real error if it rejects the SQL.
    """
    from ..services.aggregates import (AggregateSpecError, compile_aggregate_sql,
                                       normalise_spec, rls_columns_outside_grain)
    from ..services.dataset_refresh import rewrite_dataset_file, write_materialization

    ds = (await db.execute(select(Dataset).options(selectinload(Dataset.columns))
                           .where(Dataset.id == dataset_id))).scalar_one_or_none()
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_capability(db, current_user, dataset_id, "data")
    if ds.mode != "directquery" or not ds.data_source_id:
        raise HTTPException(400, "Only a DirectQuery dataset can be aggregated; an import "
                                 "dataset is already a file")
    name = (req.name or "").strip()[:255]
    if not name:
        raise HTTPException(400, "name is required")
    known = {c.name for c in ds.columns}
    try:
        spec = normalise_spec({"grain": req.grain,
                               "measures": [m.model_dump() for m in req.measures]}, known)
    except AggregateSpecError as e:
        raise HTTPException(400, str(e))
    rules = await _source_rules(db, dataset_id)
    bad = rls_columns_outside_grain([r for r, _ in rules], spec["grain"], known)
    if bad:
        raise HTTPException(400, _uncovered_message(bad, rules))

    source = await db.get(DataSource, ds.data_source_id)
    check_org(source, current_user, "Data source not found")
    cfg = dict(source.config or {})
    cfg["type"] = source.type
    sql = compile_aggregate_sql(ds, spec)
    path = upload_store.allocate_path(current_user.org_id, "aggregate.csv")
    try:
        df, type_map = await asyncio.to_thread(rewrite_dataset_file, cfg, str(path), None, sql)
    except Exception as e:  # noqa: BLE001 -- the source's own complaint is the useful message
        raise HTTPException(400, f"The source rejected the aggregate query: {type(e).__name__}")

    inherited = {}
    if (ds.column_meta or {}).get("__exports_disabled__"):
        inherited["__exports_disabled__"] = ds.column_meta["__exports_disabled__"]
    new = Dataset(
        name=name, filename=str(path), org_id=current_user.org_id, mode="import",
        data_source_id=ds.data_source_id, source_query=sql,
        aggregate_of_dataset_id=ds.id, aggregate_spec=spec,
        refresh_interval_minutes=req.refresh_interval_minutes,
        row_count=len(df), col_count=len(df.columns), file_size=path.stat().st_size,
        last_refreshed_at=datetime.utcnow(), column_meta=inherited,
    )
    db.add(new)
    await db.flush()
    for col_name, dtype in type_map.items():
        db.add(DatasetColumn(dataset_id=new.id, name=col_name, dtype=dtype,
                             missing_pct=round(df[col_name].isnull().mean() * 100, 2), stats={}))
    await write_materialization(db, new.id, str(path), "full", len(df), list(df.columns), None)
    await audit(db, current_user, "dataset.aggregate", "dataset", new.id,
                f"from {dataset_id}, grain {spec['grain']}, {len(df)} rows")
    await db.commit()
    return (await db.execute(select(Dataset).options(selectinload(Dataset.columns))
                             .where(Dataset.id == new.id))).scalar_one()


@router.get("/{dataset_id}/aggregates")
async def list_aggregates(
    dataset_id: int,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """The aggregates of a source, each with the scheduler's last failure for
    it (a ScheduleFailure row), so a grain a later rule outgrew is visible."""
    from ..models.models import ScheduleFailure
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_read(db, current_user, dataset_id)
    aggs = (await db.execute(select(Dataset).options(selectinload(Dataset.columns))
                             .where(Dataset.aggregate_of_dataset_id == dataset_id)
                             .order_by(Dataset.id))).scalars().all()
    out = []
    for a in aggs:
        failure = (await db.execute(select(ScheduleFailure).where(
            ScheduleFailure.kind == "dataset", ScheduleFailure.item_id == a.id))).scalar_one_or_none()
        out.append({"dataset": DatasetOut.model_validate(a, from_attributes=True),
                    "last_error": failure.last_error if failure else None,
                    "attempts": failure.attempts if failure else 0})
    return out
```

Check the imports at the top of the router: `asyncio`, `datetime`, `DataSource`, `DatasetColumn`, `upload_store`, `audit`, `require_dataset_read` — each is already imported for `materialize_dataset`; `grep -n "^import asyncio\|^from datetime\|upload_store\|^from ..services.audit" app/routers/datasets.py` confirms which, and add any that is missing.

- [ ] **Step 5: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_aggregate_endpoints.py tests/test_aggregate_security.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/datasets.py backend/app/schemas/schemas.py backend/tests/test_aggregate_endpoints.py
git commit -m "Aggregate datasets: create with a governed grain, list, preflight"
```

---

### Task 5: Every refresh re-checks the grain

**Files:**
- Modify: `backend/app/services/refresh_scheduler.py` (`refresh_one` ≈ line 598)
- Test: `backend/tests/test_aggregate_refresh.py`

**Interfaces:**
- Consumes: `refresh_one(session, ds) -> bool`, `record_failure(session, kind, item_id, error, now=None) -> int`, `clear_failure(session, kind, item_id)`, Task 2 `rls_columns_outside_grain`, Task 4 `_uncovered_message` (duplicate its two sentences here rather than import from a router — a service must not import a router).
- Produces: an aggregate whose source gained a rule outside its grain is not refreshed; a `ScheduleFailure(kind="dataset", item_id=<aggregate id>)` row carries a message naming role and column; a later refresh whose grain covers again clears it.

- [ ] **Step 1: Find the `kind` string the scheduler uses for datasets**

Run: `grep -n "run_items(" app/services/refresh_scheduler.py`
The call that passes `Dataset` also passes `kind=` — use that exact literal (expected `"dataset"`) in Step 3 and in the test below; if it differs, change both.

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_aggregate_refresh.py
"""A refresh re-checks the grain against the source's rules.

Rules can be added after the aggregate was built. One that reads a column the
grain lacks would be applied to an aggregate that cannot honour it -- reads
for that role already fail closed (test_aggregate_security.py); this makes
the refresh say WHY, the way every scheduler failure is said, instead of
silently rewriting the file every hour.
"""
import pandas as pd
import pytest
from sqlalchemy import select

from app.models.models import (DataSource, Dataset, DatasetColumn, Role, RowSecurityRule,
                               ScheduleFailure)
from app.services import refresh_scheduler


@pytest.fixture
async def pair(db_session, two_orgs, tmp_path):
    org = two_orgs["a"]["org"]
    ds_src = DataSource(name="W", type="postgresql", org_id=org.id,
                        config={"host": "h", "port": 5432, "database": "d", "username": "u", "password": "p"})
    db_session.add(ds_src)
    await db_session.flush()
    src = Dataset(name="orders", org_id=org.id, mode="directquery", source_table="orders", data_source_id=ds_src.id)
    db_session.add(src)
    await db_session.flush()
    for c in ("tenant", "region", "product", "amount"):
        db_session.add(DatasetColumn(dataset_id=src.id, name=c, dtype="categorical"))
    p = tmp_path / "agg.csv"
    pd.DataFrame([{"tenant": "acme", "region": "N", "amount_sum": 1.0, "row_count": 1}]).to_csv(p, index=False)
    agg = Dataset(name="agg", org_id=org.id, mode="import", filename=str(p), data_source_id=ds_src.id,
                  source_query="SELECT 1", aggregate_of_dataset_id=src.id,
                  aggregate_spec={"grain": ["tenant", "region"],
                                  "measures": [{"column": "amount", "agg": "sum", "name": "amount_sum"}]},
                  refresh_interval_minutes=60)
    db_session.add(agg)
    role = Role(org_id=org.id, name="Tenant", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=src.id, filter_expr="tenant == 'acme'"))
    await db_session.commit()
    return src, agg, role


@pytest.fixture
def rewrites(monkeypatch):
    calls = []

    def _rewrite(cfg, filename, source_table, source_query):
        calls.append(source_query)
        df = pd.DataFrame([{"tenant": "acme", "region": "N", "amount_sum": 2.0, "row_count": 1}])
        df.to_csv(filename, index=False)
        from app.services.ingest import detect_types
        return df, detect_types(df)
    from app.services import dataset_refresh
    monkeypatch.setattr(dataset_refresh, "rewrite_dataset_file", _rewrite)
    monkeypatch.setattr(refresh_scheduler, "rescan_insights", _noop_async)
    return calls


async def _noop_async(*a, **kw):
    return None


@pytest.mark.asyncio
async def test_a_covered_grain_refreshes_normally(db_session, pair, rewrites):
    src, agg, role = pair
    assert await refresh_scheduler.refresh_one(db_session, agg) is True
    assert rewrites == ["SELECT 1"]


@pytest.mark.asyncio
async def test_a_rule_outside_the_grain_stops_the_refresh_and_says_why(db_session, pair, rewrites):
    src, agg, role = pair
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=src.id, filter_expr="product == 'x'"))
    await db_session.commit()
    # A role may hold at most one rule per dataset in the admin UI; two rows
    # here only make the misfit obvious. If the model enforces uniqueness,
    # UPDATE the existing rule's filter_expr to "product == 'x'" instead.
    assert await refresh_scheduler.refresh_one(db_session, agg) is True
    assert rewrites == []                                   # the file was NOT rewritten
    failure = (await db_session.execute(select(ScheduleFailure).where(
        ScheduleFailure.kind == "dataset", ScheduleFailure.item_id == agg.id))).scalar_one()
    assert "product" in failure.last_error and "Tenant" in failure.last_error


@pytest.mark.asyncio
async def test_the_failure_clears_once_the_grain_covers_again(db_session, pair, rewrites):
    src, agg, role = pair
    await refresh_scheduler.record_failure(db_session, "dataset", agg.id, "old")
    assert await refresh_scheduler.refresh_one(db_session, agg) is True
    assert (await db_session.execute(select(ScheduleFailure).where(
        ScheduleFailure.kind == "dataset", ScheduleFailure.item_id == agg.id))).scalar_one_or_none() is None
```

- [ ] **Step 3: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_aggregate_refresh.py -q`
Expected: `test_a_rule_outside_the_grain_stops_the_refresh_and_says_why` FAILS (`rewrites == ["SELECT 1"]`, no failure row). If `test_a_covered_grain_refreshes_normally` fails on the advisory lock (`_try_lock` uses a Postgres advisory lock), check how `tests/test_dataset_refresh_modes.py` calls `refresh_one` on SQLite and copy its monkeypatch of `_try_lock`/`_unlock`.

- [ ] **Step 4: Add the check to `refresh_one`**

In `backend/app/services/refresh_scheduler.py`, inside `refresh_one`, immediately after `if derived_from_of(ds) is not None: return await _rebuild_derived(session, ds)`:

```python
        if ds.aggregate_of_dataset_id is not None:
            # An aggregate is governed by its SOURCE's rules at read time,
            # which is only sound while the grain carries every column those
            # rules read. A rule added since creation can break that. Reads
            # for that role already fail closed; this refuses to keep
            # rewriting the file and says why, the way every scheduler
            # failure is said, so the Aggregates tab can show it.
            from ..models.models import Role, RowSecurityRule
            from ..services.aggregates import rls_columns_outside_grain
            src = await session.get(Dataset, ds.aggregate_of_dataset_id)
            rows = (await session.execute(
                select(RowSecurityRule, Role.name).join(Role, Role.id == RowSecurityRule.role_id)
                .where(RowSecurityRule.dataset_id == ds.aggregate_of_dataset_id))).all()
            known = {c.name for c in (await session.execute(
                select(DatasetColumn).where(DatasetColumn.dataset_id == ds.aggregate_of_dataset_id)
            )).scalars().all()}
            bad = rls_columns_outside_grain([r for r, _ in rows], (ds.aggregate_spec or {}).get("grain") or [], known)
            if bad:
                names = {r.role_id: n for r, n in rows}
                role_id, col = bad[0]
                who = names.get(role_id, f"role {role_id}")
                msg = (f"Not refreshed: the row-level security rule for role '{who}' reads "
                       f"'{col}', which this aggregate's grain does not include. Rebuild the "
                       "aggregate with that column in its grain, or change the rule.")
                await record_failure(session, "dataset", ds.id, msg)
                ds.last_refreshed_at = datetime.utcnow()
                await session.commit()
                return True
            await clear_failure(session, "dataset", ds.id)
```

`clear_failure` exists in this module (it is called in `run_items`); confirm its signature with `grep -n "async def clear_failure" app/services/refresh_scheduler.py` and match it.

- [ ] **Step 5: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_aggregate_refresh.py tests/test_refresh_schedule.py tests/test_dataset_refresh_modes.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/refresh_scheduler.py backend/tests/test_aggregate_refresh.py
git commit -m "Aggregate datasets: every refresh re-checks that the grain covers the rules"
```

---

### Task 6: The Aggregates tab

**Files:**
- Modify: `frontend/src/services/api.ts` (add types and `aggregatesApi` after `predictionModelsApi` ≈ line 589; add `aggregate_of_dataset_id?`, `aggregate_spec?`, `mode?`, `refresh_interval_minutes?` to `interface Dataset` if absent — check with `grep -n "mode" src/services/api.ts` around line 139)
- Create: `frontend/src/components/dataset/AggregatesPanel.tsx`
- Create: `frontend/src/components/dataset/AggregatesPanel.test.tsx`
- Modify: `frontend/src/pages/DatasetDetail.tsx` (`type Tab` line 32; the `urlTab` guard ≈ line 94; the tab array ≈ line 662; the label chain ≈ line 673; the mount block after `PredictionModelsPanel` ≈ line 711)

**Interfaces:**
- Consumes: Task 4 endpoints.
- Produces: `aggregatesApi.preflight(datasetId)`, `.list(datasetId)`, `.create(datasetId, body)`; `AggregatesPanel({ datasetId, mode })`.

- [ ] **Step 1: Write the failing tests**

```tsx
// frontend/src/components/dataset/AggregatesPanel.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import AggregatesPanel from './AggregatesPanel'
import { aggregatesApi } from '../../services/api'

/**
 * The Aggregates tab. The governance rule -- the grain must include every
 * column a row-level security rule reads -- is shown, not discovered: those
 * columns arrive pre-selected and locked, with the reason beside them.
 */
vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  aggregatesApi: { preflight: vi.fn(), list: vi.fn(), create: vi.fn() },
}))

const PRE = { rls_columns: ['tenant'], grain_candidates: ['amount', 'region', 'tenant', 'units'],
              measure_candidates: ['amount', 'units'] }

beforeEach(() => {
  vi.mocked(aggregatesApi.preflight).mockResolvedValue(PRE)
  vi.mocked(aggregatesApi.list).mockResolvedValue([])
})

describe('AggregatesPanel', () => {
  it('locks the RLS columns into the grain and says why', async () => {
    render(<AggregatesPanel datasetId={5} mode="directquery" />)
    const tenant = await screen.findByLabelText('tenant') as HTMLInputElement
    expect(tenant.checked).toBe(true)
    expect(tenant.disabled).toBe(true)
    expect(screen.getByText(/row-level security rule reads it/i)).toBeInTheDocument()
  })

  it('creates with the chosen grain, measures and schedule', async () => {
    vi.mocked(aggregatesApi.create).mockResolvedValue({ id: 9, name: 'by region' } as never)
    render(<AggregatesPanel datasetId={5} mode="directquery" />)
    await screen.findByLabelText('tenant')
    fireEvent.click(screen.getByLabelText('region'))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'by region' } })
    fireEvent.change(screen.getByLabelText('Measure column'), { target: { value: 'amount' } })
    fireEvent.change(screen.getByLabelText('Aggregation'), { target: { value: 'sum' } })
    fireEvent.click(screen.getByRole('button', { name: /add measure/i }))
    fireEvent.change(screen.getByLabelText('Refresh every (minutes)'), { target: { value: '60' } })
    fireEvent.click(screen.getByRole('button', { name: /create aggregate/i }))
    await waitFor(() => expect(aggregatesApi.create).toHaveBeenCalledWith(5, {
      name: 'by region', grain: ['tenant', 'region'],
      measures: [{ column: 'amount', agg: 'sum' }], refresh_interval_minutes: 60,
    }))
  })

  it('shows the backend refusal verbatim', async () => {
    vi.mocked(aggregatesApi.create).mockRejectedValue({ response: { data: {
      detail: "The grain must include 'tenant': the row-level security rule for role 'Tenant' reads it" } } })
    render(<AggregatesPanel datasetId={5} mode="directquery" />)
    await screen.findByLabelText('tenant')
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'x' } })
    fireEvent.change(screen.getByLabelText('Measure column'), { target: { value: 'amount' } })
    fireEvent.click(screen.getByRole('button', { name: /add measure/i }))
    fireEvent.click(screen.getByRole('button', { name: /create aggregate/i }))
    expect(await screen.findByText(/The grain must include 'tenant'/)).toBeInTheDocument()
  })

  it('lists existing aggregates with the scheduler’s last failure', async () => {
    vi.mocked(aggregatesApi.list).mockResolvedValue([{
      dataset: { id: 9, name: 'by region', row_count: 120, refresh_interval_minutes: 60,
        aggregate_spec: { grain: ['tenant', 'region'], measures: [{ column: 'amount', agg: 'sum', name: 'amount_sum' }] } },
      last_error: "Not refreshed: the row-level security rule for role 'Tenant' reads 'product'",
      attempts: 3,
    }] as never)
    render(<AggregatesPanel datasetId={5} mode="directquery" />)
    expect(await screen.findByText('by region')).toBeInTheDocument()
    expect(screen.getByText(/reads 'product'/)).toBeInTheDocument()
    expect(screen.getByText(/tenant × region/)).toBeInTheDocument()
  })

  it('says why an import dataset has no aggregates tab content', async () => {
    render(<AggregatesPanel datasetId={5} mode="import" />)
    expect(await screen.findByText(/DirectQuery/)).toBeInTheDocument()
    expect(aggregatesApi.preflight).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run (from `frontend/`): `npx vitest run src/components/dataset/AggregatesPanel.test.tsx`
Expected: FAIL — cannot resolve `./AggregatesPanel` / `aggregatesApi` is not exported.

- [ ] **Step 3: The API client**

In `frontend/src/services/api.ts`, after `predictionModelsApi`:

```ts
export interface AggregatePreflight {
  /** Columns every row-level security rule on the source reads: the grain must include them. */
  rls_columns: string[]
  grain_candidates: string[]
  measure_candidates: string[]
}
export interface AggregateSpec {
  grain: string[]
  measures: { column: string; agg: 'sum' | 'count' | 'min' | 'max'; name: string }[]
}
export interface AggregateListItem {
  dataset: Dataset & { aggregate_spec?: AggregateSpec | null; refresh_interval_minutes?: number | null }
  last_error: string | null
  attempts: number
}
export const aggregatesApi = {
  preflight: (datasetId: number) =>
    api.get<AggregatePreflight>(`/datasets/${datasetId}/aggregate-preflight`).then(r => r.data),
  list: (datasetId: number) =>
    api.get<AggregateListItem[]>(`/datasets/${datasetId}/aggregates`).then(r => r.data),
  create: (datasetId: number, body: { name: string; grain: string[];
    measures: { column: string; agg: string; name?: string }[]; refresh_interval_minutes: number | null }) =>
    api.post<Dataset>(`/datasets/${datasetId}/aggregates`, body).then(r => r.data),
}
```

If `interface Dataset` lacks `mode`, `aggregate_of_dataset_id` or `aggregate_spec`, add them as optional fields (`mode?: string`, `aggregate_of_dataset_id?: number | null`, `aggregate_spec?: AggregateSpec | null`).

- [ ] **Step 4: The panel**

```tsx
// frontend/src/components/dataset/AggregatesPanel.tsx
import { useCallback, useEffect, useState } from 'react'
import { aggregatesApi } from '../../services/api'
import type { AggregateListItem, AggregatePreflight } from '../../services/api'

const AGGS = ['sum', 'count', 'min', 'max'] as const

/**
 * Aggregates of a DirectQuery dataset: a GROUP BY run where the data lives,
 * on a schedule, saved as a dataset dashboards can read in milliseconds.
 *
 * The governance rule is shown, not discovered. Every column a row-level
 * security rule reads arrives pre-selected and locked in the grain, with the
 * reason beside it -- the aggregate is governed by the source's rules at
 * read time, which only works if those columns are there.
 *
 * Measures are pre-aggregated, and only sum / count / min / max are offered:
 * a widget on the aggregate will aggregate again, and only those four survive
 * that. `row_count` is always included, so an average is sum / row_count.
 */
export default function AggregatesPanel({ datasetId, mode }: { datasetId: number; mode?: string }) {
  const [pre, setPre] = useState<AggregatePreflight | null>(null)
  const [items, setItems] = useState<AggregateListItem[]>([])
  const [name, setName] = useState('')
  const [grain, setGrain] = useState<string[]>([])
  const [measures, setMeasures] = useState<{ column: string; agg: string }[]>([])
  const [mCol, setMCol] = useState('')
  const [mAgg, setMAgg] = useState<string>('sum')
  const [every, setEvery] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    const [p, l] = await Promise.all([aggregatesApi.preflight(datasetId), aggregatesApi.list(datasetId)])
    setPre(p)
    setItems(l)
    setGrain(g => Array.from(new Set([...p.rls_columns, ...g])))
  }, [datasetId])

  useEffect(() => { if (mode === 'directquery') void load() }, [load, mode])

  if (mode !== 'directquery') {
    return (
      <p style={{ padding: 12, fontSize: 12, color: 'var(--muted)' }}>
        Aggregates are built from <strong>DirectQuery</strong> datasets, which query their source on
        every render. This dataset is already a file; a dashboard on it reads that file directly.
      </p>
    )
  }
  if (!pre) return <p style={{ padding: 12, fontSize: 12, color: 'var(--muted)' }}>Loading…</p>

  const toggle = (c: string) => setGrain(g => g.includes(c) ? g.filter(x => x !== c) : [...g, c])
  const create = async () => {
    setBusy(true); setError(null)
    try {
      await aggregatesApi.create(datasetId, {
        name: name.trim(), grain, measures,
        refresh_interval_minutes: every ? Number(every) : null,
      })
      setName(''); setMeasures([]); setEvery('')
      await load()
    } catch (e) {
      setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Could not create the aggregate')
    } finally { setBusy(false) }
  }
  const label: React.CSSProperties = { display: 'block', fontSize: 10, fontWeight: 700, color: 'var(--muted)' }

  return (
    <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div>
        <h3 style={{ fontSize: 13, margin: '0 0 4px' }}>Aggregates</h3>
        <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0, maxWidth: 640 }}>
          A GROUP BY run in the source database on a schedule and saved as a dataset, so a dashboard
          reads thousands of pre-summed rows instead of scanning millions. Measures are pre-aggregated;
          <code> row_count</code> is always included, so an average is <code>sum / row_count</code>.
        </p>
      </div>

      <fieldset style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 10 }}>
        <legend style={{ fontSize: 11, fontWeight: 700 }}>Grain</legend>
        {pre.rls_columns.length > 0 && (
          <p style={{ fontSize: 11, color: 'var(--muted)', margin: '0 0 6px' }}>
            {pre.rls_columns.join(', ')} {pre.rls_columns.length === 1 ? 'is' : 'are'} locked in: a
            row-level security rule reads {pre.rls_columns.length === 1 ? 'it' : 'them'}, and the aggregate
            is governed by the source's rules at read time.
          </p>
        )}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {pre.grain_candidates.map(c => (
            <label key={c} style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
              <input type="checkbox" aria-label={c} checked={grain.includes(c)}
                disabled={pre.rls_columns.includes(c)} onChange={() => toggle(c)} />
              {c}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 10 }}>
        <legend style={{ fontSize: 11, fontWeight: 700 }}>Measures</legend>
        <div style={{ display: 'flex', gap: 6, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div>
            <label htmlFor="agg-mcol" style={label}>Measure column</label>
            <select id="agg-mcol" value={mCol} onChange={e => setMCol(e.target.value)} style={{ fontSize: 12 }}>
              <option value="">Choose…</option>
              {pre.measure_candidates.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="agg-magg" style={label}>Aggregation</label>
            <select id="agg-magg" value={mAgg} onChange={e => setMAgg(e.target.value)} style={{ fontSize: 12 }}>
              {AGGS.map(a => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <button type="button" className="btn btn-ghost btn-sm" disabled={!mCol}
            onClick={() => { setMeasures(m => [...m, { column: mCol, agg: mAgg }]); setMCol('') }}>
            Add measure
          </button>
        </div>
        <ul style={{ fontSize: 12, margin: '8px 0 0', paddingLeft: 18 }}>
          {measures.map((m, i) => (
            <li key={i}>{m.agg}({m.column}) → <code>{m.column}_{m.agg}</code>{' '}
              <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 10 }}
                onClick={() => setMeasures(ms => ms.filter((_, j) => j !== i))}>remove</button>
            </li>
          ))}
        </ul>
      </fieldset>

      <div style={{ display: 'flex', gap: 6, alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <div>
          <label htmlFor="agg-name" style={label}>Name</label>
          <input id="agg-name" value={name} onChange={e => setName(e.target.value)} style={{ fontSize: 12 }} />
        </div>
        <div>
          <label htmlFor="agg-every" style={label}>Refresh every (minutes)</label>
          <input id="agg-every" type="number" min={5} value={every} onChange={e => setEvery(e.target.value)}
            placeholder="never" style={{ fontSize: 12, width: 90 }} />
        </div>
        <button type="button" className="btn btn-sm" onClick={create}
          disabled={busy || !name.trim() || grain.length === 0 || measures.length === 0}>
          {busy ? 'Creating…' : 'Create aggregate'}
        </button>
      </div>
      {error && <p style={{ fontSize: 11, color: 'var(--danger)', margin: 0 }}>{error}</p>}

      {items.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {items.map(it => (
            <div key={it.dataset.id} style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 10 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                <strong style={{ fontSize: 12 }}>{it.dataset.name}</strong>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                  {(it.dataset.aggregate_spec?.grain ?? []).join(' × ')} ·{' '}
                  {it.dataset.row_count.toLocaleString()} rows ·{' '}
                  {it.dataset.refresh_interval_minutes ? `every ${it.dataset.refresh_interval_minutes} min` : 'not scheduled'}
                </span>
              </div>
              {it.last_error && (
                <p style={{ fontSize: 11, color: 'var(--danger)', margin: '6px 0 0' }}>{it.last_error}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Mount the tab**

In `frontend/src/pages/DatasetDetail.tsx`:
- line 3 area: `import AggregatesPanel from '../components/dataset/AggregatesPanel'`
- `type Tab = 'overview' | 'data' | 'statistics' | 'alerts' | 'models' | 'aggregates'`
- the `urlTab` guard: add `|| urlTab === 'aggregates'`
- the tab array: `(['overview', 'data', 'statistics', 'alerts', 'models', 'aggregates'] as Tab[])`
- the label chain: replace the final `: <IconLabel icon={Brain}>Models</IconLabel>}` with
  `: t === 'models' ? <IconLabel icon={Brain}>Models</IconLabel>` + newline + `: <IconLabel icon={Layers}>Aggregates</IconLabel>}` — import `Layers` from `lucide-react` beside `Brain` (check the existing import line for the icon package name).
- after the `PredictionModelsPanel` mount block:

```tsx
      {tab === 'aggregates' && ds && (
        <AggregatesPanel datasetId={ds.id} mode={ds.mode} />
      )}
```

- [ ] **Step 6: Run the tests and type-check**

Run: `npx vitest run src/components/dataset/AggregatesPanel.test.tsx src/pages/DatasetDetail.test.tsx && npx tsc --noEmit -p tsconfig.json`
Expected: PASS; `TypeScript: No errors found`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/services/api.ts frontend/src/components/dataset/AggregatesPanel.tsx frontend/src/components/dataset/AggregatesPanel.test.tsx frontend/src/pages/DatasetDetail.tsx
git commit -m "Aggregate datasets: the Aggregates tab"
```

---

### Task 7: Docs, counts, full suites, live proof

**Files:**
- Modify: `ARCHITECTURE.md` (Layer 4 or Layer 2 — add a "Aggregate datasets" subsection next to the materialize description; find it with `grep -n "materialize" ARCHITECTURE.md`), the Alembic revision count (`28 revisions` → `29 revisions`), the backend test-module count (+5 modules: `test_aggregate_model`, `test_aggregates_compile`, `test_aggregate_security`, `test_aggregate_endpoints`, `test_aggregate_refresh`), the frontend test-file count (+1) and test count (+5).
- Modify: `ARCHITECTURE.html` — the same three pins and a mirrored paragraph.
- Modify: `docs/superpowers/specs/2026-09-12-scale-plan-design.md` — mark sub-project 6 done with the live numbers.

- [ ] **Step 1: Documentation**

Add to `ARCHITECTURE.md`, directly after the materialize paragraph:

```markdown
### Aggregate datasets

A scheduled `GROUP BY` over a DirectQuery dataset, saved as an import dataset
(`services/aggregates.py`, `POST /datasets/{id}/aggregates`). The compiled SQL
runs where the data lives, through the same refresh path as every import
dataset; a dashboard on the aggregate reads thousands of rows instead of
scanning millions.

Governed, not copied. The aggregate carries no rules of its own:
`core/rls.py` follows `aggregate_of_dataset_id` and applies the **source's**
row-level and column rules at read time. That is sound only if the grain
carries every column those rules read — creation refuses otherwise, naming
the role and column, and every scheduled refresh re-checks and records a
`ScheduleFailure` if a later rule outgrew the grain (reads for that role fail
closed meanwhile). A source column denied to a role denies every measure
built on it. Only `sum`/`count`/`min`/`max`; `row_count` is always present.
Deleting the source cascades to its aggregates.
```

Then bump the three pinned counts in both files. Run `./.venv/Scripts/python.exe -m pytest tests/test_architecture_doc.py -q` from `backend/` until it passes; the failure message names the count that is off and the actual value.

- [ ] **Step 2: Full suites**

From `backend/`: `./.venv/Scripts/python.exe -m pytest tests/ -q --timeout=300` (≈26 min; do not edit backend files while it runs).
From `frontend/`: `npx vitest run` and `npx tsc --noEmit -p tsconfig.json`.
Expected: 0 failed on both; tsc clean.

- [ ] **Step 3: Live proof against the 10M-row table**

1. `MSYS_NO_PATHCONV=1 docker exec datalytics_backend python scripts/bench_directquery.py --rows 10000000 --keep` — leaves `bench_scale_orders` in the app's Postgres (~640 MB).
2. In the UI (or via the API with the demo credentials `demo-global@example.invalid` / `demo-password`): create a DirectQuery dataset on the app's own Postgres pointing at `bench_scale_orders` (Connections → the app DB as a source → table `bench_scale_orders`), then on its Aggregates tab create `order_date × region` with `sum(amount)`, `sum(units)`, refresh every 60 minutes. Note the first-refresh time from the response.
3. Build a report with a bar (`region` × `amount_sum`), a line (`order_date` monthly × `amount_sum`) and a KPI on the aggregate; time the page with `bench_dashboard.py`'s approach or the browser's network tab, cold then warm.
4. Record in the scale spec's sub-project 6 note: rows in the aggregate, first-refresh seconds, dashboard cold and warm seconds against the `< 3s` / `< 1s` targets.
5. Clean up: delete the report, the aggregate and the DirectQuery dataset in the UI; `docker exec datalytics_db psql -U datalytics -d datalytics -c "DROP TABLE IF EXISTS bench_scale_orders"`.

- [ ] **Step 4: Commit**

```bash
git add ARCHITECTURE.md ARCHITECTURE.html docs/superpowers/specs/2026-09-12-scale-plan-design.md
git commit -m "Aggregate datasets: documented, counted, proved at 10M rows"
```
