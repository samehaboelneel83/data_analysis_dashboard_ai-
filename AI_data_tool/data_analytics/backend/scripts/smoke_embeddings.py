"""Live smokes for Task M2 (docs/superpowers/plans/2026-08-30-embeddings-service.md,
"Live smokes" bullet under Task M2). Runs INSIDE the backend container --
imports `app.services.retrieval` and hits the real compose network / real
`retrieval_embeddings` table, not a mock. Run via:

    docker compose exec backend python scripts/smoke_embeddings.py arabic
    docker compose exec backend python scripts/smoke_embeddings.py killcheck
    docker compose exec backend python scripts/smoke_embeddings.py restartcheck --before
    docker compose exec backend python scripts/smoke_embeddings.py restartcheck --after

Three checks, matching the plan verbatim:

  (a) arabic       -- two Arabic-described objects in a small catalog; with
                       Backend B on, the question about ONE of them ranks it
                       first; the lexical-only ranking is printed beside it
                       for comparison. Runnable any time the stack is up --
                       this script runs it itself, no controller step needed.

  (b) killcheck     -- run AFTER the controller kills the embeddings
                       container (`docker compose stop embeddings`). Proves
                       ranking still serves (lexical, circuit open) rather
                       than raising or hanging.

  (c) restartcheck  -- two-phase, spanning a real `docker compose restart
                       backend`:
                         --before : embeds+persists a fixture, records the
                                    `retrieval_embeddings` row count to a
                                    baseline file on the bind-mounted
                                    `/app` (survives the restart).
                         --after  : (run after the controller restarts the
                                    backend container) re-ranks the SAME
                                    fixture and confirms the row count is
                                    STABLE (no re-embed burst) -- printed
                                    before/after counts are the log evidence
                                    for the controller.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.agent.context import ObjectInfo, SchemaContext  # noqa: E402
from app.services import retrieval  # noqa: E402
from app.core.config import settings  # noqa: E402

BASELINE_PATH = "/app/.smoke_embeddings_restartcheck.json"


def _fixture_ctx() -> SchemaContext:
    """Same shape as test_retrieval.py's `_ctx()` -- two Arabic-described
    objects that only a real semantic match (not "the only Arabic doc")
    can tell apart, plus two English ones as noise."""
    ctx = SchemaContext(source_id=9001, family="postgresql")
    ctx.objects["orders"] = ObjectInfo(
        name="orders", kind="table",
        description="Customer purchase orders",
        columns={"id": "integer", "st_cd": "integer", "total": "numeric"},
        enum_labels={"st_cd": {"1": "new", "2": "paid", "3": "cancelled"}},
    )
    ctx.objects["customers"] = ObjectInfo(
        name="customers", kind="table",
        description="فروع العملاء وبياناتهم الأساسية",
        columns={"id": "integer", "city": "text"},
    )
    ctx.objects["invoices"] = ObjectInfo(
        name="invoices", kind="table",
        description="فواتير المبيعات الشهرية لكل فرع",
        columns={"id": "integer", "amount": "numeric"},
    )
    ctx.objects["v_sales"] = ObjectInfo(
        name="v_sales", kind="view",
        description="Sales rollup by month",
        columns={"month": "text", "amount": "numeric"},
    )
    return ctx


def _print_header(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def _embedding_row_count() -> int | None:
    """Real row count of `retrieval_embeddings`, or None if it can't be
    read (mirrors the module's own "any DB failure is non-fatal" stance --
    this script reports that rather than crashing)."""
    try:
        from app.models.models import RetrievalEmbedding

        engine = retrieval._get_persist_engine()
        table = RetrievalEmbedding.__table__
        with engine.connect() as conn:
            from sqlalchemy import func, select
            return conn.execute(select(func.count()).select_from(table)).scalar_one()
    except Exception as exc:  # pragma: no cover -- diagnostic path only
        print(f"    [WARN] could not read retrieval_embeddings row count: {exc}")
        return None


def check_arabic() -> bool:
    _print_header("(a) Arabic discrimination -- Backend B vs lexical-only")
    print(f"embedding_base_url = {settings.embedding_base_url}")
    print(f"embedding_model    = {settings.embedding_model}")
    print(f"embedding_dim      = {settings.embedding_dim}")
    retrieval._reset_embedding_process_state()

    ctx = _fixture_ctx()
    # `customers` is the hard gate -- a plain PASS/FAIL. `invoices` is
    # reported but never flips the exit code: the plan pre-committed that
    # case as small-catalog headroom (embedding_server/README + this plan's
    # "Pre-committed honesty" section -- "expected retrieval parity on the
    # small live catalog, headroom for larger ones. No eval-gate run"), not
    # a correctness bug this script should gate on. The side-by-side lexical
    # ranking is still printed for both so a real regression is visible
    # either way.
    cases = (
        (question_c := "بيانات العملاء الأساسية", "customers", "gate"),
        (question_i := "فواتير المبيعات الشهرية", "invoices", "headroom"),
    )

    ok = True
    for question, expected, mode in cases:
        documents, corpus = retrieval._catalog_state(ctx)
        lexical = retrieval._top_k(
            retrieval._lexical_scores_from_corpus(corpus, question), k=4)
        backend_b = retrieval._try_embedding_backend(documents, question)
        b_ranked = retrieval._top_k(backend_b, k=4) if backend_b is not None else None

        print(f"\nquestion: {question!r} (expect top = {expected!r}, "
              f"mode={mode})")
        print(f"  lexical-only ranking : {lexical}")
        if b_ranked is None:
            print("  Backend B            : UNAVAILABLE (circuit open / not configured "
                  "/ dim mismatch) -- see log above")
            if mode == "gate":
                ok = False
            else:
                print("  [INFO] expected headroom case skipped -- Backend B unavailable")
            continue

        print(f"  Backend B ranking    : {b_ranked}")
        top = b_ranked[0][0] if b_ranked else None
        matched = top == expected
        if mode == "gate":
            status = "PASS" if matched else "FAIL"
            print(f"  [{status}] Backend B top result == {expected!r} (got {top!r})")
            ok = ok and matched
        else:
            if matched:
                print(f"  [PASS] Backend B top result == {expected!r} (got {top!r})")
            else:
                print(f"  [expected headroom: got {top!r} instead of {expected!r} -- "
                      f"pre-committed small-catalog gap, not gated]")

    print(f"\n(a) RESULT: {'PASS' if ok else 'FAIL'} "
          f"(gate = customers case only; invoices is reported, not gated)")
    return ok


def check_killcheck() -> bool:
    _print_header("(b) kill-container fallback (run AFTER "
                  "`docker compose stop embeddings`)")
    retrieval._reset_embedding_process_state()
    ctx = _fixture_ctx()
    try:
        ranked = retrieval.rank_objects(ctx, "show me the orders table", k=3)
    except Exception as exc:
        print(f"  [FAIL] rank_objects RAISED instead of degrading: {exc!r}")
        return False
    ok = bool(ranked) and ranked[0][0] == "orders"
    circuit_open = retrieval._circuit_open()
    print(f"  ranked            = {ranked}")
    print(f"  circuit open      = {circuit_open}")
    print(f"  [{'PASS' if ok else 'FAIL'}] ranking still served "
          f"(lexical fallback) with the embeddings container down")
    return ok


def check_restartcheck(phase: str) -> bool:
    ctx = _fixture_ctx()
    question = "show me the orders table"

    if phase == "before":
        _print_header("(c) restart persistence -- BEFORE "
                      "`docker compose restart backend`")
        retrieval._reset_embedding_process_state()
        ranked = retrieval.rank_objects(ctx, question, k=3)
        count = _embedding_row_count()
        print(f"  ranked (embeds+persists) = {ranked}")
        print(f"  retrieval_embeddings row count = {count}")
        with open(BASELINE_PATH, "w", encoding="utf-8") as f:
            json.dump({"row_count_before": count}, f)
        print(f"  baseline written to {BASELINE_PATH}")
        print("\n  Next: `docker compose restart backend`, then re-run this "
              "script with `restartcheck --after`.")
        return count is not None

    _print_header("(c) restart persistence -- AFTER "
                  "`docker compose restart backend`")
    if not os.path.exists(BASELINE_PATH):
        print(f"  [FAIL] no baseline at {BASELINE_PATH} -- run "
              f"`restartcheck --before` first")
        return False
    with open(BASELINE_PATH, encoding="utf-8") as f:
        before = json.load(f)["row_count_before"]

    # A real restart already cleared the in-process LRU (new process) --
    # this call just makes that explicit/deterministic for the check.
    retrieval._reset_embedding_process_state()
    ranked = retrieval.rank_objects(ctx, question, k=3)
    after = _embedding_row_count()
    print(f"  ranked (should hit the persisted cache, zero re-embeds) = {ranked}")
    print(f"  retrieval_embeddings row count: before={before} after={after}")
    ok = after is not None and after == before
    print(f"  [{'PASS' if ok else 'FAIL'}] row count stable across restart "
          f"(no re-embed burst)")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("check", choices=["arabic", "killcheck", "restartcheck", "all"])
    ap.add_argument("--before", action="store_true")
    ap.add_argument("--after", action="store_true")
    args = ap.parse_args()

    if args.check == "arabic":
        ok = check_arabic()
    elif args.check == "killcheck":
        ok = check_killcheck()
    elif args.check == "restartcheck":
        if args.before == args.after:
            ap.error("restartcheck requires exactly one of --before / --after")
        ok = check_restartcheck("before" if args.before else "after")
    else:  # "all" -- (a) only; (b)/(c) need controller-driven docker steps
        ok = check_arabic()
        print("\n(b) and (c) need a controller-driven docker step between "
              "runs -- see this script's module docstring:")
        print("  (b) docker compose stop embeddings")
        print("      docker compose exec backend python scripts/smoke_embeddings.py killcheck")
        print("  (c) docker compose exec backend python scripts/smoke_embeddings.py restartcheck --before")
        print("      docker compose restart backend")
        print("      docker compose exec backend python scripts/smoke_embeddings.py restartcheck --after")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
