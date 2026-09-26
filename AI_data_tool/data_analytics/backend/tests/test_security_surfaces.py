"""E01: one negative suite across every surface that returns dataset content.

Each surface had its own tests, written when it shipped, each with its own
fixture. That is how a gap survives: the export tested column security, the
preview tested row security, and nothing asked every surface the same three
questions with the same data. This file does. One fixture, one private dataset,
four people:

- `other_org`: an admin of a different organization. Must get 404 everywhere.
- `outsider`: a colleague in the same org with no way to read the dataset
  (not the owner, no share, no dashboard). Must get 404 everywhere -- the
  capability rule in docs/CAPABILITY_MATRIX.md.
- `grantee`: may read the dataset through a DatasetShare, but a column rule
  denies `salary` and a row rule keeps only `region == 'North'`. Every surface
  must answer, and no answer may carry a salary value or a South row.
- `owner`: sees everything; the control that proves the sentinels are real.

Sentinels are chosen so a leak is visible in the raw response text: every
salary value contains "7310" and nothing else does; South rows carry the
department "ZetaSouthOnly" and headcounts 40001/40002.

`SURFACES` is the inventory. Adding a data endpoint without adding it here is
the gap this file exists to close; `test_every_dataset_data_route_is_in_the_inventory`
fails when a `/datasets/{dataset_id}/...` route appears that is neither listed
nor explicitly excused.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pytest
import pytest_asyncio

from app.core.security import create_access_token, hash_password
from app.models.models import (ColumnSecurityRule, ColumnStats, Dataset,
                               DatasetColumn, DatasetShare, Organization, Role,
                               RowSecurityRule, User)

SALARY_MARK = "7310"
SOUTH_MARKS = ("ZetaSouthOnly", "40001", "40002")

def _hr_csv() -> str:
    """60 North rows (three departments of 20, enough for every statistical
    endpoint's minimum) and 6 South rows. Salaries are 7310xxx -- the only
    numbers in the file containing "7310"."""
    lines = ["region,dept,band,churned,headcount,bonus,salary"]
    n = 0
    for dept, base in (("Ops", 3), ("Sales", 20), ("Support", 50)):
        for i in range(20):
            n += 1
            band = "A" if (i * 7 + base) % 3 else "B"
            lines.append(f"North,{dept},{band},{(i + base) % 2},{base + i},{(base + i) // 3 + i % 4},{7310100 + n}")
    for i in range(6):
        n += 1
        lines.append(f"South,ZetaSouthOnly,A,1,{40001 + i},9,{7310100 + n}")
    return "\n".join(lines) + "\n"


CSV = _hr_csv()


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


@pytest_asyncio.fixture
async def world(db_session, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

    org = Organization(name="Securia")
    other = Organization(name="Elsewhere")
    db_session.add_all([org, other])
    await db_session.flush()
    admin_role = Role(org_id=org.id, name="admin", is_org_admin=True)
    analyst = Role(org_id=org.id, name="analyst", is_org_admin=False)
    restricted = Role(org_id=org.id, name="restricted", is_org_admin=False)
    other_admin_role = Role(org_id=other.id, name="admin", is_org_admin=True)
    db_session.add_all([admin_role, analyst, restricted, other_admin_role])
    await db_session.flush()

    def mk(email, role, org_id):
        return User(org_id=org_id, role_id=role.id, email=email, password_hash=hash_password("pw"))

    owner = mk("owner@securia.test", analyst, org.id)
    outsider = mk("outsider@securia.test", analyst, org.id)
    grantee = mk("grantee@securia.test", restricted, org.id)
    other_admin = mk("admin@elsewhere.test", other_admin_role, other.id)
    db_session.add_all([owner, outsider, grantee, other_admin])
    await db_session.flush()

    path = tmp_path / "hr.csv"
    path.write_text(CSV, encoding="utf-8")
    ds = Dataset(name="HR", filename=str(path), org_id=org.id, mode="import",
                 row_count=66, col_count=7, created_by=owner.id,
                 # The owner's calculated column over the denied one: a column
                 # rule must hide what is DERIVED from a column too.
                 calculated_columns=[{"name": "pay", "expression": "salary * 1"}])
    peer = tmp_path / "depts.csv"
    peer.write_text("dept,floor\nOps,1\nSales,2\nSupport,3\nZetaSouthOnly,4\n", encoding="utf-8")
    ds2 = Dataset(name="Depts", filename=str(peer), org_id=org.id, mode="import",
                  row_count=4, col_count=2, created_by=owner.id)
    db_session.add_all([ds, ds2])
    await db_session.flush()
    cols = {}
    for name, dtype in (("region", "categorical"), ("dept", "categorical"), ("band", "categorical"),
                        ("churned", "numeric"), ("headcount", "numeric"), ("bonus", "numeric"),
                        ("salary", "numeric")):
        c = DatasetColumn(dataset_id=ds.id, name=name, dtype=dtype)
        db_session.add(c)
        cols[name] = c
    for name, dtype in (("dept", "categorical"), ("floor", "numeric")):
        db_session.add(DatasetColumn(dataset_id=ds2.id, name=name, dtype=dtype))
    await db_session.flush()
    # Catalog statistics, as a metadata sync would write them: the salary
    # column's are exactly what a column rule must keep from the grantee.
    db_session.add_all([
        ColumnStats(dataset_column_id=cols["salary"].id, null_ratio=0.0, distinct_count=8,
                    top_k=[{"value": "7310166", "count": 1, "ratio": 0.015}],
                    min_value="7310101", max_value="7310166", exact=True),
        ColumnStats(dataset_column_id=cols["dept"].id, null_ratio=0.0, distinct_count=4,
                    top_k=[{"value": "ZetaSouthOnly", "count": 2, "ratio": 0.25}],
                    min_value="Ops", max_value="ZetaSouthOnly", exact=True),
    ])
    db_session.add_all([
        DatasetShare(dataset_id=ds.id, user_id=grantee.id),
        DatasetShare(dataset_id=ds2.id, user_id=grantee.id),
        ColumnSecurityRule(role_id=restricted.id, dataset_id=ds.id, denied_columns=["salary"]),
        RowSecurityRule(role_id=restricted.id, dataset_id=ds.id, filter_expr="region == 'North'"),
    ])
    await db_session.commit()
    return {"ds": ds, "peer": ds2, "owner": owner, "outsider": outsider,
            "grantee": grantee, "other_admin": other_admin, "org": org,
            "restricted": restricted}


@dataclass
class Surface:
    name: str
    method: str
    path: str                      # {ds} and {peer} are filled in
    body: Any = None               # json body; callable(world) allowed
    params: dict = field(default_factory=dict)
    #: The grantee's answer is expected to be a success. False for surfaces
    #: whose rule for a restricted reader is to refuse outright.
    grantee_ok: bool = True
    #: Also a request that NAMES the denied column; it must not return values.
    denied_variant: dict | None = None


def _wd(measure="headcount", dim="dept"):
    return {"widget_type": "bar", "config": {"dimension": dim, "measure": measure, "aggregation": "sum"}}


SURFACES: list[Surface] = [
    Surface("dataset detail", "GET", "/api/v1/datasets/{ds}"),
    Surface("export csv", "GET", "/api/v1/datasets/{ds}/export", params={"format": "csv"}),
    Surface("data preview", "POST", "/api/v1/datasets/{ds}/data-preview", body={}),
    Surface("filter preview", "POST", "/api/v1/datasets/{ds}/filter-preview",
            body={"expression": "headcount > 0"},
            denied_variant={"body": {"expression": "salary > 0"}}),
    Surface("calculated column preview", "POST", "/api/v1/datasets/{ds}/calculated-columns/preview",
            body={"expression": "headcount * 2"},
            denied_variant={"body": {"expression": "salary * 1"}}),
    Surface("measure preview", "POST", "/api/v1/datasets/{ds}/measures/preview",
            body={"expression": "SUM(headcount)", "group_by": "dept"},
            denied_variant={"body": {"expression": "SUM(salary)", "group_by": "dept"}}),
    Surface("insights", "POST", "/api/v1/datasets/{ds}/insights"),
    Surface("goal seek", "POST", "/api/v1/datasets/{ds}/goal-seek",
            params={"x_column": "bonus", "y_column": "headcount", "target_y": 10},
            denied_variant={"params": {"x_column": "salary", "y_column": "headcount", "target_y": 10}}),
    Surface("explain", "POST", "/api/v1/datasets/{ds}/explain", params={"column": "headcount"},
            denied_variant={"params": {"column": "salary"}}),
    Surface("outlier details", "POST", "/api/v1/datasets/{ds}/outlier-details",
            params={"column": "headcount"},
            denied_variant={"params": {"column": "salary"}}),
    Surface("prep preview", "POST", "/api/v1/datasets/{ds}/prep-preview", body=[]),
    Surface("join check", "POST", "/api/v1/datasets/{ds}/join-check",
            body={"steps": [{"kind": "join", "dataset_id": "{peer}", "how": "left", "left_on": "dept", "right_on": "dept"}], "index": 0}),
    Surface("quality report", "POST", "/api/v1/datasets/{ds}/quality", body={}),
    Surface("aggregates list", "GET", "/api/v1/datasets/{ds}/aggregates"),
    Surface("widget data", "POST", "/api/v1/datasets/{ds}/widget-data", body=_wd(),
            denied_variant={"body": _wd(measure="salary")}),
    Surface("widget export", "POST", "/api/v1/datasets/{ds}/widget-data/export", body=_wd(),
            params={"format": "csv"}, denied_variant={"body": _wd(measure="salary"), "params": {"format": "csv"}}),
    Surface("analysis", "POST", "/api/v1/datasets/{ds}/analysis", body={}),
    Surface("segment", "POST", "/api/v1/datasets/{ds}/segment", body={},
            denied_variant={"body": {"columns": ["salary", "headcount"]}}),
    # For the restricted reader this refuses by design ("needs more rows than
    # your access allows"): the rule is on what it may return, not that it runs.
    Surface("association rules", "POST", "/api/v1/datasets/{ds}/association-rules", body={},
            grantee_ok=False),
    Surface("key influencers", "POST", "/api/v1/datasets/{ds}/key-influencers",
            body={"target": "headcount"}, denied_variant={"body": {"target": "salary"}}),
    Surface("compare groups", "POST", "/api/v1/datasets/{ds}/statistics/compare-groups",
            body={"value_col": "headcount", "group_col": "dept"},
            denied_variant={"body": {"value_col": "salary", "group_col": "dept"}}),
    Surface("correlation", "POST", "/api/v1/datasets/{ds}/statistics/correlation",
            body={"col_a": "headcount", "col_b": "bonus"},
            denied_variant={"body": {"col_a": "salary", "col_b": "bonus"}}),
    Surface("independence", "POST", "/api/v1/datasets/{ds}/statistics/independence",
            body={"col_a": "dept", "col_b": "band"}),
    Surface("regression", "POST", "/api/v1/datasets/{ds}/statistics/regression",
            body={"target": "headcount", "predictors": ["bonus"]},
            denied_variant={"body": {"target": "headcount", "predictors": ["salary"]}}),
    Surface("logistic", "POST", "/api/v1/datasets/{ds}/statistics/glm-logistic",
            body={"target": "band", "predictors": ["headcount"]},
            denied_variant={"body": {"target": "band", "predictors": ["salary"]}}),
    Surface("mixed model", "POST", "/api/v1/datasets/{ds}/statistics/mixed-model",
            body={"target": "headcount", "predictors": ["bonus"], "group_col": "dept"}),
    Surface("survival", "POST", "/api/v1/datasets/{ds}/statistics/survival",
            body={"duration_col": "headcount", "event_col": "churned", "predictors": ["bonus"]},
            denied_variant={"body": {"duration_col": "salary", "event_col": "churned", "predictors": ["bonus"]}}),
    Surface("pairwise", "POST", "/api/v1/datasets/{ds}/statistics/pairwise",
            body={"value_col": "headcount", "group_col": "dept"},
            denied_variant={"body": {"value_col": "salary", "group_col": "dept"}}),
    Surface("difference check", "POST", "/api/v1/datasets/{ds}/difference-check",
            body={"dimension": "dept", "groups": ["Ops", "Sales"]}),
    Surface("catalogued analysis", "POST", "/api/v1/datasets/{ds}/analysis/run",
            body={"name": "correlation_test", "params": {"col_a": "headcount", "col_b": "bonus"}},
            denied_variant={"body": {"name": "correlation_test", "params": {"col_a": "salary", "col_b": "bonus"}}}),
    Surface("prediction models", "GET", "/api/v1/datasets/{ds}/prediction-models"),
    Surface("aggregate preflight", "GET", "/api/v1/datasets/{ds}/aggregate-preflight"),
    Surface("column stats", "GET", "/api/v1/datasets/{ds}/columns/dept/stats",
            denied_variant={"path": "/api/v1/datasets/{ds}/columns/salary/stats"}),
    Surface("hierarchy", "GET", "/api/v1/datasets/{ds}/hierarchy"),
    Surface("relationship check", "POST", "/api/v1/relationships/check",
            body={"from_dataset_id": "{ds}", "from_column": "dept", "to_dataset_id": "{peer}", "to_column": "dept"},
            denied_variant={"body": {"from_dataset_id": "{ds}", "from_column": "salary",
                                     "to_dataset_id": "{peer}", "to_column": "floor"}}),
    Surface("semantic query", "POST", "/api/v1/semantic/query",
            body={"dataset_id": "{ds}", "dimensions": ["dept"]},
            denied_variant={"body": {"dataset_id": "{ds}", "dimensions": ["salary"]}}),
    Surface("semantic rows", "GET", "/api/v1/semantic/datasets/{ds}/rows"),
    Surface("dependents", "GET", "/api/v1/datasets/{ds}/dependents", params={"name": "headcount"}),
]

#: `/datasets/{dataset_id}/...` routes deliberately NOT walked here, each with
#: the reason. Writes, and metadata about expressions, are covered by the
#: capability tests; these return no row content.
EXCUSED_ROUTES = {
    ("GET", "/api/v1/datasets/{dataset_id}/analysis"): "reads a cached result; 404 for anyone with RLS/CLS (test_analysis_rls.py)",
    ("POST", "/api/v1/datasets/{dataset_id}/suggest-dashboards"): "calls the language model; its frame is the one data-preview uses",
    ("POST", "/api/v1/datasets/{dataset_id}/prediction-models"): "training; covered in test_prediction_models_api.py and below",
    ("GET", "/api/v1/datasets/{dataset_id}/prediction-models/{model_id}/drift"): "only through a model the caller may use (model_access.usable_model), over their secured frame; test_model_scoring.py",
    ("POST", "/api/v1/datasets/{dataset_id}/prediction-models/{model_id}/score-jobs"): "queues a job; the job re-checks as its owner and writes their secured rows; test_model_scoring.py",
    ("POST", "/api/v1/datasets/{dataset_id}/widget-data/reconcile"): "multipart upload; resolves the widget through _resolve_widget_data as widget-data does (row rules, denied columns, other orgs); test_widget_reconcile.py",
}


def _fill(value, w):
    if isinstance(value, str):
        return value.replace("{ds}", str(w["ds"].id)).replace("{peer}", str(w["peer"].id))
    if isinstance(value, list):
        return [_fill(v, w) for v in value]
    if isinstance(value, dict):
        out = {k: _fill(v, w) for k, v in value.items()}
        # ids travel as numbers in JSON bodies
        for k in ("dataset_id", "from_dataset_id", "to_dataset_id"):
            if isinstance(out.get(k), str) and out[k].isdigit():
                out[k] = int(out[k])
        return out
    return value


async def _call(client, s: Surface, w, user, *, variant: dict | None = None):
    path = _fill((variant or {}).get("path", s.path), w)
    body = _fill((variant or {}).get("body", s.body), w)
    params = _fill((variant or {}).get("params", s.params), w)
    kw: dict[str, Any] = {"headers": _headers(user), "params": params}
    if s.method == "GET":
        return await client.get(path, **kw)
    return await client.post(path, json=body, **kw)


def _leaks(text: str) -> list[str]:
    found = []
    if SALARY_MARK in text:
        found.append("salary value")
    found += [f"South row ({m})" for m in SOUTH_MARKS if m in text]
    return found


@pytest.mark.parametrize("s", SURFACES, ids=lambda s: s.name)
async def test_the_owner_sees_the_sentinels_so_the_checks_mean_something(client, world, s):
    """Control: the same request succeeds for the owner. Without this, a
    request that no longer matches its endpoint (a 422, a 400) would pass
    every negative test below by returning nothing."""
    r = await _call(client, s, world, world["owner"])
    assert r.status_code < 300, f"{s.name}: {r.status_code} {r.text[:300]}"


@pytest.mark.parametrize("s", SURFACES, ids=lambda s: s.name)
async def test_another_organization_gets_404(client, world, s):
    r = await _call(client, s, world, world["other_admin"])
    assert r.status_code == 404, f"{s.name}: {r.status_code} {r.text[:300]}"


@pytest.mark.parametrize("s", SURFACES, ids=lambda s: s.name)
async def test_a_colleague_who_cannot_read_the_dataset_gets_404(client, world, s):
    r = await _call(client, s, world, world["outsider"])
    assert r.status_code == 404, f"{s.name}: {r.status_code} {r.text[:300]}"
    assert not _leaks(r.text)


@pytest.mark.parametrize("s", SURFACES, ids=lambda s: s.name)
async def test_the_restricted_reader_gets_no_denied_column_and_no_filtered_row(client, world, s):
    r = await _call(client, s, world, world["grantee"])
    if s.grantee_ok:
        assert r.status_code < 300, f"{s.name}: {r.status_code} {r.text[:300]}"
    leaks = _leaks(r.text)
    assert not leaks, f"{s.name} leaked {leaks}: {r.text[:500]}"


@pytest.mark.parametrize("s", [s for s in SURFACES if s.denied_variant], ids=lambda s: s.name)
async def test_naming_the_denied_column_returns_no_values(client, world, s):
    """Asking for `salary` by name must be refused, or answered without a
    single salary value -- never computed and returned."""
    r = await _call(client, s, world, world["grantee"], variant=s.denied_variant)
    leaks = _leaks(r.text)
    assert not leaks, f"{s.name} ({r.status_code}) leaked {leaks}: {r.text[:500]}"
    if r.status_code < 300:
        # A success must at least not be a computation over the column: the
        # owner's answer to the same request does carry salary.
        owner = await _call(client, s, world, world["owner"], variant=s.denied_variant)
        assert r.text != owner.text, f"{s.name}: the grantee got the owner's salary answer"


def test_every_dataset_data_route_is_in_the_inventory():
    """A new `/datasets/{dataset_id}/...` read route must join SURFACES or be
    excused with a reason. Writes (PUT/PATCH/DELETE) and routes that only
    return definitions are listed in NOT_DATA below."""
    from app.main import app
    listed = {(s.method, s.path.replace("{ds}", "{dataset_id}")) for s in SURFACES}
    gates = _gate_keys()
    listed |= {(s.method, s.denied_variant["path"].replace("{ds}", "{dataset_id}"))
               for s in SURFACES if s.denied_variant and "path" in s.denied_variant}
    missing = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/v1/datasets/{dataset_id}"):
            continue
        for m in getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}:
            if m not in ("GET", "POST"):
                continue
            key = (m, path)
            generic = (m, re.sub(r"\{column_name\}", "dept", path))
            shape = (m, re.sub(r"\{(?!dataset_id)[^}]+\}", "{x}", path))
            if (key in listed or generic in listed or shape in gates
                    or key in EXCUSED_ROUTES or key in NOT_DATA):
                continue
            missing.append(key)
    assert not missing, (
        "Dataset routes not in the cross-surface security inventory: "
        f"{sorted(missing)}. Add each to SURFACES (tests/test_security_surfaces.py), "
        "or to EXCUSED_ROUTES / NOT_DATA with the reason it returns no row content.")




@dataclass
class Gate:
    """A route that returns no row content but must still be refused to
    anyone who cannot read the dataset: definitions (expressions, labels,
    prep literals), settings, and writes. Authoring requires read."""
    name: str
    method: str
    path: str
    body: Any = None
    params: dict = field(default_factory=dict)
    #: Admin-only routes refuse every non-admin with 403 before any lookup,
    #: so the answer says nothing about whether the dataset exists.
    admin_only: bool = False


READ_GATES = [
    Gate("calculated columns", "GET", "/api/v1/datasets/{ds}/calculated-columns"),
    Gate("measures", "GET", "/api/v1/datasets/{ds}/measures"),
    Gate("custom functions", "GET", "/api/v1/datasets/{ds}/custom-functions"),
    Gate("column meta", "GET", "/api/v1/datasets/{ds}/column-meta"),
    Gate("column formats", "GET", "/api/v1/datasets/{ds}/column-formats"),
    Gate("prep steps", "GET", "/api/v1/datasets/{ds}/prep-steps"),
    Gate("sensitivity", "GET", "/api/v1/datasets/{ds}/sensitivity"),
    Gate("export policy", "GET", "/api/v1/datasets/{ds}/export-policy", admin_only=True),
    Gate("alerts", "GET", "/api/v1/datasets/{ds}/alerts"),
    Gate("shares", "GET", "/api/v1/datasets/{ds}/shares", admin_only=True),
    Gate("measure history", "GET", "/api/v1/datasets/{ds}/measures/m/history"),
    Gate("active refresh", "GET", "/api/v1/datasets/{ds}/refresh-jobs/active"),
]

WRITE_GATES = [
    Gate("duplicate column", "POST", "/api/v1/datasets/{ds}/columns/dept/duplicate"),
    Gate("set export policy", "POST", "/api/v1/datasets/{ds}/export-policy", params={"disabled": "true"},
         admin_only=True),
    Gate("save measure", "POST", "/api/v1/datasets/{ds}/measures", body={"name": "m", "expression": "SUM(headcount)"}),
    Gate("rename measure", "POST", "/api/v1/datasets/{ds}/measures/m/rename", body={"new_name": "n"}),
    Gate("restore measure", "POST", "/api/v1/datasets/{ds}/measures/m/restore", body={"version": 1}),
    Gate("rename calculated column", "POST", "/api/v1/datasets/{ds}/calculated-columns/c/rename", body={"new_name": "n"}),
    Gate("custom function preview", "POST", "/api/v1/datasets/{ds}/custom-functions/preview",
         body={"params": ["a"], "expression": "a", "sample_values": {"a": 1}}),
    Gate("save data view", "POST", "/api/v1/datasets/{ds}/save-data-view", params={"name": "v"}),
    Gate("apply data view", "POST", "/api/v1/datasets/{ds}/apply-data-view", params={"view_id": 1}),
    Gate("materialize", "POST", "/api/v1/datasets/{ds}/materialize", body={"name": "copy"}),
    Gate("create aggregate", "POST", "/api/v1/datasets/{ds}/aggregates",
         body={"name": "a", "grain": ["dept"], "measures": [{"column": "headcount", "agg": "sum"}]}),
    Gate("rebuild", "POST", "/api/v1/datasets/{ds}/rebuild"),
    Gate("refresh", "POST", "/api/v1/datasets/{ds}/refresh", body={}),
    Gate("queue refresh", "POST", "/api/v1/datasets/{ds}/refresh-jobs", body={}),
    Gate("create alert", "POST", "/api/v1/datasets/{ds}/alerts",
         body={"name": "a", "expression": "headcount > 0", "recipients": ["x@securia.test"]}),
    Gate("share", "POST", "/api/v1/datasets/{ds}/shares", body={"user_id": 1}, admin_only=True),
    Gate("hierarchy node", "POST", "/api/v1/datasets/{ds}/hierarchy", body={"name": "Folder"}),
    Gate("hierarchy auto-generate", "POST", "/api/v1/datasets/{ds}/hierarchy/auto-generate"),
    Gate("default filter", "PATCH", "/api/v1/datasets/{ds}/filter", body={"expression": "headcount > 0"}),
    Gate("score model", "POST", "/api/v1/datasets/{ds}/prediction-models/1/score", body={"from_dataset": True}),
    Gate("promote model", "POST", "/api/v1/datasets/{ds}/prediction-models/1/promote"),
    Gate("model drift", "GET", "/api/v1/datasets/{ds}/prediction-models/1/drift"),
    Gate("queue model scoring", "POST", "/api/v1/datasets/{ds}/prediction-models/1/score-jobs"),
]


async def _call_gate(client, g: Gate, w, user):
    kw: dict[str, Any] = {"headers": _headers(user), "params": _fill(g.params, w)}
    path = _fill(g.path, w)
    if g.method == "GET":
        return await client.get(path, **kw)
    return await client.request(g.method, path, json=_fill(g.body, w), **kw)


@pytest.mark.parametrize("g", READ_GATES + WRITE_GATES, ids=lambda g: g.name)
async def test_definitions_settings_and_writes_are_refused_to_a_colleague_who_cannot_read(client, world, g):
    r = await _call_gate(client, g, world, world["outsider"])
    expected = {403, 404} if g.admin_only else {404}
    assert r.status_code in expected, f"{g.name}: {r.status_code} {r.text[:300]}"
    r = await _call_gate(client, g, world, world["other_admin"])
    assert r.status_code == 404, f"{g.name} (other org): {r.status_code} {r.text[:300]}"


#: Anything else under /datasets/{dataset_id} that is neither data nor gated
#: here, with the reason. Keep this short.
NOT_DATA: set[tuple[str, str]] = set()


def _gate_keys() -> set[tuple[str, str]]:
    return {(g.method, re.sub(r"/(dept|m|c|1)(/|$)", lambda m_: "/{x}" + m_.group(2), g.path.replace("{ds}", "{dataset_id}")))
            for g in READ_GATES + WRITE_GATES}


async def test_a_row_rule_that_cannot_be_evaluated_exports_no_rows(client, world, db_session):
    """Every read fails CLOSED on a broken row rule; the whole-table export
    used the fail-open evaluator and exported every row instead."""
    from sqlalchemy import update
    await db_session.execute(update(RowSecurityRule)
                             .where(RowSecurityRule.dataset_id == world["ds"].id)
                             .values(filter_expr="no_such_column == 'x'"))
    await db_session.commit()
    r = await client.get(f"/api/v1/datasets/{world['ds'].id}/export", params={"format": "csv"},
                         headers=_headers(world["grantee"]))
    assert r.status_code == 200, r.text
    lines = [ln for ln in r.text.lstrip("\ufeff").splitlines() if ln.strip()]
    assert len(lines) == 1, f"expected the header only, got {len(lines) - 1} rows"


# ── Surfaces that are not under /datasets/{id} ───────────────────────────────

async def _report(db_session, world, *, extra_dataset_id=None, published=True):
    from app.models.models import Report, ReportPage, ReportWidget
    rep = Report(name="HR board", org_id=world["org"].id, created_by=world["owner"].id,
                 dataset_id=world["ds"].id, published=published)
    db_session.add(rep)
    await db_session.flush()
    page = ReportPage(report_id=rep.id, name="P1", position=0)
    db_session.add(page)
    await db_session.flush()
    db_session.add(ReportWidget(page_id=page.id, widget_type="bar", title="Headcount",
                                config={"dimension": "dept", "measure": "headcount", "aggregation": "sum"},
                                layout={"x": 0, "y": 0, "w": 6, "h": 4}))
    if extra_dataset_id:
        db_session.add(ReportWidget(page_id=page.id, widget_type="bar", title="Borrowed",
                                    config={"dataset_id": extra_dataset_id, "dimension": "dept",
                                            "measure": "floor", "aggregation": "sum"},
                                    layout={"x": 6, "y": 0, "w": 6, "h": 4}))
    await db_session.commit()
    return rep


async def test_a_pdf_leaves_out_a_widget_whose_dataset_its_reader_was_never_given(db_session, world, tmp_path):
    """The PDF matched the dataset's org to the report's and drew it. The
    widget endpoint asks the read rule through the report, which only opens
    what the report's AUTHOR could read; the PDF now asks the same."""
    from app.models.models import Report
    from app.routers.reports import _resolve_report_sections
    theirs = tmp_path / "theirs.csv"
    theirs.write_text("dept,floor\nOUTSIDERSECRET,99\n", encoding="utf-8")
    private = Dataset(name="Outsider private", filename=str(theirs), org_id=world["org"].id,
                      mode="import", row_count=1, col_count=2, created_by=world["outsider"].id)
    db_session.add(private)
    await db_session.commit()
    rep = await _report(db_session, world, extra_dataset_id=private.id)
    rep = await db_session.get(Report, rep.id)
    sections = await _resolve_report_sections(db_session, rep, world["grantee"])
    titles = [w["title"] for s in sections for w in s["widgets"]]
    assert "Headcount" in titles and "Borrowed" not in titles
    assert "OUTSIDERSECRET" not in repr(sections)
    assert not _leaks(repr(sections))


async def test_schedules_are_run_and_deleted_only_through_their_own_report_by_an_editor(
        client, db_session, world):
    from app.models.models import ReportSchedule
    rep = await _report(db_session, world)
    other = await _report(db_session, world)
    sched = ReportSchedule(org_id=world["org"].id, report_id=other.id,
                           creator_user_id=world["owner"].id, interval_minutes=60,
                           recipients=["x@securia.test"])
    db_session.add(sched)
    await db_session.commit()
    owner = _headers(world["owner"])
    # Through the wrong report: the schedule does not exist there.
    r = await client.post(f"/api/v1/reports/{rep.id}/schedules/{sched.id}/run-now", headers=owner)
    assert r.status_code == 404, r.text
    r = await client.delete(f"/api/v1/reports/{rep.id}/schedules/{sched.id}", headers=owner)
    assert r.status_code == 404, r.text
    # A viewer of the right report cannot fire its emails.
    r = await client.post(f"/api/v1/reports/{other.id}/schedules/{sched.id}/run-now",
                          headers=_headers(world["grantee"]))
    assert r.status_code == 403, r.text
    assert await db_session.get(ReportSchedule, sched.id) is not None


async def test_auto_compose_is_authoring_and_needs_edit(client, db_session, world):
    rep = await _report(db_session, world)
    r = await client.post(f"/api/v1/reports/{rep.id}/auto-compose", headers=_headers(world["grantee"]))
    assert r.status_code == 403, r.text


async def test_the_query_builder_preview_is_for_admins_like_the_raw_preview(client, db_session, world):
    from app.models.models import DataSource
    src = DataSource(name="Warehouse", type="sqlite", config={"filepath": world["ds"].filename},
                     org_id=world["org"].id)
    db_session.add(src)
    await db_session.commit()
    r = await client.post(f"/api/v1/data-sources/{src.id}/build-query/preview",
                          json={"base": "t", "columns": [{"table": "t", "column": "x"}]},
                          headers=_headers(world["owner"]))
    assert r.status_code == 403, r.text


async def test_a_conversation_stops_reading_a_dataset_once_the_share_is_revoked(client, db_session, world):
    from sqlalchemy import delete
    h = _headers(world["grantee"])
    r = await client.post("/api/v1/agent/conversations", json={"dataset_ids": [world["ds"].id]}, headers=h)
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    await db_session.execute(delete(DatasetShare).where(DatasetShare.user_id == world["grantee"].id))
    await db_session.commit()
    r = await client.post(f"/api/v1/agent/conversations/{cid}/ask", json={"question": "total headcount?"},
                          headers=h)
    assert r.status_code == 404, r.text


async def test_a_copy_of_a_private_dataset_stays_private(client, db_session, world):
    """Materializing writes a new dataset. Left unowned it was readable by the
    whole org, so copying a private dataset published it to every colleague.
    (A dataset with row or column rules refuses to be materialized at all.)"""
    r = await client.post(f"/api/v1/datasets/{world['peer'].id}/materialize", json={"name": "Depts copy"},
                          headers=_headers(world["owner"]))
    assert r.status_code == 200, r.text
    new_id = r.json()["id"]
    assert (await db_session.get(Dataset, new_id)).created_by == world["owner"].id
    r = await client.get(f"/api/v1/datasets/{new_id}", headers=_headers(world["outsider"]))
    assert r.status_code == 404


async def test_an_import_is_owned_by_the_admin_who_ran_it(client, db_session, world, tmp_path):
    import sqlite3
    from app.models.models import DataSource, Role, User as U
    path = tmp_path / "src.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()
    admin_role = (await db_session.execute(
        __import__("sqlalchemy").select(Role).where(Role.org_id == world["org"].id, Role.is_org_admin.is_(True))
    )).scalar_one()
    admin = U(org_id=world["org"].id, role_id=admin_role.id, email="adm@securia.test",
              password_hash=hash_password("pw"))
    src = DataSource(name="W", type="sqlite", config={"filepath": str(path)}, org_id=world["org"].id)
    db_session.add_all([admin, src])
    await db_session.commit()
    r = await client.post(f"/api/v1/data-sources/{src.id}/import", json={"dataset_name": "T", "table": "t"},
                          headers=_headers(admin))
    assert r.status_code == 200, r.text
    assert (await db_session.get(Dataset, r.json()["id"])).created_by == admin.id


# ── Revocation: a cached answer never outlives the permission behind it ──────

async def test_revoking_a_share_ends_access_even_to_a_cached_answer(client, db_session, world):
    from sqlalchemy import delete
    h = _headers(world["grantee"])
    url = f"/api/v1/datasets/{world['ds'].id}/widget-data"
    first = await client.post(url, json=_wd(), headers=h)
    assert first.status_code == 200
    again = await client.post(url, json=_wd(), headers=h)       # served from the cache
    assert again.json() == first.json()
    await db_session.execute(delete(DatasetShare).where(DatasetShare.user_id == world["grantee"].id))
    await db_session.commit()
    assert (await client.post(url, json=_wd(), headers=h)).status_code == 404


async def test_a_changed_row_rule_changes_a_cached_answer(client, db_session, world):
    from sqlalchemy import update
    h = _headers(world["grantee"])
    url = f"/api/v1/datasets/{world['ds'].id}/widget-data"
    before = (await client.post(url, json=_wd(), headers=h)).text
    assert "Ops" in before
    await db_session.execute(update(RowSecurityRule).where(RowSecurityRule.dataset_id == world["ds"].id)
                             .values(filter_expr="dept == 'Sales'"))
    await db_session.commit()
    after = (await client.post(url, json=_wd(), headers=h)).text
    assert "Ops" not in after and "Sales" in after


async def test_a_column_rule_added_later_applies_to_a_cached_answer(client, db_session, world):
    from sqlalchemy import update
    h = _headers(world["grantee"])
    url = f"/api/v1/datasets/{world['ds'].id}/widget-data"
    body = _wd(measure="bonus")
    first = await client.post(url, json=body, headers=h)
    assert first.status_code == 200
    await db_session.execute(update(ColumnSecurityRule).where(ColumnSecurityRule.dataset_id == world["ds"].id)
                             .values(denied_columns=["salary", "bonus"]))
    await db_session.commit()
    after = await client.post(url, json=body, headers=h)
    assert after.status_code >= 400 or after.json() != first.json()


#: Requests that name `pay`, the owner's calculated column `salary * 1`.
DERIVED = [
    ("widget data", "POST", "/api/v1/datasets/{ds}/widget-data", _wd(measure="pay"), {}),
    ("data preview", "POST", "/api/v1/datasets/{ds}/data-preview", {}, {}),
    ("goal seek", "POST", "/api/v1/datasets/{ds}/goal-seek", None,
     {"x_column": "pay", "y_column": "headcount", "target_y": 10}),
    ("explain", "POST", "/api/v1/datasets/{ds}/explain", None, {"column": "pay"}),
    ("outlier details", "POST", "/api/v1/datasets/{ds}/outlier-details", None, {"column": "pay"}),
    ("measure preview", "POST", "/api/v1/datasets/{ds}/measures/preview",
     {"expression": "SUM(pay)", "group_by": "dept"}, {}),
    ("calculated column preview", "POST", "/api/v1/datasets/{ds}/calculated-columns/preview",
     {"expression": "pay * 1"}, {}),
    ("semantic query", "POST", "/api/v1/semantic/query",
     {"dataset_id": "{ds}", "dimensions": ["dept"], "measures": [{"column": "pay", "agg": "sum"}]}, {}),
    ("export csv", "GET", "/api/v1/datasets/{ds}/export", None, {"format": "csv"}),
    ("quality report", "POST", "/api/v1/datasets/{ds}/quality", {}, {}),
    ("insights", "POST", "/api/v1/datasets/{ds}/insights", None, {}),
]


@pytest.mark.parametrize("case", DERIVED, ids=lambda c: c[0])
async def test_a_column_derived_from_the_denied_one_is_denied_too(client, world, case):
    name, method, path, body, params = case
    s = Surface(name, method, path, body=body, params=params)
    r = await _call(client, s, world, world["grantee"])
    leaks = _leaks(r.text)
    assert not leaks, f"{name} ({r.status_code}) leaked {leaks}: {r.text[:400]}"


async def test_a_model_cannot_be_trained_on_a_column_derived_from_a_denied_one(client, world):
    """Training dropped denied columns AFTER calculated columns, so `pay`
    (`salary * 1`) was a usable predictor -- the model carried the column the
    rule hides and every later caller inherited it."""
    r = await client.post(f"/api/v1/datasets/{world['ds'].id}/prediction-models",
                          json={"name": "m", "target": "headcount", "predictors": ["pay", "bonus"]},
                          headers=_headers(world["grantee"]))
    assert not _leaks(r.text)
    if r.status_code < 300:
        assert "pay" not in r.json()["features"], r.text[:400]
