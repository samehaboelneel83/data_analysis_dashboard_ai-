"""The real accuracy gate: runs the golden set through the LIVE agent and scores it.

Self-contained, meant to run INSIDE the backend container -- it imports `app.*`
(DB models, security, direct_query) and talks to the API over loopback HTTP,
neither of which exist outside that container:

    docker exec datalytics_backend python -m evals.run_gate \\
        --source-id 2 --golden evals/golden/maps.jsonl --min-accuracy 0.6

For each golden `{question, sql, intent}` pair this opens a FRESH conversation
against `--source-id`, asks the question, pulls the last step's generated SQL
off `GET /agent/runs/{id}`, then executes golden+generated SQL directly
against the source (`direct_query.get_engine`, same as the live agent) and
scores with `evals.run_eval.evaluate()` -- execution equality, strict: no
attempt is made here to credit a "right numbers, different label" near-miss,
because that judgment call needs a human. The full per-question record (SQL,
status, repair count, latency, strict-correct) is written to `--out` so that
kind of hand value-verification can happen afterwards without re-running
anything live.

Exit codes mirror `evals.report`'s CLI: 0 at/above --min-accuracy, 1 below,
2 on malformed input (bad golden file, bad args) -- never a bare traceback,
because this is meant to gate a merge from a shell script's $LASTEXITCODE.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time

from evals.report import build_report
from evals.run_eval import evaluate

_ASK_TIMEOUT_S = 240.0
_BASE_URL = "http://localhost:8000"


class GateInputError(ValueError):
    """Malformed golden file or CLI input -- caller turns this into exit 2."""


def load_golden(path: str) -> list[dict]:
    """Read a `{question, sql, intent}`-per-line JSONL golden set. Raises
    GateInputError with a human-readable message on anything malformed --
    missing file, bad JSON, or a row missing a required key -- so `main` can
    turn it into a clean exit 2 instead of a traceback."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        raise GateInputError(f"could not read {path}: {e}") from e

    pairs = []
    for i, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise GateInputError(f"{path}:{i} is not valid JSON: {e}") from e
        if not isinstance(row, dict) or not row.get("question") or not row.get("sql"):
            raise GateInputError(
                f"{path}:{i} does not look like a golden row "
                "(expected an object with 'question' and 'sql' keys)")
        pairs.append({"question": row["question"], "sql": row["sql"],
                      "intent": row.get("intent") or "unknown"})
    if not pairs:
        raise GateInputError(f"{path} contains no golden rows")
    return pairs


def _last_step_sql(run_detail: dict) -> tuple[str | None, int]:
    """The generated SQL to score is the LAST step's -- earlier steps in a
    multi-step plan are intermediate lookups, not the answer. repair_attempts
    is summed across all steps: any repair the run needed, at any step, is
    evidence about robustness the gate should surface."""
    steps = run_detail.get("steps") or []
    repairs = sum(s.get("repair_attempts") or 0 for s in steps)
    if not steps:
        return None, repairs
    return steps[-1].get("sql"), repairs


async def _ask_one(client, token: str, source_id: int, question: str) -> dict:
    """One golden question's full round trip: fresh conversation -> ask ->
    pull the run's steps. Never raises -- any HTTP failure, timeout, or
    unexpected response shape is caught and turned into a `status: "error"`
    record, because one bad question must not crash the other 24."""
    headers = {"Authorization": f"Bearer {token}"}
    start = time.monotonic()
    try:
        conv_resp = await client.post(f"{_BASE_URL}/agent/conversations",
                                      json={"data_source_id": source_id},
                                      headers=headers, timeout=30.0)
        conv_resp.raise_for_status()
        cid = conv_resp.json()["id"]

        ask_resp = await client.post(f"{_BASE_URL}/agent/conversations/{cid}/ask",
                                     json={"question": question},
                                     headers=headers, timeout=_ASK_TIMEOUT_S)
        ask_resp.raise_for_status()
        ask_body = ask_resp.json()
        status = ask_body.get("status") or "error"
        run_id = ask_body.get("run_id")

        sql, repairs = None, 0
        if run_id is not None:
            run_resp = await client.get(f"{_BASE_URL}/agent/runs/{run_id}",
                                        headers=headers, timeout=30.0)
            run_resp.raise_for_status()
            sql, repairs = _last_step_sql(run_resp.json())

        latency_ms = int((time.monotonic() - start) * 1000)
        return {"status": status, "generated_sql": sql, "repair_attempts": repairs,
                "latency_ms": latency_ms, "error": ask_body.get("error")}
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {"status": "error", "generated_sql": None, "repair_attempts": 0,
                "latency_ms": latency_ms, "error": f"{type(exc).__name__}: {exc}"}


async def run_ask_loop(golden: list[dict], source_id: int) -> list[dict]:
    """Sequential by design -- concurrent asks would share the agent's
    per-source rate limiting and make latency numbers meaningless."""
    import httpx

    from app.core.security import create_access_token

    token = create_access_token(1, 1)
    results = []
    async with httpx.AsyncClient() as client:
        for pair in golden:
            ask_result = await _ask_one(client, token, source_id, pair["question"])
            results.append({**pair, "golden_sql": pair["sql"], **ask_result})
    return results


async def _source_cfg(source_id: int) -> dict:
    """The direct_query.get_engine() config for --source-id, fetched straight
    from the DB (the measurement appendix's method) rather than through the
    API -- there is no HTTP endpoint that hands back raw connection config,
    by design."""
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models.models import DataSource

    async with AsyncSessionLocal() as db:
        source = (await db.execute(
            select(DataSource).where(DataSource.id == source_id))).scalar_one_or_none()
        if source is None:
            raise GateInputError(f"no data source with id {source_id}")
        cfg = dict(source.config or {})
        cfg["type"] = source.type
        return cfg


def make_executor(cfg: dict):
    """A synchronous `execute(sql) -> list[dict]` closure over one pooled
    engine, matching evaluate()'s expected signature (run_eval.py) and the
    live agent's own executor (app/services/agent/executor.py) -- same
    get_engine(), same raw-row shape, so scoring is apples to apples."""
    from sqlalchemy import text

    from app.services.direct_query import get_engine

    engine = get_engine(cfg)

    def execute(sql: str) -> list[dict]:
        with engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(text(sql))]

    return execute


def score(ask_results: list[dict], execute) -> dict:
    """Strict execution-equality scoring via evaluate() -- a question with no
    generated SQL (clarification, error, or a run that never reached a SQL
    step) is scored against an empty-string "query" that evaluate()'s
    try/except turns into a wrong answer, same as a crashing query would."""
    pairs = [{"golden_sql": r["golden_sql"], "generated_sql": r["generated_sql"] or "",
             "intent": r["intent"]} for r in ask_results]
    return evaluate(pairs, execute)


def operational_summary(ask_results: list[dict]) -> dict:
    completed = sum(1 for r in ask_results if r["status"] == "ok")
    clarification = sum(1 for r in ask_results if r["status"] == "needs_clarification")
    failed = sum(1 for r in ask_results if r["status"] not in ("ok", "needs_clarification"))
    latencies = [r["latency_ms"] for r in ask_results]
    return {
        "completed": completed, "clarification": clarification, "failed": failed,
        "median_latency_ms": statistics.median(latencies) if latencies else 0,
    }


def build_operational_report(op: dict, n: int) -> str:
    return (f"Completed: {op['completed']}/{n}  "
            f"Clarification: {op['clarification']}/{n}  "
            f"Failed: {op['failed']}/{n}  "
            f"Median latency: {op['median_latency_ms']} ms")


def annotate_strict_correct(ask_results: list[dict], execute) -> list[dict]:
    """Attach a per-row `strict_correct` bool to each ask result -- the same
    golden/generated row-equality check evaluate() does in aggregate, but
    kept per-question so both the --out JSON and --value-verified's listing
    can identify exactly WHICH rows failed strict scoring, not just the
    overall count. Without this, hand value-verification (the whole point of
    writing --out) would have no way to find the wrong rows without
    re-running the comparison itself."""
    from evals.run_eval import rows_equal

    annotated = []
    for r in ask_results:
        ok = False
        if r["generated_sql"]:
            try:
                golden_rows = execute(r["golden_sql"])
                generated_rows = execute(r["generated_sql"])
                ok = rows_equal(golden_rows, generated_rows)
            except Exception:
                ok = False
        annotated.append({**r, "strict_correct": ok})
    return annotated


def build_hand_verification_note(annotated_results: list[dict]) -> str:
    """Only meaningful accompanying --value-verified: a plain listing of every
    strict-wrong question with both SQL strings, so a human can tell "actually
    wrong" from "right numbers, different label/order/rounding" without
    re-running anything. Strict accuracy (and the exit code) never changes
    from this -- that judgment call belongs to a person, not this script."""
    wrong = [r for r in annotated_results if not r["strict_correct"]]
    lines = ["", "Hand-verification candidates (strict-wrong questions):", "-" * 56]
    if not wrong:
        lines.append("(none -- all questions scored strict-correct)")
    for r in wrong:
        lines.append(f"[{r['intent']}] {r['question']}")
        lines.append(f"  status: {r['status']}  repairs: {r['repair_attempts']}")
        lines.append(f"  golden:    {r['golden_sql']}")
        lines.append(f"  generated: {r['generated_sql'] or '(none)'}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m evals.run_gate",
        description="Run the golden set through the live agent and gate on strict accuracy.",
    )
    parser.add_argument("--source-id", type=int, required=True)
    parser.add_argument("--golden", required=True, help="Path to a golden *.jsonl file")
    parser.add_argument("--min-accuracy", type=float, default=0.0,
                        help="Exit 1 if strict accuracy is below this threshold (default: 0.0)")
    parser.add_argument("--out", default="/tmp/eval_gate_results.json",
                        help="Where to write the raw per-question results JSON")
    parser.add_argument("--value-verified", action="store_true",
                        help="Also print a hand-verification listing of strict-wrong "
                             "questions (SQL + status), for manual value-accuracy review. "
                             "Does not change scoring or the exit code.")
    args = parser.parse_args(argv)

    try:
        golden = load_golden(args.golden)
    except GateInputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.source_id <= 0:
        print("error: --source-id must be a positive integer", file=sys.stderr)
        return 2

    try:
        ask_results = asyncio.run(run_ask_loop(golden, args.source_id))
        cfg = asyncio.run(_source_cfg(args.source_id))
    except GateInputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    execute = make_executor(cfg)
    scored = score(ask_results, execute)
    op = operational_summary(ask_results)
    # Annotated once, up front: both the printed --value-verified listing and
    # the --out JSON need to know WHICH rows failed strict scoring, not just
    # evaluate()'s aggregate counts.
    ask_results = annotate_strict_correct(ask_results, execute)

    print(build_report(scored))
    print()
    print(build_operational_report(op, len(ask_results)))
    if args.value_verified:
        print(build_hand_verification_note(ask_results))

    out_payload = {
        "source_id": args.source_id, "golden": args.golden,
        "min_accuracy": args.min_accuracy, "summary": scored, "operational": op,
        "questions": ask_results,
    }
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out_payload, f, indent=2)
    except OSError as e:
        print(f"warning: could not write {args.out}: {e}", file=sys.stderr)

    accuracy = scored.get("accuracy", 0.0) or 0.0
    return 0 if accuracy >= args.min_accuracy else 1


if __name__ == "__main__":
    sys.exit(main())
