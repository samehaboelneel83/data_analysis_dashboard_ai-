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

import re

import pandas as pd
from .semantic_guard import (default_summary, direction_of, is_identifier, is_outcome, is_quantity,
                             value_order)

MAX_MEASURES = 6
MAX_CATEGORIES = 6
MAX_LEVELS = 12
MIN_ROWS = 20
#: Outcome columns (late, returned ...) whose rate per group is examined.
MAX_OUTCOMES = 4
#: A group's share of a total must differ from its share of the ROWS by this
#: much before the share is a finding; closer than this it only says the
#: group is big (docs/meaning-map/PLAN.md).
SIZE_MARGIN = 0.05
#: A column label longer than this is a description, not a name for a sentence.
LABEL_MAX = 40
#: Findings of one kind kept in the ranked list, so twelve "outlying rows"
#: lines cannot crowd out everything else. Unlisted kinds: PER_KIND_DEFAULT.
PER_KIND = {"outlier_impact": 2, "data_quality": 3}
PER_KIND_DEFAULT = 4
#: A month's TOTAL that moved within this many points of how the month's ROW
#: COUNT moved is the month's volume: the finding says so and ranks lower.
VOLUME_MARGIN = 10.0
#: A total with more than this share carried by outlying rows has no monthly
#: trend worth reporting: the months differ by which of those rows they hold.
OUTLIER_TOTAL = 0.5
#: ... when those rows are at most this share of all rows.
OUTLIER_FEW = 0.05
#: Months a measure needs before its months are judged against each other.
TIMELINE_MIN_PERIODS = 12
#: A Pareto finding: at most this share of the groups carry this share of the total,
#: in a category with at least this many groups.
PARETO_FEW, PARETO_TARGET, PARETO_MIN_GROUPS = 0.35, 0.8, 6
#: A closing month with under this share of the usual rows is the data's tail.
THIN_MONTH = 0.2
#: A group holding at least this share of a total is the only one that HAS the
#: measure: a fact about the data's structure, not a comparison between groups.
ONLY_ONE_SHARE = 0.99
#: Standout / laggard findings kept about one measure.
PER_MEASURE = 2
#: Rows a group needs before its rate is compared with the others.
RATE_MIN_BASE = 30
#: A rate must be this many percentage points above the overall one to be said.
RATE_MIN_GAP = 0.02


def _month_is_partial(dt: pd.Series, month) -> bool:
    """Whether the data ends partway through `month`."""
    from .relative_dates import cadence_days
    last = dt.max()
    if pd.isna(last):
        return False
    try:
        step = max(float(cadence_days(dt.dropna())), 1.0)
    except Exception:  # noqa: BLE001
        step = 1.0
    return last.normalize() + pd.Timedelta(days=step) < month.end_time.normalize()


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


def is_code_like(value: str) -> bool:
    """A short token that NEEDS a gloss -- 'd001', 'M', '3', 'CS' -- as opposed
    to a value already written in words ('Senior Staff', 'Marketing')."""
    v = str(value).strip()
    if not v or " " in v:
        return False
    if any(ch.isdigit() for ch in v):
        return True                         # d001, 3, A12
    if len(v) == 1:
        return True                         # M, F, Y
    return len(v) <= 4 and v.isupper()      # CS, HR, NYC


#: A group needs this many rows before its average is compared with the rest.
MEAN_STANDOUT_MIN_ROWS = 30


def _mean_standouts(v: pd.Series, levels: pd.Series, cat: str, m: str,
                    col_label, val_label) -> list[dict]:
    """Highest / lowest AVERAGE per category, for an intensive measure.

    "Sales has the highest average salary (88,968 vs 72,012 overall)" is the
    finding a reader wants; "Sales carries 16% of salary" is a head-count."""
    out: list[dict] = []
    frame = pd.DataFrame({"g": levels, "v": v}).dropna()
    if len(frame) < MIN_ROWS:
        return out
    overall = float(frame["v"].mean())
    if overall == 0:
        return out
    stats = frame.groupby("g")["v"].agg(["mean", "count"])
    stats = stats[stats["count"] >= MEAN_STANDOUT_MIN_ROWS]
    if len(stats) < 2:
        return out
    hi_name, hi = stats["mean"].idxmax(), float(stats["mean"].max())
    lo_name, lo = stats["mean"].idxmin(), float(stats["mean"].min())
    p = None
    try:
        from scipy import stats as st
        groups = [g["v"].to_numpy() for _, g in frame.groupby("g") if len(g) >= MEAN_STANDOUT_MIN_ROWS]
        if len(groups) >= 2:
            p = float(st.f_oneway(*groups).pvalue)
    except Exception:                               # noqa: BLE001
        p = None
    weak = p is not None and p >= SIGNIFICANCE_ALPHA
    if hi / overall >= 1.1:
        out.append({
            "kind": "standout",
            "score": min((hi / overall - 1) * 2, 1.0) * (0.4 if weak else 1.0),
            "title": f"{val_label(cat, hi_name)} has the highest average {col_label(m)}",
            "detail": (f"{_fmt(hi)} against {_fmt(overall)} overall, across "
                       f"{int(stats.loc[hi_name, 'count']):,} rows."
                       + (f" p = {p:.3g}." if p is not None else "")),
            "columns": [cat, m],
            "figures": {"mean": round(hi, 4), "overall_mean": round(overall, 4),
                        "member": str(hi_name), "ratio": round(hi / overall, 4)},
            "p_value": None if p is None else round(p, 6),
            "significant": None if p is None else (not weak),
            "evidence": None if p is None else {
                "test": "One-way ANOVA across groups", "n": int(len(frame)),
                "effect": f"{hi / overall:.2f}× the overall average"},
        })
    if lo / overall <= 0.9:
        out.append({
            "kind": "laggard",
            "score": min((1 - lo / overall) * 2, 0.9) * (0.4 if weak else 1.0),
            "title": f"{val_label(cat, lo_name)} has the lowest average {col_label(m)}",
            "detail": (f"{_fmt(lo)} against {_fmt(overall)} overall, across "
                       f"{int(stats.loc[lo_name, 'count']):,} rows."),
            "columns": [cat, m],
            "figures": {"mean": round(lo, 4), "overall_mean": round(overall, 4),
                        "member": str(lo_name), "ratio": round(lo / overall, 4)},
        })
    return out


#: Below this many rows the detectors run one after another: a thread pool
#: costs more than it saves on a small frame.
PARALLEL_SCAN_MIN_ROWS = 200_000


def drop_duplicate_measures(df, measures: list[str], sample: int = 20_000) -> list[str]:
    """The measures, without any that copy an earlier one.

    A calculated "price (copy)" headed the Olist panel's patterns as "price
    moves with price (copy)" (2026-10-02): a column against its own copy is
    r = 1 and says nothing. A measure is dropped when it correlates at 0.999 or
    more with one already kept (a rescaled copy -- cents for pounds -- too)."""
    if len(measures) < 2:
        return list(measures)
    frame = df[measures].apply(pd.to_numeric, errors="coerce")
    if len(frame) > sample:
        frame = frame.sample(sample, random_state=0)
    # Only continuous measures can be copies: two two-valued columns that line
    # up are r = 1 by construction and are different things.
    def continuous(c):
        return frame[c].nunique() >= 10 and frame[c].std() != 0
    kept: list[str] = []
    for m in measures:
        if continuous(m) and any(continuous(k) and abs(frame[m].corr(frame[k])) >= 0.999 for k in kept):
            continue
        kept.append(m)
    return kept


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
        """What to call a column in a sentence a person reads. A LABEL, not a
        description: "carries 44% of The numeric cost of the delivery service
        in Egyptian Pounds." is a sentence inside a sentence -- a long or
        full-stopped label is a description, and the column's own name reads
        better."""
        label = str(names.get(column) or "").strip()
        if label and len(label) <= LABEL_MAX and not label.endswith(".") and len(label.split()) <= 6:
            return label
        return column

    def val_label(column: str, value) -> str:
        """What a coded value MEANS, when the catalog recorded it -- and only
        for a CODE. A value that is already words ("Senior Staff") keeps its
        own words: the catalog's generated gloss turned it into "Senior
        staff-level engineering role" in a headline (HR evaluation)."""
        raw = str(value)
        if not is_code_like(raw):
            return raw
        return (vmaps.get(column) or {}).get(raw, raw)

    def group_label(column: str, value) -> str:
        """A group named in a headline. "15800 has the highest average score"
        names nothing: a value that is only a number is given its column."""
        label = val_label(column, value)
        try:
            float(str(label).replace(",", ""))
        except ValueError:
            return label
        return f"{col_label(column)} {label}"

    roles = effective_roles(type_map, column_meta)
    # The semantic veto: a numeric latitude, id or year is not a quantity, and
    # a "trend in latitude" or "year moves with revenue" is a finding about
    # nothing (services/semantic_guard.py).
    # The column's STORED classification is read first (column_meta: number,
    # level, order, direction, outcome -- services/column_classes.py); its
    # name is the fallback for a column nobody classified.
    measures = drop_duplicate_measures(
        df, [c for c, t in roles.items() if t == "numeric" and is_quantity(c, column_meta)
             # A true/false column is not a quantity, whatever its type was
             # read as: it is an outcome, and the rate detector measures it.
             and not (c in df.columns and pd.api.types.is_bool_dtype(df[c]))])[:MAX_MEASURES]
    categories = [c for c, t in roles.items() if t == "categorical"][:MAX_CATEGORIES]
    # Columns that say what became of a row (late, returned, resolved): never
    # a breakdown here -- they are what the rate detector measures.
    outcomes = [c for c in df.columns if c in roles and is_outcome(c, column_meta)][:MAX_OUTCOMES]
    # The date a record HAPPENED on leads: the trend detector reads the first.
    # Olist's first date column was the estimated delivery -- a promise that runs
    # past the data, so "freight in 2018-09 ran 44% below its monthly average"
    # was the orders not yet placed (five-dataset review, 2026-10-02).
    dates = order_event_dates([c for c, t in roles.items() if t == "datetime"], df)

    if len(df) < MIN_ROWS:
        return {"findings": [], "narrative": "Too few rows to say anything with confidence."}

    # trend: last full month vs mean of the prior months
    # How each measure rolls up when nobody said (semantic_guard.default_summary):
    # a salary or a price is AVERAGED, an amount is summed. Every detector below
    # asks this instead of assuming a sum (HR evaluation, blocker 5).
    summary = {m: default_summary(m, column_meta) for m in measures}
    intensive = {m for m, s_ in summary.items() if s_ in ("avg", "median")}

    def m_words(m: str) -> str:
        return f"average {col_label(m)}" if m in intensive else col_label(m)

    # 5.21: the five detector families read the same frame and write nothing
    # but their own findings, so they run side by side on a large frame
    # (pandas releases the GIL in its heavy kernels). Each fills its OWN list
    # and the lists are joined in a fixed order, so the result -- and the
    # stable sort below -- is identical to running them one after another.
    def _trends(findings: list) -> None:
        for dcol in dates[:1]:
            dt = pd.to_datetime(df[dcol], errors="coerce")
            if dt.notna().sum() < MIN_ROWS:
                continue
            for m in measures[:3]:
                v = pd.to_numeric(df[m], errors="coerce")
                grouped = v.groupby(dt.dt.to_period("M"))
                # A total -- or an average -- that a few extreme rows make up is
                # those rows' calendar: "area ran 100% below its average" in a
                # month that simply had none of the 159 rows carrying 96% of it.
                if _outlier_share(v) > OUTLIER_TOTAL:
                    continue
                if m in intensive:
                    # An average over a handful of rows is noise, not a month: a
                    # month with too few rows behind it is not compared.
                    counts = grouped.count()
                    monthly = grouped.mean().dropna()
                    floor = max(10, int(counts.median() * 0.2)) if len(counts) else 10
                    monthly = monthly[counts.reindex(monthly.index).fillna(0) >= floor]
                else:
                    monthly = grouped.sum().dropna()
                volume = grouped.count().reindex(monthly.index)
                # The LAST FULL month. A month the data stops partway through is
                # not a drop: a call log ending on 19 Sep "ran 96% below its monthly
                # average" in September (live QA 2026-09-28). Partial means the
                # data's own cadence would have put another date inside it.
                if len(monthly) and _month_is_partial(dt, monthly.index[-1]):
                    monthly = monthly.iloc[:-1]
                # A THIN last month is not a month either: a listing table with
                # a handful of rows dated ahead "ran 100% below its average"
                # (apartments, 2026-10-10). Months at the end holding under a
                # fifth of the usual rows are the data's tail, not its trend.
                while len(monthly) > 4:
                    vols = volume.reindex(monthly.index)
                    usual = float(vols.iloc[:-1].median())
                    if usual and float(vols.iloc[-1]) < THIN_MONTH * usual:
                        monthly = monthly.iloc[:-1]
                    else:
                        break
                if len(monthly) < 4:
                    continue
                last, prior = monthly.iloc[-1], monthly.iloc[:-1].mean()
                if prior == 0:
                    continue
                change = (last - prior) / abs(prior) * 100
                if abs(change) < 10:
                    continue
                # THE SIZE CHECK, over time. A total that rose 30% in a month
                # with 30% more rows is still news -- the business grew -- but
                # it is news about the VOLUME, not about each row. The finding
                # is kept, says so, and ranks below one where the measure
                # itself moved. (Dropping it lost "revenue up last month".)
                volume_note, volume_change = "", None
                if m not in intensive:
                    vol = volume.reindex(monthly.index)
                    v_prior = float(vol.iloc[:-1].mean()) if len(vol) > 1 else 0.0
                    if v_prior:
                        volume_change = (float(vol.iloc[-1]) - v_prior) / abs(v_prior) * 100
                        if abs(volume_change) >= 10 and abs(change - volume_change) < VOLUME_MARGIN:
                            volume_note = (f" The number of rows moved the same way ({volume_change:+.0f}%),"
                                           " so this is the month's volume rather than a change per row.")
                direction = "above" if change > 0 else "below"
                findings.append({
                    "kind": "trend", "score": min(abs(change) / 100, 1.0) * (0.6 if volume_note else 1.0),
                    "title": f"{m_words(m)[:1].upper() + m_words(m)[1:]} in {monthly.index[-1]} ran {abs(change):.0f}% {direction} its monthly average",
                    "detail": f"{_fmt(float(last))} against an average of {_fmt(float(prior))} over the prior {len(monthly) - 1} months.{volume_note}",
                    "columns": [m, dcol],
                    # The evidence boundary: the numbers as DATA. A consumer must
                    # never have to regex a finding's own sentence to draw a badge.
                    "figures": {"delta_pct": round(float(change), 2),
                                "value": round(float(last), 4),
                                "direction": "up" if change > 0 else "down",
                                **({"volume_pct": round(volume_change, 2), "follows_volume": bool(volume_note)}
                                   if volume_change is not None else {})},
                })

    def _standouts(findings: list) -> None:
        # standout / laggard per category x top measure
        for cat in categories:
            levels = df[cat].astype(str)
            n_levels = levels.nunique()
            if not (2 <= n_levels <= MAX_LEVELS):
                continue
            for m in measures[:2]:
                v = pd.to_numeric(df[m], errors="coerce")
                if m in intensive:
                    findings.extend(_mean_standouts(v, levels, cat, m, col_label, group_label))
                    continue
                shares = v.groupby(levels).sum()
                total = shares.sum()
                if total == 0 or shares.isna().any():
                    continue
                frac = shares / total
                uniform = 1.0 / n_levels
                top_name, top_frac = frac.idxmax(), float(frac.max())
                # THE SIZE CHECK. "Cairo carries 45% of fees" when Cairo has 45%
                # of the rows says Cairo is big, not that Cairo stands out: a
                # big group has more of everything. A share is a finding only
                # when it departs from the group's share of the ROWS; when it
                # does not, what CAN stand out is the amount per row.
                of_rows = levels[v.notna()].value_counts(normalize=True)
                follows_size = abs(top_frac - float(of_rows.get(top_name, 0.0))) < SIZE_MARGIN
                if follows_size:
                    per_row = _mean_standouts(v, levels, cat, m, col_label, group_label)
                    for f in per_row:
                        f["title"] = f["title"].replace(" average ", " ") + " per row"
                        f["figures"]["per_row"] = True
                    findings.extend(per_row)
                    continue
                if top_frac > uniform * 1.6 and top_frac > 0.3:
                    # Is the concentration more than sampling noise? A chi-square
                    # goodness-of-fit against an even split answers exactly that,
                    # and without it "carries 45%" is a description presented with
                    # the confidence of a finding.
                    p = _uniformity_p(shares)
                    weak = p is not None and p >= SIGNIFICANCE_ALPHA
                    detail = (f"{n_levels} values of {cat} would average "
                              f"{uniform * 100:.0f}% each; {top_name} holds "
                              f"{_fmt(float(shares.max()))} of {_fmt(float(total))}"
                              f" with {float(of_rows.get(top_name, 0.0)) * 100:.0f}% of the rows.")
                    if p is not None:
                        detail += f" p = {p:.3g}."
                    if weak:
                        detail += (" The split is not distinguishable from an even "
                                   "one at this sample size.")
                    findings.append({
                        "kind": "standout",
                        "score": min((top_frac - uniform) * 2, 1.0) * (0.4 if weak else 1.0)
                                 * (0.3 if top_frac >= ONLY_ONE_SHARE else 1.0),
                        "title": (f"Almost all {col_label(m)} is in {group_label(cat, top_name)}"
                                  if top_frac >= ONLY_ONE_SHARE else
                                  f"{group_label(cat, top_name)} carries {top_frac * 100:.0f}% of {col_label(m)}"),
                        "detail": detail,
                        "columns": [cat, m],
                        "figures": {"share_pct": round(top_frac * 100, 2),
                                    "member": str(top_name),
                                    "value": round(float(shares.max()), 4),
                                    "rows_share_pct": round(float(of_rows.get(top_name, 0.0)) * 100, 2)},
                        "p_value": None if p is None else round(float(p), 6),
                        "significant": None if p is None else (not weak),
                        # The evidence chip (Phase 7.2): which test, over how many rows.
                        "evidence": None if p is None else {
                            "test": "Chi-square vs an even split", "n": int(v.notna().sum()),
                            "effect": f"{top_frac * 100:.0f}% vs {uniform * 100:.0f}% expected"},
                    })
                low_name, low_frac = frac.idxmin(), float(frac.min())
                # A small group trails on everything; that is its size again.
                low_follows = abs(low_frac - float(of_rows.get(low_name, 0.0))) < SIZE_MARGIN
                if 0 < low_frac < uniform * 0.45 and n_levels <= 8 and not low_follows:
                    findings.append({
                        "kind": "laggard", "score": min((uniform - low_frac) * 2, 0.9),
                        "title": f"{val_label(cat, low_name)} trails the other {col_label(cat)} values on {col_label(m)}",
                        "detail": f"{low_frac * 100:.0f}% of {m}, against an even share of {uniform * 100:.0f}%.",
                        "columns": [cat, m],
                        "figures": {"share_pct": round(low_frac * 100, 2),
                                    "member": str(low_name)},
                    })

    def _correlations(findings: list) -> None:
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

    def _outliers(findings: list) -> None:
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
            # A total of gains and losses cancels itself: "85 rows carry -36%
            # of profit" (demo sales). Such a column is read through its average.
            mixed_sign = bool(len(v)) and float(v.min()) < 0 < float(v.max())
            if m in intensive or mixed_sign:
                # "Outliers carry 9% of salary" is a share of a meaningless total.
                # What they do to an average is the question a reader has.
                if count == 0 or count / len(v) <= 0.005:
                    continue
                mean_all, mean_in = float(v.mean()), float(v[~mask].mean())
                if mean_in == 0:
                    continue
                shift = (mean_all - mean_in) / abs(mean_in)
                if abs(shift) > 0.02:
                    findings.append({
                        "kind": "outlier_impact", "score": min(abs(shift) * 4, 0.9),
                        "title": f"{count} outlying rows move the average {col_label(m)} by {abs(shift) * 100:.0f}%",
                        "detail": (f"Average {_fmt(mean_all)} with them, {_fmt(mean_in)} without; "
                                   f"{count} of {len(v):,} rows sit beyond the 1.5×IQR fences."),
                        "columns": [m],
                        "figures": {"shift_pct": round(shift * 100, 2), "count": int(count)},
                    })
                continue
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

    def _quality(findings: list) -> None:
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

    def _rates(findings: list) -> None:
        # The share of rows with an OUTCOME (late, returned, resolved) per group,
        # against the share overall. This is the question a count cannot
        # answer -- "which branch has a problem" -- because it is read against
        # each group's own size. Groups too small to carry a rate are left out.
        for oc in outcomes:
            col = df[oc]
            known = col.notna()
            if int(known.sum()) < MIN_ROWS:
                continue
            values = col[known]
            if set(values.unique().tolist()[:3]) <= {True, False}:
                targets = [True]
            else:
                # A status of several values: its minority outcomes, the common one
                # being "nothing happened".
                counts = values.astype(str).value_counts(normalize=True)
                targets = [k for k, share in counts.items() if 0.01 <= share <= 0.5][:2]
            for target in targets:
                hit = (values == target) if target is True else (values.astype(str) == target)
                overall = float(hit.mean())
                if not 0 < overall < 1:
                    continue
                what = col_label(oc) if target is True else f"{col_label(oc)}: {val_label(oc, target)}"
                for cat in categories:
                    if cat == oc:
                        continue
                    levels = df.loc[known, cat].astype(str)
                    if not (2 <= levels.nunique() <= MAX_LEVELS):
                        continue
                    stats = hit.groupby(levels).agg(["mean", "count", "sum"])
                    stats = stats[stats["count"] >= RATE_MIN_BASE]
                    if len(stats) < 2:
                        continue
                    hi_name, hi = stats["mean"].idxmax(), float(stats["mean"].max())
                    lo = float(stats["mean"].min())
                    if hi - overall < RATE_MIN_GAP or hi / overall < 1.15:
                        continue
                    p = None
                    try:
                        from scipy import stats as st
                        table = [[float(r["sum"]), float(r["count"] - r["sum"])] for _, r in stats.iterrows()]
                        p = float(st.chi2_contingency(table)[1])
                    except Exception:                       # noqa: BLE001
                        p = None
                    weak = p is not None and p >= SIGNIFICANCE_ALPHA
                    findings.append({
                        "kind": "rate",
                        "score": min((hi / overall - 1) * 1.2, 1.0) * (0.4 if weak else 1.0),
                        "title": (f"{group_label(cat, hi_name)} has the highest share of {what}: "
                                  f"{hi * 100:.1f}% against {overall * 100:.1f}% overall"),
                        "detail": (f"{int(stats.loc[hi_name, 'sum']):,} of {int(stats.loc[hi_name, 'count']):,} rows; "
                                   f"the lowest {col_label(cat)} is at {lo * 100:.1f}%. Groups under "
                                   f"{RATE_MIN_BASE} rows are left out."
                                   + (f" p = {p:.3g}." if p is not None else "")),
                        "columns": [cat, oc],
                        "figures": {"rate_pct": round(hi * 100, 2), "overall_pct": round(overall * 100, 2),
                                    "lowest_pct": round(lo * 100, 2), "member": str(hi_name),
                                    "outcome": None if target is True else str(target),
                                    "rows": int(stats.loc[hi_name, "count"])},
                        "p_value": None if p is None else round(p, 6),
                        "significant": None if p is None else (not weak),
                        "evidence": None if p is None else {
                            "test": "Chi-square across groups", "n": int(known.sum()),
                            "effect": f"{hi * 100:.1f}% vs {overall * 100:.1f}% overall"},
                    })

    def _gradients(findings: list) -> None:
        # A measure that rises or falls steadily across an ORDERED category
        # (Low -> Medium -> High; age bands): visible only when the order is
        # known, which is why it is stored with the column.
        for cat in categories:
            order = value_order(cat, column_meta)
            if not order or len(order) < 3:
                continue
            rank = {v: i for i, v in enumerate(order)}
            levels = df[cat].astype(str)
            for m in measures[:3]:
                v = pd.to_numeric(df[m], errors="coerce")
                stats = v.groupby(levels).agg(["mean", "count"])
                stats = stats[(stats["count"] >= MEAN_STANDOUT_MIN_ROWS) & stats.index.isin(list(rank))]
                if len(stats) < 3:
                    continue
                stats = stats.loc[sorted(stats.index, key=lambda k: rank[k])]
                means = stats["mean"].tolist()
                steps = [b - a for a, b in zip(means, means[1:])]
                if not (all(s_ > 0 for s_ in steps) or all(s_ < 0 for s_ in steps)):
                    continue
                first, last = means[0], means[-1]
                if first == 0 or abs(last - first) / abs(first) < 0.1:
                    continue
                word = "rises" if last > first else "falls"
                findings.append({
                    "kind": "gradient",
                    "score": min(abs(last - first) / abs(first), 1.0) * 0.9,
                    "title": (f"Average {col_label(m)} {word} with every step of {col_label(cat)}: "
                              f"{_fmt(first)} at {val_label(cat, stats.index[0])}, "
                              f"{_fmt(last)} at {val_label(cat, stats.index[-1])}"),
                    "detail": " → ".join(f"{val_label(cat, k)} {_fmt(x)}" for k, x in zip(stats.index, means)) + ".",
                    "columns": [cat, m],
                    "figures": {"first": round(float(first), 4), "last": round(float(last), 4),
                                "direction": "up" if last > first else "down", "steps": len(means),
                                "order": [str(k) for k in stats.index]},
                })

    def _timeline(findings: list) -> None:
        # A MONTH OUTSIDE ITS USUAL RANGE, and the place a LEVEL CHANGED --
        # read from each measure's own months (services/analysis/timeline.py).
        # The trend detector above compares the last month with the average
        # of the rest; these look at every month against the months before it.
        from .analysis import timeline
        for dcol in dates[:1]:
            dt = pd.to_datetime(df[dcol], errors="coerce")
            if dt.notna().sum() < MIN_ROWS:
                continue
            for m in measures[:3]:
                v = pd.to_numeric(df[m], errors="coerce")
                if _outlier_share(v) > OUTLIER_TOTAL:
                    continue
                grouped = v.groupby(dt.dt.to_period("M"))
                counts = grouped.count()
                monthly = (grouped.mean() if m in intensive else grouped.sum()).dropna()
                # Months with too few rows behind them are not months to judge,
                # and the month the data stops inside is not finished.
                floor = max(3, int(counts.median() * THIN_MONTH)) if len(counts) else 3
                monthly = monthly[counts.reindex(monthly.index).fillna(0) >= floor]
                if len(monthly) and _month_is_partial(dt, monthly.index[-1]):
                    monthly = monthly.iloc[:-1]
                if len(monthly) < TIMELINE_MIN_PERIODS:
                    continue
                values = [float(x) for x in monthly.values]
                what = m_words(m)
                band = timeline.expected_band(values, timeline.season_of("month", len(values)))
                out = timeline.anomalies(values, band)
                if out:
                    a = max(out, key=lambda x: x["deviations"])
                    findings.append({
                        "kind": "anomaly", "score": min(0.4 + a["deviations"] / 20, 0.95),
                        "title": (f"{what[:1].upper() + what[1:]} in {monthly.index[a['index']]} was far "
                                  f"{a['side']} its usual range"),
                        "detail": (f"{_fmt(a['value'])} against an expected {_fmt(a['lo'])} to {_fmt(a['hi'])}, "
                                   f"judged from the months before it."
                                   + (f" {len(out) - 1} other month{'s' if len(out) > 2 else ''} also fell outside."
                                      if len(out) > 1 else "")),
                        "columns": [m, dcol],
                        "figures": {"period": str(monthly.index[a["index"]]), "value": round(a["value"], 4),
                                    "lo": round(a["lo"], 4), "hi": round(a["hi"], 4), "side": a["side"],
                                    "outside": len(out)},
                    })
                cp = timeline.change_point(values)
                if cp:
                    findings.append({
                        "kind": "change_point", "score": min(0.4 + abs(cp["shift_pct"]) / 100, 0.9),
                        "title": (f"{what[:1].upper() + what[1:]} has run {abs(cp['shift_pct']):.0f}% "
                                  f"{'higher' if cp['shift'] > 0 else 'lower'} since {monthly.index[cp['index']]}"),
                        "detail": (f"About {_fmt(cp['before'])} a month before, {_fmt(cp['after'])} from then on. "
                                   "The change is in the level, not in one month."),
                        "columns": [m, dcol], "p_value": cp["p_value"], "significant": True,
                        "figures": {"period": str(monthly.index[cp["index"]]), "before": round(cp["before"], 4),
                                    "after": round(cp["after"], 4), "shift_pct": round(cp["shift_pct"], 2)},
                    })

    def _pareto(findings: list) -> None:
        # A FEW GROUPS CARRY MOST OF A TOTAL: "3 of 14 carry 80%". Only for a
        # number that adds up, a category with enough groups for "few" to
        # mean something, and a total of one sign (a share of gains and
        # losses is not a share).
        for cat in categories:
            levels = df[cat].astype(str)
            n_levels = levels.nunique()
            if not (PARETO_MIN_GROUPS <= n_levels <= MAX_LEVELS):
                continue
            for m in measures[:2]:
                if m in intensive:
                    continue
                totals = pd.to_numeric(df[m], errors="coerce").groupby(levels).sum().sort_values(ascending=False)
                whole = float(totals.sum())
                if whole <= 0 or (totals < 0).any():
                    continue
                running = totals.cumsum() / whole
                few = int((running >= PARETO_TARGET).values.argmax()) + 1
                # ONE group carrying it all is the standout finding, already
                # said ("X carries 93%"); "few" starts at two.
                if few < 2 or few / n_levels > PARETO_FEW:
                    continue
                names = [val_label(cat, v) for v in totals.index[:3]]
                findings.append({
                    "kind": "pareto",
                    "score": min(0.35 + (PARETO_FEW - few / n_levels) / PARETO_FEW * 0.55, 0.9),
                    "title": (f"{few} of {n_levels} {col_label(cat)} values carry "
                              f"{running.iloc[few - 1] * 100:.0f}% of {col_label(m)}"),
                    "detail": (f"Largest first: {', '.join(str(x) for x in names)}"
                               + ("..." if few > 3 else "") + f". The other {n_levels - few} share the rest."),
                    "columns": [cat, m],
                    "figures": {"groups": few, "of": int(n_levels),
                                "share_pct": round(float(running.iloc[few - 1]) * 100, 2)},
                })

    _detectors = (_trends, _standouts, _correlations, _outliers, _quality, _rates, _gradients, _pareto, _timeline)
    _outs: list[list] = [[] for _ in _detectors]
    if len(df) >= PARALLEL_SCAN_MIN_ROWS:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(_detectors)) as pool:
            for fut in [pool.submit(fn, out) for fn, out in zip(_detectors, _outs)]:
                fut.result()
    else:
        for fn, out in zip(_detectors, _outs):
            fn(out)
    for out in _outs:
        findings.extend(out)

    # The engine is itself a MULTIPLE-COMPARISON problem, and shipping it
    # without saying so would be the exact failure the tests warn about: a
    # standout test per (category x measure) and a correlation test per
    # measure-pair is easily twenty tests on one dataset, where roughly one
    # reaches p < 0.05 by chance alone. Correcting here -- across the whole
    # run, before ranking -- is what makes "significant" mean something in a
    # scanned list rather than in a single deliberate test.
    _apply_multiple_comparison_correction(findings)

    # Which way is good: "the highest average rating" is good news and "the
    # highest average delay" is not. Carried as data (`tone`), so no reader
    # has to guess it from the words -- and only where the column's
    # classification says which way it points.
    for f in findings:
        way = next((direction_of(c, column_meta) for c in f.get("columns") or []
                    if direction_of(c, column_meta) != "neither"), None)
        if not way:
            continue
        high = f.get("kind") == "standout" or (f.get("kind") in ("trend", "gradient")
                                               and (f.get("figures") or {}).get("direction") == "up")
        low = f.get("kind") == "laggard" or (f.get("kind") in ("trend", "gradient")
                                             and (f.get("figures") or {}).get("direction") == "down")
        if high or low:
            f["tone"] = "good" if (high and way == "higher_better") or (low and way == "higher_worse") else "bad"

    findings.sort(key=lambda f: f["score"], reverse=True)
    # A ranked list that is five "outlying rows" lines says one thing five
    # times: each kind keeps its strongest few, and the places go to the rest.
    kept, per_kind, per_measure = [], {}, {}
    for f in findings:
        k = f.get("kind")
        if per_kind.get(k, 0) >= PER_KIND.get(k, PER_KIND_DEFAULT):
            continue
        if k in ("standout", "laggard") and len(f.get("columns") or []) > 1:
            key = (k, f["columns"][-1])
            if per_measure.get(key, 0) >= PER_MEASURE:
                continue
            per_measure[key] = per_measure.get(key, 0) + 1
        per_kind[k] = per_kind.get(k, 0) + 1
        kept.append(f)
    findings = kept[:12]

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
    "correlation":    "numeric_series",
    # A box plot needs a category the finding does not carry; a histogram
    # shows the outlying tail from the measure alone.
    "outlier_impact": "histogram",
    # The share of an outcome per group: each group's bar split into "with"
    # and "without", every bar the same height -- the rate is what the eye reads.
    "rate":           "bar",
    # An ordered category, in its order.
    "gradient":       "bar",
    # a line that is READ: its usual range and what fell outside; where its level changed
    "anomaly":        "line",
    "change_point":   "line",
    # the groups from the largest down, with the running share of the whole
    "pareto":         "dual_axis_bar_line",
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


#: Below this the basics say nothing a table would not -- and the engine's own
#: "too few rows" answer is the honest one.
BASELINE_MIN_ROWS = 20

#: Words for WHEN A RECORD BEGAN and for dates that are something else, in
#: the neutral vocabulary of any record (see services/semantic_guard.py): no
#: industry's events (a hire, a purchase, a delivery). Where the rows are in
#: hand the VALUES decide (order_event_dates): the date that is filled in for
#: every row and comes first is when the record began.
_START_DATE = ("start", "created", "opened", "open", "begin", "date")
#: Dates that are not when a record began. "order_estimated_delivery_date"
#: carries "order" and was the Olist panel's time axis -- a promise date,
#: running into the future (2026-10-02).
_NOT_START_DATE = ("to_date", "end", "birth", "dob", "close", "expire", "until", "updated", "modified",
                   "estimated", "expected", "due", "deadline", "limit")


def order_event_dates(dates: list[str], df: pd.DataFrame | None = None) -> list[str]:
    """Date columns with the ones a record starts on first, promise and end
    dates (estimated, due, closed) last. Nothing is dropped.

    With the rows (`df`) the VALUES order the columns no name marks: a date
    every row has, and that falls before the others, is when the record began;
    one that is often empty or falls later is something that happened to it
    afterwards. That holds for an order, an admission, a ticket or a contract
    without knowing which of them the table is."""
    seen: dict[str, tuple] = {}
    if df is not None:
        for c in dates:
            try:
                dt = pd.to_datetime(df[c], errors="coerce")
                filled = float(dt.notna().mean())
                mid = dt.dropna().astype("int64").median() if filled else float("inf")
                # To the nearest percent: a finish date empty for 1% of rows
                # (the ones still open) is not the date every row has, and its
                # median -- over finished rows only -- runs early.
                seen[c] = (round(1 - filled, 2), mid)
            except Exception:                                   # noqa: BLE001
                continue

    def rank(c: str) -> tuple:
        named = _rank_by_name(c)
        return (named[0], *seen.get(c, (0, 0)), named[1]) if seen else named
    return sorted(dates, key=rank)


def _rank_by_name(c: str) -> tuple:
    low = str(c).lower()
    if any(k in low for k in _NOT_START_DATE):
        return 2, 0
    # Among the rest, a column NAMED a date before a time of day (FULL_DATE
    # before CALL_TIME).
    return (0 if any(k in low for k in _START_DATE[:-1]) else 1), (0 if "date" in low else 1)


def _h(col: str) -> str:
    return " ".join(str(col).replace("_", " ").split())


def _outlier_share(v: pd.Series) -> float:
    """The share of a column's total carried by a FEW rows beyond the
    1.5 x IQR fences; 0 when there is no spread, no total, or the rows beyond
    the fences are many (a long tail is how sales look, and its total still
    has a trend)."""
    # As plain numbers: a yes/no column that reaches here has no quantiles
    # to subtract (found by the discovery tests, 2026-10-11).
    v = pd.to_numeric(v, errors="coerce").dropna().astype(float)
    if len(v) < 8:
        return 0.0
    q1, q3 = v.quantile(0.25), v.quantile(0.75)
    iqr, total = q3 - q1, float(v.abs().sum())
    if iqr == 0 or total == 0:
        return 0.0
    mask = (v < q1 - 1.5 * iqr) | (v > q3 + 1.5 * iqr)
    if not mask.any() or mask.mean() > OUTLIER_FEW:
        return 0.0
    return float(v[mask].abs().sum()) / total


_ID_TAIL = re.compile(r"[\s_]*(?:id|key|uuid|no|number|code)$", re.I)
#: The same word where Arabic puts it: in front ("رقم الشحنة").
_ID_HEAD = re.compile(r"^(?:رقم|كود|معرف|مسلسل)[\s_]+")


def counted_as(id_col: str) -> str:
    """What to call a count of an identifier column. "Number of shipment id"
    counts shipments: the identifier's own word is dropped and the thing it
    numbers is named ("Shipment count"). A column that is ONLY an identifier
    word (`id`, `uuid`) or has no such tail keeps the plain form."""
    name = _h(id_col)
    stem = _ID_TAIL.sub("", name).strip()
    if stem and stem != name:
        return f"{stem[:1].upper()}{stem[1:]} count"
    stem = _ID_HEAD.sub("", name).strip()
    if stem and stem != name:
        return f"عدد {stem}"
    return f"Number of {name}"


def baseline_suggestions(df: pd.DataFrame | None, roles: dict[str, str],
                         column_meta: dict | None = None,
                         ineligible: set[str] | None = None) -> list[dict]:
    """The charts anyone would draw first, whether or not anything stands out.

    HR evaluation (item 3, re-test 2026-10-01): suggestions were built ONLY from
    "what stands out" findings, so a workforce dataset was offered three
    average-salary charts and never a headcount by department or hires per
    year -- the two questions every HR reader opens with. These four come from
    the shape of the data, not from a finding:

    1. how many of the main entity per main category (headcount by dept),
    2. how many per year of the main start date (hires per year),
    3. the main measure, summarised its own way, by a small category (avg
       salary by gender),
    4. the distribution of that measure.

    Nothing here reads a value into a title: titles are built from column
    names, so they cannot leak a row the reader is not allowed to see.
    """
    if df is None or len(df) < BASELINE_MIN_ROWS:
        return []
    blocked = {c.casefold() for c in (ineligible or set())}
    cols = [c for c in df.columns if c in roles and str(c).casefold() not in blocked]
    from .widget_data import _is_id_like_column

    def nunique(c):
        try:
            return int(df[c].nunique(dropna=True))
        except Exception:                                   # noqa: BLE001
            return 0

    ids = [c for c in cols if (is_identifier(c, column_meta) or _is_id_like_column(c, column_meta))
           and nunique(c) >= 0.5 * len(df)]
    id_col = ids[0] if ids else None
    # A column that says what became of a row (late, returned) is measured as a
    # share per group -- the rate findings draw that; "total weight by is_late"
    # is not a first chart anyone asks for.
    cats = [c for c in cols if roles.get(c) == "categorical" and c not in ids
            and not is_outcome(c, column_meta)]
    card = {c: nunique(c) for c in cats}
    main_cats = sorted([c for c in cats if 3 <= card[c] <= 30], key=lambda c: -card[c])
    small_cats = sorted([c for c in cats if 2 <= card[c] <= 6], key=lambda c: card[c])
    nums = [c for c in cols if roles.get(c) == "numeric" and c not in ids
            and not _is_id_like_column(c, column_meta) and not is_identifier(c, column_meta)]
    dates = order_event_dates([c for c in cols if roles.get(c) == "datetime"
                               and not any(k in str(c).lower() for k in _NOT_START_DATE)], df)

    if id_col:
        count_word = counted_as(id_col)
    else:
        count_word = "Rows"

    def count_measure(fallback: str) -> tuple[str, str]:
        return (id_col, "countd") if id_col else (fallback, "count")

    out: list[dict] = []

    def add(wt: str, title: str, reason: str, config: dict, score: float) -> None:
        out.append({"widget_type": wt, "title": title[:120], "reason": reason,
                    "config": config, "score": score, "kind": "baseline",
                    "aligned": False, "keep_granularity": "dimension_granularity" in config})

    if main_cats:
        dim = main_cats[0]
        meas, agg = count_measure(dim)
        add("bar", f"{count_word} by {_h(dim)}",
            f"How the {len(df):,} rows split across {_h(dim)} -- the first thing most readers ask.",
            {"dimension": dim, "measure": meas, "aggregation": agg,
             "sort": "desc", "sort_by": "value"}, 10.0)
    if dates:
        d = dates[0]
        meas, agg = count_measure(d)
        try:
            dt = pd.to_datetime(df[d], errors="coerce")
            span_days = (dt.max() - dt.min()).days
        except Exception:                                   # noqa: BLE001
            span_days = 0
        if span_days >= 2 * 365:
            title = f"{count_word} per year of {_h(d)}"
            config = {"dimension": d, "measure": meas, "aggregation": agg,
                      "dimension_granularity": "year"}
        else:
            # A short span is bucketed by whoever knows it (polish_widget):
            # a year bucket over four months is one bar.
            title = f"{count_word} over {_h(d)}"
            config = {"dimension": d, "measure": meas, "aggregation": agg}
        add("line", title, f"How many rows fall in each period of {_h(d)}.", config, 9.5)
    if nums:
        m = nums[0]
        summ = default_summary(m, column_meta)
        summ = summ if summ in ("avg", "median", "sum") else "avg"
        word = {"avg": "Average", "median": "Median", "sum": "Total"}[summ]
        by = next((c for c in small_cats), None) or (main_cats[0] if main_cats else None)
        if by:
            add("bar", f"{word} {_h(m)} by {_h(by)}",
                f"{word} {_h(m)} for each {_h(by)}.",
                {"dimension": by, "measure": m, "aggregation": summ}, 9.0)
        add("histogram", f"Distribution of {_h(m)}",
            f"How {_h(m)} is spread across the rows.", {"measure": m, "bins": 20}, 8.5)
    return out


def suggest_widgets_from_findings(findings: list[dict], roles: dict[str, str],
                                  description: str | None = None,
                                  limit: int = 12,
                                  ineligible: set[str] | None = None,
                                  column_meta: dict | None = None,
                                  frame: pd.DataFrame | None = None,
                                  per_type: int = 2) -> list[dict]:
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
        real_nums = [c for c in nums if not _is_id_like_column(c, column_meta)]
        # A salary or a price is averaged, never summed (default_summary).
        if nums and (_is_id_like_column(nums[0], column_meta) or is_identifier(nums[0], column_meta)):
            additive = "count"
        elif nums:
            summ = default_summary(nums[0], column_meta)
            additive = summ if summ in ("avg", "median", "sum") else "sum"
        else:
            additive = "sum"

        config: dict | None = None
        if f.get("kind") == "rate" and len(cols) >= 2:
            # columns = [group, outcome]; counted, never summed.
            config = {"dimension": cols[0], "dimension2": cols[1], "measure": cols[0],
                      "aggregation": "count", "bar_mode": "stacked100"}
        elif f.get("kind") == "pareto" and cats and nums:
            # `measure2` names the same column: this chart type takes two
            # measures, and a Pareto's second series is the first one's
            # running share (widget_data.shape_dual_series).
            config = {"dimension": cats[0], "measure": nums[0], "measure2": nums[0], "aggregation": "sum",
                      "pareto": True, "y2_axis_label": "Cumulative share (%)"}
        elif f.get("kind") == "gradient" and cats and nums:
            config = {"dimension": cats[0], "measure": nums[0], "aggregation": "avg", "sort_by": "order",
                      "category_order": list((f.get("figures") or {}).get("order") or [])}
        elif wt == "line" and dates and nums:
            config = {"dimension": dates[0], "measure": nums[0],
                      "aggregation": additive, "dimension_granularity": "month"}
            if f.get("kind") == "anomaly":
                config["anomaly_band"] = True
            elif f.get("kind") == "change_point":
                config["change_point"] = True
        elif wt == "bar" and cats and nums:
            config = {"dimension": cats[0], "measure": nums[0],
                      "aggregation": additive}
        elif wt == "numeric_series" and len(real_nums) >= 2:
            # Two measures row by row. The category scatter (x as a dimension,
            # y averaged per x value) read as a ranking -- "322 is highest at
            # 8,455" -- for a correlation finding (daily-ops panel, 2026-10-02).
            config = {"measure": real_nums[0], "measure2": real_nums[1]}
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
    if frame is not None:
        from .suggest_variety import diversify, draws, variety_suggestions

        # A finding that asks for the same chart as a basic is the same chart,
        # so it is not repeated. dimension2 is part of the identity: a mix of
        # title by department is not the headcount by department.
        def _key(x):
            c = x["config"]
            return (f"{x['widget_type']}|{c.get('dimension')}|{c.get('dimension2')}|"
                    f"{c.get('measure')}|{c.get('aggregation')}")
        # Same chart twice: the finding's version wins -- its sentence states
        # the numbers, a basic's only names the columns.
        found = {_key(x) for x in out}
        base = [b for b in baseline_suggestions(frame, roles, column_meta, ineligible)
                if _key(b) not in found]
        found |= {_key(b) for b in base}
        # Charts chosen by the SHAPE of the data -- a mix, a spread, a bubble,
        # a share -- so the panel is not four kinds of bar (HR re-test
        # 2026-10-02). See services/suggest_variety.py.
        variety = [v for v in variety_suggestions(frame, roles, column_meta, ineligible)
                   if _key(v) not in found]
        # A finding that matches what the dashboard says it is FOR still
        # leads: the description outranks the generic basics.
        aligned = [x for x in out if x.get("aligned")]
        others = [x for x in out if not x.get("aligned")]
        # Findings rank among the shape-driven ideas by their own strength
        # (0..1 above 8.6: between a mix chart and a share). Ranking only --
        # each keeps its own score, which auto-compose sizes widgets by.
        def _rank(x):
            return 8.6 + min(float(x.get("score") or 0), 1.0) if x in others else float(x["score"])
        ranked = aligned + sorted(base + variety + others, key=_rank, reverse=True)
        # Offered only if it draws on this reader's rows: a blank tile in the
        # panel is worse than one idea fewer. The rules widget was built from
        # rules just mined, so it is not mined a second time.
        # Whether a chart has anything to draw does not need every row: the
        # check runs on a fixed 20,000-row sample (the numbers in the
        # suggestions themselves were computed on the whole frame).
        probe = frame if len(frame) <= 20_000 else frame.sample(20_000, random_state=0)
        # A measure recorded in different units per group is never totalled
        # across the groups (fact_sheet.mixed_units).
        from .analyst_panel import mixes_units, one_unit
        from .fact_sheet import mixed_units
        from .suggest_variety import _Profile
        prof = _Profile(frame, roles, column_meta, ineligible)
        mixed = mixed_units(probe, prof.nums, prof.cats, prof.card)
        ranked = [one_unit(x, mixed) for x in ranked]
        ranked = [x for x in ranked
                  if not mixes_units(x, mixed)
                  and (x.get("kind") == "rules" or draws(x["widget_type"], x["config"], probe))]
        chosen = diversify(ranked, limit, per_type=per_type)
        # What each one SHOWS, read from its result on every row (the probe
        # sample only had to prove it draws). The rules widget's reason
        # already states its mined numbers.
        from .readback import as_i18n, takeaway
        from .widget_data import get_widget_data_from_df
        # The common gate (services/suggest_gate.py): drawn is not enough. A
        # suggestion whose chart says nothing -- one bar, the same value in
        # every group, a headline of zero -- is not offered, the same rule the
        # dashboard designers and the guided setup apply.
        from .suggest_gate import says_nothing
        _dates = {c for c, t in roles.items() if t == "datetime"}
        kept = []
        for x in chosen:
            if x.get("kind") == "rules":
                kept.append(x)
                continue
            try:
                drawn = get_widget_data_from_df(frame, dict(x["config"]), x["widget_type"])
            except Exception:                                # noqa: BLE001
                drawn = None
            nothing = says_nothing(x, drawn, _dates) if drawn is not None else None
            # The basics ("how many per department") are the first thing a
            # reader asks even when the split is even: they are dropped only
            # when there is nothing, or one group, to show.
            counted = str((x.get("config") or {}).get("aggregation") or "").startswith("count")
            if nothing and (not (x.get("kind") == "baseline" and counted) or nothing in (
                    "it has nothing to show", "it has only one group to show")):
                continue
            kept.append(x)
            if x.get("kind") == "correlation":
                # The title carries r measured on EVERY row. The chart draws a
                # sample of points, and a sentence read off it restated the
                # same pair with another r ("r = 0.70" over "r = 0.27, 500
                # rows", Nile Express 2026-10-10): one number per claim.
                continue
            try:
                said = takeaway(x["widget_type"], x["config"], drawn) if drawn is not None else None
            except Exception:                                # noqa: BLE001 -- a sentence is optional
                said = None
            if said:
                x["takeaway"] = str(said)
                # The same sentence as a key and its pieces: the browser says
                # it in the reader's language (readback.Said).
                x["takeaway_i18n"] = as_i18n(said)
        return kept
    return out[:limit]
