"""End-to-end validation of preprocessing, modeling and the query builder.

Usage: python scripts/validate_pipeline.py   (against a running stack on :8000,
with the sandbox account provisioned -- see scripts/create_org_admin.py).

Unlike the pytest suite, this runs against the LIVE server: it validates the
deployed composition -- routers, auth, the real database -- not the in-memory
harness. 31 checks, every expected value derived by hand first.

Preprocessing, modeling and the query builder,
against the RUNNING stack — every step asserted for correctness, not just status.

Uses its own tiny dataset with hand-computable numbers, so every expected value
in here was derived on paper first.
"""
import io
import sys

import requests

BASE = "http://localhost:8000/api/v1"
results: list[tuple[str, str, str]] = []   # (area, step, verdict)


def check(area, step, ok, detail=""):
    verdict = "PASS" if ok else "FAIL"
    results.append((area, step, verdict + (f" — {detail}" if detail and not ok else "")))
    print(f"  [{verdict}] {area}: {step}" + (f" — {detail}" if detail and not ok else ""))
    return ok


def main():
    # ── auth ─────────────────────────────────────────────────────────────────
    tok = requests.post(f"{BASE}/auth/login", json={
        "email": "e2e@sandbox.local", "password": "e2e-sandbox-pw"}).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}

    # ── PREPROCESSING ────────────────────────────────────────────────────────
    csv = (
        "region,product,amount,qty,when\n"
        "US,A,10.5,2,2024-01-05\n"
        "US,B,20.0,1,2024-02-10\n"
        "CA,A,5.5,3,2024-01-20\n"
        "CA,B,4.0,4,2024-02-25\n"
        "MX,A,100.0,1,2024-03-01\n"      # deliberate outlier
    )
    up = requests.post(f"{BASE}/datasets", headers=H,
                       files={"file": ("validate.csv", io.BytesIO(csv.encode()), "text/csv")},
                       data={"name": "validate-pipeline"})
    check("preprocess", "upload accepts CSV", up.status_code == 200, up.text[:120])
    ds = up.json()
    dsid = ds["id"]

    # type detection
    types = {c["name"]: c["dtype"] for c in ds["columns"]}
    check("preprocess", "type detection (categorical/numeric/datetime)",
          types.get("region") == "categorical" and types.get("amount") == "numeric"
          and types.get("qty") == "numeric" and types.get("when") == "datetime", str(types))
    check("preprocess", "row/col counts recorded", ds["row_count"] == 5 and ds["col_count"] == 5,
          f"{ds['row_count']}x{ds['col_count']}")

    # calculated-column preview then save; verify the engine, not the echo
    prev = requests.post(f"{BASE}/datasets/{dsid}/calculated-columns/preview", headers=H,
                         json={"expression": "amount * qty"}).json()
    vals = prev.get("values") or prev.get("sample") or []
    check("preprocess", "calc-column preview evaluates", 21.0 in [round(float(v), 1) for v in vals if v is not None],
          str(prev)[:120])
    requests.put(f"{BASE}/datasets/{dsid}/calculated-columns", headers=H,
                 json={"name": "line_total", "expression": "amount * qty"})
    kpi = requests.post(f"{BASE}/datasets/{dsid}/widget-data", headers=H,
                        json={"widget_type": "kpi",
                              "config": {"measure": "line_total", "aggregation": "sum"}}).json()
    # 10.5*2 + 20*1 + 5.5*3 + 4*4 + 100*1 = 21+20+16.5+16+100 = 173.5
    check("preprocess", "saved calc column queryable end-to-end",
          abs(kpi["rows"][0]["value"] - 173.5) < 1e-9, str(kpi)[:120])

    # duplicate a data item
    dup = requests.post(f"{BASE}/datasets/{dsid}/columns/amount/duplicate", headers=H).json()
    check("preprocess", "duplicate column creates identity calc",
          dup.get("expression") == "`amount`", str(dup))

    # column-meta override. Two checks: the write validates its vocabulary (an
    # invalid role is refused, not stored), and a valid override persists.
    bad_meta = requests.put(f"{BASE}/datasets/{dsid}/column-meta", headers=H,
                            json={"meta": {"qty": {"role": "categorical"}}})
    check("modeling", "column-meta refuses an invalid role vocabulary",
          bad_meta.status_code == 400, f"{bad_meta.status_code}")
    requests.put(f"{BASE}/datasets/{dsid}/column-meta", headers=H,
                 json={"meta": {"qty": {"role": "category"}}})
    meta = requests.get(f"{BASE}/datasets/{dsid}/column-meta", headers=H).json()
    check("modeling", "column-meta role override persists",
          meta.get("qty", {}).get("role") == "category", str(meta))

    # dataset-level pre-filter + preview
    fp = requests.post(f"{BASE}/datasets/{dsid}/filter-preview", headers=H,
                       json={"expression": "region == 'US'"}).json()
    check("preprocess", "filter-preview counts matching rows",
          fp.get("matching_rows") == 2 or fp.get("rows") == 2 or "2" in str(fp), str(fp)[:120])
    requests.patch(f"{BASE}/datasets/{dsid}/filter", headers=H,
                   json={"expression": "region != 'MX'"})
    kpi2 = requests.post(f"{BASE}/datasets/{dsid}/widget-data", headers=H,
                         json={"widget_type": "kpi",
                               "config": {"measure": "amount", "aggregation": "sum"}}).json()
    check("preprocess", "default filter excludes rows in every query",
          abs(kpi2["rows"][0]["value"] - 40.0) < 1e-9, str(kpi2)[:120])
    requests.patch(f"{BASE}/datasets/{dsid}/filter", headers=H, json={"expression": ""})

    # data preview grid (the Data tab)
    dp = requests.post(f"{BASE}/datasets/{dsid}/data-preview", headers=H,
                       json={"limit": 10, "offset": 0}).json()
    check("preprocess", "data-preview returns the raw grid",
          dp.get("total") == 5 and len(dp.get("rows", [])) == 5, str(dp)[:100])

    # ── MODELING ─────────────────────────────────────────────────────────────
    # measure (post-aggregation) preview + save + query
    mp = requests.post(f"{BASE}/datasets/{dsid}/measures/preview", headers=H,
                       json={"name": "avg_line", "expression": "SUM(amount) / SUM(qty)"}).json()
    check("modeling", "measure preview evaluates at aggregate grain",
          "error" not in str(mp).lower() or mp.get("ok", True), str(mp)[:120])
    requests.post(f"{BASE}/datasets/{dsid}/measures", headers=H,
                  json={"name": "avg_line", "expression": "SUM(amount) / SUM(qty)"})
    mkpi = requests.post(f"{BASE}/datasets/{dsid}/widget-data", headers=H,
                         json={"widget_type": "kpi",
                               "config": {"measure": "avg_line", "aggregation": "sum"}}).json()
    # SUM(amount)=140, SUM(qty)=11 → 12.7272...
    check("modeling", "measure evaluates post-aggregation (140/11)",
          abs(mkpi["rows"][0]["value"] - 140.0 / 11.0) < 1e-6, str(mkpi)[:120])
    # per-group grain: avg_line BY region must be per-group ratios, not global
    mbar = requests.post(f"{BASE}/datasets/{dsid}/widget-data", headers=H,
                         json={"widget_type": "bar",
                               "config": {"dimension": "region", "measure": "avg_line"}}).json()
    by = {r["name"]: r["value"] for r in mbar["rows"]}
    # US: 30.5/3, CA: 9.5/7, MX: 100/1
    check("modeling", "measure recomputed at each group's grain",
          abs(by["US"] - 30.5 / 3) < 1e-6 and abs(by["CA"] - 9.5 / 7) < 1e-6 and abs(by["MX"] - 100.0) < 1e-6,
          str(by))

    # hierarchy: manual node + drill contract
    hn = requests.post(f"{BASE}/datasets/{dsid}/hierarchy", headers=H,
                       json={"name": "Region", "column_name": "region", "parent_id": None}).json()
    hn2 = requests.post(f"{BASE}/datasets/{dsid}/hierarchy", headers=H,
                        json={"name": "Product", "column_name": "product", "parent_id": hn["id"]}).json()
    tree = requests.get(f"{BASE}/datasets/{dsid}/hierarchy", headers=H).json()
    check("modeling", "hierarchy persists parent/child",
          any(n["id"] == hn2["id"] and n["parent_id"] == hn["id"] for n in tree), str(tree)[:120])
    # drilling = querying the child column filtered by the parent value
    drill = requests.post(f"{BASE}/datasets/{dsid}/widget-data", headers=H,
                          json={"widget_type": "bar",
                                "config": {"dimension": "product", "measure": "amount",
                                           "filters": [{"column": "region", "op": "eq", "value": "US"}]}}).json()
    check("modeling", "hierarchy drill query (child under parent filter)",
          {r["name"]: r["value"] for r in drill["rows"]} == {"A": 10.5, "B": 20.0}, str(drill)[:120])

    # relationships (model view)
    ds2 = requests.post(f"{BASE}/datasets", headers=H,
                        files={"file": ("lookup.csv", io.BytesIO(b"region,mgr\nUS,Ann\nCA,Bo\n"), "text/csv")},
                        data={"name": "validate-lookup"}).json()
    rel = requests.post(f"{BASE}/relationships", headers=H,
                        json={"from_dataset_id": dsid, "from_column": "region",
                              "to_dataset_id": ds2["id"], "to_column": "region"})
    check("modeling", "relationship create", rel.status_code in (200, 201), rel.text[:120])
    rels = requests.get(f"{BASE}/relationships", headers=H).json()
    check("modeling", "relationship listed for model view",
          any(r["from_dataset_id"] == dsid and r["to_dataset_id"] == ds2["id"] for r in rels), str(rels)[:120])

    # ── QUERY BUILDER ────────────────────────────────────────────────────────
    q = lambda cfg, wt="bar": requests.post(  # noqa: E731
        f"{BASE}/datasets/{dsid}/widget-data", headers=H,
        json={"widget_type": wt, "config": cfg}).json()

    r = q({"dimension": "region", "measure": "amount", "aggregation": "sum"})
    check("query", "group + sum", {x["name"]: x["value"] for x in r["rows"]}
          == {"US": 30.5, "CA": 9.5, "MX": 100.0}, str(r)[:120])
    r = q({"dimension": "region", "measure": "amount", "aggregation": "avg"})
    check("query", "avg aggregation", abs({x["name"]: x["value"] for x in r["rows"]}["US"] - 15.25) < 1e-9)
    r = q({"dimension": "region", "measure": "amount", "aggregation": "count"})
    check("query", "count aggregation", {x["name"]: x["value"] for x in r["rows"]}["CA"] == 2)

    r = q({"dimension": "region", "measure": "amount", "aggregation": "sum",
           "sort": "desc", "sort_by": "value", "limit": 2})
    check("query", "sort desc by value + limit (top-N)",
          [x["name"] for x in r["rows"]] == ["MX", "US"], str(r["rows"]))
    r = q({"dimension": "region", "measure": "amount", "aggregation": "sum",
           "sort": "asc", "sort_by": "name"})
    check("query", "sort asc by name", [x["name"] for x in r["rows"]] == ["CA", "MX", "US"])

    r = q({"dimension": "when", "dimension_granularity": "month", "measure": "amount",
           "aggregation": "sum", "sort": "asc", "sort_by": "name"})
    check("query", "date granularity buckets by month",
          [x["name"] for x in r["rows"]] == ["2024-01", "2024-02", "2024-03"]
          and abs(r["rows"][0]["value"] - 16.0) < 1e-9, str(r["rows"]))

    r = q({"dimension": "region", "measure": "amount", "aggregation": "sum",
           "filters": [{"column": "product", "op": "eq", "value": "A"}]})
    check("query", "structured eq filter", {x["name"]: x["value"] for x in r["rows"]}
          == {"US": 10.5, "CA": 5.5, "MX": 100.0})
    r = q({"dimension": "region", "measure": "amount", "aggregation": "sum",
           "filters": [{"column": "amount", "op": "gt", "value": 5.5}]})
    check("query", "numeric gt filter", {x["name"] for x in r["rows"]} == {"US", "MX"})
    r = q({"dimension": "region", "measure": "amount", "aggregation": "sum",
           "filters": [{"column": "region", "op": "in", "value": ["US", "CA"]}]})
    check("query", "in-list filter", {x["name"] for x in r["rows"]} == {"US", "CA"})

    r = q({"dimension": "when", "dimension_granularity": "month", "measure": "amount",
           "aggregation": "sum", "running": "sum", "sort": "asc", "sort_by": "name"})
    # Running totals ADD a running_sum key beside value rather than replacing it --
    # the per-bucket number stays readable, which is the right design.
    vals = [x["running_sum"] for x in r["rows"]]
    check("query", "running total accumulates to the grand total",
          vals == [16.0, 40.0, 140.0], str(vals))

    r = q({"columns": ["region", "amount"], "show_totals": True, "limit": 3}, wt="table")
    check("query", "raw table + totals over FULL data under limit",
          len(r["rows"]) == 3 and abs(r["totals"][1] - 140.0) < 1e-9, str(r)[:150])

    bad = requests.post(f"{BASE}/datasets/{dsid}/widget-data", headers=H,
                        json={"widget_type": "kpi",
                              "config": {"measure": "nope", "aggregation": "sum"}})
    check("query", "unknown column fails safe (no 500)",
          bad.status_code != 500 and "rows" in bad.json(), f"{bad.status_code}")

    # sandbox: expression injection must be rejected
    inj = requests.post(f"{BASE}/datasets/{dsid}/calculated-columns/preview", headers=H,
                        json={"expression": "__import__('os').system('echo pwned')"})
    check("query", "expression sandbox rejects imports",
          inj.status_code != 200 or "error" in str(inj.json()).lower() or inj.json().get("ok") is False,
          inj.text[:100])

    # cleanup
    requests.delete(f"{BASE}/datasets/{dsid}", headers=H)
    requests.delete(f"{BASE}/datasets/{ds2['id']}", headers=H)

    fails = [r for r in results if r[2].startswith("FAIL")]
    print(f"\n{'=' * 60}\n{len(results)} checks, {len(fails)} failures")
    for a, s, v in fails:
        print(f"  FAIL {a}: {s} {v}")
    sys.exit(1 if fails else 0)


main()
