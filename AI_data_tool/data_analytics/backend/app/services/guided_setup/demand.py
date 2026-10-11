"""What the person wants, as one checked record (docs/guided-setup/PLAN_V2.md, 3).

Every step of the setup understood the person, and every step forgot: the
request travelled as loose text ("hints, never rules"), so someone who asked
for one kind of thing got a dashboard of everything and a filter to find it.

The Demand is written ONCE, from everything they said -- "About you", the
dataset they chose and why it was proposed, what they typed in its chat --
and then it is binding on the check and on the dashboard:

* `sentence`   what they want, in one plain line, shown back to them;
* `questions`  the 3-6 questions the dashboard must answer, most important first;
* `scope`      the part of the data they asked for, as real filters.

Nothing here knows a domain. A scope is never trusted as the model wrote it:
`resolve_scope` finds the column and the values in the rows themselves
(as the person may read them) and counts what matches. A subject the data
does not hold is reported as "unmatched" with what the data does hold --
never quietly dropped, and never replaced by everything.
"""
from __future__ import annotations

import logging
import re

import pandas as pd

logger = logging.getLogger(__name__)

MAX_QUESTIONS = 6
#: Columns described to the model, and values listed for a column of few values.
PROMPT_COLUMNS = 45
LIST_VALUES_UP_TO = 60
LISTED_VALUES = 25
EXAMPLE_VALUES = 6
#: A text column with more distinct values than this is not searched for a subject.
SEARCH_VALUES_UP_TO = 2000
CANDIDATE_COLUMNS = 4
CANDIDATE_VALUES = 12

OPS = ("in", "gt", "gte", "lt", "lte")

_LANGUAGE = {"ar": "Arabic (Modern Standard, simple words)", "en": "English"}

DEMAND_SCHEMA = {
    "type": "object",
    "properties": {
        "sentence": {"type": "string"},
        "who": {"type": "string"},
        "subject": {"type": "string"},
        "questions": {"type": "array", "items": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "asked": {"type": "boolean"}},
            "required": ["text", "asked"]}},
        "exclude": {"type": "array", "items": {"type": "string"}},
        "not_in_data": {"type": "array", "items": {"type": "string"}},
        "scope": {"type": "array", "items": {
            "type": "object",
            "properties": {"dataset": {"type": "string"}, "said": {"type": "string"},
                           "column": {"type": "string"}, "op": {"type": "string"},
                           "values": {"type": "array", "items": {"type": "string"}}},
            "required": ["dataset", "said", "column", "op", "values"]}},
    },
    "required": ["sentence", "who", "subject", "questions", "exclude", "not_in_data", "scope"],
}


# ── the data, as the model is shown it ──────────────────────────────────────

def _is_number(s: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(s) and s.dtype != bool


def _is_date(s: pd.Series) -> bool:
    return pd.api.types.is_datetime64_any_dtype(s)


def _fmt(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{f:,.0f}" if abs(f) >= 1000 or f == int(f) else f"{f:,.2f}"


def profile_text(df: pd.DataFrame) -> str:
    """One line per column: what it holds and, for a column of few values, the values."""
    lines = []
    for col in list(df.columns)[:PROMPT_COLUMNS]:
        s = df[col]
        if _is_number(s):
            q = s.dropna()
            desc = (f"number, {_fmt(q.min())} to {_fmt(q.max())}, typical {_fmt(q.median())}"
                    if len(q) else "number, empty")
        elif _is_date(s):
            q = s.dropna()
            desc = f"date, {str(q.min())[:10]} to {str(q.max())[:10]}" if len(q) else "date, empty"
        else:
            q = s.dropna().astype(str)
            n = int(q.nunique())
            counts = q.value_counts()
            if n <= LIST_VALUES_UP_TO:
                shown = list(counts.index[:LISTED_VALUES])
                more = f" (+{n - len(shown)} more)" if n > len(shown) else ""
                desc = f"text, {n} values: " + " | ".join(shown) + more
            else:
                desc = f"text, {n:,} different values, e.g. " + " | ".join(counts.index[:EXAMPLE_VALUES])
        lines.append(f"- `{col}`: {desc}")
    return "\n".join(lines)


def _said(brief: dict | None, proposals: list[dict], edits: list[str]) -> str:
    """Everything the person typed, for the plain fallback's word search."""
    parts = [str(v) for v in (brief or {}).values() if v]
    for p in proposals:
        parts += [m.get("text", "") for m in p.get("history") or [] if m.get("role") == "user"]
    parts += edits
    return "\n".join(parts)


def build_prompt(brief: dict | None, datasets: list[dict], edits: list[str], lang: str,
                 earlier: dict | None = None) -> list[dict]:
    """`datasets`: [{"name", "rows", "profile", "proposal"}] -- the proposal is
    the step-2 suggestion the dataset was made from, with its chat, or None."""
    system = (
        "You write down what one person wants from their data, so that a dashboard can be built "
        "for exactly that. You are given what they said about themselves, the dataset(s) they "
        "chose and the columns in them.\n"
        "- sentence: what they want to see, in ONE plain sentence, in their own vocabulary, "
        "starting with the subject (shaped like '<the thing they care about>: <what about it>, by "
        "<group> and by <period>', in their words). Never mention columns, tables or SQL.\n"
        "- who: who they are, in a few words; '' when they did not say.\n"
        "- subject: the thing they care about, in two or three words; '' when they want everything.\n"
        f"- questions: the {3}-{MAX_QUESTIONS} questions THIS person needs answered and these columns can "
        "answer, most important first. Use what they asked for; when they asked for little, add "
        "what a person doing their work would ask next about the same subject. Each is one short "
        "question a chart or a number can answer; `asked` is true when the person asked it "
        "themselves (in any wording) and false when you added it. Never a question about the "
        "data's quality, and never one these columns cannot answer.\n"
        "- exclude: what they asked to leave out, as short items; [] when nothing.\n"
        "- scope: ONLY when they asked for a PART of the data -- one kind, one place, one "
        "period, a range ('only ...', 'I need ...', 'under ...', 'since ...'). One item per "
        "restriction: dataset = the dataset's name; said = the two or three words that name it "
        "('online orders', 'since 2024', 'the north region'), not their whole sentence; column = the "
        "column that holds it; op = 'in' with the matching values copied EXACTLY from the "
        "column's listed values, or gt / gte / lt / lte with ONE number, or gte / lte with one "
        "date as YYYY-MM-DD on a date column. If no listed column holds what they asked for, "
        "still return the item with column '' and values [] -- never drop a restriction they "
        "stated, and never invent one they did not. [] when they want all of it. NEVER put a scope "
        "on a yes/no column (has_..., is_...): it says what HAPPENED to a row, and narrowing to 'yes' "
        "throws away the rows it must be compared with -- what happened is something to measure, not "
        "a part of the data.\n"
        "- not_in_data: be strict. When they name a KIND of thing -- a product, a service, a channel, a "
        "place, a group -- and no listed column or value is that thing, put their words for it here "
        "(a service, a product or a place the listed values do not include). Do not treat everything in the data as that thing, do not use the word "
        "in the sentence or the questions as if the data held it, and do not put a scope item for it. "
        "[] when the data holds everything they named.\n"
        f"Write sentence, who, subject, questions and exclude in {_LANGUAGE.get(lang, 'English')}.")
    b = brief or {}
    about = [f"- {label}: {b[key]}" for label, key in (
        ("Their work", "work"), ("What to focus on", "focus"),
        ("What they need to know", "questions"), ("What to leave out", "exclude")) if b.get(key)]
    blocks = []
    for d in datasets:
        p = d.get("proposal") or {}
        lines = [f"## {d['name']} ({d['rows']:,} rows)"]
        if p.get("purpose"):
            lines.append(f"Made for: {p['purpose']}")
        if p.get("includes"):
            lines.append("Includes: " + "; ".join(p["includes"]))
        if p.get("leaves_out"):
            lines.append("Leaves out: " + "; ".join(p["leaves_out"]))
        chat = [m.get("text", "") for m in p.get("history") or [] if m.get("role") == "user"]
        if chat:
            lines.append("While choosing it they asked: " + " / ".join(chat))
        lines.append("Columns:\n" + d["profile"])
        blocks.append("\n".join(lines))
    user = ("About the person:\n" + ("\n".join(about) if about else "- They did not say.") + "\n\n"
            + "\n\n".join(blocks))
    if earlier and earlier.get("sentence"):
        user += ("\n\nWhat was written down before: " + earlier["sentence"]
                 + "\nTheir questions then: " + " / ".join(q.get("text", "") for q in earlier.get("questions") or []))
    if edits:
        user += ("\n\nThey then corrected it, latest last -- the corrections win over everything above:\n"
                 + "\n".join(f"- {e}" for e in edits[-6:]))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# ── a scope, checked on the rows ────────────────────────────────────────────

def _norm(v) -> str:
    return re.sub(r"\s+", " ", str(v)).strip().casefold()


def _text_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if not _is_number(df[c]) and not _is_date(df[c]) and df[c].dtype != bool]


def _match_values(s: pd.Series, wanted: list[str], said: str, named: bool = True) -> list:
    """The column's own values that are what the person asked for: the values
    the model named (compared without case or stray spaces), else values that
    contain their words.

    In a column the model did NOT name, only a value that appears whole in
    their words counts ("Same Day" in "same day deliveries"): "Giza" must not
    pick the branch "Giza East Hub" when they meant parcels going TO Giza."""
    actual = s.dropna().unique().tolist()
    if len(actual) > SEARCH_VALUES_UP_TO:
        return []
    by_norm: dict[str, list] = {}
    for v in actual:
        by_norm.setdefault(_norm(v), []).append(v)
    out: list = []
    for w in wanted:
        out += by_norm.get(_norm(w), [])
    if not out and _norm(said):
        text = _norm(said)
        word = re.compile(rf"(?<!\w){re.escape(text)}(?!\w)")
        for key, vals in by_norm.items():
            if named and word.search(key):
                out += vals
            elif not named and len(key) >= 3 and re.search(rf"(?<!\w){re.escape(key)}(?!\w)", text):
                out += vals
    return list(dict.fromkeys(out))


def _number(v) -> float | None:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def is_outcome(df: pd.DataFrame, column: str) -> bool:
    """A yes/no column: it says what happened to each row. A dataset that
    keeps every order "with whether it was returned" is narrowed to the
    returned ones only by mistake -- the rate would then have no base."""
    if column not in df.columns:
        return False
    values = set(df[column].dropna().unique().tolist()[:4])
    return bool(values) and values <= {True, False} and all(isinstance(v, bool) or type(v).__name__ == "bool_"
                                                           for v in values)


def candidates(df: pd.DataFrame) -> list[dict]:
    """What the data DOES hold, to offer when a subject was not found: the
    text columns with the fewest values, and those values."""
    cols = []
    for c in _text_columns(df):
        n = int(df[c].nunique(dropna=True))
        if 2 <= n <= LIST_VALUES_UP_TO:
            cols.append((n, c))
    out = []
    for _n, c in sorted(cols)[:CANDIDATE_COLUMNS]:
        top = df[c].dropna().astype(str).value_counts().index[:CANDIDATE_VALUES].tolist()
        out.append({"column": c, "values": top})
    return out


def resolve_scope(df: pd.DataFrame, item: dict, named_only: bool = False) -> dict:
    """One restriction, as the rows answer it.

    status: "in_data"      every row already matches (the dataset was made for it);
            "in_dashboard" some rows match: the dashboard must filter to them;
            "unmatched"    nothing matches: the person is asked what they meant.
    """
    said = str(item.get("said") or "").strip()
    col = str(item.get("column") or "").strip()
    op = str(item.get("op") or "in").strip().lower()
    op = op if op in OPS else "in"
    wanted = [str(v) for v in (item.get("values") or []) if str(v).strip()]
    total = int(len(df))
    out = {"said": said, "column": col or None, "op": op, "values": [], "matched_rows": 0,
           "of_rows": total, "status": "unmatched"}

    def done(column: str, values: list, mask) -> dict:
        n = int(mask.sum())
        return {**out, "column": column, "values": values, "matched_rows": n,
                "status": "unmatched" if n == 0 else "in_data" if n == total else "in_dashboard"}

    if col in df.columns and op != "in":
        s = df[col]
        if _is_date(s) and wanted:
            try:
                when = pd.Timestamp(wanted[0])
                series = pd.to_datetime(s, errors="coerce")
                if getattr(series.dt, "tz", None) is not None:
                    series = series.dt.tz_localize(None)
                mask = {"gt": series > when, "gte": series >= when, "lt": series < when, "lte": series <= when}[op]
                return done(col, [str(when.date())], mask.fillna(False))
            except Exception:                                       # noqa: BLE001
                pass
        num = _number(wanted[0]) if wanted else None
        if _is_number(s) and num is not None:
            mask = {"gt": s > num, "gte": s >= num, "lt": s < num, "lte": s <= num}[op]
            return done(col, [num], mask.fillna(False))
        return {**out, "candidates": candidates(df)}

    out["op"] = "in"
    # The named column first; then any text column that holds their words.
    order = ([col] if col in df.columns else []) + (
        [] if named_only else [c for c in _text_columns(df) if c != col])
    for c in order:
        if _is_date(df[c]):
            continue
        values = (_match_values(df[c], wanted if c == col else [], said, named=c == col)
                  if not _is_number(df[c]) else [])
        if _is_number(df[c]) and c == col:
            nums = [n for n in (_number(w) for w in wanted) if n is not None]
            values = [n for n in nums if (df[c] == n).any()]
        if values:
            return done(c, values, df[c].isin(values))
    return {**out, "candidates": candidates(df)}


def made_for(sql: str | None, item: dict) -> list[str]:
    """The text values the dataset's own query narrows its rows to that are
    what the person asked for. A dataset made for "Express shipments" may not
    keep the column it was filtered on; the restriction is then already in
    the data, not missing from it."""
    if not sql:
        return []
    try:
        import sqlglot
        from sqlglot import exp
        tree = sqlglot.parse_one(sql)
    except Exception:                                               # noqa: BLE001
        return []
    literals = {str(lit.this) for where in tree.find_all(exp.Where)
                for lit in where.find_all(exp.Literal) if lit.is_string}
    said = _norm(item.get("said"))
    wanted = {_norm(v) for v in item.get("values") or []}
    out = []
    for lit in literals:
        key = _norm(lit).strip("%")
        if len(key) >= 2 and (key in wanted or re.search(rf"(?<!\w){re.escape(key)}(?!\w)", said)):
            out.append(lit.strip("%"))
    return sorted(out)


def plain_scope(df: pd.DataFrame, said: str) -> list[dict]:
    """Without a model: a value of a small text column that appears, as a whole
    word, in what the person typed is the part of the data they asked for."""
    text = _norm(said)
    if not text:
        return []
    found = []
    for c in _text_columns(df):
        actual = df[c].dropna().unique().tolist()
        if not 2 <= len(actual) <= LIST_VALUES_UP_TO:
            continue
        hits = [v for v in actual if len(_norm(v)) >= 3
                and re.search(rf"(?<!\w){re.escape(_norm(v))}(?!\w)", text)]
        if hits and len(hits) < len(actual):
            found.append(resolve_scope(df, {"said": ", ".join(map(str, hits)), "column": c, "op": "in",
                                            "values": [str(h) for h in hits]}))
    return [f for f in found if f["status"] != "unmatched"]


def filters_for(demand: dict | None, dataset_id: int) -> list[dict]:
    """The widget filters that narrow this dataset to what was asked for.
    Empty when the dataset already holds only that."""
    out = []
    for s in (demand or {}).get("scope") or []:
        if s.get("dataset_id") != dataset_id or s.get("status") != "in_dashboard" or not s.get("column"):
            continue
        if s["op"] == "in":
            out.append({"column": s["column"], "op": "in", "value": list(s["values"])})
        elif s.get("values"):
            out.append({"column": s["column"], "op": s["op"], "value": s["values"][0]})
    return out


def missing_words(demand: dict | None) -> list[str]:
    """What the person asked for that the data does not hold, in their words."""
    return list(dict.fromkeys(str(s.get("said")) for s in (demand or {}).get("scope") or []
                              if s.get("status") == "unmatched" and s.get("said")))


def scope_words(demand: dict | None, dataset_id: int) -> list[str]:
    """How each applied restriction reads, for titles and notes: 'body type: SUV'."""
    signs = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤"}
    out = []
    for s in (demand or {}).get("scope") or []:
        if s.get("dataset_id") != dataset_id or s.get("status") == "unmatched":
            continue
        if not s.get("column"):
            # Narrowed by the dataset's own query: their own words say it best.
            out.append(str(s.get("said") or "") or ", ".join(str(v) for v in s.get("values") or []))
            continue
        name = str(s["column"]).replace("_", " ")
        if s["op"] == "in":
            out.append(f"{name}: " + ", ".join(str(v) for v in s["values"][:6]))
        elif s.get("values"):
            out.append(f"{name} {signs.get(s['op'], s['op'])} {_fmt(s['values'][0])}")
    return out


# ── writing it ──────────────────────────────────────────────────────────────

def _split_questions(text: str | None) -> list[str]:
    parts = [p.strip(" -•\t") for p in re.split(r"[\n؟?;]+", text or "")]
    return [p for p in parts if len(p) >= 4][:MAX_QUESTIONS]


def plain(brief: dict | None, datasets: list[dict], edits: list[str]) -> dict:
    """The Demand without a model: their own words, kept as they typed them."""
    b = brief or {}
    first = (datasets[0].get("proposal") or {}) if datasets else {}
    sentence = (edits[-1] if edits else None) or b.get("focus") or b.get("questions") \
        or first.get("purpose") or (datasets[0]["name"] if datasets else "")
    return {"sentence": str(sentence).strip()[:300], "who": str(b.get("work") or "").strip()[:120],
            "subject": "", "questions": _split_questions(b.get("questions")) or _split_questions(b.get("focus")),
            "exclude": _split_questions(b.get("exclude")), "scope": []}


async def write(brief: dict | None, datasets: list[dict], edits: list[str], lang: str, client,
                earlier: dict | None = None) -> dict:
    """The Demand for these datasets. `datasets`: [{"id", "name", "frame",
    "proposal"}]. Always returns one: the model's when it answers, else the
    person's own words. Every scope is resolved on the frames."""
    described = [{"name": d["name"], "rows": int(len(d["frame"])), "profile": profile_text(d["frame"]),
                  "proposal": d.get("proposal")} for d in datasets]
    got, source = None, "plain"
    if client is not None and getattr(client, "enabled", True):
        try:
            got = await client.complete_json(build_prompt(brief, described, edits, lang, earlier),
                                             DEMAND_SCHEMA, max_tokens=1800, temperature=0.1, enforce=True)
        except Exception:                                           # noqa: BLE001
            logger.exception("guided setup: writing the demand failed")
    if got and str(got.get("sentence") or "").strip():
        source = "ai"
    else:
        got = plain(brief, described, edits)

    by_name = {_norm(d["name"]): d for d in datasets}
    scope: list[dict] = []
    for item in got.get("scope") or []:
        if not isinstance(item, dict) or not str(item.get("said") or "").strip():
            continue
        targets = [by_name[_norm(item.get("dataset"))]] if _norm(item.get("dataset")) in by_name else datasets
        for d in targets:
            # The column they named first; then what the dataset's own query
            # already narrowed to; only then a look through the other columns.
            found = resolve_scope(d["frame"], item, named_only=True)
            if found["status"] == "unmatched":
                values = made_for((d.get("proposal") or {}).get("sql"), item)
                if not values:
                    found = resolve_scope(d["frame"], item)
                if values:
                    n = int(len(d["frame"]))
                    found = {**{k: v for k, v in found.items() if k != "candidates"}, "column": None,
                           "values": values, "matched_rows": n, "of_rows": n, "status": "in_data"}
            if found.get("column") and is_outcome(d["frame"], found["column"]):
                continue            # what happened to a row is measured, never narrowed to
            scope.append({**found, "dataset_id": d["id"]})
    for missing in got.get("not_in_data") or []:
        text = str(missing).strip()
        if text and datasets and not any(_norm(x["said"]) == _norm(text) for x in scope):
            d = datasets[0]
            scope.append({"said": text, "column": None, "op": "in", "values": [], "matched_rows": 0,
                          "of_rows": int(len(d["frame"])), "status": "unmatched",
                          "candidates": candidates(d["frame"]), "dataset_id": d["id"]})
    if source == "plain":
        said = _said(brief, [d.get("proposal") or {} for d in datasets], edits)
        for d in datasets:
            scope += [{**s, "dataset_id": d["id"]} for s in plain_scope(d["frame"], said)]
    # One restriction, one line per dataset: a subject found in one of two
    # datasets is not "unmatched" in the flow.
    seen, kept = set(), []
    for s in sorted(scope, key=lambda s: s["status"] == "unmatched"):
        key = (s["dataset_id"], _norm(s["said"]))
        if key in seen:
            continue
        seen.add(key)
        if s["status"] == "unmatched" and any(
                o["status"] != "unmatched" and _norm(o["said"]) == _norm(s["said"]) for o in scope):
            continue
        kept.append(s)
    questions = []
    for q in (got.get("questions") or [])[:MAX_QUESTIONS]:
        text = str(q.get("text") if isinstance(q, dict) else q or "").strip()
        if text:
            questions.append({"text": text, "asked": bool(q.get("asked", True)) if isinstance(q, dict) else True})
    return {
        "sentence": str(got.get("sentence") or "").strip()[:400],
        "who": str(got.get("who") or "").strip()[:160],
        "subject": str(got.get("subject") or "").strip()[:80],
        "questions": [{"id": f"q{i + 1}", **q} for i, q in enumerate(questions)],
        "exclude": [str(x).strip() for x in (got.get("exclude") or []) if str(x).strip()][:8],
        "scope": kept,
        "source": source,
    }
