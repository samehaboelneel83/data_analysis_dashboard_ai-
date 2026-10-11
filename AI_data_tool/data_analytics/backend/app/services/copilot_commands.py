"""Plain page instructions the copilot can carry out with no model.

Reading a sentence in general needs a model. A short list of instructions does
not: "add a bar chart of amount by group", "remove Totals", "rename it to
"Monthly view"", "make it a line chart", "top 5", "sort ascending". With AI
switched off for the data (or no model answering) the copilot used to change
nothing (docs/discovery/PLAN.md §AW). It now carries these out, through the
same checked path a model's edits take (routers/report_copilot.py): the same
column check, the same revision, the same undo.

Rules, not guesses:
* a column counts only when EVERY word of its name is in the message;
* an existing chart is the one selected, the one whose whole title is in the
  message, or the only chart on the page -- otherwise nothing is done;
* a message this does not fully recognise returns None, and the caller says
  what else can be done without AI. Nothing here is specific to any data.
"""
from __future__ import annotations

import re

from .agent.without_model import _kind, language_of

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_QUOTED = re.compile(r"[\"“”«»']([^\"“”«»']{1,120})[\"“”«»']")
_NUMBER = re.compile(r"\d+")
_PLAIN = ("text", "slicer", "button", "image")

_ADD = {"add", "create", "show", "draw", "insert", "plot", "أضف", "اضف", "أنشئ", "انشئ", "ارسم", "اعرض", "أعرض"}
_REMOVE = {"remove", "delete", "drop", "احذف", "امسح", "أزل", "ازل"}
_RENAME = {"rename", "retitle", "سمّ", "سم", "سمِّ", "أعد", "غيّر", "غير"}
_RENAME_HINT = {"rename", "retitle", "title", "name", "تسمية", "اسم", "عنوان", "سمّ", "سم", "سمِّ"}
_CHANGE = {"change", "make", "convert", "turn", "switch", "حوّل", "حول", "اجعل", "اجعله", "اجعلها", "غيّر", "غير"}
_TOP = {"top", "first", "highest", "largest", "أعلى", "اعلى", "أكبر", "اكبر", "أول", "اول"}
_SORT = {"sort", "order", "رتّب", "رتب"}
_ASC = {"ascending", "asc", "smallest", "lowest", "تصاعدي", "تصاعديا", "تصاعديًا"}
_DESC = {"descending", "desc", "largest", "highest", "تنازلي", "تنازليا", "تنازليًا"}
_KINDS = {
    "bar": {"bar", "bars", "column", "columns", "أعمدة", "اعمدة", "شريطي"},
    "line": {"line", "trend", "خطي", "خط"},
    "area": {"area", "مساحي", "مساحة"},
    "donut": {"donut", "doughnut", "pie", "دائري", "دائرية"},
    "table": {"table", "جدول"},
    "kpi": {"kpi", "number", "card", "total", "رقم", "مؤشر", "بطاقة"},
    "scatter": {"scatter", "انتشار", "مبعثر"},
    "treemap": {"treemap"},
}
_AGGS = {
    "avg": {"average", "avg", "mean", "متوسط"},
    "count": {"count", "عدد"},
    "sum": {"sum", "total", "مجموع", "إجمالي", "اجمالي"},
    "max": {"max", "maximum", "أقصى", "اقصى"},
    "min": {"min", "minimum", "أدنى", "ادنى"},
}
_SAID = {
    "en": {"done": "Done without AI — this was a plain instruction.",
           "agg": {"sum": "Total", "avg": "Average", "count": "Count of", "max": "Highest", "min": "Lowest"},
           "by": "by", "rows": "Number of rows"},
    "ar": {"done": "تم دون ذكاء اصطناعي — كان هذا طلبًا مباشرًا.",
           "agg": {"sum": "إجمالي", "avg": "متوسط", "count": "عدد", "max": "أعلى", "min": "أدنى"},
           "by": "حسب", "rows": "عدد الصفوف"},
}


#: Arabic short-vowel marks and the stretching dash: a word is the same word with or without them.
_MARKS = re.compile(r"[\u064B-\u0652\u0640]")


def _words(text: str) -> list[str]:
    return [w.casefold() for w in _WORD.findall(_MARKS.sub("", text or ""))]


for _name in ("_ADD", "_REMOVE", "_RENAME", "_RENAME_HINT", "_CHANGE", "_TOP", "_SORT", "_ASC", "_DESC"):
    globals()[_name] = {_MARKS.sub("", w) for w in globals()[_name]}
_KINDS = {k: {_MARKS.sub("", w) for w in v} for k, v in _KINDS.items()}
_AGGS = {k: {_MARKS.sub("", w) for w in v} for k, v in _AGGS.items()}


def _named_columns(message: str, columns: dict[str, str]) -> list[tuple[str, str]]:
    """(column, kind) for each column whose every word is in the message, in
    the order they are mentioned. A column whose words are all part of a
    longer matched column's name is that longer column, not a second one."""
    said = _words(message)
    have = set(said)
    found = []
    for name, dtype in columns.items():
        parts = _words(str(name))
        if parts and all(p in have for p in parts):
            found.append((min(said.index(p) for p in parts), str(name), _kind(dtype), set(parts)))
    found.sort(key=lambda f: (f[0], -len(f[3])))
    kept: list[tuple[int, str, str, set]] = []
    for f in sorted(found, key=lambda f: -len(f[3])):
        if not any(f[3] < k[3] for k in kept):
            kept.append(f)
    return [(name, kind) for _at, name, kind, _p in sorted(kept, key=lambda f: f[0])]


def _kind_asked(words: set[str]) -> str | None:
    return next((k for k, names in _KINDS.items() if names & words), None)


def _target(message: str, widgets: list[dict], selected: int | None) -> dict | None:
    charts = [w for w in widgets if w.get("widget_type") not in _PLAIN]
    low = " ".join(_words(message))
    titled = [w for w in widgets if w.get("title") and " ".join(_words(str(w["title"]))) and
              " ".join(_words(str(w["title"]))) in low]
    if titled:
        return max(titled, key=lambda w: len(str(w["title"])))
    if selected is not None:
        return next((w for w in widgets if w.get("id") == selected), None)
    return charts[0] if len(charts) == 1 else None


def _create(message: str, words: set[str], columns: dict[str, str], lang: str) -> dict | None:
    named = _named_columns(message, columns)
    numbers = [c for c, k in named if k == "number"]
    dates = [c for c, k in named if k == "date"]
    cats = [c for c, k in named if k == "category"]
    kind = _kind_asked(words - {p for c, _k in named for p in _words(c)})
    agg = next((a for a, names in _AGGS.items() if names & words), None)
    if not named:
        return None
    w = _SAID[lang]
    if kind == "table":
        return {"op": "create", "widget_type": "table", "title": ", ".join(c for c, _k in named)[:120],
                "config": {"columns": ",".join(c for c, _k in named)}}
    if kind == "scatter":
        if len(numbers) < 2:
            return None
        return {"op": "create", "widget_type": "scatter", "title": f"{numbers[0]} / {numbers[1]}"[:120],
                "config": {"dimension": numbers[0], "measure": numbers[1]}}
    split = (dates or cats or [None])[0]
    measure = numbers[0] if numbers else None
    agg = agg or ("sum" if measure else "count")
    if measure is None and agg != "count":
        return None
    config: dict = {"aggregation": agg}
    if measure and agg != "count":
        config["measure"] = measure
    what = f"{w['agg'][agg]} {measure}" if measure and agg != "count" else w["rows"]
    if split is None:
        if kind not in (None, "kpi"):
            return None
        return {"op": "create", "widget_type": "kpi", "title": what[:120], "config": config}
    config["dimension"] = split
    if split in dates:
        config["dimension_granularity"] = "month"
    chosen = kind if kind not in (None, "kpi") else ("line" if split in dates else "bar")
    return {"op": "create", "widget_type": chosen, "title": f"{what} {w['by']} {split}"[:120], "config": config}


def parse(message: str, widgets: list[dict], columns_by_table: dict[str, dict[str, str]],
          selected: int | None = None) -> dict | None:
    """{"reply", "actions", "data_question": None} for a plain instruction, in
    the shape a model's answer has; None when the message is not one."""
    text = (message or "").strip()
    said = _words(text)
    if not said or len(text) > 300:
        return None
    words = set(said)
    lang = language_of(text)
    # The first table is the dashboard's own dataset: a new chart reads it.
    columns = next(iter((columns_by_table or {}).values()), {})
    first = said[0]
    quoted = [q.strip() for q in _QUOTED.findall(text) if q.strip()]
    action = None

    if first in _ADD:
        action = _create(text, words, columns, lang)
    elif first in _REMOVE:
        target = _target(text, widgets, selected)
        if target is not None:
            action = {"op": "delete", "widget_id": target["id"]}
    elif (first in _RENAME and words & _RENAME_HINT) and quoted:
        # The new title is the LAST thing in quotes; a title quoted before it names the chart.
        target = _target(text.replace(quoted[-1], " "), widgets, selected)
        if target is not None:
            action = {"op": "update", "widget_id": target["id"], "title": quoted[-1][:120]}
    elif first in _SORT and (words & (_ASC | _DESC)):
        target = _target(text, widgets, selected)
        if target is not None:
            action = {"op": "update", "widget_id": target["id"],
                      "config": {"sort": "asc" if words & _ASC and not words & (_DESC - _ASC) else "desc"}}
    elif first in _TOP and _NUMBER.search(text):
        target = _target(text, widgets, selected)
        n = int(_NUMBER.search(text).group())
        if target is not None and 1 <= n <= 100:
            action = {"op": "update", "widget_id": target["id"], "config": {"limit": n, "sort": "desc"}}
    elif first in _CHANGE:
        target = _target(text, widgets, selected)
        kind = _kind_asked(words - set(_words(str((target or {}).get("title") or ""))))
        if target is not None and kind and kind != target.get("widget_type"):
            action = {"op": "update", "widget_id": target["id"], "widget_type": kind}
    if action is None:
        return None
    return {"reply": _SAID[lang]["done"], "actions": [action], "data_question": None, "language": lang}
