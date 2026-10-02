"""How close an automatic panel comes to a hand-picked set of visuals.

The reference is the HR analyst panel's hand-picked list (tests/data/
hr_reference_visuals.json): forty-nine visuals, each a question with a chart
that answers it, verified against SQL. The automatic panel is judged by how
many of those QUESTIONS it also asks -- not by matching chart types, because
"headcount by department" is the same question as a bar or a treemap.

A question is (kind, columns):

  kind     summary (one number), spread (a distribution), model, or compare
           (everything else: a measure split by something, a mix, a trend)
  columns  the dataset columns it analyses. An identifier is dropped: it is
           only ever counted, so "headcount by department" is (compare,
           {dept_name}). A model of a number or a category is its outcome
           column alone.

`coverage` reports strict recall (same kind and columns), loose recall (same
columns, any kind: a box plot of pay by department answers most of what a bar
of average pay by department does), and what was missed and what was extra.
"""
from __future__ import annotations

_SUMMARY = ("kpi", "card", "gauge")
_SPREAD = ("box_plot", "histogram")
_COUNTING = ("count", "countd", "frequency")


def question(widget_type: str, config: dict, columns: set[str], id_cols: set[str] = frozenset()) -> tuple:
    wt = str(widget_type)
    cfg = config or {}
    # A list of records answers one question -- "can I look a record up?" --
    # whichever columns it shows.
    if wt in ("table", "list") and isinstance(cfg.get("columns"), list) and not cfg.get("dimension"):
        return "detail", frozenset()
    used: set[str] = set()
    for k, v in (config or {}).items():
        if k == "filters":
            continue
        for x in (v if isinstance(v, list) else [v]):
            if isinstance(x, str) and x in columns:
                used.add(x)
    # An identifier is only ever counted: it is the question's verb, not its subject.
    used -= set(id_cols)
    if wt in ("model_linear", "model_logistic", "model_tree"):
        # A model's question is its outcome; predictor choices are its answer.
        target = (config or {}).get("measure") or (config or {}).get("response")
        used = {target} if target in columns else used
    kind = ("model" if wt.startswith("model_") else "summary" if wt in _SUMMARY
            else "spread" if wt in _SPREAD else "compare")
    return kind, frozenset(used)


def coverage(picks: list[dict], reference: list[dict], columns: set[str],
             id_cols: set[str] = frozenset()) -> dict:
    """Recall of the reference's questions among `picks` (both lists of
    {widget_type, config, title})."""
    def key(w):
        return question(w["widget_type"], w.get("config") or {}, columns, id_cols)

    # A slicer is a control, not a question: it asks nothing on its own.
    picks = [w for w in picks if w.get("widget_type") != "slicer"]
    reference = [w for w in reference if w.get("widget_type") != "slicer"]
    mine = {key(w) for w in picks}
    mine_cols = {k[1] for k in mine}
    ref_keys = [key(w) for w in reference]
    strict = [k in mine for k in ref_keys]
    loose = [k[1] in mine_cols for k in ref_keys]
    ref_set = set(ref_keys)
    n = len(reference) or 1
    return {
        "reference": len(reference), "picks": len(picks),
        "strict": sum(strict), "loose": sum(loose),
        "strict_recall": round(sum(strict) / n, 3), "loose_recall": round(sum(loose) / n, 3),
        "missed": [w.get("title") for w, hit in zip(reference, loose) if not hit],
        "extra": [w.get("title") for w in picks if key(w)[1] not in {k[1] for k in ref_set}],
        "distinct_reference_questions": len(ref_set),
        # The same, counting each distinct reference question once: several
        # hand-picked visuals ask one question at different grains or filters.
        "question_recall": round(len({k for k in ref_set if k[1] in mine_cols}) / (len(ref_set) or 1), 3),
        # Near misses count: a reference question is asked when one pick
        # charts at least two thirds of its columns and nothing unrelated --
        # "top 10 days by canceled orders" showing orders and cancellations
        # asks the reference's question even without its third column. Exact
        # column sets understated daily ops (five-dataset review, 2026-10-02).
        "overlap_recall": round(len({k for k in ref_set if any(_near(k[1], m) for m in mine_cols)})
                                / (len(ref_set) or 1), 3),
    }


def _near(ref: frozenset, mine: frozenset) -> bool:
    if not ref or not mine:
        return ref == mine
    shared = len(ref & mine)
    return shared >= max(1, -(-2 * len(ref) // 3)) and shared >= len(mine) / 2
