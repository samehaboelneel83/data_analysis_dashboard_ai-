"""The analyst panel's benchmark, live: how many of the hand-picked HR
questions does the automatic panel ask on the real dataset?

Run inside the backend container, by hand, before merging a change to the
panel (lenses, prompts, selection) -- the same "no CI" convention as
run_gate.py:

    python -m evals.panel_gate --dataset-id 214 --user admin@example.com --size 50
    python -m evals.panel_gate ... --min-question-recall 0.6     # exit 1 below it

It runs exactly what the dialog runs (`suggest_inputs.prepare` + `panel`) as
the named user, so row and column security apply, then scores the picks with
`services.panel_benchmark.coverage` against tests/data/hr_reference_visuals.json.
Prints the scores, what was missed and what was extra; `--json FILE` keeps the
whole run for comparison.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

REFERENCE = os.path.join(os.path.dirname(__file__), "..", "tests", "data", "hr_reference_visuals.json")


async def run(dataset_id: int, email: str, goal: str, size: int) -> dict:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.core.database import AsyncSessionLocal
    from app.models.models import Dataset, User
    from app.services import suggest_inputs as sug

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).options(selectinload(User.role))
                                 .where(User.email == email))).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"no user {email}")
        ds = await db.get(Dataset, dataset_id)
        if ds is None or ds.org_id != user.org_id:
            raise SystemExit(f"no dataset {dataset_id} in {email}'s organisation")
        inputs = await sug.prepare(db, user, ds)
    t0 = time.monotonic()
    out = await sug.panel(inputs, goal, size)
    out["seconds"] = round(time.monotonic() - t0, 1)
    return out


def score(out: dict, reference: dict) -> dict:
    from app.services.panel_benchmark import coverage
    picks = [w for p in out["proposals"] for w in p["widgets"]]
    return coverage(picks, reference["visuals"], set(reference["columns"]), {"emp_no"})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dataset-id", type=int, required=True)
    ap.add_argument("--user", required=True, help="email of the user to run as")
    ap.add_argument("--size", type=int, default=50)
    ap.add_argument("--goal", default="I am the HR director. I want to understand where people work, "
                                       "how pay differs and why, how hiring changed over time, and what goes together.")
    ap.add_argument("--min-question-recall", type=float, default=None)
    ap.add_argument("--json", default=None, help="write the whole run here")
    args = ap.parse_args(argv)

    reference = json.load(open(REFERENCE))
    out = asyncio.run(run(args.dataset_id, args.user, args.goal, args.size))
    cov = score(out, reference)
    p = out["panel"]
    print(f"panel: {p['candidates']} ideas ({p['from_model']} analysts, {p['from_statistics']} statistics), "
          f"{p['drawn']} drew, {p['rejected']} refused, {p['duplicates_merged']} merged, "
          f"{p['selected']} kept of {p['size']} in {out['seconds']}s")
    print(f"reference: {cov['reference']} visuals, {cov['distinct_reference_questions']} distinct questions")
    print(f"question recall {cov['question_recall']:.0%}  |  visuals: strict {cov['strict']} "
          f"({cov['strict_recall']:.0%}), loose {cov['loose']} ({cov['loose_recall']:.0%})")
    print("missed:", "; ".join(cov["missed"]) or "-")
    print("extra :", "; ".join(t or "?" for t in cov["extra"]) or "-")
    if args.json:
        json.dump({"coverage": cov, "run": out}, open(args.json, "w"), indent=1, default=str)
    if args.min_question_recall is not None and cov["question_recall"] < args.min_question_recall:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
