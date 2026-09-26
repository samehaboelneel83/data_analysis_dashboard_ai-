"""Run Ask AI against the held-out bilingual benchmark and score it (E11).

    python backend/scripts/bench_ask.py --base http://localhost:8000 \
        --email admin@datalytics.local --password demo-password \
        --cases qa/ask_benchmark.json --out ask_bench.json

Needs the language model reachable (it is what is being measured) and the
demo dataset the benchmark names. Each question is asked in a conversation
of its own, so no answer leans on an earlier one. Expected numbers are
computed from the data through the widget-data API as the same user, so the
benchmark follows the data. Scoring and targets: app/services/agent/
benchmark.py and docs/ASK_BENCHMARK.md. It asks questions and reads
answers; it changes no data (the "delete" case is one Ask AI must refuse).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.services.agent.benchmark import score, summarise  # noqa: E402

#: Proposed; to agree with the owner (docs/ASK_BENCHMARK.md).
TARGETS = {"answer_accuracy": {"en": 0.9, "ar": 0.85}, "ungrounded": 0, "refusals": 1.0}


def _value(client, ds_id: int, spec: dict) -> float | None:
    r = client.post(f"/api/v1/datasets/{ds_id}/widget-data", json=spec)
    r.raise_for_status()
    body = r.json()
    if body.get("value") is not None:
        return float(body["value"])
    rows = body.get("rows") or []
    return float(rows[0]["value"]) if rows and rows[0].get("value") is not None else None


def _top(client, ds_id: int, spec: dict) -> str | None:
    r = client.post(f"/api/v1/datasets/{ds_id}/widget-data", json=spec)
    r.raise_for_status()
    rows = r.json().get("rows") or []
    return str(rows[0]["name"]) if rows else None


def expected_for(client, ds_id: int, case: dict):
    e = case["expect"]
    if e["kind"] == "number":
        if "difference" in e:
            a, b = (_value(client, ds_id, s) for s in e["difference"])
            return None if a is None or b is None else a - b
        return _value(client, ds_id, e["from"])
    if e["kind"] == "mentions" and "top_of" in e:
        name = _top(client, ds_id, e["top_of"])
        case["expect"] = {**e, "all": [name] if name else []}
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--cases", default=os.path.join(os.path.dirname(__file__), "..", "..", "qa", "ask_benchmark.json"))
    ap.add_argument("--only", default=None, help="comma-separated case ids")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    bench = json.load(open(args.cases, encoding="utf-8"))
    cases = bench["cases"]
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]

    with httpx.Client(base_url=args.base, timeout=300, headers={"X-Requested-With": "XMLHttpRequest"}) as c:
        r = c.post("/api/v1/auth/login", json={"email": args.email, "password": args.password})
        r.raise_for_status()
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        ds = next((d for d in c.get("/api/v1/datasets").json() if d["name"] == bench["dataset"]), None)
        if ds is None:
            sys.exit(f"The benchmark's dataset {bench['dataset']!r} is not on this server (load the demo)")
        results = []
        for case in cases:
            expected = expected_for(c, ds["id"], case)
            conv = c.post("/api/v1/agent/conversations",
                          json={"dataset_ids": [ds["id"]], "title": f"benchmark {case['id']}"}).json()
            t0 = time.perf_counter()
            resp = c.post(f"/api/v1/agent/conversations/{conv['id']}/ask", json={"question": case["question"]})
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            if resp.status_code != 200:
                body = {"status": f"http {resp.status_code}", "error": body.get("detail")}
            body["ms"] = round((time.perf_counter() - t0) * 1000)
            res = score(case, body, expected)
            results.append({**res, "question": case["question"], "answer": body.get("answer")})
            print(f"{'PASS' if res['correct'] else 'FAIL'} {case['id']:24} {res['why'] or ''}", file=sys.stderr)
            c.delete(f"/api/v1/agent/conversations/{conv['id']}")
    summary = summarise(results)
    print(json.dumps({"summary": summary, "targets": TARGETS}, indent=2, ensure_ascii=False))
    if args.out:
        json.dump({"summary": summary, "targets": TARGETS, "results": results},
                  open(args.out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
