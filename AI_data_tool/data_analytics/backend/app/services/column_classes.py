"""One classification per column, decided once (docs/suggestions/PLAN.md, phase 1).

Every suggestion feature used to work out for itself what a column is --
from its name, with its own word list: the insights engine, the builder's
suggestions, the dashboard designer, the data check, the browser. The same
dataset therefore got different treatment, and the same mistake, depending on
which door the person came through.

Here a column is classified ONCE and the result is kept in the dataset's
`column_meta`, where the author can see and correct it:

  number     what a number is: amount | count (add up) · level | duration |
             score | share (average) · code (never calculate)
  unit       EGP, kg, days ...
  direction  higher_better | higher_worse | neither
  level      nominal | ordinal | interval | ratio
  order      an ordinal column's values in their real order
  geo_level  country | region | city | postcode | latitude | longitude
  outcome    the column says what became of a row (late, returned)

Sources, strongest last: what the rows show -> a NEUTRAL vocabulary of
measurement words (a rate, a price, an id -- never one industry's nouns) ->
the model, asked ONCE per dataset what each number is and kept (`model_hints`)
-> the connection's Meaning map (measured on the database) -> the author,
whose word (`class_source: "confirmed"`) is never overwritten.

Datalytics is a general-purpose platform. That a `salary`, a `mileage`, a
`gpa` or a `premium` is a level to average is knowledge about ONE field of
work; it is not written into the code. The model reads the column names in
whatever language and field the data is from, and its answer is stored where
the author can see and correct it.

Everything is read back through `services/semantic_guard.py`, which every
engine already calls.
"""
from __future__ import annotations

import logging
import re

import pandas as pd

from . import semantic_guard as guard
from .llm import data_block as _data_block

logger = logging.getLogger(__name__)

#: Distinct values an ordered scale may have; more is not a scale.
ORDINAL_MAX = 40
#: Rows looked at when judging a column; a sample says the same.
SAMPLE_ROWS = 50_000

# ── ordered scales, in the words people actually store ──────────────────────
# Each list runs low -> high (or first -> last). A column whose values are all
# in one list, at least two of them, is ordinal in that order.
_SCALES: list[list[list[str]]] = [
    [["very low"], ["low"], ["medium", "moderate", "mid", "med", "average", "normal"], ["high"], ["very high"],
     ["critical", "extreme"]],
    [["xxs"], ["xs", "extra small"], ["s", "small"], ["m", "medium"], ["l", "large"], ["xl", "extra large", "x-large"],
     ["xxl", "2xl"], ["xxxl", "3xl"]],
    [["very poor", "terrible"], ["poor", "bad"], ["fair", "acceptable", "ok", "okay"], ["good"], ["very good"],
     ["excellent", "outstanding"]],
    [["never"], ["rarely", "seldom"], ["sometimes", "occasionally"], ["often", "frequently"], ["always"]],
    [["strongly disagree"], ["disagree"], ["neutral", "neither"], ["agree"], ["strongly agree"]],
    [["very dissatisfied"], ["dissatisfied"], ["neutral"], ["satisfied"], ["very satisfied"]],
    [["intern", "trainee"], ["junior", "entry"], ["mid", "intermediate", "mid-level"], ["senior"], ["lead", "principal"],
     ["manager"], ["director"], ["executive", "vp"]],
    [["bronze"], ["silver"], ["gold"], ["platinum"], ["diamond"]],
    [["beginner", "basic"], ["intermediate"], ["advanced"], ["expert"]],
    [["minor"], ["moderate"], ["major"], ["severe"], ["critical"]],
    [["p4"], ["p3"], ["p2"], ["p1"], ["p0"]],
    [["primary", "elementary"], ["preparatory", "middle"], ["secondary", "high school"], ["diploma"],
     ["bachelor", "bachelors", "bsc", "ba"], ["master", "masters", "msc", "ma"], ["phd", "doctorate"]],
    [["q1"], ["q2"], ["q3"], ["q4"]],
    [["mon", "monday"], ["tue", "tues", "tuesday"], ["wed", "wednesday"], ["thu", "thur", "thurs", "thursday"],
     ["fri", "friday"], ["sat", "saturday"], ["sun", "sunday"]],
    [["jan", "january"], ["feb", "february"], ["mar", "march"], ["apr", "april"], ["may"], ["jun", "june"],
     ["jul", "july"], ["aug", "august"], ["sep", "sept", "september"], ["oct", "october"], ["nov", "november"],
     ["dec", "december"]],
    # Arabic
    [["منخفض جدا", "منخفض جداً"], ["منخفض", "قليل"], ["متوسط"], ["مرتفع", "عالي", "عال"], ["مرتفع جدا", "مرتفع جداً"]],
    [["صغير جدا"], ["صغير"], ["متوسط"], ["كبير"], ["كبير جدا"]],
    [["ضعيف جدا"], ["ضعيف"], ["مقبول"], ["جيد"], ["جيد جدا", "جيد جداً"], ["ممتاز"]],
    [["ابدا", "أبدا", "أبداً"], ["نادرا", "نادراً"], ["احيانا", "أحيانا", "أحياناً"], ["غالبا", "غالباً"],
     ["دائما", "دائماً"]],
    [["السبت"], ["الأحد", "الاحد"], ["الاثنين", "الإثنين"], ["الثلاثاء"], ["الأربعاء", "الاربعاء"], ["الخميس"],
     ["الجمعة"]],
    [["يناير"], ["فبراير"], ["مارس"], ["أبريل", "ابريل"], ["مايو"], ["يونيو", "يونيه"], ["يوليو", "يوليه"],
     ["أغسطس", "اغسطس"], ["سبتمبر"], ["أكتوبر", "اكتوبر"], ["نوفمبر"], ["ديسمبر"]],
    [["ابتدائي"], ["إعدادي", "اعدادي"], ["ثانوي"], ["دبلوم"], ["بكالوريوس"], ["ماجستير"], ["دكتوراه"]],
]
_NUMBERED = re.compile(r"^\s*(\d+)\s*[-–—.):]\s*\S")
_BAND = re.compile(r"^\s*(?:[<>≤≥]=?|under|over|below|above|up to|less than|more than|أقل من|أكثر من)?\s*"
                   r"(-?\d+(?:[.,]\d+)?)\s*(?:k|m|%)?\s*(?:[-–—]|to|الى|إلى|\+|and over|and above|فأكثر)?", re.I)

# ── geography, by the words a column of places is headed with ───────────────
_GEO_WORDS = {
    "country": ("country", "nation", "country_name", "country_code", "الدولة", "دولة", "البلد", "بلد"),
    "region": ("state", "province", "governorate", "region", "emirate", "county", "prefecture", "territory",
               "muhafazah", "wilaya", "المحافظة", "محافظة", "المنطقة", "منطقة", "الإمارة", "إمارة", "الولاية", "ولاية"),
    "city": ("city", "town", "municipality", "district", "المدينة", "مدينة", "الحي", "حي", "المركز", "مركز"),
    "postcode": ("zip", "zipcode", "zip_code", "postcode", "postal_code", "postal", "الرمز_البريدي"),
    "latitude": ("lat", "latitude"),
    "longitude": ("lon", "lng", "long", "longitude"),
}


def _norm(v) -> str:
    return re.sub(r"\s+", " ", str(v)).strip().casefold()


def ordered_values(values: list) -> list[str] | None:
    """The values in their real order when they form a scale, else None.

    Three shapes, none of them tied to a subject: numbered labels
    ("1 - New", "2 - Open"), bands of a number ("0-17", "18-25", "65+"), and
    the scales people write in words (low / medium / high, weekdays, months,
    grades), in English and Arabic."""
    raw = [str(v) for v in values if v is not None and str(v).strip()]
    uniq = list(dict.fromkeys(raw))
    if not 2 <= len(uniq) <= ORDINAL_MAX:
        return None
    numbered = [_NUMBERED.match(v) for v in uniq]
    if all(numbered) and len({int(m.group(1)) for m in numbered}) == len(uniq):
        return [v for _n, v in sorted(zip((int(m.group(1)) for m in numbered), uniq))]
    if len(uniq) >= 3 and all(re.search(r"\d", v) and re.search(r"[-–—+<>≤≥]|\bto\b|under|over|below|above|"
                                                              r"أقل|أكثر|الى|إلى", v, re.I) for v in uniq):
        keys = []
        for v in uniq:
            m = _BAND.match(v)
            if not m:
                keys = []
                break
            n = float(m.group(1).replace(",", "."))
            # "<18" sorts before "18-25"; "65+" and ">65" after "45-64".
            keys.append(n - 0.5 if re.match(r"^\s*(<|≤|under|below|up to|less than|أقل)", v, re.I)
                        else n + 0.5 if re.match(r"^\s*(>|≥|over|above|more than|أكثر)", v, re.I) else n)
        if keys and len(set(keys)) == len(uniq):
            return [v for _k, v in sorted(zip(keys, uniq))]
    normed = {_norm(v): v for v in uniq}
    if len(normed) == len(uniq):
        for scale in _SCALES:
            rank = {word: i for i, group in enumerate(scale) for word in group}
            if all(k in rank for k in normed):
                ranks = [rank[k] for k in normed]
                if len(set(ranks)) == len(ranks):
                    return [normed[k] for k in sorted(normed, key=lambda k: rank[k])]
    return None


def geo_level(column: str, role: str | None = None) -> str | None:
    """What kind of place a column holds, from how it is headed."""
    low = str(column).casefold().strip()
    parts = set(re.split(r"[\s_\-.]+", low)) | {low}
    for level, words in _GEO_WORDS.items():
        if any(w in parts or low.endswith("_" + w) or low.startswith(w + "_") for w in words):
            return level
    return None


def _is_sequence(s: pd.Series) -> bool:
    """Whole numbers, each its own, running without gaps: a row number or a
    key issued in order -- a code, however it is named."""
    q = s.dropna()
    if len(q) < 50:
        return False
    try:
        if not (q == q.astype("int64")).all():
            return False
    except (TypeError, ValueError, OverflowError):
        return False
    n, d = len(q), q.nunique()
    span = float(q.max() - q.min()) + 1
    return d >= 0.98 * n and span <= 1.2 * d


def _fixed_width_code(s: pd.Series) -> bool:
    """Whole numbers of eight or more digits, nearly all the same length, most
    of them different: a number that NAMES something (a phone, a device, a
    national id, an account) whatever the column is called. A quantity that
    large does not keep one width."""
    q = pd.to_numeric(s, errors="coerce").dropna()
    if len(q) < 50:
        return False
    try:
        if not (q == q.round()).all() or (q < 0).any():
            return False
        width = q.astype("int64").astype(str).str.len()
    except (TypeError, ValueError, OverflowError):
        return False
    usual = int(width.mode().iloc[0])
    return usual >= 8 and float((width == usual).mean()) >= 0.95 and q.nunique() >= 0.2 * len(q)


def _plain_number(column: str, s: pd.Series) -> dict:
    """What a number is from its rows and its name, when nothing better is known."""
    kind = guard.non_additive_kind(column)
    if kind in ("identifier", "year") or _is_sequence(s):
        return {"number": "code", "direction": "neither"}
    if kind == "coordinate":
        return {"number": "level", "direction": "neither"}
    low = re.sub(r"[\s\-.]+", "_", str(column).strip().lower())
    if _fixed_width_code(s):
        return {"number": "code", "direction": "neither"}
    if re.search(r"(^|_)(days?|hours?|hrs?|minutes?|mins?|seconds?|secs?|duration|age|مدة|المدة|عمر|العمر)(_|$)", low):
        return {"number": "duration", "direction": "neither"}
    if re.search(r"(rating|score|grade|stars|تقييم|درجة)", low):
        return {"number": "score", "direction": "higher_better"}
    q = pd.to_numeric(s, errors="coerce").dropna()
    if re.search(r"(pct|percent|percentage|ratio|share|(^|_)rate$|نسبة|معدل)", low):
        return {"number": "share", "unit": "%", "direction": "neither"}
    if guard.is_intensive(column):
        return {"number": "level", "direction": "neither"}
    if re.search(r"(^|_)(count|qty|quantity|units|items|n|عدد|كمية|الكمية)(_|$)", low) and len(q) \
            and (q == q.round()).all():
        return {"number": "count", "direction": "neither"}
    return {"number": "amount", "direction": "neither"}


def _is_flag(s: pd.Series) -> bool:
    values = set(s.dropna().unique().tolist()[:6])
    if not values or len(values) > 2:
        return False
    return all(isinstance(v, bool) or type(v).__name__ == "bool_" for v in values)


def classify(df: pd.DataFrame, column_meta: dict | None = None, *,
             numbers: dict[str, dict] | None = None, outcomes: set[str] | None = None) -> dict[str, dict]:
    """The classification of every column of `df`: {column: {number, unit,
    direction, level, order, geo_level, outcome, class_source}} (only the keys
    that apply).

    `numbers` and `outcomes` come from the connection's Meaning map when the
    dataset has one: {column: {"kind", "unit", "direction"}} and the columns
    that say what became of a row. They outrank the name; the rows are read
    either way (an ordered scale, a place, a yes/no are seen in the values)."""
    meta = column_meta or {}
    numbers, outcomes = numbers or {}, outcomes or set()
    frame = df if len(df) <= SAMPLE_ROWS else df.sample(SAMPLE_ROWS, random_state=0)
    out: dict[str, dict] = {}
    for col in df.columns:
        name = str(col)
        if name.startswith("__"):
            continue
        s = frame[col]
        entry = meta.get(name) if isinstance(meta.get(name), dict) else {}
        role = entry.get("role")
        c: dict = {"class_source": "measured"}
        flag = _is_flag(s)
        if pd.api.types.is_datetime64_any_dtype(s) or role in ("temporal", "timestamp"):
            c["level"] = "interval"
        elif flag:
            c.update(level="nominal", outcome=True)
        elif pd.api.types.is_numeric_dtype(s) and role not in ("category", "dimension", "freetext", "geography"):
            hint = numbers.get(name)
            if role == "identifier":
                c.update(number="code", direction="neither")
            elif hint and hint.get("kind") in guard.NUMBER_KINDS:
                kind = hint["kind"]
                # How a number is MEASURED is said by its own heading (a price,
                # a rate, an average: per one thing by definition). A reading
                # of it as something to add up is not taken over that -- only
                # the author's word is.
                if kind in guard.ADDITIVE_KINDS and guard.is_intensive(name):
                    kind = _plain_number(name, s)["number"]
                c.update(number=kind, direction=hint.get("direction") if hint.get("direction")
                         in guard.DIRECTIONS else "neither", class_source="ai")
                if hint.get("unit"):
                    c["unit"] = str(hint["unit"])[:12]
            else:
                c.update(_plain_number(name, s))
            c["level"] = ("nominal" if c["number"] == "code" else "ordinal" if c["number"] == "score"
                          else "interval" if c["number"] == "level" else "ratio")
            geo = geo_level(name)
            if geo in ("latitude", "longitude", "postcode"):
                c["geo_level"] = geo
        else:
            order = None if role == "freetext" else ordered_values(
                s.dropna().astype(str).unique().tolist()[:ORDINAL_MAX + 1])
            if order:
                c.update(level="ordinal", order=order)
            else:
                c["level"] = "nominal"
            geo = geo_level(name)
            if geo and geo not in ("latitude", "longitude"):
                c["geo_level"] = geo
            if name in outcomes:
                c["outcome"] = True
        out[name] = c
    return out


#: The keys this module owns in a column's `column_meta` entry.
KEYS = ("number", "unit", "direction", "level", "order", "geo_level", "outcome", "class_source")


def merge(column_meta: dict | None, classes: dict[str, dict]) -> tuple[dict, bool]:
    """(the map with the classification filled in, whether anything changed).

    Fills what is missing and refreshes what was measured before; an entry the
    author confirmed is theirs and is left exactly as it is. Nothing else in
    an entry (role, label, hidden ...) is touched."""
    meta = dict(column_meta or {})
    changed = False
    for col, c in classes.items():
        old = meta.get(col) if isinstance(meta.get(col), dict) else {}
        if old.get("class_source") == "confirmed":
            continue
        kept = {k: v for k, v in old.items() if k not in KEYS}
        new = {**kept, **c}
        if new != old:
            meta[col] = new
            changed = True
    return meta, changed


def _open(entry, hint: dict | None) -> bool:
    """Whether a column still has to be classified: never done, or only
    MEASURED so far while a better source (the model, the Meaning map) now
    says what kind of number it is."""
    if not (isinstance(entry, dict) and entry.get("class_source")):
        return True
    return bool(entry.get("class_source") == "measured" and hint
                and hint.get("kind") in guard.NUMBER_KINDS and hint.get("kind") != entry.get("number"))


def classified(df: pd.DataFrame, column_meta: dict | None, numbers: dict | None = None,
               outcomes: set | None = None) -> tuple[dict, bool]:
    """(column_meta with every column of `df` classified, whether it changed).

    Synchronous and pure -- for the engines that already hold the frame inside
    a worker thread. Columns classified before are left as they are; nothing is
    written anywhere (`remember` does that, afterwards, on the event loop).
    Never raises: on any failure the map comes back as it was."""
    current = dict(column_meta or {})
    try:
        todo = [c for c in df.columns if _open(current.get(str(c)), (numbers or {}).get(str(c)))]
        if not todo:
            return current, False
        return merge(current, classify(df[todo], current, numbers=numbers, outcomes=outcomes))
    except Exception:                                           # noqa: BLE001
        logger.exception("column classes: classifying a frame failed")
        return current, False


async def remember(db, dataset, column_meta: dict) -> None:
    """Keep a classification worked out in a worker thread, so it is decided
    once and the author can see and correct it. Never raises."""
    try:
        from sqlalchemy.orm.attributes import flag_modified
        dataset.column_meta = column_meta
        flag_modified(dataset, "column_meta")
        await db.commit()
    except Exception:                                           # noqa: BLE001
        logger.exception("column classes: keeping the classification of dataset %s failed",
                         getattr(dataset, "id", None))
        try:
            await db.rollback()
        except Exception:                                       # noqa: BLE001
            pass


#: Where the model's answer is kept inside `column_meta` (a reserved key: the
#: column-meta route preserves every `__key` and refuses to be sent one).
AI_KEY = "__classes_ai__"
#: Columns asked about in one request; a wider table is asked in turns.
ASK_MAX_COLUMNS = 120
#: After the model failed, how long before it is tried again.
ASK_AGAIN_AFTER_S = 1800

CLASS_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["a_row_is", "rows_are", "numbers"],
    "properties": {
        # Asked first, because the rest follows from it.
        "a_row_is": {"type": "string"},
        "rows_are": {"type": "string", "enum": ["things", "events"]},
        "numbers": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["column", "kind", "unit", "direction"],
        "properties": {
            "column": {"type": "string"},
            "kind": {"type": "string", "enum": list(guard.NUMBER_KINDS)},
            "unit": {"type": "string"},
            "direction": {"type": "string", "enum": list(guard.DIRECTIONS)},
        }}},
    },
}


def build_class_prompt(name: str, description: str | None, columns: list[dict]) -> list[dict]:
    """The question put to the model: what is each NUMBER of this table. Only
    names, types and ranges are sent -- no row and no text value."""
    lines = []
    for c in columns:
        bits = [f"- {c['name']}"]
        if c.get("range"):
            bits.append(f"range {c['range']}")
        if c.get("description"):
            bits.append(f"described as: {str(c['description'])[:120]}")
        lines.append(" | ".join(bits))
    others = ", ".join(c for c in (columns[0].get("_others") or [])[:60]) if columns else ""
    system = (
        "You classify the NUMERIC columns of one table, whatever field of work it comes from and "
        "whatever language its names are in.\n"
        "FIRST decide what one row is (a_row_is, a few words) and whether rows_are:\n"
        "  things - each row DESCRIBES something that exists (a person, an item, a place, an account, a "
        "listing, a contract, a state of something at a date). Its numbers are that thing's ATTRIBUTES.\n"
        "  events - each row is something that HAPPENED once (a transaction, a visit, a movement, a "
        "reading taken, a request). Its numbers are what that one event carried.\n"
        "Then, for each listed column return:\n"
        "kind =\n"
        "  amount   - a quantity that adds up across rows into a meaningful total\n"
        "  count    - a whole number of things held in the row, which also adds up\n"
        "  level    - a reading or a per-unit figure whose total over rows means nothing and whose "
        "average does (something measured AT a moment or PER one thing)\n"
        "  duration - a length of time\n"
        "  score    - a mark on a scale\n"
        "  share    - a percentage, ratio or rate\n"
        "  code     - a number that NAMES something (an identifier, a year, a phone, a postcode): never calculated\n"
        "unit = the unit when the name or description states it (a currency code, kg, km, days, %), else ''.\n"
        "direction = higher_better, higher_worse, or neither when it is not good or bad in itself.\n"
        "Amount against level, the rule: an amount is a piece that each row ADDS to a whole -- what one "
        "event moved, paid, produced or used. A level is how big, how much per unit or how far along "
        "something IS. So when rows are THINGS, their numeric attributes (what each is worth, costs, earns "
        "per period, measures, weighs, holds, or how old it is) are levels: two things side by side are not "
        "one bigger thing, and the sum of their attributes is not a figure of the table. When rows are "
        "EVENTS, what each event carried is an amount or a count; a per-unit figure inside an event (a unit "
        "price, a rate) is still a level.\n"
        "Return every listed column exactly once, with its name copied exactly. Do not add columns."
    )
    user = (f"Table: {name}\n" + (f"About: {str(description)[:300]}\n" if description else "")
            + (f"Its other columns (for context only): {others}\n" if others else "")
            + "Numeric columns to classify:\n" + _data_block("\n".join(lines), "column names and ranges"))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _range_of(stats: dict | None) -> str:
    st = stats if isinstance(stats, dict) else {}
    lo, hi = st.get("min"), st.get("max")
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
        return f"{lo:g} to {hi:g}"
    return ""


async def model_hints(db, dataset, client=None, only: set[str] | None = None,
                      denied: set[str] | None = None) -> dict[str, dict]:
    """{column: {"kind", "unit", "direction"}} for this dataset's numbers, as
    the model read them. ASKED ONCE: the answer is kept in the dataset's
    `column_meta` and only columns never asked about are sent again (a new
    column after a refresh). Never raises; {} when the model is off or fails.

    `only`: the columns the person on whose request this runs may see. The
    model is never shown the name of a column hidden from them; such a column
    waits for a request by someone who may see it."""
    try:
        import time
        from sqlalchemy import select
        from sqlalchemy.orm.attributes import flag_modified
        from ..models.models import DatasetColumn
        meta = dict(dataset.column_meta or {})
        kept = dict(meta.get(AI_KEY) or {}) if isinstance(meta.get(AI_KEY), dict) else {}
        numbers = dict(kept.get("numbers") or {})
        asked = set(kept.get("asked") or [])
        rows = (await db.execute(select(DatasetColumn).where(DatasetColumn.dataset_id == dataset.id))).scalars().all()
        if denied:
            only = {r.name for r in rows if r.name not in denied} & (only if only is not None else {r.name for r in rows})
        todo = [r for r in rows if str(r.dtype).lower() in ("numeric", "number", "integer", "float")
                and r.name not in asked and (only is None or r.name in only)
                and not (isinstance(meta.get(r.name), dict) and meta[r.name].get("class_source") == "confirmed")]
        if not todo:
            return numbers
        if kept.get("failed_at") and time.time() - float(kept["failed_at"]) < ASK_AGAIN_AFTER_S:
            return numbers
        # "Allow AI" for this data (services/ai_policy.py) -- checked here as
        # well as at the request's door, because this is also reached from
        # background refreshes that have no door.
        from . import ai_policy
        if not await ai_policy.dataset_allows(db, dataset):
            return numbers
        if client is None:
            from ..core.config import settings
            if not settings.classify_columns_with_model:
                return numbers
            # Red light seen moments ago: asking would only wait for the
            # connect timeout to say the same thing (B-10 / AD-01).
            from . import llm_endpoints
            if not llm_endpoints.model_available()[0]:
                return numbers
            from . import llm
            client = llm.get_client()
        if not getattr(client, "enabled", True):
            return numbers
        todo = todo[:ASK_MAX_COLUMNS]
        others = [r.name for r in rows if r not in todo and (only is None or r.name in only)]
        cols = [{"name": r.name, "range": _range_of(r.stats), "description": r.description, "_others": others}
                for r in todo]
        messages = build_class_prompt(dataset.name, getattr(dataset, "description", None), cols)
        try:
            # Counted against the organisation's AI budget like every other
            # model call: under the request's meter when there is one, under
            # its own when this runs from a route or a refresh that has none.
            from . import llm as _llm
            if _llm.current_meter() is None and getattr(dataset, "org_id", None):
                from . import quotas
                async with quotas.metered(db, dataset.org_id, None, "metadata"):
                    got = await client.complete_json(messages, CLASS_SCHEMA, max_tokens=3000,
                                                     temperature=0.0, enforce=True)
            else:
                got = await client.complete_json(messages, CLASS_SCHEMA, max_tokens=3000,
                                                 temperature=0.0, enforce=True)
        except Exception:                                       # noqa: BLE001
            logger.warning("column classes: the model could not classify dataset %s", dataset.id, exc_info=True)
            got = None
        names = {r.name for r in todo}
        if not isinstance(got, dict):
            kept["failed_at"] = time.time()
        else:
            for x in got.get("numbers") or []:
                if not isinstance(x, dict) or x.get("column") not in names or x.get("kind") not in guard.NUMBER_KINDS:
                    continue
                numbers[x["column"]] = {
                    "kind": x["kind"], "unit": str(x.get("unit") or "")[:12],
                    "direction": x.get("direction") if x.get("direction") in guard.DIRECTIONS else "neither"}
            asked |= names
            kept.pop("failed_at", None)
            kept["model"] = str(getattr(client, "model", "") or "")
        kept["numbers"], kept["asked"] = numbers, sorted(asked)
        meta[AI_KEY] = kept
        dataset.column_meta = meta
        flag_modified(dataset, "column_meta")
        await db.commit()
        return numbers
    except Exception:                                           # noqa: BLE001
        logger.exception("column classes: asking the model about dataset %s failed", getattr(dataset, "id", None))
        try:
            await db.rollback()
        except Exception:                                       # noqa: BLE001
            pass
        return {}


def forget(column_meta: dict | None) -> dict:
    """The map with everything this module worked out removed, so the next
    scan classifies afresh and the model is asked again. What the AUTHOR set
    (`class_source: "confirmed"`) stays exactly as it is."""
    out: dict = {}
    for col, entry in (column_meta or {}).items():
        if col == AI_KEY:
            continue
        if isinstance(entry, dict) and not str(col).startswith("__") and entry.get("class_source") != "confirmed":
            entry = {k: v for k, v in entry.items() if k not in KEYS}
        out[col] = entry
    return out


async def hints_for(db, dataset, ask: bool = True, client=None, only: set[str] | None = None,
                    denied: set[str] | None = None) -> tuple[dict[str, dict], set[str]]:
    """What is KNOWN about this dataset's columns beyond their rows: the
    model's reading of each number (asked once, `model_hints`), and over it
    the connection's Meaning map, which was measured on the database."""
    asked = await model_hints(db, dataset, client, only, denied) if ask else {}
    mapped, outcomes = await _map_hints(db, dataset)
    return {**asked, **mapped}, outcomes


async def _map_hints(db, dataset) -> tuple[dict[str, dict], set[str]]:
    """What the connection's Meaning map knows about this dataset's columns."""
    if not getattr(dataset, "data_source_id", None):
        return {}, set()
    try:
        from .guided_setup import meaning
        m = await meaning.load(db, dataset.data_source_id)
    except Exception:                                           # noqa: BLE001
        return {}, set()
    numbers: dict[str, dict] = {}
    seen: dict[str, int] = {}
    for (_table, column), n in m.numbers.items():
        seen[column] = seen.get(column, 0) + 1
        numbers[column] = n
    # A column name that means two things in two tables is not taken on trust.
    numbers = {c: n for c, n in numbers.items() if seen[c] == 1}
    return numbers, {o["column"] for o in m.outcomes}


async def ensure(db, dataset, df: pd.DataFrame, ask: bool = True) -> dict:
    """The dataset's `column_meta` with every column classified, written back
    when anything was missing. Called where a frame is already in hand (the
    insights scan, the suggestion engines), so classifying costs no extra read.
    Never raises: an engine that cannot classify falls back to the names, as
    all of them did before."""
    try:
        current = dict(dataset.column_meta or {})
        numbers, outcomes = await hints_for(db, dataset, ask=ask, only={str(c) for c in df.columns})
        current = dict(dataset.column_meta or {})
        unclassified = [str(c) for c in df.columns if _open(current.get(str(c)), numbers.get(str(c)))]
        if not unclassified:
            return current
        import asyncio
        classes = await asyncio.to_thread(classify, df[unclassified], current, numbers=numbers, outcomes=outcomes)
        merged, changed = merge(current, classes)
        if changed:
            from sqlalchemy.orm.attributes import flag_modified
            dataset.column_meta = merged
            flag_modified(dataset, "column_meta")
            await db.commit()
        return merged
    except Exception:                                           # noqa: BLE001
        logger.exception("column classes: classifying dataset %s failed", getattr(dataset, "id", None))
        try:
            await db.rollback()
        except Exception:                                       # noqa: BLE001
            pass
        return dict(dataset.column_meta or {})
