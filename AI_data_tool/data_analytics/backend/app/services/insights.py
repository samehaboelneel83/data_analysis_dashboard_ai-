"""The insights engine: scan a dataset's secured frame unprompted and return
ranked, plain-language findings — SAS's Insights / Power BI's Insights, sized
to this app.

Six deterministic detectors, each yielding findings with a 0-1 interest score
so unrelated kinds rank in ONE list:

  trend          last full period vs the average of prior periods, per measure
  standout       a category member carrying an outsized share of a measure
  laggard        the weakest member of an otherwise even category
  correlation    strongly moving measure pairs
  outlier_impact rows beyond the IQR fences and the share of the total they carry
  data_quality   heavy missingness and date-coverage gaps

Every number is computed here, never guessed: each finding carries the figures
its sentence states, so the UI can show exactly what the words claim. The
`narrative` ties the top findings into one prose paragraph — a generated
summary, honest about being template prose rather than an LLM's.
"""
from __future__ import annotations

import pandas as pd
from .semantic_guard import is_quantity

MAX_MEASURES = 6
MAX_CATEGORIES = 6
MAX_LEVELS = 12
MIN_ROWS = 20


def _fmt(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if abs(v) >= 1_000:
        return f"{v / 1_000:.1f}k"
    return f"{v:.4g}"


#: Shared with services/analysis/inferential.py deliberately: a finding the
#: insights engine calls significant and a test the user then runs by hand must
#: not disagree about where the line is.
SIGNIFICANCE_ALPHA = 0.05

#: Below this, a p-value carries no information worth printing, so the finding
#: is reported without one rather than with a meaningless one.
MIN_ROWS_FOR_TEST = 10


def _pearson_p(a: pd.Series, b: pd.Series) -> float | None:
    """Two-sided p for a Pearson correlation, or None when untestable.

    Imported lazily: this module is on the dataset-open path, and scipy costs
    real import time that a dataset with no numeric pairs should not pay.
    """
    try:
        from scipy import stats
        pair = pd.concat([a, b], axis=1).dropna()
        if len(pair) < MIN_ROWS_FOR_TEST:
            return None
        x, y = pair.iloc[:, 0], pair.iloc[:, 1]
        if x.std() == 0 or y.std() == 0:
            return None
        return float(stats.pearsonr(x, y)[1])
    except Exception:  # noqa: BLE001 -- a finding without a p beats no finding
        return None


def _uniformity_p(shares: pd.Series) -> float | None:
    """Chi-square goodness-of-fit against an even split, or None when untestable.

    Counts must be non-negative for this to mean anything -- a measure that can
    go negative (profit, variance) is not a frequency, and testing it as one
    would be arithmetic dressed as inference.
    """
    try:
        from scipy import stats
        vals = shares.dropna().to_numpy(dtype=float)
        if len(vals) < 2 or (vals < 0).any() or vals.sum() <= 0:
            return None
        if vals.sum() < MIN_ROWS_FOR_TEST:
            return None
        return float(stats.chisquare(vals)[1])
    except Exception:  # noqa: BLE001
        return None


def _apply_multiple_comparison_correction(findings: list[dict]) -> None:
    """Adjust every tested finding's p-value across the whole run, in place.

    Benjamini-Hochberg rather than Bonferroni: this is exploratory scanning, not
    a confirmatory trial. Bonferroni controls the chance of ANY false positive
    and would suppress most true findings along with the false ones; BH controls
    the expected PROPORTION of false findings among those reported, which is
    what a reader of a ranked list actually cares about.

    A finding whose significance does not survive is DEMOTED, not deleted --
    the pattern is real in these rows, it is simply not evidence about anything
    beyond them, and the detail text says so. Deleting it would hide a genuine
    description; presenting it as significant would be a false claim.
    """
    tested = [f for f in findings if f.get("p_value") is not None]
    if len(tested) < 2:
        return          # nothing to correct against
    # `.analysis`, not `..analysis`: this module is app.services.insights, so
    # two dots resolve to app.analysis, which does not exist. The first version
    # of this had the wrong depth and the broad `except` below turned that typo
    # into a silent no-op -- the correction never ran, and nothing said so. The
    # import is now OUTSIDE the try for exactly that reason: a missing module
    # is a bug to fix, not a condition to swallow.
    from .analysis.inferential import correct_p_values

    try:
        out = correct_p_values([f["p_value"] for f in tested])
    except Exception:   # noqa: BLE001 -- a runtime failure must not lose findings
        return
    for finding, adjusted, kept in zip(tested, out["adjusted"], out["rejected"]):
        if adjusted is None:
            continue
        was = finding.get("significant")
        finding["p_adjusted"] = round(float(adjusted), 6)
        finding["significant"] = bool(kept)
        if was and not kept:
            # It looked significant on its own and does not survive the family.
            finding["score"] = round(float(finding.get("score", 0)) * 0.4, 3)
            finding["detail"] = (
                finding.get("detail", "").rstrip()
                + f" Adjusted for the {out['n_tests']} tests run over this "
                  f"dataset, this is no longer significant (adjusted "
                  f"p = {adjusted:.3g}).")


#: `column_meta.role` is written by two vocabularies that had to be reconciled.
#:
#: The Fields pane writes `category` / `measure` / `hidden` -- what an author
#: chose. The metadata plane (`infer_semantic.classify_role`, and the
#: automation chain's describe step through it) writes `identifier` /
#: `dimension` / `measure` / `timestamp` -- what the data looks like.
#:
#: Before this map the second vocabulary was silently discarded: anything that
#: was not `category` or `measure` fell through to the DETECTED type, so a
#: column recorded as an identifier came back out as `numeric` and every
#: consumer went on summing it. The value was being written and ignored.
_ROLE_TO_ANALYSIS_KIND = {
    "category": "categorical",
    "dimension": "categorical",
    "measure": "numeric",
    "timestamp": "datetime",
    # An explicit OUTCOME, not a reason to drop the column. A column missing
    # from the map reads as "never seen", not as "identifier", and each
    # consumer would then invent its own meaning for absence -- which is the
    # distributed inference this change exists to remove. Every consumer
    # filters by exact equality (== "numeric", == "categorical", == "datetime"),
    # so `identifier` matches none of them, which is exactly right: an
    # identifier is not a measure, not a category and not a date.
    "identifier": "identifier",
    # The time concept under its canonical name. `timestamp` above is kept
    # because the map has read it since it shipped and a stored value must not
    # stop meaning what it meant.
    "temporal": "datetime",
    # Free text: a comments column is not a category, however hard detection
    # tries. `detect_types` emits only numeric/categorical/datetime, so a
    # 3,000-distinct-value notes field arrives labelled `categorical` and gets
    # proposed as a bar chart with 3,000 bars. `text` matches no consumer's
    # equality check -- they all test == "numeric" / "categorical" / "datetime"
    # -- so the column correctly drops out of dimension pickers, and
    # `text_topics` is the one analysis that goes looking for it.
    "freetext": "text",
    #
    # `geography` is deliberately ABSENT. It falls through to detection, which
    # is what it has always done: a country name detects as categorical and a
    # latitude as numeric, and both are right. Mapping it to one kind here would
    # silently reclassify whichever of those two the choice went against.
}


def effective_roles(type_map: dict[str, str], column_meta: dict | None) -> dict[str, str]:
    """Detection overlaid with the RECORDED role -- the same rule the Fields
    pane lives by. A numeric `year` reclassified as a category must stop being
    a measure HERE too, or the engine reports trends on a label; hidden columns
    leave the analysis entirely, matching the author's intent.

    A recorded role always outranks detection. That is the point of recording
    one: `student_id` is numeric by dtype, and dtype is precisely what is wrong
    about it.
    """
    out: dict[str, str] = {}
    meta = column_meta or {}
    for col, detected in type_map.items():
        m = meta.get(col)
        m = m if isinstance(m, dict) else {}
        if m.get("hidden"):
            continue
        out[col] = _ROLE_TO_ANALYSIS_KIND.get(m.get("role"), detected)
    return out


def generate_insights(df: pd.DataFrame, type_map: dict[str, str],
                      column_meta: dict | None = None,
                      labels: dict[str, str] | None = None,
                      value_labels: dict[str, dict[str, str]] | None = None) -> dict:
    """Ranked findings over a secured frame.

    `labels` and `value_labels` come from `services/knowledge.py` and are both
    optional. Without them a finding reads "wait_minutes in 2026-03 ran 18%
    above its monthly average" -- correct, and written in the schema's words
    rather than the reader's. With them the same finding names the thing the
    business calls it and spells out what a coded value stands for.

    Nothing about the NUMBERS changes: every figure is still computed here and
    still carried on the finding, so the UI can show exactly what the sentence
    claims. Only the words the numbers are wrapped in.
    """
    findings: list[dict] = []
    names = dict(labels or {})
    vmaps = dict(value_labels or {})

    # Deliberately not `n` and `v`: the detectors below already bind `v` to a
    # numeric Series, and a one-letter helper that a loop can shadow is a
    # TypeError waiting for whichever detector runs first.
    def col_label(column: str) -> str:
        """What to call a column in a sentence a person reads."""
        return names.get(column) or column

    def val_label(column: str, value) -> str:
        """What a coded value MEANS, when the catalog recorded it."""
        return (vmaps.get(column) or {}).get(str(value), str(value))

    roles = effective_roles(type_map, column_meta)
    # The semantic veto: a numeric latitude, id or year is not a quantity, and
    # a "trend in latitude" or "year moves with revenue" is a finding about
    # nothing (services/semantic_guard.py).
    measures = [c for c, t in roles.items() if t == "numeric" and is_quantity(c)][:MAX_MEASURES]
    categories = [c for c, t in roles.items() if t == "categorical"][:MAX_CATEGORIES]
    dates = [c for c, t in roles.items() if t == "datetime"]

    if len(df) < MIN_ROWS:
        return {"findings": [], "narrative": "Too few rows to say anything with confidence."}

    # trend: last full month vs mean of the prior months
    for dcol in dates[:1]:
        dt = pd.to_datetime(df[dcol], errors="coerce")
        if dt.notna().sum() < MIN_ROWS:
            continue
        for m in measures[:3]:
            v = pd.to_numeric(df[m], errors="coerce")
            monthly = v.groupby(dt.dt.to_period("M")).sum().dropna()
            if len(monthly) < 4:
                continue
            last, prior = monthly.iloc[-1], monthly.iloc[:-1].mean()
            if prior == 0:
                continue
            change = (last - prior) / abs(prior) * 100
            if abs(change) < 10:
                continue
            direction = "above" if change > 0 else "below"
            findings.append({
                "kind": "trend", "score": min(abs(change) / 100, 1.0),
                "title": f"{col_label(m)} in {monthly.index[-1]} ran {abs(change):.0f}% {direction} its monthly average",
                "detail": f"{_fmt(float(last))} against an average of {_fmt(float(prior))} over the prior {len(monthly) - 1} months.",
                "columns": [m, dcol],
                # The evidence boundary: the numbers as DATA. A consumer must
                # never have to regex a finding's own sentence to draw a badge.
                "figures": {"delta_pct": round(float(change), 2),
                            "value": round(float(last), 4),
                            "direction": "up" if change > 0 else "down"},
            })

    # standout / laggard per category x top measure
    for cat in categories:
        levels = df[cat].astype(str)
        n_levels = levels.nunique()
        if not (2 <= n_levels <= MAX_LEVELS):
            continue
        for m in measures[:2]:
            v = pd.to_numeric(df[m], errors="coerce")
            shares = v.groupby(levels).sum()
            total = shares.sum()
            if total == 0 or shares.isna().any():
                continue
            frac = shares / total
            uniform = 1.0 / n_levels
            top_name, top_frac = frac.idxmax(), float(frac.max())
            if top_frac > uniform * 1.6 and top_frac > 0.3:
                # Is the concentration more than sampling noise? A chi-square
                # goodness-of-fit against an even split answers exactly that,
                # and without it "carries 45%" is a description presented with
                # the confidence of a finding.
                p = _uniformity_p(shares)
                weak = p is not None and p >= SIGNIFICANCE_ALPHA
                detail = (f"{n_levels} values of {cat} would average "
                          f"{uniform * 100:.0f}% each; {top_name} holds "
                          f"{_fmt(float(shares.max()))} of {_fmt(float(total))}.")
                if p is not None:
                    detail += f" p = {p:.3g}."
                if weak:
                    detail += (" The split is not distinguishable from an even "
                               "one at this sample size.")
                findings.append({
                    "kind": "standout",
                    "score": min((top_frac - uniform) * 2, 1.0) * (0.4 if weak else 1.0),
                    "title": f"{val_label(cat, top_name)} carries {top_frac * 100:.0f}% of {col_label(m)}",
                    "detail": detail,
                    "columns": [cat, m],
                    "figures": {"share_pct": round(top_frac * 100, 2),
                                "member": str(top_name),
                                "value": round(float(shares.max()), 4)},
                    "p_value": None if p is None else round(float(p), 6),
                    "significant": None if p is None else (not weak),
                    # The evidence chip (Phase 7.2): which test, over how many rows.
                    "evidence": None if p is None else {
                        "test": "Chi-square vs an even split", "n": int(v.notna().sum()),
                        "effect": f"{top_frac * 100:.0f}% vs {uniform * 100:.0f}% expected"},
                })
            low_name, low_frac = frac.idxmin(), float(frac.min())
            if 0 < low_frac < uniform * 0.45 and n_levels <= 8:
                findings.append({
                    "kind": "laggard", "score": min((uniform - low_frac) * 2, 0.9),
                    "title": f"{val_label(cat, low_name)} trails the other {col_label(cat)} values on {col_label(m)}",
                    "detail": f"{low_frac * 100:.0f}% of {m}, against an even share of {uniform * 100:.0f}%.",
                    "columns": [cat, m],
                    "figures": {"share_pct": round(low_frac * 100, 2),
                                "member": str(low_name)},
                })

    # correlation: strongest pairs
    if len(measures) >= 2:
        nums = df[measures].apply(pd.to_numeric, errors="coerce")
        corr = nums.corr()
        for i, a in enumerate(measures):
            for b in measures[i + 1:]:
                r = corr.loc[a, b]
                if pd.notna(r) and abs(r) >= 0.7:
                    word = "moves with" if r > 0 else "moves against"
                    # An r of 0.7 on 12 rows is not the same claim as an r of
                    # 0.7 on 12,000, and only the p-value separates them. A
                    # finding that fails its test is DEMOTED rather than
                    # dropped: the pattern is real in this data, it is just not
                    # evidence about anything beyond it, and saying so is more
                    # useful than silence.
                    p = _pearson_p(nums[a], nums[b])
                    weak = p is not None and p >= SIGNIFICANCE_ALPHA
                    detail = ("Strong enough that either could stand in for the "
                              "other in a first look.")
                    if p is not None:
                        detail += f" p = {p:.3g}."
                    if weak:
                        detail += (" Not statistically significant, so treat it "
                                   "as a pattern in these rows rather than a "
                                   "reliable relationship.")
                    findings.append({
                        "kind": "correlation",
                        "score": (abs(float(r)) - 0.3) * (0.4 if weak else 1.0),
                        "title": f"{col_label(a)} {word} {col_label(b)} (r = {r:.2f})",
                        "detail": detail,
                        "columns": [a, b],
                        "figures": {"r": round(float(r), 4)},
                        "p_value": None if p is None else round(float(p), 6),
                        "significant": None if p is None else (not weak),
                        "evidence": None if p is None else {
                            "test": "Pearson correlation",
                            "n": int((nums[a].notna() & nums[b].notna()).sum()),
                            "effect": f"r = {r:.2f}"},
                    })

    # outlier impact
    for m in measures:
        v = pd.to_numeric(df[m], errors="coerce").dropna()
        if len(v) < MIN_ROWS:
            continue
        q1, q3 = v.quantile(0.25), v.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        mask = (v < q1 - 1.5 * iqr) | (v > q3 + 1.5 * iqr)
        count = int(mask.sum())
        total = float(v.sum())
        if count == 0 or total == 0:
            continue
        share = float(v[mask].sum()) / total
        if count / len(v) > 0.005 and abs(share) > 0.05:
            findings.append({
                "kind": "outlier_impact", "score": min(abs(share) * 2, 0.95),
                "title": f"{count} outlying rows carry {share * 100:.0f}% of {col_label(m)}",
                "detail": f"{count} of {len(v):,} rows sit beyond the 1.5×IQR fences.",
                "columns": [m],
                "figures": {"share_pct": round(float(share) * 100, 2),
                            "count": int(count)},
            })

    # data quality: missingness and date gaps -- only over columns still in play
    for c in [c for c in df.columns if c in roles]:
        miss = float(df[c].isna().mean())
        if miss > 0.2:
            findings.append({
                "kind": "data_quality", "score": min(miss, 0.85),
                "title": f"{col_label(c)} is {miss * 100:.0f}% missing",
                "detail": "Aggregations over this column silently ignore the gaps.",
                "columns": [c],
                "figures": {"missing_pct": round(float(miss) * 100, 2)},
            })
    for dcol in dates[:1]:
        dt = pd.to_datetime(df[dcol], errors="coerce").dropna().sort_values()
        if len(dt) >= MIN_ROWS:
            gaps = int((dt.diff() > pd.Timedelta(days=14)).sum())
            if gaps > 0:
                findings.append({
                    "kind": "data_quality", "score": 0.4,
                    "figures": {"gap_count": int(gaps)},
                    "title": f"{col_label(dcol)} has {gaps} gap{'s' if gaps != 1 else ''} of more than two weeks",
                    "detail": "Trend lines bridge these gaps as if the time in between never happened.",
                    "columns": [dcol],
                })

    # The engine is itself a MULTIPLE-COMPARISON problem, and shipping it
    # without saying so would be the exact failure the tests warn about: a
    # standout test per (category x measure) and a correlation test per
    # measure-pair is easily twenty tests on one dataset, where roughly one
    # reaches p < 0.05 by chance alone. Correcting here -- across the whole
    # run, before ranking -- is what makes "significant" mean something in a
    # scanned list rather than in a single deliberate test.
    _apply_multiple_comparison_correction(findings)

    findings.sort(key=lambda f: f["score"], reverse=True)
    findings = findings[:12]

    # narrative: the top findings as one paragraph of template prose
    if findings:
        parts = [f["title"] for f in findings[:4]]
        narrative = (f"Across {len(df):,} rows: " + ". ".join(parts) + "."
                     ).replace("..", ".")
    else:
        narrative = f"Across {len(df):,} rows, nothing stands out strongly — shares are even, correlations weak, and the data is clean."
    # row_count rides along so narrate_findings can hand the model the dataset
    # size as EVIDENCE -- without it the digit guard would correctly discard
    # any prose that mentions the row total.
    return {"findings": findings, "narrative": narrative, "row_count": int(len(df))}

# ── LLM narrative: phrasing, never evidence ──────────────────────────────────

def _digit_runs(text: str) -> set[str]:
    import re
    return set(re.findall(r"\d+", text))


#: The narrative is decoration on top of a computed result, so it gets a few
#: seconds, not the LLM client's long default. Without this bound, a DOWN model
#: made every insights request wait out connect timeouts -- measured at ~20s
#: per request in the test run that caught it -- which violates the exact
#: "degrades prose, never availability" contract this feature claims.
NARRATIVE_TIMEOUT_S = 8.0

#: After a failed attempt, skip the model for this long. The 8s ceiling above
#: bounds ONE request; without a memory of the failure, EVERY insights click
#: pays that ceiling for as long as the model is down (measured live: 8.3s per
#: request against a dead endpoint). Per-process and reset by success or
#: restart -- decoration does not deserve shared-state machinery.
NARRATIVE_RETRY_S = 120.0
_narrative_down_until = 0.0


async def narrate_findings(findings: list[dict], row_count: int | None = None) -> str | None:
    """One paragraph of prose over the findings, from the local model -- or None.

    The boundary is the one `agent/nodes/explain.py` already proved: the model
    receives ONLY pre-computed sentences (each finding's title and detail,
    numbers already baked in) and is asked to phrase them. It never sees the
    frame, so it cannot compute anything; the worst it can do is misstate, and
    the digit guard below catches the common form of that.

    Returns None whenever the answer should not be used -- endpoint disabled,
    unreachable, empty reply, or a reply stating a number the evidence does not
    contain -- and the caller keeps the deterministic template narrative. A
    dead model degrades prose quality, never availability, matching llm.py's
    "failure is normal and must not propagate" contract.
    """
    global _narrative_down_until
    if not findings:
        return None
    import time
    if time.monotonic() < _narrative_down_until:
        return None                    # the model failed recently; use the template
    try:
        from .llm import get_client
        client = get_client()
    except Exception:                              # noqa: BLE001
        return None

    lines = [f"- {f.get('title', '')}. {f.get('detail', '')}" for f in findings[:6]]
    if row_count is not None:
        lines.insert(0, f"- The dataset has {row_count} rows.")
    facts = chr(10).join(lines)

    import asyncio

    try:
        got = await asyncio.wait_for(_complete(client, facts),
                                     timeout=NARRATIVE_TIMEOUT_S)
    except Exception:                              # noqa: BLE001 -- includes
        _narrative_down_until = time.monotonic() + NARRATIVE_RETRY_S
        return None                                # asyncio.TimeoutError
    if not got:
        # None is llm.py's "disabled or unreachable" -- remember it. An empty
        # STRING is a model that answered badly, which is not downtime.
        _narrative_down_until = time.monotonic() + NARRATIVE_RETRY_S
        return None
    if not got.strip():
        return None
    text = got.strip()

    # The digit guard: every number in the reply must exist in the evidence.
    # A model that rounds "18%" to "about 20%" or invents a comparison fails
    # here and the template -- which cannot misstate -- is used instead. The
    # guard is deliberately on the OUTPUT, not the prompt: explain.py's
    # round-5 note shows prompts alone do not hold this line.
    if not _digit_runs(text) <= _digit_runs(facts):
        return None
    return text


async def _complete(client, facts: str) -> str | None:
    return await client.complete(
        [{"role": "system", "content": (
            "Weave the findings below into ONE short paragraph of 2-4 "
            "sentences for a business reader. State numbers exactly as "
            "given; do not add any number, comparison, trend or cause that "
            "is not in the findings. Do not speculate about why anything "
            "happened. Plain prose only -- no bullets, no headings.")},
         {"role": "user", "content": "Findings:" + chr(10) + facts}],
        max_tokens=220, temperature=0.2)


async def narrate_one(finding: dict) -> str | None:
    """One guarded sentence for one finding -- the Dynamic Pin card's prose.

    Identical boundary and failure contract to narrate_findings above, and the
    SAME breaker state: a model that just failed a scan narration is not asked
    again for a card. The model receives only the finding's already-computed
    sentence and figures; the digit guard discards any reply stating a number
    the evidence does not contain, and the caller keeps the deterministic
    template line.
    """
    global _narrative_down_until
    if not finding or not finding.get("title"):
        return None
    import time
    if time.monotonic() < _narrative_down_until:
        return None
    try:
        from .llm import get_client
        client = get_client()
    except Exception:                              # noqa: BLE001
        return None

    figures = finding.get("figures") or {}
    facts = (f"- {finding.get('title', '')}. {finding.get('detail', '')}"
             + (f" Figures: {figures}" if figures else ""))

    import asyncio

    async def _one():
        return await client.complete(
            [{"role": "system", "content": (
                "Rewrite the finding below as ONE short sentence for a "
                "business reader. State numbers exactly as given; do not add "
                "any number, comparison, trend or cause that is not in the "
                "finding. No speculation about why. Plain prose, no bullets.")},
             {"role": "user", "content": "Finding:" + chr(10) + facts}],
            max_tokens=80, temperature=0.2)

    try:
        got = await asyncio.wait_for(_one(), timeout=NARRATIVE_TIMEOUT_S)
    except Exception:                              # noqa: BLE001 -- incl. timeout
        _narrative_down_until = time.monotonic() + NARRATIVE_RETRY_S
        return None
    if not got:
        _narrative_down_until = time.monotonic() + NARRATIVE_RETRY_S
        return None
    text = got.strip()
    if not text:
        return None
    if not _digit_runs(text) <= _digit_runs(facts):
        return None
    return text


# ── Novelty: what changed since the last scan ─# ── Novelty: what changed since the last scan ────────────────────────────────

#: A score move smaller than this is refinement, not news. The detectors are
#: deterministic over the same rows, so any drift at all means the DATA moved;
#: the threshold separates "the trend strengthened a little" from "something
#: happened worth pulling up the ranking".
NOVELTY_CHANGED_DELTA = 0.15
#: Ranking boosts. A brand-new finding outranks an equal-scored persistent one
#: -- the reader has seen the persistent one before -- but the boost is small
#: enough that a weak new finding cannot bury a strong standing one.
NOVELTY_NEW_BOOST = 0.15
NOVELTY_CHANGED_BOOST = 0.10


def _finding_identity(f: dict) -> tuple:
    """What makes two findings 'the same finding' across scans.

    Kind plus the columns it is about -- NOT the title, which carries the
    computed numbers and therefore changes whenever the data does. A trend on
    (revenue, date) is the same finding next week even if the percentage in
    its sentence moved.
    """
    return (f.get("kind"), tuple(sorted(f.get("columns") or [])))


def apply_novelty(findings: list[dict], previous: list[dict] | None) -> list[dict]:
    """Annotate findings with what changed since the previous scan, and re-rank.

    Returns a NEW list; the input dicts are copied, not mutated, so the caller
    can persist the raw scan (pre-boost scores) for the next comparison --
    storing boosted scores would compound the boost on every run.

    No previous scan means no annotations at all, deliberately: marking every
    finding "new" on the first run is noise dressed as signal, and the reader
    learns nothing from a page of NEW badges.
    """
    if previous is None:
        return [dict(f) for f in findings]

    prev_by_id = {_finding_identity(p): p for p in previous}
    out: list[dict] = []
    for f in findings:
        g = dict(f)
        prev = prev_by_id.get(_finding_identity(f))
        if prev is None:
            g["novelty"] = "new"
            g["score"] = round(min(float(g.get("score", 0)) + NOVELTY_NEW_BOOST, 1.0), 4)
        elif abs(float(g.get("score", 0)) - float(prev.get("score", 0))) >= NOVELTY_CHANGED_DELTA:
            g["novelty"] = "changed"
            g["score"] = round(min(float(g.get("score", 0)) + NOVELTY_CHANGED_BOOST, 1.0), 4)
        else:
            g["novelty"] = "unchanged"
        out.append(g)
    out.sort(key=lambda f: f["score"], reverse=True)
    return out


# ── Widget suggestions from findings ─────────────────────────────────────────

_FINDING_CHART = {
    # finding kind -> how its columns become a widget
    "trend":          "line",
    "standout":       "bar",
    "laggard":        "bar",
    "correlation":    "scatter",
    # A box plot needs a category the finding does not carry; a histogram
    # shows the outlying tail from the measure alone.
    "outlier_impact": "histogram",
}


def _description_tokens(text: str | None) -> set[str]:
    """Lower-cased word set from the report's name + description. snake_case
    and kebab-case column names match their parts, so a description saying
    "monthly revenue by region" boosts columns `revenue` and `region`."""
    import re
    if not text:
        return set()
    return {w for w in re.split(r"[^a-z0-9]+", text.lower()) if len(w) >= 3}


def _column_matches(column: str, tokens: set[str]) -> bool:
    import re
    parts = [p for p in re.split(r"[^a-z0-9]+", column.lower()) if len(p) >= 3]
    return any(p in tokens for p in parts)


def suggest_widgets_from_findings(findings: list[dict], roles: dict[str, str],
                                  description: str | None = None,
                                  limit: int = 8,
                                  ineligible: set[str] | None = None) -> list[dict]:
    """Rank the engine's findings into one-click widget suggestions.

    Score = the finding's own interest score, plus a boost per column the
    report's name/description mentions -- the description states what the
    report is FOR, so findings about the columns it names come first. Each
    suggestion carries an honest reason: the finding's sentence, plus the
    alignment note when the boost fired.

    `ineligible` names columns the author marked not-to-be-volunteered. They are
    dropped HERE rather than upstream in `generate_insights`, and the difference
    matters: the finding is still computed, still true, and still shown in the
    insights list if the person goes looking. What eligibility withholds is the
    platform putting a chart of it in front of somebody who did not ask -- which
    is a different and much weaker claim than hiding the column.
    """
    tokens = _description_tokens(description)
    blocked = {c.casefold() for c in (ineligible or set())}
    out: list[dict] = []
    seen: set[str] = set()
    for f in findings:
        wt = _FINDING_CHART.get(f.get("kind"))
        if not wt:
            continue  # data_quality flags are prose, not charts
        cols = f.get("columns") or []
        # One ineligible column disqualifies the whole suggestion: a chart is
        # about the relationship between its columns, and dropping one of them
        # would silently propose a different chart from the one the finding
        # justified.
        if blocked and any((c or "").casefold() in blocked for c in cols):
            continue
        cats = [c for c in cols if roles.get(c) == "categorical"]
        nums = [c for c in cols if roles.get(c) == "numeric"]
        dates = [c for c in cols if roles.get(c) == "datetime"]

        # An id column is numeric, so a finding about one would otherwise be
        # charted as a SUM of identity numbers -- a total with no referent.
        # Counting it is the question that column can actually answer ("how many
        # encounters"), so the aggregation is corrected rather than the chart
        # dropped. On a hospital dataset this was three of eight suggestions.
        from .widget_data import _is_id_like_column
        real_nums = [c for c in nums if not _is_id_like_column(c)]
        additive = "count" if (nums and _is_id_like_column(nums[0])) else "sum"

        config: dict | None = None
        if wt == "line" and dates and nums:
            config = {"dimension": dates[0], "measure": nums[0],
                      "aggregation": additive, "dimension_granularity": "month"}
        elif wt == "bar" and cats and nums:
            config = {"dimension": cats[0], "measure": nums[0],
                      "aggregation": additive}
        elif wt == "scatter" and len(real_nums) >= 2:
            nums = real_nums
            # shape_series semantics: dimension is the x numeric, measure the
            # y, averaged per x and sorted along it -- the working scatter
            # shape (x_column/y_column keys exist in no shaper).
            config = {"dimension": nums[0], "measure": nums[1], "aggregation": "avg",
                      "limit": 250, "sort": "asc", "sort_by": "name"}
        elif wt == "histogram" and real_nums:
            # A distribution of identity numbers describes the id sequence, not
            # anything about the data.
            config = {"measure": real_nums[0], "bins": 20}
        if config is None:
            continue

        key = f"{wt}|{sorted(config.items())!r}"
        if key in seen:
            continue
        seen.add(key)

        matched = [c for c in cols if _column_matches(c, tokens)]
        boost = min(len(matched), 2) * 0.5
        reason = f.get("title", "")
        if matched:
            reason += f" — matches {', '.join(matched)} in the report description"
        out.append({
            "widget_type": wt,
            "title": f.get("title", "")[:120],
            "reason": reason,
            "config": config,
            "score": round(float(f.get("score", 0)) + boost, 3),
            "kind": f.get("kind"),
            "aligned": bool(matched),
        })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:limit]
