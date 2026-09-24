"""Association rules: which values travel together.

"Customers who bought A also bought B" is the question this answers, and it is
the one gap in the analysis catalogue that no existing analysis approaches --
correlation needs two numeric columns, key influencers needs a chosen outcome,
and neither can say that three particular values co-occur.

**Lift is the number that matters, not confidence.** A rule can be 90%
confident and worthless: if B appears in 90% of all baskets anyway, then "A
implies B, 90% confident" states nothing about A. Lift divides that confidence
by B's own base rate, so 1.0 means independent and 3.2 means the pair happens
3.2x more than chance. Rules are therefore ranked by lift and the base rate is
reported beside it, so a reader can see what the comparison was against.

**Support before significance.** A rule resting on four baskets is noise
whatever its lift, so `MIN_SUPPORT_COUNT` sets a floor in ROWS rather than a
fraction -- 1% of a 200-row dataset is two rows, and a fractional floor would
silently admit exactly the rules that cannot be trusted.

**No mlxtend.** Apriori's pruning is a dozen lines over pandas and the
candidate space is already bounded hard (`MAX_ITEMS`, `MAX_LEN`), so the
air-gapped image gains nothing from the dependency. Same reasoning as
`influencers.py`'s "no ML dependency at all".

**It is co-occurrence, never causation.** The result says these values appear
together more than chance predicts. It does not say one causes the other, and
the caveat travels with the payload rather than living in documentation.
"""
from __future__ import annotations

import itertools

import pandas as pd

from ..analysis_contract import AnalysisContract

RANDOM_STATE = 42

#: Above this the frame is sampled. Rule mining is combinatorial, and an
#: unbounded frame turns one request into a long CPU burn on a shared worker --
#: the same ceiling `influencers.py` and `segment.py` apply.
FRAME_SAMPLE_THRESHOLD = 50_000

#: A rule needs enough baskets behind it to mean anything. In ROWS, not a
#: fraction: 1% of 200 rows is two, and a fractional floor would admit exactly
#: the rules a reader should not trust.
MIN_SUPPORT_COUNT = 20

#: Distinct values considered per column. A 5,000-value id column has no
#: frequent pairs and would dominate the candidate space computing that.
MAX_LEVELS = 50
#: Total items across all columns entering the search.
MAX_ITEMS = 200
#: Longest itemset. Past three the rules stop being readable and start being a
#: description of individual rows.
MAX_LEN = 3
#: Rules returned. Ranked by lift, so the cut takes the weakest.
TOP_N = 25

#: Below this a rule is not worth reporting: the pair is essentially as common
#: as chance predicts, which is the definition of no pattern.
MIN_LIFT = 1.2

#: A longer rule must beat the simpler rule it contains by this factor to be
#: worth reporting separately. Below it, the extra condition is decoration.
REDUNDANCY_MARGIN = 1.1

#: Confidence at or above which a rule is treated as schema structure rather
#: than a discovery. "Australia implies Asia Pacific" holds in 100% of rows
#: because it is how the columns are DEFINED -- a hierarchy, a lookup, a
#: derived column. Reporting it is true and useless, and on a dataset with any
#: such pair these rules take every slot: mining the demo sales data returned
#: 25 rules of which 25 were country/region restatements.
FUNCTIONAL_DEPENDENCY_CONFIDENCE = 0.99


class PatternError(ValueError):
    """Unusable input for rule mining. The router maps this to HTTP 400."""


def _items(df: pd.DataFrame, columns: list[str]) -> tuple[list[tuple[str, str]], dict]:
    """Column/value pairs frequent enough to be worth pairing up.

    Items are `(column, value)` rather than bare values so that `region=North`
    and `channel=North` stay distinct -- collapsing them would invent
    co-occurrences between unrelated columns that happen to share a label.
    """
    masks: dict[tuple[str, str], pd.Series] = {}
    for col in columns:
        counts = df[col].astype(str).value_counts()
        if len(counts) > MAX_LEVELS:
            counts = counts.head(MAX_LEVELS)
        for value, n in counts.items():
            if n < MIN_SUPPORT_COUNT:
                # value_counts is sorted descending, so nothing after this
                # value clears the floor either.
                break
            masks[(col, str(value))] = df[col].astype(str) == str(value)
    # Most frequent first, so the cap keeps the items most likely to form rules.
    ordered = sorted(masks, key=lambda k: -int(masks[k].sum()))[:MAX_ITEMS]
    return ordered, {k: masks[k] for k in ordered}


def _dependent_pairs(df: pd.DataFrame, columns: list[str]) -> set[frozenset]:
    """Column pairs where one determines the other -- schema, not discovery.

    `country` determines `region` because that is how the columns are DEFINED:
    a hierarchy, a lookup, or a derived column. Every rule between such a pair
    is true, unavoidable, and worthless, and there are a LOT of them: mining
    the demo sales data returned 25 rules of which 25 were country/region
    restatements, burying every real finding.

    Suppressing at the PAIR level rather than per rule, because a dependency
    also leaks into compound conclusions -- `country=Australia -> region=Asia
    Pacific, shipping=standard` is the same non-finding with a real column
    bolted on, and a per-rule confidence filter lets it through.

    Detected by measuring, not by naming columns: for each ordered pair, if
    almost every value of A maps to a single B, A determines B.
    """
    dependent: set[frozenset] = set()
    for a in columns:
        for b in columns:
            if a == b or frozenset((a, b)) in dependent:
                continue
            # Rows where A's value maps to its most common B, over all rows.
            grouped = df.groupby(a, observed=True)[b]
            agreed = grouped.transform(lambda g: g.map(g.value_counts()).max()
                                       if len(g) else 0)
            purity = float((agreed / grouped.transform("size")).mean())
            if purity >= FUNCTIONAL_DEPENDENCY_CONFIDENCE:
                dependent.add(frozenset((a, b)))
    return dependent


def _drop_redundant(rows: list[dict]) -> list[dict]:
    """Remove rules that only restate a simpler one with noise attached.

    Adding an independent value to a rule nudges lift around by chance, so
    `region=N, shipping=express -> tier=premium` can OUTRANK the finding it
    contains, `shipping=express -> tier=premium`. Both are true; only the
    second is the pattern. Left in, the list fills with variations of one rule
    and buries every other finding.

    Both SIDES are checked. Suppressing only wordier antecedents still left
    `tier=premium -> region=N, shipping=express` -- the same finding with an
    independent column bolted onto the conclusion.

    Rules are compared against every simpler rule, not merely against ones
    already kept: a longer variant usually sorts FIRST (its inflated lift is
    what promoted it), so a backward-only scan never sees what it duplicates.
    That was the first version of this and it suppressed nothing.

    A longer rule survives only if it beats the simpler rule it contains by
    `REDUNDANCY_MARGIN` -- the extra condition has to earn its place.
    """
    def parts(row: dict) -> tuple[frozenset, frozenset]:
        return (frozenset(row["if"].split(", ")),
                frozenset(row["then"].split(", ")))

    index = {parts(r): r for r in rows}

    def simpler_forms(ante: frozenset, cons: frozenset):
        """Every rule contained in this one: fewer conditions, or a narrower
        conclusion, or both."""
        for a_size in range(1, len(ante) + 1):
            for a in itertools.combinations(sorted(ante), a_size):
                for c_size in range(1, len(cons) + 1):
                    for c in itertools.combinations(sorted(cons), c_size):
                        if len(a) == len(ante) and len(c) == len(cons):
                            continue                     # the rule itself
                        hit = index.get((frozenset(a), frozenset(c)))
                        if hit is not None:
                            yield hit

    kept: list[dict] = []
    for row in rows:
        ante, cons = parts(row)
        if any(row["lift"] <= s["lift"] * REDUNDANCY_MARGIN
               for s in simpler_forms(ante, cons)):
            continue
        kept.append(row)
    return kept


def association_rules(df: pd.DataFrame,
                      columns: list[str] | None = None) -> AnalysisContract:
    """Find value combinations that co-occur more than chance predicts.

    `columns` limits the search to specific categorical columns; omitted, every
    usable categorical column is considered.
    """
    total_rows = len(df)
    sampled = total_rows > FRAME_SAMPLE_THRESHOLD
    if sampled:
        df = df.sample(n=FRAME_SAMPLE_THRESHOLD, random_state=RANDOM_STATE)

    if columns:
        missing = [c for c in columns if c not in df.columns]
        if missing:
            raise PatternError(f"column '{missing[0]}' is not in this dataset")
        usable = list(columns)
    else:
        usable = [c for c in df.columns
                  if not pd.api.types.is_numeric_dtype(df[c])
                  and 1 < df[c].nunique() <= MAX_LEVELS]

    if len(usable) < 2:
        raise PatternError(
            "rule mining needs at least two categorical columns; this dataset "
            "has " + (str(len(usable)) if usable else "none"))

    n = len(df)
    if n < MIN_SUPPORT_COUNT * 2:
        raise PatternError(
            f"need at least {MIN_SUPPORT_COUNT * 2} rows to mine rules; "
            f"this has {n}")

    dependent = _dependent_pairs(df, usable)
    ordered, masks = _items(df, usable)
    if len(ordered) < 2:
        raise PatternError(
            "no value appears often enough to form a rule "
            f"(each needs {MIN_SUPPORT_COUNT} rows)")

    # ---- frequent itemsets, apriori-style ------------------------------------
    # Each level is built only from surviving items of the previous one: an
    # itemset cannot be frequent if any subset is not, which is the entire
    # reason this stays tractable without a library.
    support: dict[frozenset, int] = {}
    level: list[tuple[tuple, pd.Series]] = [((k,), masks[k]) for k in ordered]
    level = [(combo, m) for combo, m in level if int(m.sum()) >= MIN_SUPPORT_COUNT]
    for combo, m in level:
        support[frozenset(combo)] = int(m.sum())

    for _ in range(MAX_LEN - 1):
        nxt: list[tuple[tuple, pd.Series]] = []
        for i, (combo_a, mask_a) in enumerate(level):
            for combo_b, mask_b in level[i + 1:]:
                merged = tuple(sorted(set(combo_a) | set(combo_b)))
                if len(merged) != len(combo_a) + 1:
                    continue
                if frozenset(merged) in support:
                    continue
                # Two values of the SAME column never co-occur in a row, so
                # pairing them would produce a rule with zero support and waste
                # the candidate slot.
                cols_in = [c for c, _ in merged]
                if len(set(cols_in)) != len(merged):
                    continue
                # Nor pair columns where one determines the other: that rule is
                # the schema restating itself. See _dependent_pairs.
                if any(frozenset((x, y)) in dependent
                       for i2, x in enumerate(cols_in) for y in cols_in[i2 + 1:]):
                    continue
                mask = mask_a & mask_b
                count = int(mask.sum())
                if count >= MIN_SUPPORT_COUNT:
                    support[frozenset(merged)] = count
                    nxt.append((merged, mask))
        if not nxt:
            break
        level = nxt

    # ---- rules from those itemsets -------------------------------------------
    rows: list[dict] = []
    for itemset, joint in support.items():
        if len(itemset) < 2:
            continue
        for r in range(1, len(itemset)):
            for antecedent in itertools.combinations(sorted(itemset), r):
                ante = frozenset(antecedent)
                cons = itemset - ante
                ante_n = support.get(ante)
                cons_n = support.get(cons)
                if not ante_n or not cons_n:
                    continue
                confidence = joint / ante_n
                base_rate = cons_n / n
                lift = confidence / base_rate if base_rate else 0.0
                if lift < MIN_LIFT:
                    continue
                if confidence >= FUNCTIONAL_DEPENDENCY_CONFIDENCE:
                    # A rule that never fails is describing the schema, not the
                    # data. See FUNCTIONAL_DEPENDENCY_CONFIDENCE.
                    continue
                rows.append({
                    "if": ", ".join(f"{c}={v}" for c, v in sorted(ante)),
                    "then": ", ".join(f"{c}={v}" for c, v in sorted(cons)),
                    "support_rows": joint,
                    "support_pct": round(joint / n * 100, 2),
                    "confidence": round(confidence, 4),
                    # The number the confidence must be read against: without
                    # it, "90% confident" looks impressive for an outcome that
                    # happens 90% of the time anyway.
                    "base_rate": round(base_rate, 4),
                    "lift": round(lift, 3),
                })

    rows.sort(key=lambda r: (-r["lift"], -r["support_rows"], r["if"]))
    rows = _drop_redundant(rows)[:TOP_N]

    caveats = [
        "These are co-occurrences, not causes: the values appear together more "
        "often than chance predicts, which says nothing about one producing "
        "the other.",
        f"Only rules holding in at least {MIN_SUPPORT_COUNT} rows and lifting "
        f"at least {MIN_LIFT}x above the base rate are reported.",
    ]
    if sampled:
        caveats.append(
            f"Computed on a {FRAME_SAMPLE_THRESHOLD:,}-row sample of "
            f"{total_rows:,} rows.")

    return AnalysisContract(
        kind="association_rules",
        columns=[
            {"name": "if", "type": "text"},
            {"name": "then", "type": "text"},
            {"name": "lift", "type": "number"},
            {"name": "confidence", "type": "number"},
            {"name": "base_rate", "type": "number"},
            {"name": "support_rows", "type": "number"},
            {"name": "support_pct", "type": "number"},
        ],
        rows=rows,
        meta={"rows_scanned": n, "total_rows": total_rows, "sampled": sampled,
              "columns_considered": usable, "items_considered": len(ordered),
              "params": {"min_support_rows": MIN_SUPPORT_COUNT,
                         "min_lift": MIN_LIFT, "max_itemset_size": MAX_LEN}},
        warnings=caveats,
    )
