"""Score the persona benchmark against the app's own analyses (Phase 4.1-4.2).

Reads docs/persona-test/benchmark.json, finds for each scenario the latest
guided-setup analysis on its connection that made a dashboard (or the flow
given with --flow S1=123), and scores what that dashboard SAYS: the text on
its pages, the titles of its charts and pages (or, before a dashboard is made,
what its designed pages say). Read-only: nothing is created
or changed in the app.

    python scripts/persona_benchmark.py BENCH.json [--flow S1=123 ...]
           [--out scores.json] [--baseline baseline.json] [--set-baseline]

Exit code 1 when the gate fails (a scenario scored lower than its baseline).
A fresh run of every persona through the guided setup is made in the app
(or by the browser walk) first; this script only reads its result.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys

from sqlalchemy import select

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.models import Report, ReportPage, ReportWidget, SetupFlow  # noqa: E402
from app.services.persona_benchmark import GATE_MARGIN, average, gate, score_scenario  # noqa: E402


async def dashboard_text(db, report_id: int) -> str:
    """Everything a dashboard says in words: page names and titles, chart
    titles, and the text of its text boxes."""
    report = await db.get(Report, report_id)
    if report is None:
        return ""
    parts = [report.name or ""]
    pages = (await db.execute(select(ReportPage).where(ReportPage.report_id == report_id))).scalars().all()
    for p in pages:
        parts += [p.name or "", p.title or ""]
        widgets = (await db.execute(select(ReportWidget).where(ReportWidget.page_id == p.id))).scalars().all()
        for w in widgets:
            cfg = w.config or {}
            parts.append(w.title or "")
            for key in ("content", "text", "markdown", "subtitle"):
                if isinstance(cfg.get(key), str):
                    parts.append(cfg[key])
    return "\n".join(x for x in parts if x)


def designs_text(flow: SetupFlow) -> str:
    """What the designed pages say, before any dashboard is made from them:
    page titles and answers, chart titles, the text boxes."""
    parts = []
    for item in (flow.designs or {}).get("items") or []:
        page = item.get("proposal") or {}
        parts += [str(page.get("title") or ""), str(page.get("answer") or ""), str(page.get("note") or "")]
        parts += [str(a) for a in page.get("answers") or [] if isinstance(a, str)]
        parts += [str(u) for u in page.get("unanswered") or [] if isinstance(u, str)]
        for w in page.get("widgets") or []:
            cfg = w.get("config") or {}
            parts.append(str(w.get("title") or ""))
            parts += [cfg[k] for k in ("content", "text", "markdown", "subtitle") if isinstance(cfg.get(k), str)]
    return "\n".join(x for x in parts if x)


async def flow_text(db, flow: SetupFlow) -> str:
    """The dashboard the analysis made, else the pages it designed."""
    if flow.report_id:
        return await dashboard_text(db, flow.report_id)
    return designs_text(flow)


async def latest_flow(db, connection_id: int) -> SetupFlow | None:
    q = (select(SetupFlow).where(SetupFlow.data_source_id == connection_id)
         .order_by(SetupFlow.id.desc()).limit(10))
    for f in (await db.execute(q)).scalars().all():
        if f.report_id or (f.designs or {}).get("items"):
            return f
    return None


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("benchmark")
    ap.add_argument("--flow", action="append", default=[], help="S1=123: score this flow for S1")
    ap.add_argument("--out")
    ap.add_argument("--baseline")
    ap.add_argument("--set-baseline", action="store_true")
    ap.add_argument("--average", nargs="+", help="score files of several runs of one version: report their mean")
    args = ap.parse_args()
    bench = json.loads(pathlib.Path(args.benchmark).read_text(encoding="utf-8"))
    chosen = dict(f.split("=", 1) for f in args.flow)

    scores: dict[str, dict] = {}
    if args.average:
        scores = average([json.loads(pathlib.Path(f).read_text(encoding="utf-8"))["scores"] for f in args.average])
        for s in scores.values():
            s["flow_id"] = f"mean of {s['runs']}"
    else:
        async with AsyncSessionLocal() as db:
            for sc in bench["scenarios"]:
                flow = (await db.get(SetupFlow, int(chosen[sc["id"]]))) if sc["id"] in chosen \
                    else await latest_flow(db, int(sc["connection_id"]))
                text = await flow_text(db, flow) if flow else ""
                result = score_scenario(sc, text)
                result["flow_id"] = flow.id if flow else None
                scores[sc["id"]] = result

    baseline = {}
    if args.baseline and pathlib.Path(args.baseline).exists() and not args.set_baseline:
        baseline = json.loads(pathlib.Path(args.baseline).read_text(encoding="utf-8")).get("scores", {})
    verdict = gate(scores, baseline, GATE_MARGIN if args.average else 0.0)
    for sid, s in scores.items():
        spread = f" (spread {s['spread']:.1f})" if "spread" in s else ""
        print(f"{sid:4} {s['score']:4.1f} / {s['out_of']:<4.0f} flow {s['flow_id']}  {s['connection']}{spread}")
    print(f"total {verdict['total']:.1f} / {verdict['out_of']:.0f}; lowest {verdict['lowest']}; "
          f"{'gate passed' if verdict['ok'] else 'GATE FAILED: lower than baseline: ' + ', '.join(verdict['lowered'])}")
    payload = {"scores": scores, "gate": verdict}
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.set_baseline and args.baseline:
        pathlib.Path(args.baseline).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
