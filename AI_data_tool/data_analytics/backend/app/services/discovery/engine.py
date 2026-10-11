"""What is worth doing with a dataset: candidates -> fit -> evidence -> rank ->
cards (docs/discovery/PLAN.md, section C). No model is called anywhere here.

    tier 0   what the data SUPPORTS, from the stored profile and the stored
             column classification alone -- no row is read
    tier 1   what the data SHOWS: the insight detectors' findings, each drawn
             on the reader's own rows and refused when it says nothing

A card states separately whether the data fits, how strong the evidence is,
what kind of claim it is and what it costs; there is no single "confidence".
"""
from __future__ import annotations

import hashlib
import json
import logging
import re

from .. import semantic_guard as guard
from ..readback import Said, _s, as_i18n
from . import capabilities as caps
from . import profile as profile_store

logger = logging.getLogger(__name__)

#: Cards returned by default, and at most per family, so one kind of idea
#: cannot fill the list.
DEFAULT_LIMIT = 24
PER_FAMILY = 4
#: A free-text column: long values, mostly different from each other.
TEXT_MIN_AVG_LEN = 25
#: A column naming things has at least this many different values, and at
#: most this many (beyond it nothing repeats often enough to pair).
ITEM_MIN, ITEM_MAX = 5, 200
#: A group's key repeats: on average at least this many rows per value, and
#: few of its values occur only once.
GROUP_MIN_ROWS_EACH, GROUP_MAX_SINGLE = 1.5, 0.5
#: Evidence bands from a finding's own strength (insights' 0..1 score).
STRONG, MODERATE = 0.5, 0.25
#: How long a reader's computed cards are kept for the same data.
CACHE_TTL_S = 900
_WORD = re.compile(r"[^\W_]{3,}", re.UNICODE)

#: Which capability a finding of each kind is, and what it claims.
_FINDING = {
    "trend": ("trend", "observation"), "standout": ("compare", "observation"), "laggard": ("compare", "observation"),
    "rate": ("compare", "observation"), "gradient": ("compare", "association"),
    "pareto": ("composition", "observation"),
    "anomaly": ("anomaly", "observation"), "change_point": ("trend", "observation"),
    "correlation": ("relationship", "association"), "outlier_impact": ("distribution", "observation"),
    "data_quality": ("basics", "observation"), "baseline": ("basics", "observation"), "rules": ("pattern", "association"),
}
#: What usually comes next after a result of each family (stage 15).
_NEXT = {
    "trend": ["explain_change", "forecast_ets", "explain_response"],
    "anomaly": ["explain_change", "compare_groups"],
    "compare": ["compare_groups", "key_influencers", "explain_response"],
    "relationship": ["correlation_test", "regression", "segment"],
    "distribution": ["anomaly_iqr", "compare_groups"],
    "basics": ["explain_response", "segment"],
    "pattern": ["key_influencers", "decision_tree"],
    "forecast": ["forecast_goal", "forecast_scenario"],
    "model": ["automated_prediction", "decision_tree"],
}


# ── what kind of thing each column is ────────────────────────────────────────
def column_kinds(profile: dict, column_meta: dict | None) -> dict[str, set[str]]:
    """{column: kinds} from the stored statistics and the stored classification.
    A column that is hidden, withheld from suggestions or personal is left out."""
    meta = column_meta or {}
    out: dict[str, set[str]] = {}
    for name, st in (profile.get("columns") or {}).items():
        entry = meta.get(name) if isinstance(meta.get(name), dict) else {}
        if entry.get("hidden") or entry.get("eligible_for_suggestion") is False:
            continue
        kinds: set[str] = set()
        geo = entry.get("geo_level")
        kind = st.get("kind")
        if kind == "number":
            if geo in ("latitude", "longitude"):
                kinds.add(geo)
            elif guard.non_additive_kind(name, meta) == "year":
                pass            # a year numbers a period: not a quantity, and not the key of a group
            elif guard.is_identifier(name, meta) or guard.non_additive_kind(name, meta) == "identifier":
                kinds.add("key")
            else:
                kinds.add("number")
                kinds.add("level" if guard.is_intensive(name, meta) else "additive")
        elif kind == "date":
            kinds.add("date")
        elif kind == "flag":
            kinds.update(("category", "outcome"))
        elif kind == "text":
            distinct, count = st.get("distinct") or 0, (st.get("count") or 0) - (st.get("missing") or 0)
            if 2 <= distinct <= profile_store.CATEGORY_MAX:
                kinds.add("category")
                if guard.is_outcome(name, meta):
                    kinds.add("outcome")
            elif (st.get("len_avg") or 0) >= TEXT_MIN_AVG_LEN and count and distinct >= 0.5 * count:
                kinds.add("text")
            elif count and (distinct >= 0.9 * count or (st.get("pattern") and distinct > ITEM_MAX)):
                # Nearly one value per row -- or values of one fixed shape (a
                # reference that repeats, as a group's key does on its lines).
                kinds.add("key")
            if ITEM_MIN <= distinct <= ITEM_MAX and "text" not in kinds and "key" not in kinds:
                # A column that names THINGS: the lines of a group.
                kinds.add("item")
            if geo in ("country", "region", "city"):
                kinds.add("place")
        if kinds:
            out[name] = kinds
    return out


def have_of(kinds: dict[str, set[str]]) -> dict[str, int]:
    have = {k: 0 for k in caps.KINDS}
    for ks in kinds.values():
        for k in ks:
            if k in have:
                have[k] += 1
    have["coords"] = min(sum("latitude" in ks for ks in kinds.values()), sum("longitude" in ks for ks in kinds.values()))
    return have


_WORDS = {"number": "a number column", "additive": "a number that adds up", "level": "a number that is averaged",
          "date": "a date column", "category": "a column of categories", "outcome": "a column that says what became of a row",
          "text": "a column of free text", "place": "a column of countries", "coords": "latitude and longitude",
          "key": "an identifier"}


def fit(cap: caps.Capability, have: dict[str, int], table: dict) -> tuple[bool, str | None]:
    """(does the data satisfy what this needs, and if not, why -- in plain words)."""
    for kind, n in cap.needs.items():
        got = have.get(kind, 0)
        if got < n:
            what = _WORDS.get(kind, kind)
            return False, (f"needs {what}; this data has none" if not got
                           else f"needs {n} of: {what}; this data has {got}")
    rows = table.get("rows") or 0
    floor = cap.minimum.get("rows")
    if floor and rows < floor:
        return False, f"needs at least {floor:,} rows; this data has {rows:,}"
    periods = cap.minimum.get("periods")
    if periods and (table.get("periods") or 0) < periods:
        return False, f"needs at least {periods} months of dates; this data covers {table.get('periods') or 0}"
    texts = cap.minimum.get("texts")
    if texts and rows < texts:
        return False, f"needs at least {texts} texts; this data has {rows:,}"
    if cap.minimum.get("columns") and len(table.get("usable") or ()) < cap.minimum["columns"]:
        return False, f"needs at least {cap.minimum['columns']} usable columns"
    if cap.structure and not (table.get("structure") or {}).get(cap.structure):
        return False, {"hierarchies": "needs columns that nest inside each other (a hierarchy)",
                       "transactions": "needs one row per (group, thing), with groups that hold several things",
                       "parent_child": "needs a column that points at another row of the same table"}.get(
                           cap.structure, f"needs {cap.structure}")
    return True, None


def supported(kinds: dict[str, set[str]], table: dict) -> tuple[list[caps.Capability], list[dict]]:
    """(capabilities this data supports, the others with the reason)."""
    have = have_of(kinds)
    yes, no = [], []
    for cap in caps.all_capabilities().values():
        ok, why = fit(cap, have, table)
        if ok:
            yes.append(cap)
        else:
            no.append({"capability": cap.name, "kind": cap.kind, "family": cap.family, "reason": why})
    return yes, no


# ── choosing columns for an analysis card ────────────────────────────────────
def _pick(kinds: dict[str, set[str]], profile: dict, kind: str) -> list[str]:
    cols = [c for c, ks in kinds.items() if kind in ks]
    st = profile.get("columns") or {}
    if kind in ("number", "additive", "level"):
        # The most VARIED first: a number that barely moves has little to say.
        def spread(c):
            s = st.get(c) or {}
            mean, std = abs(s.get("mean") or 0), s.get("std") or 0
            return -(std / mean) if mean else 0
        return sorted(cols, key=spread)
    if kind == "category":
        return sorted(cols, key=lambda c: (st.get(c) or {}).get("distinct") or 0)
    if kind == "date":
        # When the record began: filled for every row and earliest (the same
        # rule as insights.order_event_dates, read from the stored figures).
        def began(c):
            s = st.get(c) or {}
            total = s.get("count") or 1
            # To the nearest percent: a finish date missing for 1% of rows (the
            # ones still open) is already not the date every row has -- and
            # its median, taken over finished rows only, runs EARLY.
            return (round((s.get("missing") or 0) / total, 2), str(s.get("median") or ""))
        return sorted(cols, key=began)
    return cols


def group_key(kinds: dict[str, set[str]], profile: dict) -> str | None:
    """The column whose value several rows SHARE -- an order on its lines, a
    visit on its procedures -- read from the stored figures: an identifier
    that repeats, with few values seen only once. None when every row has its
    own key (a table of things, not of lines)."""
    best, best_rows = None, 0.0
    for name, ks in kinds.items():
        if "key" not in ks:
            continue
        st = (profile.get("columns") or {}).get(name) or {}
        distinct, filled = st.get("distinct") or 0, (st.get("count") or 0) - (st.get("missing") or 0)
        if distinct < 40 or not filled:
            continue
        each = filled / distinct
        if each >= GROUP_MIN_ROWS_EACH and (st.get("unique") or 0) <= GROUP_MAX_SINGLE * distinct and each > best_rows:
            best, best_rows = name, each
    return best


def _analysis_cards(fits: list[caps.Capability], kinds: dict, profile: dict, column_meta: dict | None) -> list[dict]:
    """One card per analysis the data supports, with the columns it would use.
    Tier 0: nothing has been computed, and the card says so."""
    fit_names = {c.name for c in fits if c.kind == "analysis"}
    additive, levels = _pick(kinds, profile, "additive"), _pick(kinds, profile, "level")
    # Quantities that add up lead; a number that is averaged (a rate, a level)
    # follows -- and a share computed FROM an outcome is that outcome again.
    numbers = additive + [c for c in levels if c not in additive]
    cats, dates = _pick(kinds, profile, "category"), _pick(kinds, profile, "date")
    outcomes, texts = _pick(kinds, profile, "outcome"), _pick(kinds, profile, "text")
    worth = sorted((c for c, e in (column_meta or {}).items() if isinstance(e, dict)
                    and e.get("target_candidate_priority") is not None and c in kinds),
                   key=lambda c: -(column_meta[c].get("target_candidate_priority") or 0))
    target = (worth or outcomes or [None])[0]
    cards: list[dict] = []

    def add(name: str, title: str, sentence: str, fields: list[str], params: dict, widget: tuple | None = None):
        cap = caps.analysis(name)
        if cap is None or name not in fit_names or not all(fields):
            return
        action = ({"kind": "add_widget", "widget_type": widget[0], "config": widget[1]} if widget
                  else {"kind": "run_analysis", "analysis": name, "params": params})
        cards.append(_card(cap, title, sentence, fields, action,
                           why={"reason": "fit", "detail": _T("why.fit", "The data has what this needs; nothing has been computed yet.")}))

    if dates and (additive or numbers):
        m = (additive or numbers)[0]
        add("forecast_ets" if additive else "forecast_simple", _T("forecast.t", "Forecast {m}", m=_h(m)),
            _T("forecast.s", "Projects {m} into the coming periods from its history by {d}, with a likely range.", m=_h(m), d=_h(dates[0])),
            [m, dates[0]], {},
            ("forecast", {"dimension": dates[0], "measure": m, "aggregation": guard.default_summary(m, column_meta)}))
    if dates and (additive or numbers) and cats:
        m = (additive or numbers)[0]
        how = guard.default_summary(m, column_meta)
        add("explain_change", _T("change.t", "What is behind the latest change in {m}", m=_h(m)),
            _T("change.s", "Splits the difference between the last two complete periods of {m} by each category "
                           "and says which values carry it.", m=_h(m)),
            [m, dates[0]], {"date_column": dates[0], "measure": m,
                            "aggregation": how if how in ("sum", "avg", "median", "count") else "sum"})
    if dates and len(numbers) >= 2:
        m, f = (additive or numbers)[0], next(c for c in numbers if c != (additive or numbers)[0])
        add("compare_scenarios", _T("scenarios.t", "{m} if {f} went up or down by a tenth", m=_h(m), f=_h(f)),
            _T("scenarios.s", "Projects {m} forward three ways -- {f} as it is, 10% higher and 10% lower -- and sets them side by side.",
               m=_h(m), f=_h(f)),
            [m, f, dates[0]], {"date_column": dates[0], "measure": m, "factors": [f],
                               "scenarios": [{"name": f"{_h(f)} +10%", "adjustments": {f: 0.1}},
                                             {"name": f"{_h(f)} -10%", "adjustments": {f: -0.1}}]})
    if target:
        factors = [c for c in (cats + numbers) if c != target][:8]
        add("key_influencers", _T("influencers.t", "What goes with {t}", t=_h(target)),
            _T("influencers.s", "Finds which values of the other columns go together with {t}, against the overall rate.", t=_h(target)),
            [target], {"target": target, "factors": factors},
            ("model_influencers", {"response": target, "predictors": factors}))
        add("decision_tree", _T("tree.t", "Rules that separate {t}", t=_h(target)),
            _T("tree.s", "Finds simple rules on the other columns that separate the values of {t}, tested on rows it did not see.",
               t=_h(target)),
            [target], {"target": target, "predictors": factors},
            ("model_tree", {"response": target, "predictors": factors}))
        add("automated_prediction", _T("predict.t", "How well can {t} be predicted", t=_h(target)),
            _T("predict.s", "Tries several models on {t} and reports how each does on rows held back.", t=_h(target)),
            [target], {"target": target, "predictors": factors})
    if len(numbers) >= 2:
        add("segment", _T("segment.t", "Groups of similar rows"),
            _T("segment.s", "Groups rows that resemble each other on {cols}.", cols=", ".join(_h(c) for c in numbers[:4])),
            numbers[:2], {"columns": numbers[:6]}, ("model_cluster", {"measures": numbers[:6]}))
        add("correlation_test", _T("together.t", "Do {a} and {b} move together", a=_h(numbers[0]), b=_h(numbers[1])),
            _T("together.s", "Measures how closely the two move together, and whether that could be chance."),
            numbers[:2], {"col_a": numbers[0], "col_b": numbers[1]})
    if numbers and len(kinds) >= 3:
        add("explain_response", _T("moves.t", "What moves {m}", m=_h(numbers[0])),
            _T("moves.s", "Ranks the other columns by how much {m} changes with them.", m=_h(numbers[0])),
            [numbers[0]], {"response": numbers[0]})
    if len(cats) >= 2:
        add("association_rules", _T("rules.t", "Values that appear together"),
            _T("rules.s", "Finds values of {cols} that occur together more often than chance.", cols=", ".join(_h(c) for c in cats[:4])),
            cats[:2], {"columns": cats[:8]}, ("model_rules", {"predictors": cats[:8]}))
    group = group_key(kinds, profile)
    things = [c for c, ks in kinds.items() if "item" in ks and c != group]
    if group and things:
        # The thing with the most values is what a group's lines list.
        thing = max(things, key=lambda c: (profile["columns"].get(c) or {}).get("distinct") or 0)
        add("basket_rules", _T("basket.t", "What occurs together in the same {g}", g=_h(group)),
            _T("basket.s", "Finds values of {thing} that turn up in the same {g} more often than chance.", thing=_h(thing), g=_h(group)),
            [group, thing], {"basket": group, "item": thing}, ("model_rules", {"basket": group, "item": thing}))
    if texts:
        add("text_topics", _T("topics.t", "What {c} talks about", c=_h(texts[0])),
            _T("topics.s", "Finds the subjects that recur in {c}.", c=_h(texts[0])), [texts[0]], {"column": texts[0]})
        add("text_sentiment", _T("tone.t", "Tone of {c}", c=_h(texts[0])),
            _T("tone.s", "Reads whether each text in {c} is positive or negative.", c=_h(texts[0])), [texts[0]], {"column": texts[0]})
    return cards


async def dataset_health(db, user, dataset) -> dict:
    """The dataset's health checks for one reader (services/discovery/health.py),
    from the kept profile; measured once when there is none. A reader with
    hidden columns is told nothing of them; one under a row rule gets the
    checks that are counts of the table, not the month-by-month volume."""
    from ...core.rls import resolve_denied_columns, resolve_rls_expr
    from . import health
    denied = set(await resolve_denied_columns(db, user, dataset.id) or [])
    rls_expr = await resolve_rls_expr(db, user, dataset.id)
    kept = await profile_store.stored(db, dataset)
    if kept is not None:
        profile, from_store = profile_store.for_reader(kept, denied, bool(rls_expr)), True
    else:
        from .. import suggest_inputs as sug
        inputs = await sug.prepare(db, user, dataset)
        profile, from_store = await profile_store.ensure(db, dataset, inputs.df, denied=denied,
                                                         row_rule=bool(rls_expr), type_map=inputs.type_map)
    kinds = column_kinds(profile, dataset.column_meta)
    dates = _pick(kinds, profile, "date")
    out = health.checks(profile, dates[0] if dates else None)
    return {"dataset_id": dataset.id, "version": profile_store.fingerprint(dataset), "from_store": from_store,
            "restricted": bool(profile.get("restricted")), **out}


#: A newest record older than this is worth saying.
STALE_HOURS = 48


def _profile_cards(profile: dict, kinds: dict[str, set[str]]) -> list[dict]:
    """What the stored profile shows by itself: values that are not what their
    column mostly holds, exact copies of rows, data that has stopped arriving.
    Counts only -- nothing here is a value of a row."""
    cards: list[dict] = []
    table = profile.get("table") or {}
    open_columns = {"kind": "open", "target": "columns"}
    for name, st in (profile.get("columns") or {}).items():
        wrong, count = st.get("mistyped") or 0, st.get("count") or 0
        if not wrong or not count:
            continue
        share = wrong / count
        num = st.get("holds") == "number"
        cards.append(_card(
            caps.profile_capability("mistyped_values"),
            _T("mistyped.num.t", "{n} values in {c} are not numbers", n=f"{wrong:,}", c=_h(name)) if num else
            _T("mistyped.text.t", "{n} values in {c} are not text", n=f"{wrong:,}", c=_h(name)),
            _T("mistyped.num.s" if num else "mistyped.text.s",
               ("{c} holds numbers in {pct}% of its rows; {n} values are something else and are left out of any calculation on it."
                if num else
                "{c} holds text in {pct}% of its rows; {n} values are something else and are left out of any calculation on it."),
               c=_h(name), pct=f"{100 - share * 100:.1f}", n=f"{wrong:,}"),
            [name], {**open_columns, "column": name},
            why={"reason": "evidence", "detail": _T("why.profiled", "Counted when the dataset was profiled.")},
            evidence={"band": "strong" if share >= 0.05 else "moderate" if share >= 0.01 else "weak",
                      "strength": round(min(share * 10, 1.0), 3), "kind": "data_quality",
                      "figures": {"count": wrong, "share_pct": round(share * 100, 2)}}))
    copies, measured = table.get("duplicates") or 0, table.get("measured_rows") or table.get("rows") or 0
    if copies and measured:
        share = copies / measured
        cards.append(_card(
            caps.profile_capability("duplicate_rows"), _T("copies.t", "{n} rows are exact copies of another row", n=f"{copies:,}"),
            _T("copies.s", "{pct}% of the rows repeat another row in every column; totals and counts include them.",
               pct=f"{share * 100:.1f}"),
            [], open_columns, why={"reason": "evidence", "detail": _T("why.profiled", "Counted when the dataset was profiled.")},
            evidence={"band": "strong" if share >= 0.05 else "moderate" if share >= 0.005 else "weak",
                      "strength": round(min(share * 10, 1.0), 3), "kind": "data_quality",
                      "figures": {"count": copies, "share_pct": round(share * 100, 2)}},
            limits=[_T("lim.sample", "Counted on a sample of the rows.")] if table.get("sampled") else None))
    dates = _pick(kinds, profile, "date")
    if dates:
        card = profile_store.card_of(dates[0], (profile.get("columns") or {}).get(dates[0]) or {})
        hours = card.get("delay_hours")
        if hours is not None and hours >= STALE_HOURS:
            days = hours / 24
            cards.append(_card(
                caps.profile_capability("data_delay"), _T("delay.t", "The newest {d} is {days} days old", d=_h(dates[0]), days=f"{days:,.0f}"),
                _T("delay.s", "No row is dated after {when}. Anything read as \"now\" or \"this month\" is as of then.",
                   when=str(card.get("max"))[:10]),
                [dates[0]], {**open_columns, "column": dates[0]},
                why={"reason": "evidence", "detail": _T("why.newest", "The latest value of the date a record begins on.")},
                evidence={"band": "strong" if days >= 30 else "moderate" if days >= 7 else "weak",
                          "strength": round(min(days / 90, 1.0), 3), "kind": "data_quality",
                          "figures": {"delay_hours": hours, "newest": card.get("max")}}))
    return cards


def _h(col: str) -> str:
    return " ".join(str(col).replace("_", " ").split())


def _T(key: str, template: str, **vars) -> Said:
    """A card's own words: the English text, with the key and pieces the
    browser says it with in the reader's language (`rb.card.<key>`)."""
    return _s("card." + key, template, **vars)


def _limit(card: dict, said) -> None:
    """Add one line to a card's limits, in step with its translations."""
    card["limits"] = [*card.get("limits", []), str(said)]
    card["limits_i18n"] = [*card.get("limits_i18n", [None] * (len(card["limits"]) - 1)), as_i18n(said)]


def _card(cap: caps.Capability, title: str, sentence: str, fields: list[str], action: dict, *,
          why: dict, evidence: dict | None = None, limits: list[str] | None = None,
          family: str | None = None, claim: str | None = None) -> dict:
    fam = family or cap.family
    # Text given as `Said` travels twice: as English, and as key + pieces.
    title_i18n, sentence_i18n = as_i18n(title), as_i18n(sentence)
    limits_i18n = [as_i18n(l) for l in (limits or [])]
    limits = [str(l) for l in (limits or [])]
    if isinstance(why.get("detail"), Said):
        why = {**why, "detail_i18n": as_i18n(why["detail"]), "detail": str(why["detail"])}
    title, sentence = str(title), str(sentence)
    body = {"capability": f"{cap.kind}:{cap.name}", "fields": fields, "action": action}
    return {
        "id": "sig:" + hashlib.sha1(json.dumps(body, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16],
        "capability": cap.name, "kind": cap.kind, "family": fam, "claim": claim or cap.claim,
        "title": title, "sentence": sentence, "why": why, "fields": fields,
        "title_i18n": title_i18n, "sentence_i18n": sentence_i18n, "limits_i18n": limits_i18n,
        # Never written by a model: measured, or absent.
        "evidence": evidence, "limits": limits or [],
        "cost": {"tier": cap.cost, "state": "ready"},
        "action": action, "next": _NEXT.get(fam, []), "llm": cap.llm, "source": "deterministic",
    }


def _band(finding: dict | None, score: float) -> str:
    if finding is not None and finding.get("significant") is False:
        return "weak"
    return "strong" if score >= STRONG else "moderate" if score >= MODERATE else "weak"


def evidence_cards(suggestions: list[dict], findings: list[dict]) -> list[dict]:
    """Cards for what the insight detectors FOUND, each already drawn on the
    reader's rows and passed through the shared gate (insights.py)."""
    by_title = {f.get("title"): f for f in findings}
    cards = []
    for s in suggestions:
        cap = caps.widget(s.get("widget_type"))
        if cap is None:
            continue
        title = str(s.get("title") or "")
        # A suggestion narrowed to one unit carries its finding's title plus
        # a suffix ("... (Voice)"): it is still that finding.
        finding = by_title.get(title) or next((f for t, f in by_title.items() if t and title.startswith(t)), None)
        kind = s.get("kind") or (finding or {}).get("kind") or "baseline"
        family, claim = _FINDING.get(kind, (cap.family, cap.claim))
        config = s.get("config") or {}
        fields = [v for k, v in config.items() if k in ("dimension", "dimension2", "measure", "measure2")
                  and isinstance(v, str)]
        fields = list(dict.fromkeys(fields))
        evidence = None
        # EVIDENCE is claimed only where a detector found something: a chart
        # offered for coverage (a total, a count by category, a mix) is a
        # basic, however high it was ranked for variety.
        if finding is None and kind != "rules":
            kind, family, claim = "baseline", "basics", "observation"
        if kind != "baseline":
            score = float((finding or {}).get("score") or s.get("score") or 0)
            evidence = {"band": _band(finding, score), "strength": round(min(score, 1.0), 3), "kind": kind}
            if finding:
                if finding.get("p_value") is not None:
                    evidence["p_value"] = finding["p_value"]
                evidence["figures"] = finding.get("figures") or {}
                if isinstance(finding.get("evidence"), dict):
                    evidence["test"] = finding["evidence"]
        limits = []
        if claim == "association":
            limits.append("Shows that the two go together, not that one causes the other.")
        card = _card(cap, s.get("title") or cap.name,
                     s.get("takeaway") or (finding or {}).get("detail") or s.get("reason") or "",
                     fields, {"kind": "add_widget", "widget_type": s["widget_type"], "config": config},
                     why={"reason": "evidence" if evidence else "basics",
                          "detail": (finding or {}).get("detail") or s.get("reason") or ""},
                     evidence=evidence, limits=limits, family=family, claim=claim)
        # What the suggestion pane already reads of a server idea: the reason
        # as written, whether it bears on the page's purpose, and the sentence
        # as a key it can say in the reader's language.
        card["suggestion"] = {"kind": s.get("kind"), "reason": s.get("reason"), "aligned": bool(s.get("aligned")),
                              "takeaway": s.get("takeaway"), "takeaway_i18n": s.get("takeaway_i18n")}
        cards.append(card)
    return cards


#: Months of dates a headline number needs before its history is worth showing.
HISTORY_MIN_PERIODS = 3


def _with_history(cards: list[dict], kinds: dict, profile: dict, column_meta: dict | None) -> None:
    """A headline number is offered WITH its recent history when the table has
    a date its records begin on: the card then shows a sparkline and the
    change against the previous period (widget_data.kpi_trend). Which way is
    good comes from the column's stored direction; with none, no colour."""
    dates = _pick(kinds, profile, "date")
    if not dates or ((profile.get("columns") or {}).get(dates[0]) or {}).get("periods", 0) < HISTORY_MIN_PERIODS:
        return
    for card in cards:
        action = card.get("action") or {}
        if action.get("kind") != "add_widget" or action.get("widget_type") != "kpi":
            continue
        config = action.setdefault("config", {})
        if config.get("dimension") or config.get("sparkline_date"):
            continue
        config["sparkline_date"] = dates[0]
        direction = guard.direction_of(config.get("measure"), column_meta)
        if direction in ("higher_better", "higher_worse"):
            config["trend_good"] = "up" if direction == "higher_better" else "down"
        _limit(card, _T("lim.history", "The change compares the last complete period with the one before it, and with "
                                       "the same period a year before when the history reaches that far."))


#: Calendar readings (second reference set). A weekday needs enough weeks to
#: be a habit rather than one week's accident; a time of day needs most
#: values to carry one, over most of the day; a year needs another to sit beside.
CALENDAR_MIN_DAYS = 28
CALENDAR_TIMED = 0.5
CALENDAR_HOURS = 6
CALENDAR_YEARS = 2
CALENDAR_YEAR_PERIODS = 13
#: More lines than this on one chart cannot be told apart; the grid still can.
CALENDAR_MAX_LINES = 6


def _calendar_cards(profile: dict, kinds: dict, column_meta: dict | None) -> list[dict]:
    """What a date's position in the week, the day and the year can show:
    when things happen (weekday x hour), each year over the months, and the
    year x month grid. From the stored figures of the date the records begin
    on -- nothing is read, and nothing here knows what the records are."""
    dates = _pick(kinds, profile, "date")
    if not dates:
        return []
    date = dates[0]
    st = (profile.get("columns") or {}).get(date) or {}
    additive = _pick(kinds, profile, "additive")
    measure = additive[0] if additive else None
    what = _h(measure) if measure else "rows"
    base = ({"measure": measure, "aggregation": "sum"} if measure
            else {"measure": date, "aggregation": "count"})
    grid, line = caps.widget("heatmap"), caps.widget("line")
    fields = [date, *([measure] if measure else [])]
    why = {"reason": "fit", "detail": _T("why.calendar", "The dates cover enough of the calendar for this; nothing has been computed yet.")}
    cards: list[dict] = []

    def add(cap, title, sentence, config, limit):
        if cap is not None:
            cards.append(_card(cap, title, sentence, fields,
                               {"kind": "add_widget", "widget_type": cap.name,
                                # A line counts rows with no measure named; a grid needs one to count.
                                "config": {**(base if measure or cap.name == "heatmap" else {"aggregation": "count"}),
                                           **config}},
                               why=why, limits=[limit], family="trend"))

    days, hours = st.get("days") or 0, st.get("hours") or 0
    if days >= CALENDAR_MIN_DAYS and (st.get("timed") or 0) >= CALENDAR_TIMED and hours >= CALENDAR_HOURS:
        add(grid, _T("weekhour.rows.t", "When rows happen: weekday and hour") if not measure else
            _T("weekhour.t", "{m} by weekday and hour", m=what),
            _T("weekhour.rows.s", "A grid of rows for every day of the week against every hour of the day, by {d}.", d=_h(date))
            if not measure else
            _T("weekhour.s", "A grid of {m} for every day of the week against every hour of the day, by {d}.", m=what, d=_h(date)),
            {"dimension": date, "dimension_granularity": "weekday",
             "dimension2": date, "dimension2_granularity": "hour_of_day"},
            _T("lim.hours", "Hours are as stored; no time zone is applied."))
    years = st.get("years") or 0
    if years >= CALENDAR_YEARS and (st.get("periods") or 0) >= CALENDAR_YEAR_PERIODS:
        add(line if years <= CALENDAR_MAX_LINES else None, (_T("years.t", "Each year of {m} over the months", m=what) if measure else _T("years.rows.t", "Each year of rows over the months")),
            _T("years.s", "One line per year of {d}, month by month, so the same month can be compared across years.", d=_h(date)),
            {"dimension": date, "dimension_granularity": "month_of_year",
             "dimension2": date, "dimension2_granularity": "year"},
            _T("lim.year", "The year the data stops inside is drawn as far as its last complete month."))
        add(caps.widget("bar"), (_T("twoyears.t", "The last two years of {m}, month against month", m=what) if measure else
                                 _T("twoyears.rows.t", "The last two years of rows, month against month")),
            _T("twoyears.s", "Each month of the latest year of {d} beside the same month a year before.", d=_h(date)),
            {"dimension": date, "dimension_granularity": "month_of_year",
             "dimension2": date, "dimension2_granularity": "year",
             "filters": [{"column": date, "op": "relative",
                          "value": {"mode": "last", "unit": "year", "n": 2, "include_current": True,
                                    "anchor": "data_max"}}]},
            _T("lim.twoyears", "The latest year is drawn as far as its last complete month; the two years are counted back "
                               "from the newest date in the data."))
        add(grid, _T("yearmonth.t", "{m} by year and month", m=what) if measure else _T("yearmonth.rows.t", "Rows by year and month"),
            _T("yearmonth.s", "A grid of {m} for every year of {d} against every month of the year.", m=what, d=_h(date)) if measure
            else _T("yearmonth.rows.s", "A grid of rows for every year of {d} against every month of the year.", d=_h(date)),
            {"dimension": date, "dimension_granularity": "year",
             "dimension2": date, "dimension2_granularity": "month_of_year"},
            _T("lim.emptymonth", "A month with no rows is left empty, not shown as zero, unless rows are counted."))
    return cards


#: Two numbers are offered against each other only when they are recorded in
#: the same unit and are of the same size (their averages within this factor):
#: a difference of two things measured differently is not a number. The size
#: test is tight on purpose: on real data a fee and the price of the thing it
#: was charged on share a unit and sit within 3x of each other, and their
#: difference means nothing (checked 2026-10-11). A yardstick for a number is
#: of that number's size.
PAIR_SIZE = 1.5
PAIR_MAX = 2


def comparable_pairs(profile: dict, kinds: dict, column_meta: dict | None) -> list[tuple[str, str]]:
    """Pairs of numbers that add up, share a recorded unit, and are of the
    same size -- from the classification and the stored figures. Which of the
    two is the yardstick is not something the data says: the pair is offered
    in the table's own column order, and the limits line says so."""
    meta = column_meta or {}
    unit = lambda c: str((meta.get(c) or {}).get("unit") or "").strip().casefold() if isinstance(meta.get(c), dict) else ""  # noqa: E731
    mean = lambda c: ((profile.get("columns") or {}).get(c) or {}).get("mean")                                       # noqa: E731
    numbers = [c for c in (profile.get("columns") or {}) if c in set(_pick(kinds, profile, "additive"))]
    pairs = []
    for i, a in enumerate(numbers):
        for b in numbers[i + 1:]:
            ma, mb = mean(a), mean(b)
            if not unit(a) or unit(a) != unit(b) or not ma or not mb or ma * mb <= 0:
                continue
            if max(abs(ma), abs(mb)) / min(abs(ma), abs(mb)) <= PAIR_SIZE:
                pairs.append((a, b))
    return pairs[:PAIR_MAX]


def _pair_cards(fits: list[caps.Capability], profile: dict, kinds: dict, column_meta: dict | None) -> list[dict]:
    """One number against another: where the difference sits, the bridge from
    one to the other, and the grid of the difference over time."""
    pairs = comparable_pairs(profile, kinds, column_meta)
    cats, dates = _pick(kinds, profile, "category"), _pick(kinds, profile, "date")
    if not pairs or not cats:
        return []
    fit_names = {c.name for c in fits if c.kind == "analysis"}
    why = {"reason": "fit", "detail": _T("why.pair", "The two numbers are recorded in the same unit and are of the same size; "
                                                     "nothing has been computed yet.")}
    order = _T("lim.yardstick", "The data does not say which of the two is the yardstick: swap them if it reads the wrong way round.")
    cards = []
    for a, b in pairs:
        cap = caps.analysis("explain_variance")
        if cap is not None and "explain_variance" in fit_names:
            cards.append(_card(cap, _T("differ.t", "Where {a} and {b} differ", a=_h(a), b=_h(b)),
                               _T("differ.s", "Sets {a} against {b} and splits the difference by each category.", a=_h(a), b=_h(b)),
                               [a, b], {"kind": "run_analysis", "analysis": "explain_variance",
                                        "params": {"measure": a, "reference": b, "aggregation": "sum"}},
                               why=why, limits=[order]))
        bridge = caps.widget("waterfall")
        if bridge is not None:
            cards.append(_card(bridge, _T("bridge.t", "From {b} to {a}, by {c}", a=_h(a), b=_h(b), c=_h(cats[0])),
                               _T("bridge.s", "Starts at the total of {b}, adds each {c}'s difference, and arrives at the total of {a}.",
                                  a=_h(a), b=_h(b), c=_h(cats[0])),
                               [a, b, cats[0]], {"kind": "add_widget", "widget_type": "waterfall",
                                                 "config": {"dimension": cats[0], "measure": a, "aggregation": "sum",
                                                            "bridge_from": b}},
                               why=why, limits=[order], family="compare"))
        grid = caps.widget("heatmap")
        if grid is not None and dates and ((profile.get("columns") or {}).get(dates[0]) or {}).get("periods", 0) >= HISTORY_MIN_PERIODS:
            cards.append(_card(grid, _T("minus.t", "{a} minus {b}, by {c} and month", a=_h(a), b=_h(b), c=_h(cats[0])),
                               _T("minus.s", "A grid of the difference for every {c} in every month of {d}, coloured by its sign.",
                                  c=_h(cats[0]), d=_h(dates[0])),
                               [a, b, cats[0], dates[0]],
                               {"kind": "add_widget", "widget_type": "heatmap",
                                "config": {"dimension": cats[0], "dimension2": dates[0], "dimension2_granularity": "month",
                                           "measure": a, "aggregation": "sum", "difference_of": b}},
                               why=why, limits=[order], family="compare"))
    return cards


#: A finish date is one that is empty on some rows and filled on others: the
#: rows still going. Outside this range it is a date like any other.
OPEN_MIN, OPEN_MAX = 0.005, 0.95
STAGES_MIN, STAGES_MAX = 3, 12


def stage_columns(profile: dict, kinds: dict, column_meta: dict | None) -> dict | None:
    """The columns a stage board reads, found from the stored figures: the
    date rows begin on; a date that is empty on some rows (the finish, and so
    which rows are open); another complete date whose middle falls after the
    start's (the due date); and a category of 3 to 12 values to stand as the
    stage -- one with a stored order first. None unless there is a finish
    date: without one, nothing says which rows are still going."""
    columns = profile.get("columns") or {}
    dates = _pick(kinds, profile, "date")
    if not dates:
        return None
    start = dates[0]
    every_date = [c for c, ks in kinds.items() if "date" in ks or (columns.get(c) or {}).get("kind") == "date"]

    def empty_share(c):
        st = columns.get(c) or {}
        return (st.get("missing") or 0) / st["count"] if st.get("count") else 0.0
    finish = [c for c in every_date if c != start and OPEN_MIN <= empty_share(c) <= OPEN_MAX]
    if not finish:
        return None
    done = max(finish, key=empty_share)
    mid = lambda c: str((columns.get(c) or {}).get("median") or "")       # noqa: E731
    due = next((c for c in every_date if c not in (start, done) and empty_share(c) < OPEN_MIN
                and mid(c) and mid(start) and mid(c) >= mid(start)), None)
    meta = column_meta or {}
    stages = [c for c in _pick(kinds, profile, "category")
              if STAGES_MIN <= ((columns.get(c) or {}).get("distinct") or 0) <= STAGES_MAX]
    if not stages:
        return None
    ordered = [c for c in stages if isinstance(meta.get(c), dict) and (meta[c].get("order") or meta[c].get("outcome"))]
    return {"stage_col": (ordered or stages)[0], "start_date": start, "done_date": done, "due_date": due}


def _stage_cards(fits: list[caps.Capability], profile: dict, kinds: dict, column_meta: dict | None) -> list[dict]:
    cap = caps.analysis("stage_board")
    if cap is None or "stage_board" not in {c.name for c in fits if c.kind == "analysis"}:
        return []
    found = stage_columns(profile, kinds, column_meta)
    if not found:
        return []
    return [_card(cap, _T("stage.t", "Where rows stand, by {c}", c=_h(found["stage_col"])),
                  _T("stage.due.s", "Counts rows in each {c}, how long the ones with no {done} have been going, and what is "
                                    "overdue against {due}.", c=_h(found["stage_col"]), done=_h(found["done_date"]),
                     due=_h(found["due_date"])) if found["due_date"] else
                  _T("stage.s", "Counts rows in each {c}, how long the ones with no {done} have been going.",
                     c=_h(found["stage_col"]), done=_h(found["done_date"])),
                  [found["stage_col"], found["start_date"], found["done_date"], *([found["due_date"]] if found["due_date"] else [])],
                  {"kind": "run_analysis", "analysis": "stage_board", "params": found},
                  why={"reason": "fit", "detail": _T("why.stage", "{done} is empty on some rows: those are still going. "
                                                                  "Nothing has been computed yet.", done=_h(found["done_date"]))},
                  limits=[_T("lim.now", "\"Now\" is the newest date in the data, not today."),
                          _T("lim.stagepick", "Which column is the stage was picked from the table's shape: change it if it reads wrong.")])]


#: Two-group readings offered at most, and the fewest rows the smaller group
#: must hold (the analysis' own minimum).
TWO_GROUP_CARDS = 2
TWO_GROUP_ROWS = 30


def two_valued(profile: dict, kinds: dict) -> list[str]:
    """Columns that split the rows into exactly two groups, each big enough
    -- read off the stored counts of each column's values."""
    out = []
    for name, st in (profile.get("columns") or {}).items():
        top = st.get("top") or []
        if st.get("distinct") != 2 or len(top) != 2 or name not in kinds:
            continue
        if kinds[name] & {"date", "key"} or min(int(top[0][1]), int(top[1][1])) < TWO_GROUP_ROWS:
            continue
        out.append(name)
    return out


def _two_group_cards(fits: list[caps.Capability], profile: dict, kinds: dict, column_meta: dict | None) -> list[dict]:
    """Two groups side by side on the outcome that matters (or, with none, on
    the first number): rate or average, difference, lift, how sure."""
    cap = caps.analysis("compare_two_groups")
    if cap is None or "compare_two_groups" not in {c.name for c in fits if c.kind == "analysis"}:
        return []
    outcomes = _pick(kinds, profile, "outcome")
    numbers = _pick(kinds, profile, "additive") + _pick(kinds, profile, "level")
    worth = sorted((c for c, e in (column_meta or {}).items() if isinstance(e, dict)
                    and e.get("target_candidate_priority") is not None and c in kinds),
                   key=lambda c: -(column_meta[c].get("target_candidate_priority") or 0))
    what = (worth or outcomes or numbers or [None])[0]
    if not what:
        return []
    cards = []
    for group in [g for g in two_valued(profile, kinds) if g != what][:TWO_GROUP_CARDS]:
        cards.append(_card(cap, _T("groups.t", "{w} in the two groups of {g}", w=_h(what), g=_h(group)),
                           _T("groups.s", "Sets the two values of {g} side by side on {w}: how far apart they are, "
                                          "and how sure that is.", w=_h(what), g=_h(group)),
                           [group, what], {"kind": "run_analysis", "analysis": "compare_two_groups",
                                           "params": {"group_col": group, "outcome": what}},
                           why={"reason": "fit", "detail": _T("why.groups", "The column splits the rows into two groups of "
                                                                            "enough rows; nothing has been computed yet.")},
                           limits=[_T("lim.random", "A difference is the effect of the group only if rows were put in their "
                                                    "groups at random.")]))
    return cards


#: Discovery ideas handed to a dashboard designer at most.
CANDIDATES_MAX = 8


def candidates(df, type_map: dict | None, column_meta: dict | None, section_of=None, tiles: bool = False) -> list[dict]:
    """What a look at the rows FOUND, as candidates for a designer that builds
    whole dashboards (the analyst panel): only cards kept WITH evidence -- a
    weekly rhythm, a season, two numbers that move together, a stage column
    that separates open rows -- each as the widget that draws it. They go
    through that designer's own gate, drawing and selection like any other
    idea; this only makes sure they are on the table.

    `section_of(widget_type, config)` names the page a widget belongs on.
    Analysis tiles are left out unless `tiles`: a designer that scores what a
    chart drew has no way to score them."""
    from . import evidence
    profile = profile_store.compute(df, type_map)
    base = tier0(profile, column_meta)
    cards, _ = evidence.look(list(base["cards"]), df, column_meta)
    _with_tiles(cards)
    out, seen = [], set()
    for card in cards:
        ev = card.get("evidence")
        if not ev or card.get("kind") == "profile":
            continue
        action = card.get("action") or {}
        widget = ({"widget_type": action["widget_type"], "config": action["config"]} if action.get("kind") == "add_widget"
                  else card.get("tile") if tiles else None)
        if not widget:
            continue
        # One idea per finding: the three yearly cards share one season.
        key = (ev.get("kind"), json.dumps(ev.get("figures"), sort_keys=True, default=str))
        if key in seen:
            continue
        seen.add(key)
        out.append({"question": card["title"], "widget_type": widget["widget_type"], "title": card["title"],
                    "why": card.get("found") or card.get("sentence") or "", "config": dict(widget["config"]),
                    "value": 4 if ev.get("band") == "strong" else 3, "audience": "manager",
                    "section": section_of(widget["widget_type"], widget["config"]) if section_of else "summary",
                    "source": "discovery", "takeaway_i18n": card.get("found_i18n")})
        if len(out) >= CANDIDATES_MAX:
            break
    return out


def _with_tiles(cards: list[dict]) -> None:
    """An analysis that can sit on a page says how: `tile` is the widget that
    draws it there, with the parameters the card ended up with (after the
    look at the rows chose, say, which column is the stage)."""
    from ..model_widgets import TILE_ANALYSES
    for card in cards:
        action = card.get("action") or {}
        if action.get("kind") == "run_analysis" and action.get("analysis") in TILE_ANALYSES:
            card["tile"] = {"widget_type": "analysis_result",
                            "config": {"analysis": action["analysis"], "params": dict(action.get("params") or {})}}


def _with_targets(cards: list[dict], kinds: dict, profile: dict, column_meta: dict | None) -> None:
    """A headline number whose author stored a target is offered against it.
    Only a stored target: none is ever proposed. A target for a period needs
    the number's history at that size, so the card asks for it."""
    dates = _pick(kinds, profile, "date")
    for card in cards:
        action = card.get("action") or {}
        if action.get("kind") != "add_widget" or action.get("widget_type") != "kpi":
            continue
        config = action.setdefault("config", {})
        stored = guard.target_of(config.get("measure"), column_meta)
        if stored is None or config.get("target_value") is not None:
            continue
        value, period = stored
        if period:
            if not dates:
                continue
            config.setdefault("sparkline_date", dates[0])
            config["sparkline_granularity"] = period
            config["target_period"] = period
        config["target_value"] = value
        direction = guard.direction_of(config.get("measure"), column_meta)
        if direction in ("higher_better", "higher_worse"):
            config.setdefault("trend_good", "up" if direction == "higher_better" else "down")
        _limit(card, _T(f"lim.target.{period}", "The target is the one stored for this column, for each " + period + ".")
               if period else _T("lim.target", "The target is the one stored for this column."))


# ── ranking ──────────────────────────────────────────────────────────────────
def _goal_words(goal: str | None) -> set[str]:
    return {w.casefold() for w in _WORD.findall(goal or "")}


def _matches(card: dict, words: set[str], labels: dict[str, str]) -> bool:
    if not words:
        return False
    for f in card["fields"]:
        text = f"{f} {labels.get(f, '')}"
        parts = {p.casefold() for p in _WORD.findall(text)}
        if parts & words or any(len(w) >= 4 and any(p.startswith(w[:4]) for p in parts) for w in words):
            return True
    return False


_BAND_RANK = {"strong": 3, "moderate": 2, "weak": 1}


def rank(cards: list[dict], goal: str | None = None, labels: dict[str, str] | None = None,
         limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Order by measured things only: does it bear on what was asked; how
    strong is the evidence (in bands); what does it cost. Then no family and
    no single column takes more than its share, and nothing is offered twice."""
    words = _goal_words(goal)
    for c in cards:
        c["relevance"] = {"matches_goal": _matches(c, words, labels or {})} if words else None

    def key(c):
        ev = c.get("evidence") or {}
        return (-(1 if (c.get("relevance") or {}).get("matches_goal") else 0),
                -_BAND_RANK.get(ev.get("band"), 0), c["cost"]["tier"], -(ev.get("strength") or 0))
    out, seen, per_family = [], set(), {}
    for c in sorted(cards, key=key):
        if c["id"] in seen:
            continue
        if per_family.get(c["family"], 0) >= PER_FAMILY and not (c.get("relevance") or {}).get("matches_goal"):
            continue
        seen.add(c["id"])
        per_family[c["family"]] = per_family.get(c["family"], 0) + 1
        out.append(c)
        if len(out) >= limit:
            break
    return out


# ── the two tiers ────────────────────────────────────────────────────────────
def table_of(profile: dict, kinds: dict, structure: dict | None) -> dict:
    st = profile.get("columns") or {}
    periods = max([(st.get(c) or {}).get("periods") or 0 for c, ks in kinds.items() if "date" in ks] or [0])
    shape = dict(structure or (profile.get("table") or {}).get("structure") or {})
    # One row per (group, thing): read from the stored figures, not declared.
    shape["transactions"] = bool(group_key(kinds, profile)) and any("item" in ks for ks in kinds.values())
    return {"rows": (profile.get("table") or {}).get("rows") or 0, "periods": periods,
            "usable": list(kinds), "structure": shape}


def tier0(profile: dict, column_meta: dict | None, structure: dict | None = None) -> dict:
    """What the data supports -- from what is stored; no row is read."""
    kinds = column_kinds(profile, column_meta)
    table = table_of(profile, kinds, structure)
    yes, no = supported(kinds, table)
    return {"kinds": kinds, "table": table, "supports": yes, "not_offered": no,
            "cards": _profile_cards(profile, kinds) + _analysis_cards(yes, kinds, profile, column_meta)
                     + _calendar_cards(profile, kinds, column_meta)
                     + _pair_cards(yes, profile, kinds, column_meta)
                     + _two_group_cards(yes, profile, kinds, column_meta)
                     + _stage_cards(yes, profile, kinds, column_meta)}


def cache_key(dataset, version: str, goal: str | None, reader: str, column_meta: dict | None) -> str:
    classes = {c: {k: e.get(k) for k in ("number", "level", "outcome", "geo_level", "direction", "role",
                                          "eligible_for_suggestion", "hidden")}
               for c, e in (column_meta or {}).items() if isinstance(e, dict) and not str(c).startswith("__")}
    body = json.dumps([dataset.id, version, (goal or "").strip().casefold(), reader, classes],
                      sort_keys=True, default=str)
    return "disc:1:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


async def opportunities(db, user, dataset, goal: str | None = None, *, depth: int = 1,
                        limit: int = DEFAULT_LIMIT, fresh: bool = False) -> dict:
    """The cards for one reader. `depth=0`: what the data supports, from the
    store (no row read when the profile is kept). `depth=1`: also what it shows."""
    import asyncio
    from ...core.rls import resolve_denied_columns, resolve_rls_expr
    from ..widget_shaping import get_cache_backend

    denied = set(await resolve_denied_columns(db, user, dataset.id) or [])
    rls_expr = await resolve_rls_expr(db, user, dataset.id)
    reader = hashlib.sha256(json.dumps([sorted(denied), rls_expr or ""]).encode("utf-8")).hexdigest()[:16]
    version = profile_store.fingerprint(dataset)
    labels = {c: str(e.get("label") or "") for c, e in (dataset.column_meta or {}).items() if isinstance(e, dict)}

    cache = get_cache_backend()
    key = cache_key(dataset, version, goal, f"{reader}:{depth}:{limit}", dataset.column_meta)
    if not fresh:
        try:
            hit = cache.get(key)
        except Exception:                                       # noqa: BLE001 -- a cache that fails is a miss
            hit = None
        if isinstance(hit, (bytes, bytearray, str)):       # the shared cache stores bytes
            try:
                hit = json.loads(hit)
            except ValueError:
                hit = None
        if isinstance(hit, dict):
            return {**hit, "cached": True}

    kept = await profile_store.stored(db, dataset)
    inputs = None
    if kept is None or depth >= 1:
        # The rows are needed: to measure the profile once, or to look for
        # evidence. Read exactly as every designer reads them (row rules,
        # hidden columns, preparation steps): services/suggest_inputs.py.
        from .. import suggest_inputs as sug
        inputs = await sug.prepare(db, user, dataset)
    if kept is not None:
        profile, from_store = profile_store.for_reader(kept, denied, bool(rls_expr)), True
    else:
        profile, from_store = await profile_store.ensure(db, dataset, inputs.df, denied=denied,
                                                         row_rule=bool(rls_expr), type_map=inputs.type_map)
        if not (denied or rls_expr):
            # Keep what the frame told us about the table's structure too.
            await profile_store.keep_structure(db, dataset, (inputs.profile or {}).get("structure") or {})
    column_meta = (inputs.column_meta if inputs is not None else dataset.column_meta) or {}
    structure = {k: bool(v) for k, v in ((inputs.profile or {}).get("structure") or {}).items()} if inputs is not None else None

    base = tier0(profile, column_meta, structure)
    cards = list(base["cards"])
    findings: list[dict] = []
    withheld: list[dict] = []
    if depth >= 1 and inputs is not None:
        from ..insights import effective_roles, generate_insights, suggest_widgets_from_findings
        result = await asyncio.to_thread(generate_insights, inputs.df, inputs.type_map, column_meta)
        findings = result.get("findings") or []
        roles = effective_roles(inputs.type_map, column_meta)
        suggestions = await asyncio.to_thread(
            suggest_widgets_from_findings, findings, roles, goal or dataset.description,
            ineligible=inputs.ineligible(), column_meta=column_meta, frame=inputs.df)
        cards = evidence_cards(suggestions, findings) + cards
        # The cards offered because the table COULD support them are checked
        # on the rows now in hand: kept with what was found, or withheld with
        # the reason (services/discovery/evidence.py).
        from . import evidence
        cards, withheld = await asyncio.to_thread(evidence.look, cards, inputs.df, column_meta)

    _with_history(cards, base["kinds"], profile, column_meta)
    _with_targets(cards, base["kinds"], profile, column_meta)
    _with_tiles(cards)
    ranked = rank(cards, goal, labels, limit)
    out = {
        "dataset_id": dataset.id, "profile_version": version, "profile_from_store": from_store,
        "rows": base["table"]["rows"], "depth": depth, "mode": "deterministic", "goal": (goal or "").strip() or None,
        "cards": ranked,
        # Offered by the table's shape, looked at on the rows, and not worth showing: each with why.
        "withheld": withheld,
        "supports": sorted({c.name for c in base["supports"]}),
        "not_offered": _why_not(base["not_offered"], {c.family for c in base["supports"] if c.kind == "widget"}),
        "restricted": bool(profile.get("restricted")), "cached": False,
    }
    try:
        # Under the key of the column settings as they are NOW: the first look
        # at a dataset classifies its columns, and the next request must find
        # this answer rather than compute it again.
        await db.refresh(dataset)
        key = cache_key(dataset, version, goal, f"{reader}:{depth}:{limit}", dataset.column_meta)
        cache.set(key, out, CACHE_TTL_S)
    except Exception:                                           # noqa: BLE001
        logger.warning("discovery: the cards could not be cached", exc_info=True)
    return out


def _why_not(refused: list[dict], open_families: set[str] = frozenset()) -> list[dict]:
    """What this data does not support and why: every analysis, and one line
    per kind of chart (ten map types refused for the same reason are one fact)."""
    out, seen = [], set()
    for n in refused:
        if n["kind"] == "analysis":
            out.append(n)
            continue
        # A family is "not supported" only when NONE of its charts fits: one
        # exotic chart needing three numbers does not mean no trend can be drawn.
        if n["family"] in open_families:
            continue
        key = (n["family"], n["reason"])
        if key in seen:
            continue
        seen.add(key)
        out.append({**n, "capability": n["family"], "kind": "chart family"})
    return out[:40]


async def column_profile(db, user, dataset) -> dict:
    """Every column's profile card for one reader: valid / unique / mistyped /
    missing, the most and least common value, text lengths, the shape values
    share, how old the newest date is. From the store when the profile is
    kept; measured once (on the reader's own rows) when it is not."""
    from ...core.rls import resolve_denied_columns, resolve_rls_expr
    denied = set(await resolve_denied_columns(db, user, dataset.id) or [])
    rls_expr = await resolve_rls_expr(db, user, dataset.id)
    kept = await profile_store.stored(db, dataset)
    if kept is not None:
        profile, from_store = profile_store.for_reader(kept, denied, bool(rls_expr)), True
    else:
        from .. import suggest_inputs as sug
        inputs = await sug.prepare(db, user, dataset)
        profile, from_store = await profile_store.ensure(db, dataset, inputs.df, denied=denied,
                                                         row_rule=bool(rls_expr), type_map=inputs.type_map)
    table = profile.get("table") or {}
    return {"dataset_id": dataset.id, "version": profile_store.fingerprint(dataset), "from_store": from_store,
            "rows": table.get("rows"), "measured_rows": table.get("measured_rows"), "sampled": bool(table.get("sampled")),
            "duplicates": table.get("duplicates"), "restricted": bool(profile.get("restricted")),
            "columns": [profile_store.card_of(name, st) for name, st in (profile.get("columns") or {}).items()]}
