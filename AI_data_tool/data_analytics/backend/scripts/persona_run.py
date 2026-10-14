"""Walk every persona of the benchmark through the guided setup (Phase 4.1).

For each scenario of docs/persona-test/benchmark.json, as the given user and
through the app's own API -- the calls the setup screens make:
  1. start a new analysis on the scenario's connection with the persona's
     own words (About you);
  2. ask for dataset suggestions and make every suggestion (an import);
  3. let Check & discover run (fixes for datasets the setup made apply by
     themselves, as on screen);
  4. let the pages be designed.
No dashboard is made: the benchmark reads what the designed pages say
(scripts/persona_benchmark.py). This CREATES analyses and datasets in the
app and uses the AI; it never deletes anything.

    python scripts/persona_run.py BENCH.json --user 8 [--only S2,S7] [--parallel 3] [--out flows.json]
                                  [--resume S2=82] [--redesign S1=84 ...]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
import time

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.models.models import User  # noqa: E402

API = "http://localhost:8000/api/v1"
POLL_SECONDS = 5
STEP_TIMEOUT = 1800


class Retrying(httpx.AsyncClient):
    """A kept-alive connection the server closed a moment before is reused
    and fails with an empty ReadError; such a request is sent again."""

    async def request(self, *args, **kwargs):
        for attempt in range(3):
            try:
                return await super().request(*args, **kwargs)
            except (httpx.ReadError, httpx.RemoteProtocolError):
                if attempt == 2:
                    raise
                await asyncio.sleep(1 + attempt)


def log(sid: str, msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {sid}: {msg}", flush=True)


async def wait_for(sid: str, what: str, fetch, done) -> dict:
    """Poll `fetch` until `done(result)`, or give up after STEP_TIMEOUT."""
    started = time.time()
    while True:
        got = await fetch()
        if done(got):
            log(sid, f"{what} ready after {time.time() - started:.0f}s")
            return got
        if time.time() - started > STEP_TIMEOUT:
            raise TimeoutError(f"{what} still pending after {STEP_TIMEOUT}s")
        await asyncio.sleep(POLL_SECONDS)


async def redesign(c: httpx.AsyncClient, sc: dict, flow: int) -> dict:
    """Design the pages of an analysis again, on the datasets it already has."""
    sid, src, lang = sc["id"], int(sc["connection_id"]), sc.get("language") or "en"
    started = time.time()
    (await c.post(f"/setup/{src}/dashboard/suggest", params={"lang": lang, "flow": flow})).raise_for_status()

    async def dashboard_step():
        return (await c.get(f"/setup/{src}/dashboard", params={"lang": lang, "flow": flow})).json()
    got = await wait_for(sid, "page design", dashboard_step, lambda d: not d["designs"]["pending"])
    log(sid, f"redesigned: {len(got['designs']['items'])} pages")
    return {"flow": flow, "pages": len(got["designs"]["items"]), "minutes": round((time.time() - started) / 60, 1)}


async def run_one(c: httpx.AsyncClient, sc: dict, resume: int | None = None) -> dict:
    sid, src, lang = sc["id"], int(sc["connection_id"]), sc.get("language") or "en"
    p = sc.get("persona") or {}
    brief = {k: v for k, v in {"work": p.get("work"), "focus": p.get("focus"), "questions": p.get("questions"),
                               "exclude": p.get("leave_out")}.items() if v}
    started = time.time()
    if resume:
        # Carry on with an analysis whose datasets are chosen: from the check.
        flow = resume
        log(sid, f"analysis {flow} resumed")
        return await _from_check(c, sid, src, lang, flow, started)
    r = await c.post(f"/setup/{src}/flows")
    r.raise_for_status()
    flow = r.json()["flow_id"]
    log(sid, f"analysis {flow} started")
    (await c.patch(f"/setup/{src}", params={"flow": flow}, json={"brief": brief})).raise_for_status()

    (await c.post(f"/setup/{src}/datasets/suggest", params={"lang": lang, "flow": flow})).raise_for_status()

    async def datasets_step():
        return (await c.get(f"/setup/{src}/datasets", params={"lang": lang, "flow": flow})).json()
    step = await wait_for(sid, "dataset suggestions", datasets_step, lambda d: not d["proposals"]["pending"])
    items = [{"id": it["id"], "name": it["name"]} for it in step["proposals"]["items"]]
    if not items:
        raise RuntimeError(f"no dataset was suggested ({step['proposals'].get('failed')})")
    made = (await c.post(f"/setup/{src}/datasets/create", params={"flow": flow},
                         json={"items": items, "mode": "import"})).json()
    ids = []
    for it in made["items"]:
        if it.get("dataset_id"):
            ids.append(it["dataset_id"])
            continue
        if not it.get("job_id"):
            log(sid, f"not made: {it.get('name')}: {it.get('error')}")
            continue

        async def job(jid=it["job_id"]):
            return (await c.get(f"/jobs/{jid}")).json()
        done = await wait_for(sid, f"import of {it['name']}", job,
                              lambda j: j.get("state") in ("succeeded", "failed", "cancelled"))
        if (done.get("result") or {}).get("dataset_id"):
            ids.append(done["result"]["dataset_id"])
        else:
            log(sid, f"import failed: {it['name']}: {done.get('error') or done.get('state')}")
    if not ids:
        raise RuntimeError("no dataset could be made")
    (await c.patch(f"/setup/{src}", params={"flow": flow},
                   json={"dataset_ids": ids, "created_ids": ids, "step": "check"})).raise_for_status()
    return await _from_check(c, sid, src, lang, flow, started)


async def _from_check(c: httpx.AsyncClient, sid: str, src: int, lang: str, flow: int, started: float) -> dict:
    async def check_step():
        return (await c.get(f"/setup/{src}/check", params={"lang": lang, "flow": flow})).json()
    await wait_for(sid, "check", check_step, lambda d: not any(x["findings"]["pending"] for x in d["datasets"])
                   and not (d.get("demand") or {}).get("pending"))
    (await c.patch(f"/setup/{src}", params={"flow": flow}, json={"step": "dashboard"})).raise_for_status()

    async def dashboard_step():
        return (await c.get(f"/setup/{src}/dashboard", params={"lang": lang, "flow": flow})).json()
    got = await wait_for(sid, "page design", dashboard_step, lambda d: not d["designs"]["pending"])
    took = time.time() - started
    log(sid, f"done: {len(got['designs']['items'])} pages in {took / 60:.1f} min")
    return {"flow": flow, "pages": len(got["designs"]["items"]), "minutes": round(took / 60, 1)}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("benchmark")
    ap.add_argument("--user", type=int, required=True)
    ap.add_argument("--only")
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--out")
    ap.add_argument("--resume", action="append", default=[], help="S2=82: carry on with that analysis")
    ap.add_argument("--redesign", action="append", default=[], help="S2=82: design that analysis's pages again")
    args = ap.parse_args()
    bench = json.loads(pathlib.Path(args.benchmark).read_text(encoding="utf-8"))
    wanted = set(args.only.split(",")) if args.only else None
    resume = {k: int(v) for k, v in (r.split("=", 1) for r in args.resume)}
    again = {k: int(v) for k, v in (r.split("=", 1) for r in args.redesign)}
    async with AsyncSessionLocal() as db:
        user = await db.get(User, args.user)
    token = create_access_token(user.id, user.org_id)
    gate = asyncio.Semaphore(args.parallel)
    results: dict[str, dict] = {}

    async def one(sc):
        async with gate:
            try:
                results[sc["id"]] = (await redesign(client, sc, again[sc["id"]]) if sc["id"] in again
                                     else await run_one(client, sc, resume.get(sc["id"])))
            except Exception as exc:                        # noqa: BLE001 -- one persona never stops the rest
                log(sc["id"], f"FAILED: {exc!r}")
                results[sc["id"]] = {"error": repr(exc)}
            if args.out:
                pathlib.Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")

    async with Retrying(base_url=API, headers={"Authorization": f"Bearer {token}"},
                                 timeout=httpx.Timeout(600, connect=30)) as client:
        await asyncio.gather(*(one(sc) for sc in bench["scenarios"]
                               if (not wanted or sc["id"] in wanted) and (not again or sc["id"] in again)))
    print(json.dumps(results, indent=2))
    return 0 if all("flow" in r for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
