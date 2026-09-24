"""Inferential statistics: is the difference real, or is it noise?

The eight analyses that came before this one are descriptive, forecasting,
clustering or anomaly detection. Every one of them can tell you THAT two groups
differ; none can tell you whether that difference would survive another sample.
This module adds the four tests a business analyst actually reaches for.

scipy and statsmodels were already in the image -- they shipped for the
forecasting and profiling code -- so nothing new is downloaded and the
air-gapped guarantee is untouched. That is the whole cost argument: this exposes
what was already paid for rather than buying SAS-scale breadth.

THE WAY THIS ANALYSIS LIES, AND THE RULE THAT STOPS IT
------------------------------------------------------
With an import cap of two million rows, a p-value is nearly worthless on its
own: at n=100,000 a difference of 0.1% between group means is "highly
significant" and completely irrelevant. Reporting p alone would let this feature
manufacture confident nonsense at scale.

So every test here returns an EFFECT SIZE beside its p-value -- Cohen's d, eta
squared, Cramer's V, r -- and every result carries a plain-language
`interpretation` that names both. A caller that shows only the asterisk is
choosing to; the payload never encourages it.

The second guard is a floor: below `MIN_ROWS_PER_GROUP` a test is REFUSED
rather than computed, because a p-value from five rows is not a weak answer, it
is a meaningless one. Same stance as `influencers.MIN_ROWS`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

#: Below this many usable rows in a group, refuse rather than compute. A test on
#: a handful of rows produces a number with no inferential content, and a number
#: is exactly what a reader will act on.
MIN_ROWS_PER_GROUP = 10

#: Comparing dozens of groups turns "is any pair different?" into a fishing
#: expedition, and the omnibus p stops meaning what its reader thinks.
MAX_GROUPS = 20

#: Sampling ceiling. Above this the tests are run on a reproducible sample: the
#: point estimate barely moves and the p-value is already saturated, so paying
#: for the whole frame buys nothing but latency.
SAMPLE_ABOVE = 200_000
SAMPLE_SEED = 0

#: Conventional threshold, stated once here so every interpretation agrees. It
#: is a convention, not a law of nature, and the `interpretation` text says so.
ALPHA = 0.05


class StatisticalError(ValueError):
    """A refusal a user should read: too few rows, wrong column type, too many
    groups. Distinct from a bug, and surfaced as a 400 rather than a 500."""


@dataclass
class TestResult:
    kind: str
    statistic: float
    p_value: float
    effect_size: float
    effect_name: str
    effect_label: str          # negligible | small | medium | large
    significant: bool
    n: int
    detail: dict[str, Any] = field(default_factory=dict)
    interpretation: str = ""
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "statistic": _round(self.statistic),
            "p_value": _round(self.p_value, 6),
            "effect_size": _round(self.effect_size),
            "effect_name": self.effect_name,
            "effect_label": self.effect_label,
            "significant": self.significant,
            "alpha": ALPHA,
            "n": self.n,
            "detail": self.detail,
            "interpretation": self.interpretation,
            "caveats": self.caveats,
        }


def _round(v, places: int = 4):
    """NaN and infinity are not JSON, and a silent null loses the distinction
    between 'not computed' and 'computed as nothing'."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, places)


def _numeric(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        raise StatisticalError(f"Column not found: {col}")
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if s.empty:
        raise StatisticalError(f"Column '{col}' has no numeric values")
    return s


def _sampled(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """Deterministic sample above the ceiling. Seeded so the same question asked
    twice gives the same answer -- a test whose p-value flickers between runs
    would be worse than no test."""
    if len(df) <= SAMPLE_ABOVE:
        return df, False
    return df.sample(SAMPLE_ABOVE, random_state=SAMPLE_SEED), True


def _label(value: float, small: float, medium: float, large: float) -> str:
    v = abs(value)
    if v < small:
        return "negligible"
    if v < medium:
        return "small"
    if v < large:
        return "medium"
    return "large"


def _p_text(p: float) -> str:
    """'p = 0.0312', or 'p < 0.001' -- a reader gains nothing from 1.6e-250."""
    return "p < 0.001" if p < 0.001 else f"p = {p:.4g}"


def _verdict(p: float, effect_label: str, what: str) -> str:
    """One sentence naming BOTH numbers, because either alone misleads.

    A significant result with a negligible effect is the failure mode this text
    exists to prevent: at large n it is the normal outcome, and a reader who
    sees only 'p < 0.05' will act on nothing.
    """
    if p >= ALPHA:
        return (f"No statistically significant {what} ({_p_text(p)}). "
                f"The data does not support a difference; it does not prove "
                f"there is none.")
    if effect_label == "negligible":
        return (f"Statistically significant ({_p_text(p)}) but the effect is "
                f"negligible. With this many rows almost any difference reaches "
                f"significance, so this one is unlikely to matter in practice.")
    return (f"Statistically significant {what} ({_p_text(p)}), with a "
            f"{effect_label} effect.")


# ── 1. Compare groups ────────────────────────────────────────────────────────

def compare_groups(df: pd.DataFrame, value_col: str, group_col: str) -> TestResult:
    """Is a measure different across groups?

    Two groups -> Welch's t-test. Three or more -> one-way ANOVA.

    WELCH, NOT STUDENT, and this is a deliberate default rather than an option.
    Student's t-test assumes the groups share a variance, which real business
    data almost never does (a large region and a small one differ in spread as
    well as level). Welch does not assume it, costs almost nothing when the
    assumption happens to hold, and does not silently produce an overconfident
    p-value when it does not. Offering `equal_var=True` as a toggle would be
    offering a foot-gun.
    """
    from scipy import stats

    # BOTH columns checked, not just the grouping one: a missing value column
    # otherwise surfaces as a raw pandas KeyError, which reaches the user as a
    # 500 instead of a sentence telling them which column is wrong.
    for c in (group_col, value_col):
        if c not in df.columns:
            raise StatisticalError(f"Column not found: {c}")
    frame, sampled = _sampled(df)
    work = frame[[group_col, value_col]].copy()
    work[value_col] = pd.to_numeric(work[value_col], errors="coerce")
    work = work.dropna()

    groups = [(str(name), g[value_col].to_numpy())
              for name, g in work.groupby(group_col, sort=False)]
    groups = [(n, v) for n, v in groups if len(v) >= MIN_ROWS_PER_GROUP]

    if len(groups) < 2:
        raise StatisticalError(
            f"Need at least two groups with {MIN_ROWS_PER_GROUP}+ rows each; "
            f"found {len(groups)}")
    if len(groups) > MAX_GROUPS:
        raise StatisticalError(
            f"{len(groups)} groups is too many for one comparison (limit "
            f"{MAX_GROUPS}) -- the combined test stops answering a useful question")

    n = int(sum(len(v) for _, v in groups))
    caveats = []
    if sampled:
        caveats.append(f"Computed on a {SAMPLE_ABOVE:,}-row sample of a larger dataset")

    summary = [{"group": name, "n": int(len(v)), "mean": _round(float(np.mean(v))),
                "std": _round(float(np.std(v, ddof=1)) if len(v) > 1 else 0.0)}
               for name, v in groups]

    if len(groups) == 2:
        (n1, a), (n2, b) = groups
        stat, p = stats.ttest_ind(a, b, equal_var=False)   # Welch
        # Cohen's d on the pooled SD.
        s1, s2 = np.std(a, ddof=1), np.std(b, ddof=1)
        na, nb = len(a), len(b)
        pooled = math.sqrt(((na - 1) * s1 ** 2 + (nb - 1) * s2 ** 2) / max(na + nb - 2, 1))
        d = (np.mean(a) - np.mean(b)) / pooled if pooled else 0.0
        label = _label(d, 0.2, 0.5, 0.8)
        return TestResult(
            kind="compare_groups", statistic=float(stat), p_value=float(p),
            effect_size=float(d), effect_name="cohens_d", effect_label=label,
            significant=bool(p < ALPHA), n=n,
            detail={"test": "Welch's t-test", "groups": summary,
                    "difference": _round(float(np.mean(a) - np.mean(b)))},
            interpretation=_verdict(float(p), label,
                                    f"difference in {value_col} between {n1} and {n2}"),
            caveats=caveats + [
                "Welch's t-test is used, which does not assume equal variances"],
        )

    arrays = [v for _, v in groups]
    stat, p = stats.f_oneway(*arrays)
    # eta squared: between-group sum of squares over total.
    grand = np.mean(np.concatenate(arrays))
    ss_between = sum(len(v) * (np.mean(v) - grand) ** 2 for v in arrays)
    ss_total = sum(float(((v - grand) ** 2).sum()) for v in arrays)
    eta2 = float(ss_between / ss_total) if ss_total else 0.0
    label = _label(eta2, 0.01, 0.06, 0.14)
    return TestResult(
        kind="compare_groups", statistic=float(stat), p_value=float(p),
        effect_size=eta2, effect_name="eta_squared", effect_label=label,
        significant=bool(p < ALPHA), n=n,
        detail={"test": "One-way ANOVA", "groups": summary,
                "group_count": len(groups)},
        interpretation=_verdict(float(p), label,
                                f"difference in {value_col} across {group_col}"),
        caveats=caveats + [
            "ANOVA reports that SOME group differs, not which -- compare pairs "
            "individually to find out which"],
    )


# ── 2. Test of independence ──────────────────────────────────────────────────

def test_independence(df: pd.DataFrame, col_a: str, col_b: str) -> TestResult:
    """Are two categorical columns related, or independent?

    Chi-square on the contingency table, with Cramer's V as the effect size.
    `analytics.py` already computed this statistic inside profiling; here it is
    a first-class answer with its validity conditions checked rather than a
    number embedded in a summary.
    """
    from scipy.stats import chi2_contingency

    for c in (col_a, col_b):
        if c not in df.columns:
            raise StatisticalError(f"Column not found: {c}")
    frame, sampled = _sampled(df)
    work = frame[[col_a, col_b]].dropna()
    if len(work) < MIN_ROWS_PER_GROUP:
        raise StatisticalError(
            f"Only {len(work)} complete rows; need at least {MIN_ROWS_PER_GROUP}")

    table = pd.crosstab(work[col_a], work[col_b])
    if table.shape[0] < 2 or table.shape[1] < 2:
        raise StatisticalError(
            "Both columns need at least two distinct values to be tested")
    if table.shape[0] > MAX_GROUPS or table.shape[1] > MAX_GROUPS:
        raise StatisticalError(
            f"Too many categories ({table.shape[0]}x{table.shape[1]}); limit is "
            f"{MAX_GROUPS} per column")

    chi2, p, dof, expected = chi2_contingency(table)
    n = int(table.to_numpy().sum())
    min_dim = min(table.shape) - 1
    cramers_v = math.sqrt(chi2 / (n * min_dim)) if n and min_dim else 0.0
    label = _label(cramers_v, 0.1, 0.3, 0.5)

    caveats = []
    if sampled:
        caveats.append(f"Computed on a {SAMPLE_ABOVE:,}-row sample of a larger dataset")
    # The textbook validity condition. Stated rather than silently ignored:
    # chi-square's approximation degrades badly on sparse tables.
    small_cells = int((expected < 5).sum())
    if small_cells:
        caveats.append(
            f"{small_cells} cell(s) have an expected count below 5, where the "
            f"chi-square approximation is unreliable -- treat this p-value as "
            f"indicative only")

    return TestResult(
        kind="independence", statistic=float(chi2), p_value=float(p),
        effect_size=float(cramers_v), effect_name="cramers_v", effect_label=label,
        significant=bool(p < ALPHA), n=n,
        detail={"test": "Chi-square test of independence",
                "dof": int(dof), "shape": list(table.shape),
                "table": table.to_dict()},
        interpretation=_verdict(float(p), label,
                                f"association between {col_a} and {col_b}"),
        caveats=caveats,
    )


# ── 3. Correlation with significance ─────────────────────────────────────────

def correlation_test(df: pd.DataFrame, col_a: str, col_b: str,
                     method: str = "pearson") -> TestResult:
    """Do two measures move together, and is the relationship distinguishable
    from noise?

    The existing correlation surfaces report r alone. An r of 0.3 on 20 rows and
    an r of 0.3 on 20,000 are very different claims, and only the p-value
    separates them.
    """
    from scipy import stats

    if method not in ("pearson", "spearman"):
        raise StatisticalError("method must be 'pearson' or 'spearman'")
    for c in (col_a, col_b):
        if c not in df.columns:
            raise StatisticalError(f"Column not found: {c}")

    frame, sampled = _sampled(df)
    work = frame[[col_a, col_b]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(work) < MIN_ROWS_PER_GROUP:
        raise StatisticalError(
            f"Only {len(work)} rows with both values; need at least "
            f"{MIN_ROWS_PER_GROUP}")

    a, b = work[col_a].to_numpy(), work[col_b].to_numpy()
    if np.std(a) == 0 or np.std(b) == 0:
        raise StatisticalError(
            "One of the columns is constant, so no correlation is defined")

    fn = stats.pearsonr if method == "pearson" else stats.spearmanr
    res = fn(a, b)
    r, p = float(res[0]), float(res[1])
    label = _label(r, 0.1, 0.3, 0.5)
    caveats = ["Correlation is not causation: a third factor may drive both"]
    if sampled:
        caveats.append(f"Computed on a {SAMPLE_ABOVE:,}-row sample of a larger dataset")
    if method == "pearson":
        caveats.append("Pearson measures LINEAR association only; a curved "
                       "relationship can show r near zero")

    return TestResult(
        kind="correlation_test", statistic=r, p_value=p,
        effect_size=abs(r), effect_name="r", effect_label=label,
        significant=bool(p < ALPHA), n=int(len(work)),
        detail={"test": f"{method.capitalize()} correlation",
                "r": _round(r), "direction": "positive" if r > 0 else "negative",
                "r_squared": _round(r * r)},
        interpretation=_verdict(p, label, f"relationship between {col_a} and {col_b}"),
        caveats=caveats,
    )


# ── 4. Linear regression ─────────────────────────────────────────────────────

def regression(df: pd.DataFrame, target: str, predictors: list[str]) -> TestResult:
    """Ordinary least squares: how much does each predictor move the target?

    This is the one analysis here that FITS A MODEL rather than testing a
    hypothesis about the data as it stands, so it carries the heaviest caveats.
    Its output is a coefficient table -- estimate, standard error, t, p and a
    confidence interval per predictor -- because that is the form every
    statistics package prints and every analyst can audit by hand.
    """
    import statsmodels.api as sm

    if target not in df.columns:
        raise StatisticalError(f"Column not found: {target}")
    predictors = [p for p in (predictors or []) if p != target]
    if not predictors:
        raise StatisticalError("At least one predictor column is required")
    missing = [p for p in predictors if p not in df.columns]
    if missing:
        raise StatisticalError(f"Column not found: {missing[0]}")

    frame, sampled = _sampled(df)
    work = frame[[target] + predictors].apply(pd.to_numeric, errors="coerce").dropna()
    # A regression needs more rows than parameters to be identifiable at all,
    # and materially more to be trustworthy.
    need = max(MIN_ROWS_PER_GROUP, len(predictors) * 5)
    if len(work) < need:
        raise StatisticalError(
            f"Only {len(work)} complete numeric rows; need at least {need} for "
            f"{len(predictors)} predictor(s)")

    y = work[target]
    X = sm.add_constant(work[predictors], has_constant="add")
    model = sm.OLS(y, X).fit()

    conf = model.conf_int()
    coefficients = []
    for name in X.columns:
        coefficients.append({
            "term": name,
            "coefficient": _round(float(model.params[name])),
            "std_error": _round(float(model.bse[name])),
            "t": _round(float(model.tvalues[name])),
            "p_value": _round(float(model.pvalues[name]), 6),
            "ci_low": _round(float(conf.loc[name, 0])),
            "ci_high": _round(float(conf.loc[name, 1])),
            "significant": bool(model.pvalues[name] < ALPHA),
        })

    r2 = float(model.rsquared)
    label = _label(r2, 0.02, 0.13, 0.26)
    caveats = [
        "OLS assumes a linear relationship, independent observations and "
        "roughly constant error variance; none of these is checked here",
        "Coefficients describe association within this data, not causation",
    ]
    if sampled:
        caveats.append(f"Computed on a {SAMPLE_ABOVE:,}-row sample of a larger dataset")
    if len(predictors) > 1:
        caveats.append("With correlated predictors, individual coefficients can "
                       "be unstable even when the model as a whole fits well")

    p_model = float(model.f_pvalue) if model.f_pvalue is not None else float("nan")
    return TestResult(
        kind="regression", statistic=float(model.fvalue), p_value=p_model,
        effect_size=r2, effect_name="r_squared", effect_label=label,
        significant=bool(p_model < ALPHA), n=int(len(work)),
        detail={"test": "Ordinary least squares",
                "target": target, "coefficients": coefficients,
                "r_squared": _round(r2),
                "adj_r_squared": _round(float(model.rsquared_adj))},
        interpretation=(
            f"The model explains {r2 * 100:.1f}% of the variation in {target} "
            f"({_verdict(p_model, label, 'overall fit').lower()}"
            f")" if not math.isnan(p_model) else
            f"The model explains {r2 * 100:.1f}% of the variation in {target}."),
        caveats=caveats,
    )


# ── 5. Generalized linear models ─────────────────────────────────────────────

#: Cox and logistic power comes from EVENTS, not rows: 10,000 subjects with 3
#: churns carries the information of 3 observations. Ten events per predictor
#: is the usual rule of thumb.
MIN_EVENTS_PER_PREDICTOR = 10


def glm_logistic(df: pd.DataFrame, target: str, predictors: list[str],
                 target_value: str | None = None) -> TestResult:
    """Logistic regression: which factors move the odds of a binary outcome?

    OLS is simply wrong for a yes/no target -- it can predict probabilities
    below 0 and above 1, and its standard errors are meaningless there. This is
    the model that belongs to the question.

    ODDS RATIOS, not raw coefficients, are the headline. A log-odds of 0.34
    means nothing to the person asking "does the discount reduce churn"; an odds
    ratio of 1.4 means "40% higher odds", which is a sentence they can act on.
    The raw coefficient is returned beside it for anyone who wants it.
    """
    import statsmodels.api as sm

    if target not in df.columns:
        raise StatisticalError(f"Column not found: {target}")
    predictors = [p for p in (predictors or []) if p != target]
    if not predictors:
        raise StatisticalError("At least one predictor column is required")
    missing = [p for p in predictors if p not in df.columns]
    if missing:
        raise StatisticalError(f"Column not found: {missing[0]}")

    frame, sampled = _sampled(df)
    work = frame[[target] + predictors].dropna()
    work[predictors] = work[predictors].apply(pd.to_numeric, errors="coerce")
    work = work.dropna()

    uniques = list(pd.Series(work[target]).unique())
    if len(uniques) < 2:
        raise StatisticalError(
            f"'{target}' has only one value, so there is no outcome to model")
    if len(uniques) > 2 and target_value is None:
        raise StatisticalError(
            f"'{target}' has {len(uniques)} distinct values; logistic "
            f"regression needs a binary outcome. Pass target_value to model one "
            f"value against the rest.")

    if target_value is not None:
        positive = str(target_value)
        y = (work[target].astype(str) == positive).astype(int)
    else:
        # The RARER value is the event: "what drives churn" is asked far more
        # often than "what drives staying" -- the same reasoning
        # key_influencers uses to choose its default outcome.
        counts = work[target].astype(str).value_counts()
        positive = str(counts.index[-1])
        y = (work[target].astype(str) == positive).astype(int)

    events = int(y.sum())
    need = max(MIN_ROWS_PER_GROUP, len(predictors) * MIN_EVENTS_PER_PREDICTOR)
    if events < need or (len(y) - events) < MIN_ROWS_PER_GROUP:
        raise StatisticalError(
            f"Only {events} '{positive}' outcome(s) among {len(y)} rows; need at "
            f"least {need} of each outcome for {len(predictors)} predictor(s)")

    X = sm.add_constant(work[predictors], has_constant="add")
    try:
        model = sm.GLM(y, X, family=sm.families.Binomial()).fit()
    except Exception as e:  # noqa: BLE001
        raise StatisticalError(f"The model could not be fitted: {e}")

    # Perfect separation makes statsmodels return enormous coefficients with
    # enormous standard errors rather than raising. Passing that through would
    # be emitting garbage with a p-value attached to it.
    if not np.all(np.isfinite(model.bse)) or float(np.max(np.abs(model.params))) > 50:
        raise StatisticalError(
            "The model did not converge -- usually a predictor separates the "
            "outcome perfectly (it predicts it exactly). Remove that predictor "
            "and try again.")

    conf = model.conf_int()
    coefficients = []
    for name in X.columns:
        coefficients.append({
            "term": name,
            "coefficient": _round(float(model.params[name])),
            "odds_ratio": _round(float(np.exp(model.params[name]))),
            "or_ci_low": _round(float(np.exp(conf.loc[name, 0]))),
            "or_ci_high": _round(float(np.exp(conf.loc[name, 1]))),
            "std_error": _round(float(model.bse[name])),
            "p_value": _round(float(model.pvalues[name]), 6),
            "significant": bool(model.pvalues[name] < ALPHA),
        })

    # McFadden pseudo-R^2, NAMED as pseudo: a reader who takes it for an OLS
    # R-squared will badly underrate the model -- 0.2 is a good fit here.
    null = sm.GLM(y, np.ones((len(y), 1)), family=sm.families.Binomial()).fit()
    pseudo_r2 = float(1 - (model.llf / null.llf)) if null.llf else 0.0
    label = _label(pseudo_r2, 0.05, 0.15, 0.3)

    caveats = [
        f"Modelling the odds of '{positive}' against all other values",
        "McFadden pseudo-R squared is not comparable to an OLS R squared: 0.2 "
        "already indicates a good fit",
        "Association within this data, not causation",
    ]
    if sampled:
        caveats.append(f"Computed on a {SAMPLE_ABOVE:,}-row sample of a larger dataset")

    movers = [c for c in coefficients[1:] if c["significant"]]
    return TestResult(
        kind="glm_logistic", statistic=float(model.llf), p_value=float("nan"),
        effect_size=pseudo_r2, effect_name="mcfadden_pseudo_r2",
        effect_label=label, significant=bool(movers), n=int(len(work)),
        detail={"test": "Logistic regression (GLM, binomial)",
                "target": target, "positive_outcome": positive,
                "events": events, "non_events": int(len(y) - events),
                "coefficients": coefficients,
                "pseudo_r_squared": _round(pseudo_r2)},
        interpretation=(
            f"Modelling the odds of '{positive}'. "
            + (", ".join(f"{c['term']} multiplies the odds by {c['odds_ratio']}"
                         for c in movers)
               or "No predictor reaches significance.")),
        caveats=caveats,
    )


# ── 6. Mixed-effects model ───────────────────────────────────────────────────

def mixed_model(df: pd.DataFrame, target: str, predictors: list[str],
                group_col: str) -> TestResult:
    """A random-intercept model: repeated measurements within a group.

    ORDINARY REGRESSION IS WRONG when rows are not independent. Twelve months
    from each of forty stores is 480 rows but nothing like 480 independent
    observations, and OLS treats them as if they were: the standard errors come
    out too small and everything looks significant. This model gives each group
    its own intercept, so comparisons happen WITHIN groups.

    Random intercepts only for a first version, deliberately: random slopes need
    more data per group than most business datasets carry, and they fail to
    converge in ways that are hard to explain to a non-statistician.

    The effect size is the INTRACLASS CORRELATION -- the share of variation
    between groups rather than within them. It answers the question that
    motivates the model: does the grouping matter at all?
    """
    import statsmodels.api as sm

    for c in [target, group_col]:
        if c not in df.columns:
            raise StatisticalError(f"Column not found: {c}")
    predictors = [p for p in (predictors or []) if p not in (target, group_col)]
    if not predictors:
        raise StatisticalError("At least one predictor column is required")
    missing = [p for p in predictors if p not in df.columns]
    if missing:
        raise StatisticalError(f"Column not found: {missing[0]}")

    frame, sampled = _sampled(df)
    work = frame[[target, group_col] + predictors].dropna()
    work[[target] + predictors] = work[[target] + predictors].apply(
        pd.to_numeric, errors="coerce")
    work = work.dropna()

    n_groups = int(work[group_col].nunique())
    if n_groups < 3:
        raise StatisticalError(
            f"Only {n_groups} group(s) in '{group_col}'; a mixed model needs at "
            f"least 3 to estimate between-group variation")
    per_group = len(work) / max(n_groups, 1)
    if per_group < 2:
        raise StatisticalError(
            "Groups average fewer than 2 rows each, so there are no repeated "
            "measurements to model -- ordinary regression is the right tool here")

    try:
        model = sm.MixedLM(
            work[target],
            sm.add_constant(work[predictors], has_constant="add"),
            groups=work[group_col]).fit()
    except Exception as e:  # noqa: BLE001
        raise StatisticalError(f"The model could not be fitted: {e}")

    # Refused rather than reported with a buried warning: a non-converged fit
    # produces numbers that look exactly like estimates and are not.
    if not getattr(model, "converged", True):
        raise StatisticalError(
            "The model did not converge -- try fewer predictors, or a grouping "
            "with more rows per group")

    conf = model.conf_int()
    coefficients = []
    for name in model.params.index:
        if str(name).endswith("Var"):
            continue
        coefficients.append({
            "term": str(name),
            "coefficient": _round(float(model.params[name])),
            "std_error": _round(float(model.bse[name])),
            "p_value": _round(float(model.pvalues[name]), 6),
            "ci_low": _round(float(conf.loc[name, 0])),
            "ci_high": _round(float(conf.loc[name, 1])),
            "significant": bool(model.pvalues[name] < ALPHA),
        })

    group_var = float(model.cov_re.iloc[0, 0]) if model.cov_re.size else 0.0
    resid_var = float(model.scale)
    icc = group_var / (group_var + resid_var) if (group_var + resid_var) else 0.0
    label = _label(icc, 0.05, 0.15, 0.3)

    caveats = [
        "Random intercepts only: each group gets its own baseline, but each "
        "predictor is assumed to act the same way across groups",
        "Association within this data, not causation",
    ]
    if sampled:
        caveats.append(f"Computed on a {SAMPLE_ABOVE:,}-row sample of a larger dataset")

    return TestResult(
        kind="mixed_model", statistic=float(model.llf), p_value=float("nan"),
        effect_size=icc, effect_name="icc", effect_label=label,
        significant=any(c["significant"] for c in coefficients[1:]),
        n=int(len(work)),
        detail={"test": "Linear mixed-effects model (random intercept)",
                "target": target, "group_column": group_col,
                "groups": n_groups, "rows_per_group": _round(per_group, 1),
                "coefficients": coefficients,
                "group_variance": _round(group_var),
                "residual_variance": _round(resid_var), "icc": _round(icc)},
        interpretation=(
            f"{icc * 100:.0f}% of the variation in {target} is between "
            f"{group_col} groups rather than within them ({label} grouping "
            f"effect). Ordinary regression would have treated these "
            f"{len(work)} rows as independent and overstated its confidence."),
        caveats=caveats,
    )


# ── 7. Survival analysis ─────────────────────────────────────────────────────

def survival(df: pd.DataFrame, duration_col: str, event_col: str,
             predictors: list[str] | None = None) -> TestResult:
    """Cox proportional hazards: what changes how LONG something takes?

    The point of survival analysis is CENSORING. A customer who has not churned
    yet is not a customer who never will -- they are information about "at least
    this long", and every simpler method throws that away. Dropping them
    understates lifetimes; counting them as events overstates churn. Cox uses
    them correctly.

    Reports HAZARD RATIOS: 1.5 means one-and-a-half times the instantaneous risk
    at any given moment, the form both clinical and business literature use.
    """
    from statsmodels.duration.hazard_regression import PHReg

    for c in (duration_col, event_col):
        if c not in df.columns:
            raise StatisticalError(f"Column not found: {c}")
    predictors = [p for p in (predictors or []) if p not in (duration_col, event_col)]
    if not predictors:
        raise StatisticalError("At least one predictor column is required")
    missing = [p for p in predictors if p not in df.columns]
    if missing:
        raise StatisticalError(f"Column not found: {missing[0]}")

    frame, sampled = _sampled(df)
    work = frame[[duration_col, event_col] + predictors].apply(
        pd.to_numeric, errors="coerce").dropna()
    if work.empty:
        raise StatisticalError("No complete numeric rows to model")

    if (work[duration_col] <= 0).any():
        raise StatisticalError(
            f"'{duration_col}' contains values at or below zero; a duration must "
            f"be positive")
    ev = work[event_col]
    if not set(pd.unique(ev)).issubset({0, 1}):
        raise StatisticalError(
            f"'{event_col}' must be 1 where the event happened and 0 where it "
            f"has not (censored)")

    events = int(ev.sum())
    need = len(predictors) * MIN_EVENTS_PER_PREDICTOR
    if events == 0:
        raise StatisticalError(
            "No events occurred, so there is nothing to model -- every row is "
            "censored")
    if events < need:
        raise StatisticalError(
            f"Only {events} event(s); Cox regression needs about "
            f"{MIN_EVENTS_PER_PREDICTOR} per predictor ({need} for "
            f"{len(predictors)}). Rows without an event carry very little "
            f"information here, however many there are.")

    try:
        model = PHReg(work[duration_col], work[predictors], status=ev).fit()
    except Exception as e:  # noqa: BLE001
        raise StatisticalError(f"The model could not be fitted: {e}")

    conf = model.conf_int()
    coefficients = []
    for i, name in enumerate(predictors):
        coefficients.append({
            "term": name,
            "coefficient": _round(float(model.params[i])),
            "hazard_ratio": _round(float(np.exp(model.params[i]))),
            "hr_ci_low": _round(float(np.exp(conf[i][0]))),
            "hr_ci_high": _round(float(np.exp(conf[i][1]))),
            "p_value": _round(float(model.pvalues[i]), 6),
            "significant": bool(model.pvalues[i] < ALPHA),
        })

    censored = int(len(work) - events)
    strongest = max((abs(c["coefficient"] or 0) for c in coefficients), default=0.0)
    label = _label(strongest, 0.1, 0.3, 0.5)

    caveats = [
        f"{censored:,} of {len(work):,} rows are censored (the event had not "
        f"happened yet) and are used as 'at least this long', not discarded",
        "Assumes proportional hazards: that each predictor's effect on risk "
        "stays constant over time. This is not checked here",
        "Association within this data, not causation",
    ]
    if sampled:
        caveats.append(f"Computed on a {SAMPLE_ABOVE:,}-row sample of a larger dataset")

    sig = [c for c in coefficients if c["significant"]]
    return TestResult(
        kind="survival", statistic=float(events), p_value=float("nan"),
        effect_size=strongest, effect_name="max_abs_coefficient",
        effect_label=label, significant=bool(sig), n=int(len(work)),
        detail={"test": "Cox proportional hazards",
                "duration_column": duration_col, "event_column": event_col,
                "events": events, "censored": censored,
                "coefficients": coefficients},
        interpretation=(
            ", ".join(f"a one-unit rise in {c['term']} multiplies the risk by "
                      f"{c['hazard_ratio']}" for c in sig)
            or "No predictor significantly changes the timing."),
        caveats=caveats,
    )


# ── 8. Multiple-comparison correction ────────────────────────────────────────

def correct_p_values(p_values: list, method: str = "fdr_bh",
                     alpha: float = ALPHA) -> dict:
    """Adjust a family of p-values for multiple testing.

    NOT A REGISTERED ANALYSIS, because it takes p-values rather than a dataset:
    there would be nothing to point it at. It exists to correct the surfaces
    that run MANY tests at once, which is where the problem actually bites.

    Twenty independent tests of pure noise produce one "significant" result on
    average at alpha=0.05 -- and a dashboard scanning six measures against six
    categories runs far more than twenty. Without correction, an engine that
    reports every p < 0.05 as a finding is a machine for generating confident
    nonsense out of random data.

    Benjamini-Hochberg by default rather than Bonferroni: Bonferroni controls
    the chance of ANY false positive, which is right for a drug trial and far
    too strict for exploratory scanning, where it would suppress most true
    findings as well. BH controls the expected PROPORTION of false ones among
    those reported, which is what the reader of a findings list cares about.
    """
    from statsmodels.stats.multitest import multipletests

    clean = [float(p) for p in p_values
             if p is not None and not math.isnan(float(p))]
    if not clean:
        return {"method": method, "alpha": alpha, "n_tests": 0,
                "adjusted": [None] * len(p_values),
                "rejected": [False] * len(p_values)}
    reject, adjusted, _, _ = multipletests(clean, alpha=alpha, method=method)
    out_adj, out_rej, i = [], [], 0
    for p in p_values:
        if p is None or math.isnan(float(p)):
            out_adj.append(None)
            out_rej.append(False)
        else:
            out_adj.append(float(adjusted[i]))
            out_rej.append(bool(reject[i]))
            i += 1
    return {"method": method, "alpha": alpha, "n_tests": len(clean),
            "adjusted": out_adj, "rejected": out_rej}


def pairwise_comparisons(df: pd.DataFrame, value_col: str, group_col: str,
                         method: str = "holm") -> TestResult:
    """Which PAIRS of groups differ, with the family-wise error controlled.

    `compare_groups` with three or more groups runs an ANOVA, which says only
    that SOME group differs -- its own caveat tells the reader to compare pairs
    to find out which. Doing that naively is the classic mistake: six groups
    means fifteen comparisons, and at alpha=0.05 roughly one comes back
    significant by chance alone.

    PAIRWISE WELCH + HOLM, not Tukey HSD. Tukey is the textbook post-hoc test
    and it assumes equal variances across groups -- the exact assumption
    `compare_groups` deliberately refuses to make. Using it here would have the
    platform contradicting itself between two adjacent screens.
    """
    from itertools import combinations

    from scipy import stats

    for c in (group_col, value_col):
        if c not in df.columns:
            raise StatisticalError(f"Column not found: {c}")
    frame, sampled = _sampled(df)
    work = frame[[group_col, value_col]].copy()
    work[value_col] = pd.to_numeric(work[value_col], errors="coerce")
    work = work.dropna()

    groups = [(str(name), g[value_col].to_numpy())
              for name, g in work.groupby(group_col, sort=False)]
    groups = [(gname, v) for gname, v in groups if len(v) >= MIN_ROWS_PER_GROUP]
    if len(groups) < 2:
        raise StatisticalError(
            f"Need at least two groups with {MIN_ROWS_PER_GROUP}+ rows each; "
            f"found {len(groups)}")
    if len(groups) > MAX_GROUPS:
        raise StatisticalError(
            f"{len(groups)} groups would need "
            f"{len(groups) * (len(groups) - 1) // 2} comparisons (limit "
            f"{MAX_GROUPS} groups)")

    pairs, raw_p = [], []
    for (na, a), (nb, b) in combinations(groups, 2):
        _stat, p = stats.ttest_ind(a, b, equal_var=False)
        s1, s2 = np.std(a, ddof=1), np.std(b, ddof=1)
        pooled = math.sqrt(((len(a) - 1) * s1 ** 2 + (len(b) - 1) * s2 ** 2)
                           / max(len(a) + len(b) - 2, 1))
        d = float((np.mean(a) - np.mean(b)) / pooled) if pooled else 0.0
        pairs.append({"group_a": na, "group_b": nb,
                      "mean_a": _round(float(np.mean(a))),
                      "mean_b": _round(float(np.mean(b))),
                      "difference": _round(float(np.mean(a) - np.mean(b))),
                      "cohens_d": _round(d),
                      "effect_label": _label(d, 0.2, 0.5, 0.8),
                      "p_raw": _round(float(p), 6)})
        raw_p.append(float(p))

    corrected = correct_p_values(raw_p, method=method)
    for pair, adj, rej in zip(pairs, corrected["adjusted"], corrected["rejected"]):
        pair["p_adjusted"] = _round(adj, 6)
        pair["significant"] = bool(rej)

    n_sig = sum(1 for p in pairs if p["significant"])
    n_naive = sum(1 for p in pairs if (p["p_raw"] or 1) < ALPHA)
    strongest = max((abs(p["cohens_d"] or 0) for p in pairs), default=0.0)

    caveats = [
        f"{len(pairs)} comparisons were made; p-values are adjusted by the "
        f"{method} method so the reported significance accounts for that",
        "Welch's t-test is used for each pair, which does not assume equal "
        "variances -- unlike Tukey's HSD",
    ]
    if n_naive > n_sig:
        caveats.append(
            f"{n_naive - n_sig} pair(s) would have looked significant without "
            f"the correction; with this many comparisons some reach p < 0.05 by "
            f"chance alone")
    if sampled:
        caveats.append(f"Computed on a {SAMPLE_ABOVE:,}-row sample of a larger dataset")

    return TestResult(
        kind="pairwise_comparisons", statistic=float(len(pairs)),
        p_value=min((p["p_adjusted"] for p in pairs
                     if p["p_adjusted"] is not None), default=float("nan")),
        effect_size=strongest, effect_name="max_cohens_d",
        effect_label=_label(strongest, 0.2, 0.5, 0.8),
        significant=bool(n_sig), n=int(len(work)),
        detail={"test": f"Pairwise Welch t-tests, {method}-adjusted",
                "comparisons": len(pairs), "significant_pairs": n_sig,
                "pairs": pairs},
        interpretation=(
            f"{n_sig} of {len(pairs)} pairs differ significantly after "
            f"correcting for multiple comparisons."
            if n_sig else
            f"No pair differs significantly once the {len(pairs)} comparisons "
            f"are accounted for."),
        caveats=caveats,
    )


# ── "Is this difference real?" on a chart (Phase 7.2) ────────────────────────

def difference_check(df: pd.DataFrame, dimension: str, groups: list, measure: str | None = None,
                     aggregation: str = "sum", granularity: str | None = None) -> dict:
    """Two bars on a chart: is the gap between them more than noise?

    The chart's AGGREGATION decides what "the difference" is, so the answer
    tests that and says which test it used:

      * count  -> are the two groups' row counts different from an even split?
                  (exact binomial test; effect = Cohen's h)
      * avg / mean -> does a typical row differ? (Welch's t-test; Cohen's d)
      * median -> does a typical row differ, without assuming normal values?
                  (Mann-Whitney U; effect = rank-biserial r)
      * sum    -> a total is (rows x typical value), so BOTH parts are tested
                  and the sentence says which one drives the gap.

    The population is the rows the chart itself drew from -- the caller hands
    in the frame already narrowed by the widget's filters -- and it is stated
    with the result, because a p-value without its population is a number
    about nothing in particular.
    """
    import numpy as np
    from scipy import stats

    if dimension not in df.columns:
        raise StatisticalError(f"Column not found: {dimension}")
    if measure and measure not in df.columns:
        raise StatisticalError(f"Column not found: {measure}")
    if not isinstance(groups, (list, tuple)) or len(groups) != 2 or str(groups[0]) == str(groups[1]):
        raise StatisticalError("Pick two different bars to compare")
    agg = (aggregation or ("sum" if measure else "count")).lower()
    if not measure:
        agg = "count"
    keys = df[dimension]
    if granularity:
        from ..widget_data import _bucket_dimension
        keys = _bucket_dimension(keys, granularity)
    keys = keys.astype(str)
    a_name, b_name = str(groups[0]), str(groups[1])
    in_a, in_b = keys == a_name, keys == b_name
    na, nb = int(in_a.sum()), int(in_b.sum())
    if na == 0 or nb == 0:
        raise StatisticalError(f"No rows for {a_name if na == 0 else b_name} under this chart's filters")

    population = {"rows_a": na, "rows_b": nb, "group_a": a_name, "group_b": b_name,
                  "dimension": dimension, "measure": measure, "aggregation": agg}
    out: dict[str, Any] = {"kind": "difference_check", "population": population, "tests": []}

    def count_test() -> dict:
        res = stats.binomtest(na, na + nb, 0.5)
        p = float(res.pvalue)
        share = na / (na + nb)
        h = 2 * math.asin(math.sqrt(share)) - 2 * math.asin(math.sqrt(0.5))
        label = _label(h, 0.2, 0.5, 0.8)
        return {"question": "row counts", "test": "Exact binomial test (even split)",
                "p_value": _round(p, 6), "p_text": _p_text(p), "significant": bool(p < ALPHA),
                "effect_name": "cohens_h", "effect_size": _round(h), "effect_label": label,
                "values": {a_name: na, b_name: nb},
                "sentence": _verdict(p, label, f"difference in how many rows {a_name} and {b_name} have")}

    def value_test(kind: str) -> dict:
        va = pd.to_numeric(df.loc[in_a, measure], errors="coerce").dropna().to_numpy()
        vb = pd.to_numeric(df.loc[in_b, measure], errors="coerce").dropna().to_numpy()
        if len(va) < MIN_ROWS_PER_GROUP or len(vb) < MIN_ROWS_PER_GROUP:
            raise StatisticalError(
                f"Each bar needs at least {MIN_ROWS_PER_GROUP} rows with a {measure} value to test; "
                f"{a_name} has {len(va)}, {b_name} has {len(vb)}")
        if kind == "median":
            u, p = stats.mannwhitneyu(va, vb, alternative="two-sided")
            r = 1 - 2 * float(u) / (len(va) * len(vb))
            label = _label(r, 0.1, 0.3, 0.5)
            return {"question": "typical row", "test": "Mann-Whitney U",
                    "p_value": _round(float(p), 6), "p_text": _p_text(float(p)), "significant": bool(p < ALPHA),
                    "effect_name": "rank_biserial", "effect_size": _round(r), "effect_label": label,
                    "values": {a_name: _round(float(np.median(va))), b_name: _round(float(np.median(vb)))},
                    "sentence": _verdict(float(p), label, f"difference in a typical {measure} between {a_name} and {b_name}")}
        t, p = stats.ttest_ind(va, vb, equal_var=False)
        s1, s2 = np.std(va, ddof=1), np.std(vb, ddof=1)
        pooled = math.sqrt(((len(va) - 1) * s1 ** 2 + (len(vb) - 1) * s2 ** 2) / max(len(va) + len(vb) - 2, 1))
        d = (np.mean(va) - np.mean(vb)) / pooled if pooled else 0.0
        label = _label(d, 0.2, 0.5, 0.8)
        return {"question": "typical row", "test": "Welch's t-test",
                "p_value": _round(float(p), 6), "p_text": _p_text(float(p)), "significant": bool(p < ALPHA),
                "effect_name": "cohens_d", "effect_size": _round(float(d)), "effect_label": label,
                "values": {a_name: _round(float(np.mean(va))), b_name: _round(float(np.mean(vb)))},
                "sentence": _verdict(float(p), label, f"difference in average {measure} between {a_name} and {b_name}")}

    if agg == "count":
        out["tests"].append(count_test())
        out["summary"] = out["tests"][0]["sentence"]
    elif agg in ("avg", "mean", "average"):
        out["tests"].append(value_test("mean"))
        out["summary"] = out["tests"][0]["sentence"]
    elif agg == "median":
        out["tests"].append(value_test("median"))
        out["summary"] = out["tests"][0]["sentence"]
    elif agg == "sum":
        typical, sizes = value_test("mean"), count_test()
        out["tests"] = [typical, sizes]
        parts = (("a typical row's value", typical), ("the number of rows", sizes))
        drivers = [n for n, t in parts if t["significant"] and t["effect_label"] != "negligible"]
        tiny = [n for n, t in parts if t["significant"] and t["effect_label"] == "negligible"]
        if drivers:
            tail = f"The gap is driven by {' and '.join(drivers)}."
        elif tiny:
            tail = (f"Only {' and '.join(tiny)} differs significantly, and by a negligible amount -- "
                    f"with this many rows that is expected, so the gap is unlikely to matter.")
        else:
            tail = ("Neither the typical value nor the row count differs beyond noise, "
                    "so the gap between these totals may not be real.")
        out["summary"] = "A total is rows × typical value. " + tail
    else:
        raise StatisticalError(f"A '{agg}' bar is one extreme row; there is no spread to test against")

    out["caveats"] = [
        f"Tested on the {na + nb:,} rows behind these two bars, after this chart's filters.",
        f"Significance at {int(ALPHA * 100)}%; with many rows, tiny differences are 'significant' -- read the effect size.",
        "An observed difference, not a cause.",
    ]
    return safe_json(out)


def safe_json(obj):
    """numpy scalars -> python, for the wire."""
    import numpy as np
    if isinstance(obj, dict):
        return {k: safe_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [safe_json(v) for v in obj]
    if isinstance(obj, np.generic):
        return obj.item()
    return obj
