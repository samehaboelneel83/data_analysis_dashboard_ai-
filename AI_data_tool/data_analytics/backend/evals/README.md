# evals

Execution-accuracy evaluation for the agent's generated SQL (spec: "results, not
strings" -- two queries that return the same rows are the same answer, regardless of
column aliases or row order).

- `run_eval.py` -- the library: `rows_equal()` (order/alias/type-tolerant row
  comparison) and `evaluate(pairs, execute)`, which runs each `{golden_sql,
  generated_sql, intent}` pair through `execute` and returns
  `{total, correct, accuracy, by_intent: {intent: {total, correct}}}`.
- `report.py` -- turns that results dict into a printable table and a pass/fail exit
  code: `python -m evals.report results.json --min-accuracy 0.5` (exit 0 at/above the
  threshold, 1 below, 2 on a malformed/missing results file).
- `run_gate.py` -- the real end-to-end gate: runs the golden set through the LIVE
  agent (fresh conversation + ask per question), executes golden and generated SQL
  against the source, scores with `evaluate()`, and prints the same kind of report as
  `report.py` plus completion/clarification/failed counts and median latency. Meant
  to run *inside* the backend container -- see "The gate" below.
- `golden/*.jsonl` -- the golden question sets (`fixture.jsonl`, `maps.jsonl`), one
  `{question, sql, intent}` object per line.

## The gate

**This repository has no CI (no remote either).** `run_eval_gate.ps1` (one directory
up, `backend/run_eval_gate.ps1`) IS the gate -- there is nothing else, and that's the
plan until CI infra exists. Run it by hand before merging a change that touches agent
generation, retrieval, or prompt behavior.

```powershell
cd backend
.\run_eval_gate.ps1 -SourceId 2 -Golden evals/golden/maps.jsonl -MinAccuracy 0.6
```

It restarts the backend container, waits for it to come up, then runs
`python -m evals.run_gate` inside the container (`docker exec datalytics_backend ...`)
and propagates its exit code:

```
docker exec datalytics_backend python -m evals.run_gate \
    --source-id 2 --golden evals/golden/maps.jsonl --min-accuracy 0.6 [--value-verified]
```

For each golden question this opens a fresh conversation against `--source-id`, asks
it, pulls the last step's generated SQL off `GET /agent/runs/{id}`, executes both
golden and generated SQL against the source, and scores strict execution-equality
with `evaluate()` (the "results, not strings" method from
`docs/superpowers/specs/2026-08-25-layer-4-agent-orchestration-design.md`'s
measurement appendix -- same one used for every `v1 measured results` / `hardening
pass` / `all-layers pass` round documented there). `--value-verified` additionally
prints a listing of every strict-wrong question's SQL, for the kind of by-hand "right
numbers, different label" review those rounds also did -- it never changes the score
or the exit code, since that judgment call needs a person. The raw per-question
results (status, SQL, repair count, latency, strict-correct) are always written to
`--out` (default `/tmp/eval_gate_results.json`) so that review can happen after the
run without re-executing anything.

Exit codes (same semantics as `report.py`'s CLI):

- `0` -- strict accuracy >= `--min-accuracy`
- `1` -- strict accuracy below `--min-accuracy`
- `2` -- malformed input (bad golden file, bad `--source-id`, etc.)

Runtime: roughly 20 minutes for the 25-question `maps.jsonl` golden set. The ask-loop
is deliberately sequential (a real LLM round trip per question, ~240s timeout each),
not parallelised -- concurrent asks would share the agent's per-source rate limiting
and make the latency numbers meaningless.

## Tests

`backend/tests/test_agent_eval.py` covers `rows_equal`/`evaluate`.
`backend/tests/test_eval_report.py` covers `report.py`'s table rendering and exit
codes.
`backend/tests/test_eval_gate.py` covers `run_gate.py`'s pure parts -- golden-set
loading/validation, the results-to-report plumbing, and the exit-code decision -- with
the HTTP/executor seams mocked. The ask-loop itself (live HTTP against a running
agent, a real DB) needs the live stack and is exercised only by actually running the
gate, not by pytest.
