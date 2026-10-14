"""Step 3 of the guided setup: Check & discover (docs/guided-setup/PLAN.md, 3a-3c).

The quality report (services/data_quality.py) is correct and hard to read:
`nan 73%`, "1,567 outliers", "-1 looks like a code for unknown". This turns
it into lines that say WHAT is wrong, WHY it matters and WHAT TO DO, each
with a "Fix it" action where the app can do it (a prep step or a saved
check), in the reader's language.

Single-column checks come from the quality report. Problems ACROSS columns
(a ten-year-old car with 180 km; a negative price) come from two places,
both verified on the rows before they are shown:

* generic rules any database can break (negative amounts, future dates);
* rules the model proposes from the columns and a few rows -- each one is
  run, and kept only when it fails for a small, real share of the rows that
  have the values it needs. A rule the data cannot judge is dropped.

Insights come from the app's own statistical scan (services/insights.py);
the model only rewords the strongest ones for the person's work.
"""
from __future__ import annotations

import ast
import logging
import math
import re
from datetime import datetime, timedelta

import pandas as pd

logger = logging.getLogger(__name__)

#: Shares of empty values that are worth saying, and that make a column useless.
EMPTY_NOTE = 0.05
EMPTY_WARN = 0.20
EMPTY_USELESS = 0.90
#: Outliers worth a line: at least this share of the rows.
OUTLIER_SHARE = 0.005
#: A cross-column rule is kept when it fails for at least this many rows and
#: at most this share of them (more means the rule, not the data, is wrong:
#: EGX 2026-10-07, a rule that read a percentage as price points "failed"
#: 10.2% of rows; the real rules on Cars failed 2-4%).
RULE_MIN_ROWS = 3
RULE_MAX_SHARE = 0.10
MAX_MODEL_RULES = 6
MAX_INSIGHTS = 5

#: Names that hold a percentage or a change, not an amount in the same unit as
#: its neighbours -- said to the model so it does not compare them as such.
_PERCENT = re.compile(r"(pct|percent|percentage|ratio|rate|change|chg|return|growth)", re.I)
#: Level-like measures (a price, an index level, a change): a total of them
#: over a month means nothing.
_LEVEL = re.compile(r"(^|_)(close|open|high|low|change|chg|return|price|index|level|rate|pct|percent|ratio|"
                    r"avg|average|mean|median|score|rating)(_|$)", re.I)

_ID_COLUMN = re.compile(r"(^id$|_id$|^id_|_key$|^key$|_code$|_no$|^no$|number$)", re.I)

_AMOUNT = re.compile(r"(price|amount|cost|fee|qty|quantity|age|revenue|total|count|area|weight|height|"
                     r"length|distance|duration|مبلغ|سعر|كمية|عدد|وزن|مساحة|مدة)",
                     re.I)

T = {
    "en": {
        "empty.what": "{pct}% of “{col}” is empty.",
        "empty.why": "Charts using it describe only {kept}% of the rows, and blanks are easy to misread as “No”.",
        "empty.why.num": "Charts of it describe only {kept}% of the rows.",
        "empty.todo.text": "Treat empty values as “Unknown”, so they show up as their own group.",
        "empty.todo.num": "Totals and averages of “{col}” skip the empty rows; keep that in mind.",
        "useless.what": "“{col}” is almost all empty ({pct}%).",
        "useless.why": "There is too little in it to chart or compare.",
        "useless.todo": "Leave this column out.",
        "placeholder.what": "{n} rows of “{col}” hold {value}, which looks like a code for “unknown”.",
        "placeholder.why": "It is counted, added up and averaged as if it were a real value.",
        "placeholder.todo": "Leave those rows out of charts.",
        "rule.group": " Almost all of them are “{col}” = {value}: this may be how that group works, so it was not removed by itself.",
        "outliers.what": "“{col}” goes from {lo} to {hi}, and {n} values are far from the rest.",
        "outliers.why": "A few extreme values pull the average away from the typical value ({median}).",
        "outliers.todo": "Prefer the median to the average, and look at the extreme values before trusting totals.",
        "outliers.many.what": "{n} number columns have extreme values far from the rest: {cols}.",
        "outliers.many.why": "A few extreme values pull averages and totals away from what is typical.",
        "textnum.what": "“{col}” holds numbers stored as text.",
        "textnum.why": "Text cannot be added up, averaged or charted as an amount.",
        "textnum.todo": "Turn it into a number column.",
        "spaces.what": "{n} values of “{col}” have extra spaces.",
        "spaces.why": "“North” and “North ” are counted as two different values.",
        "spaces.todo": "Remove the extra spaces.",
        "constant.what": "“{col}” has the same value in every row.",
        "constant.why": "It cannot tell rows apart, so it adds nothing to a chart.",
        "constant.todo": "Leave this column out.",
        "dups.what": "{n} rows are exact copies of other rows.",
        "dups.why": "Counts and totals include them twice.",
        "dups.todo": "Remove the copies.",
        "dups.maybe.what": "{n} rows look the same as other rows, but no column here names each row, so they may be real repeats.",
        "dups.maybe.why": "Removing them would drop real rows if they are repeats; keeping them counts them twice if they are copies.",
        "dups.maybe.todo": "Remove them only if each row should be unique.",
        "negative.what": "{n} rows have a negative “{col}”.",
        "negative.why": "An amount like this cannot be below zero, so these are most likely entry mistakes.",
        "negative.todo": "Leave those rows out.",
        "future.what": "{n} rows of “{col}” are dates in the future.",
        "future.why": "Records cannot be dated later than today, so the dates are probably wrong.",
        "future.todo": "Check where these dates come from before charting by date.",
        "stray.what": "{n} rows of “{col}” are dated far outside the period the rest covers ({lo} to {hi}).",
        "stray.why": "A few rows years away make a time chart mostly empty and turn them into a baseline for comparisons.",
        "stray.todo": "Leave them out unless those dates are right.",
        "subtotal.what": "{n} rows where “{col}” is {value} hold the totals of the other rows (their “{measure}” adds up to about the same).",
        "subtotal.why": "Adding them to the other rows counts everything twice.",
        "subtotal.todo": "Leave the total rows out; the other rows add up to the same totals.",
        "odd.what": "{k} values of “{col}” are written unlike the rest ({values}), in {n} rows.",
        "odd.scale": "{k} values of “{col}” have “{m}” on another scale from the rest, a hundred times or more apart ({values}), in {n} rows.",
        "odd.why": "They may be a different kind of thing (totals, adjustments or tests, for example) and would be ranked beside the rest.",
        "odd.todo": "Leave them out if they are not the same kind of thing.",
        "good.what": "No problems found in {rows} rows and {cols} columns.",
        "good.why": "Empty values, copies, odd codes and extreme values were all checked.",
        "fix.fill": "Treat empty as “Unknown”", "fix.drop_column": "Leave the column out",
        "fix.exclude": "Leave those rows out", "fix.retype": "Make it a number", "fix.trim": "Remove the spaces",
        "fix.dedupe": "Remove the copies", "fix.check": "Warn me on every refresh",
        "unknown": "Unknown",
    },
    "ar": {
        "empty.what": "{pct}% من «{col}» فارغ.",
        "empty.why": "الرسوم التي تستخدمه تصف {kept}% فقط من الصفوف، ومن السهل أن يُفهم الفارغ على أنه «لا».",
        "empty.why.num": "رسومه تصف {kept}% فقط من الصفوف.",
        "empty.todo.text": "اعتبر القيم الفارغة «غير معروف» لتظهر كمجموعة مستقلة.",
        "empty.todo.num": "المجاميع والمتوسطات لـ«{col}» تتجاهل الصفوف الفارغة؛ ضع ذلك في اعتبارك.",
        "useless.what": "«{col}» فارغ تقريبًا بالكامل ({pct}%).",
        "useless.why": "ما فيه قليل جدًا للرسم أو المقارنة.",
        "useless.todo": "استبعد هذا العمود.",
        "placeholder.what": "{n} صفًا من «{col}» تحمل القيمة {value}، ويبدو أنها رمز لـ«غير معروف».",
        "placeholder.why": "تُعدّ وتُجمع ويُحسب متوسطها كأنها قيمة حقيقية.",
        "placeholder.todo": "استبعد هذه الصفوف من الرسوم.",
        "rule.group": " كلها تقريبًا «{col}» = {value}: قد تكون هذه طبيعة هذه المجموعة، لذلك لم تُستبعد تلقائيًا.",
        "outliers.what": "«{col}» يتراوح من {lo} إلى {hi}، و{n} قيمة بعيدة عن البقية.",
        "outliers.why": "بضع قيم متطرفة تسحب المتوسط بعيدًا عن القيمة المعتادة ({median}).",
        "outliers.todo": "استخدم الوسيط بدل المتوسط، وراجع القيم المتطرفة قبل الوثوق بالمجاميع.",
        "outliers.many.what": "{n} أعمدة أرقام بها قيم متطرفة بعيدة عن البقية: {cols}.",
        "outliers.many.why": "بضع قيم متطرفة تسحب المتوسطات والمجاميع بعيدًا عن المعتاد.",
        "textnum.what": "«{col}» يحمل أرقامًا مخزنة كنص.",
        "textnum.why": "لا يمكن جمع النص أو حساب متوسطه أو رسمه كمقدار.",
        "textnum.todo": "حوّله إلى عمود أرقام.",
        "spaces.what": "{n} قيمة في «{col}» بها مسافات زائدة.",
        "spaces.why": "تُعدّ «القاهرة» و«القاهرة » قيمتين مختلفتين.",
        "spaces.todo": "احذف المسافات الزائدة.",
        "constant.what": "«{col}» له القيمة نفسها في كل الصفوف.",
        "constant.why": "لا يميّز بين الصفوف، فلا يضيف شيئًا للرسم.",
        "constant.todo": "استبعد هذا العمود.",
        "dups.what": "{n} صفًا نسخ مطابقة لصفوف أخرى.",
        "dups.why": "تُحسب في العدّ والمجاميع مرتين.",
        "dups.todo": "احذف النسخ المكررة.",
        "dups.maybe.what": "{n} صفًا تبدو مطابقة لصفوف أخرى، لكن لا يوجد عمود يميّز كل صف، فقد تكون تكرارات حقيقية.",
        "dups.maybe.why": "حذفها يُسقط صفوفًا حقيقية إن كانت تكرارات، وإبقاؤها يعدّها مرتين إن كانت نسخًا.",
        "dups.maybe.todo": "احذفها فقط إذا كان كل صف يجب أن يكون فريدًا.",
        "negative.what": "{n} صفًا بها «{col}» سالب.",
        "negative.why": "قيمة كهذه لا تكون أقل من الصفر، فهي على الأرجح أخطاء إدخال.",
        "negative.todo": "استبعد هذه الصفوف.",
        "future.what": "{n} صفًا من «{col}» تواريخ في المستقبل.",
        "future.why": "لا يمكن أن تكون السجلات بتاريخ بعد اليوم، فالتواريخ غالبًا خاطئة.",
        "future.todo": "تحقق من مصدر هذه التواريخ قبل الرسم حسب التاريخ.",
        "stray.what": "{n} صفًا من «{col}» مؤرخة بعيدًا خارج الفترة التي تغطيها بقية البيانات ({lo} إلى {hi}).",
        "stray.why": "بضعة صفوف بعيدة بسنوات تجعل الرسم الزمني فارغًا تقريبًا وتصبح أساسًا للمقارنات.",
        "stray.todo": "استبعدها ما لم تكن هذه التواريخ صحيحة.",
        "subtotal.what": "{n} صفًا قيمة «{col}» فيها {value} تحمل مجاميع الصفوف الأخرى (مجموع «{measure}» فيها يساوي مجموع الباقي).",
        "subtotal.why": "جمعها مع الصفوف الأخرى يحسب كل شيء مرتين.",
        "subtotal.todo": "استبعد صفوف المجاميع؛ الصفوف الأخرى تعطي المجاميع نفسها.",
        "odd.what": "{k} قيمة من «{col}» مكتوبة بشكل مختلف عن البقية ({values})، في {n} صفًا.",
        "odd.scale": "{k} قيمة من «{col}» قيم «{m}» فيها على مقياس آخر غير البقية، بفارق مئة مرة أو أكثر ({values})، في {n} صفًا.",
        "odd.why": "قد تكون نوعًا مختلفًا من الأشياء (مجاميع أو تسويات أو اختبارات مثلًا) وستُرتَّب بجانب البقية.",
        "odd.todo": "استبعدها إن لم تكن من النوع نفسه.",
        "good.what": "لم نجد مشكلات في {rows} صف و{cols} عمود.",
        "good.why": "فُحصت القيم الفارغة والنسخ المكررة والرموز الغريبة والقيم المتطرفة.",
        "fix.fill": "اعتبر الفارغ «غير معروف»", "fix.drop_column": "استبعد العمود",
        "fix.exclude": "استبعد هذه الصفوف", "fix.retype": "اجعله أرقامًا", "fix.trim": "احذف المسافات",
        "fix.dedupe": "احذف النسخ", "fix.check": "نبّهني عند كل تحديث",
        "unknown": "غير معروف",
    },
}


def _t(lang: str, key: str, **kw) -> str:
    table = T.get(lang, T["en"])
    return (table.get(key) or T["en"][key]).format(**kw)


def _num(v, lang: str = "en") -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if math.isnan(f):
        return "—"
    if abs(f) >= 1000 or f == int(f):
        return f"{f:,.0f}"
    return f"{f:,.2f}"


def _pct(share: float) -> int:
    """A share as a whole percent, halves rounded up as people do (66.5 -> 67)."""
    return int(math.floor(share * 100 + 0.5))


def _q(col: str) -> str:
    return f"`{col}`"


def _keep_rows(rule: str, cols: list[str]) -> str:
    """A filter that keeps rows satisfying `rule` AND rows the rule cannot judge
    (an empty value in a column it needs): `x != x` is true only for empty."""
    unknown = " or ".join(f"{_q(c)} != {_q(c)}" for c in cols)
    return f"({rule}) or {unknown}" if unknown else rule


def _item(i: int, tone: str, kind: str, lang: str, *, column=None, what, why, todo,
          action=None, rows=None) -> dict:
    return {"id": f"{kind}:{column or ''}:{i}", "tone": tone, "kind": kind, "column": column,
            "what": what, "why": why, "todo": todo, "action": action, "rows": rows}


def _number_of(col: str, column_meta: dict | None) -> str | None:
    """What a number was classified as (services/column_classes.py), or None
    for a column nobody classified -- its name is then the fallback."""
    from ..semantic_guard import recorded_number
    return recorded_number(col, column_meta)


#: A nearly empty column is a DETAIL of some rows when at least this many
#: values are in it, this share of them sit on the rows another column marks,
#: and it is filled on at least this share of those marked rows.
DETAIL_MIN_VALUES = 20
DETAIL_INSIDE = 0.95
DETAIL_COVERS = 0.5
#: The marking column must itself single out a minority of the rows.
DETAIL_MARK_MAX_SHARE = 0.3


def detail_of(df: pd.DataFrame, col: str) -> str | None:
    """The column whose "yes" (or non-zero count) marks the rows `col` is
    filled on, or None. Read from the rows alone: no column name is consulted."""
    if col not in df.columns:
        return None
    filled = df[col].notna()
    if pd.api.types.is_object_dtype(df[col]):
        filled &= df[col].astype(str).str.strip() != ""
    n = int(filled.sum())
    if n < DETAIL_MIN_VALUES:
        return None
    for other in df.columns:
        if other == col:
            continue
        s = df[other]
        if s.dtype == bool or set(s.dropna().unique().tolist()[:3]) <= {True, False}:
            mark = s.fillna(False).astype(bool)
        elif pd.api.types.is_numeric_dtype(s):
            mark = s.fillna(0) != 0
        else:
            continue
        marked = int(mark.sum())
        if not marked or marked / len(df) > DETAIL_MARK_MAX_SHARE:
            continue
        inside = int((filled & mark).sum())
        if inside >= DETAIL_INSIDE * n and inside >= DETAIL_COVERS * marked:
            return str(other)
    return None


#: A column with at least this share of distinct values names each row.
ROW_KEY_SHARE = 0.95


def has_row_key(df: pd.DataFrame) -> bool:
    """Whether a column names each row: text or whole numbers, almost all
    distinct. Only then are identical rows certainly copies of one row."""
    n = len(df)
    if not n:
        return False
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_float_dtype(s) or pd.api.types.is_bool_dtype(s) \
                or pd.api.types.is_datetime64_any_dtype(s):
            continue
        try:
            if s.nunique(dropna=True) >= ROW_KEY_SHARE * n:
                return True
        except TypeError:
            continue
    return False


def column_items(report: dict, df: pd.DataFrame, lang: str, column_meta: dict | None = None) -> list[dict]:
    """Plain lines from the quality report, worst first."""
    rows = int(report.get("rows") or len(df))
    out: list[dict] = []
    if report.get("duplicate_rows"):
        n = int(report["duplicate_rows"])
        keyed = has_row_key(df)
        if keyed:
            out.append(_item(len(out), "problem", "dups", lang, what=_t(lang, "dups.what", n=f"{n:,}"),
                             why=_t(lang, "dups.why"), todo=_t(lang, "dups.todo"), rows=n,
                             action={"kind": "dedupe", "label": _t(lang, "fix.dedupe")}))
        else:
            # Nothing here names each row: two real, identical sales lines look
            # like copies once the invoice number is not in the dataset (persona
            # test 2026-10-12). Said, and left to the person.
            out.append(_item(len(out), "warning", "dups", lang, what=_t(lang, "dups.maybe.what", n=f"{n:,}"),
                             why=_t(lang, "dups.maybe.why"), todo=_t(lang, "dups.maybe.todo"), rows=n,
                             action={"kind": "dedupe", "label": _t(lang, "fix.dedupe")}))
        out[-1]["keyed"] = keyed
    for c in report.get("column_report") or []:
        col, pct = c["column"], float(c.get("missing_pct") or 0) / 100
        numeric = col in df.columns and pd.api.types.is_numeric_dtype(df[col]) and df[col].dtype != bool
        issues = " ".join(c.get("issues") or [])
        if pct >= EMPTY_USELESS and detail_of(df, col) is not None:
            # Empty on purpose: it is filled exactly where another column says
            # "yes" (hours to resolve, on the rows that have a complaint). It is
            # a detail of those rows, not a broken column -- leaving it out took
            # away the answer to a question asked about it (retry-2, 2026-10-11).
            continue
        if pct >= EMPTY_USELESS:
            out.append(_item(len(out), "warning", "useless", lang, column=col,
                             what=_t(lang, "useless.what", col=col, pct=_pct(pct)),
                             why=_t(lang, "useless.why"), todo=_t(lang, "useless.todo"),
                             action={"kind": "drop_column", "column": col, "label": _t(lang, "fix.drop_column")}))
            continue
        # One value AND blanks ("Yes" or empty) is a flag column whose story is
        # the blanks, not a constant one.
        if "constant" in (c.get("issues") or []) and pct < EMPTY_NOTE:
            out.append(_item(len(out), "info", "constant", lang, column=col,
                             what=_t(lang, "constant.what", col=col), why=_t(lang, "constant.why"),
                             todo=_t(lang, "constant.todo"),
                             action={"kind": "drop_column", "column": col, "label": _t(lang, "fix.drop_column")}))
            continue
        if pct >= EMPTY_NOTE:
            # A date cannot be "Unknown": the word would turn the column into text.
            dated = col in df.columns and pd.api.types.is_datetime64_any_dtype(df[col])
            act = None if numeric or dated else {"kind": "fill", "column": col, "label": _t(lang, "fix.fill")}
            out.append(_item(len(out), "warning" if pct >= EMPTY_WARN else "info", "empty", lang, column=col,
                             what=_t(lang, "empty.what", col=col, pct=_pct(pct)),
                             why=_t(lang, "empty.why.num" if numeric else "empty.why", kept=_pct(1 - pct)),
                             todo=_t(lang, "empty.todo.num" if numeric else "empty.todo.text", col=col),
                             action=act, rows=int(c.get("missing") or 0)))
        ph = c.get("placeholder")
        if ph:
            value = ph["value"]
            lit = repr(value) if isinstance(value, str) else str(value)
            rule = f"{_q(col)} != {lit}"
            out.append(_item(len(out), "warning", "placeholder", lang, column=col,
                             what=_t(lang, "placeholder.what", n=f"{int(ph['rows']):,}", col=col, value=lit),
                             why=_t(lang, "placeholder.why"), todo=_t(lang, "placeholder.todo"),
                             rows=int(ph["rows"]),
                             action={"kind": "exclude", "expression": _keep_rows(rule, [col]), "rule": rule,
                                     "label": _t(lang, "fix.exclude")}))
        n_out = c.get("outliers") or 0
        # An identifier has no "extreme values": branch 17 is not far from branch 1.
        _kind = _number_of(col, column_meta)
        if numeric and rows and n_out / rows >= OUTLIER_SHARE and (
                _kind != "code" if _kind else not _ID_COLUMN.search(str(col))):
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(s):
                out.append(_item(len(out), "info", "outliers", lang, column=col,
                                 what=_t(lang, "outliers.what", col=col, lo=_num(s.min()), hi=_num(s.max()),
                                         n=f"{int(n_out):,}"),
                                 why=_t(lang, "outliers.why", median=_num(s.median())),
                                 todo=_t(lang, "outliers.todo"), rows=int(n_out)))
        if "numbers stored as text" in issues:
            out.append(_item(len(out), "warning", "textnum", lang, column=col,
                             what=_t(lang, "textnum.what", col=col), why=_t(lang, "textnum.why"),
                             todo=_t(lang, "textnum.todo"),
                             action={"kind": "retype", "column": col, "label": _t(lang, "fix.retype")}))
        m = re.search(r"([\d,]+) values? with leading/trailing spaces", issues)
        if m:
            out.append(_item(len(out), "info", "spaces", lang, column=col,
                             what=_t(lang, "spaces.what", n=m.group(1), col=col), why=_t(lang, "spaces.why"),
                             todo=_t(lang, "spaces.todo"),
                             action={"kind": "trim", "column": col, "label": _t(lang, "fix.trim")}))
    return _merge_outliers(out, lang)


#: From this many "extreme values" lines on, they read as one.
MERGE_OUTLIERS_AT = 3


def _merge_outliers(items: list[dict], lang: str) -> list[dict]:
    """Four near-identical "extreme values" lines (a stock table: close,
    change, market close, market change) read as noise; one line naming the
    columns says the same thing once (owner: simple first)."""
    lines = [i for i in items if i["kind"] == "outliers"]
    if len(lines) < MERGE_OUTLIERS_AT:
        return items
    cols = [i["column"] for i in lines]
    sep = "، " if lang == "ar" else ", "
    merged = _item(0, "info", "outliers", lang, column=", ".join(cols),
                   what=_t(lang, "outliers.many.what", n=len(cols), cols=sep.join(f"“{c}”" for c in cols)),
                   why=_t(lang, "outliers.many.why"), todo=_t(lang, "outliers.todo"),
                   rows=sum(i.get("rows") or 0 for i in lines))
    merged["id"] = "outliers:many:0"
    first = items.index(lines[0])
    rest = [i for i in items if i["kind"] != "outliers"]
    return rest[:first] + [merged] + rest[first:]


def generic_rules(df: pd.DataFrame, lang: str, skip: set[str] | None = None,
                  column_meta: dict | None = None) -> list[dict]:
    """Rules any database can break: negative amounts, dates in the future.
    `skip`: columns already explained (a -1 "unknown" code is not ALSO a
    negative amount)."""
    out: list[dict] = []
    for col in df.columns:
        if skip and col in skip:
            continue
        s = df[col]
        # A quantity that cannot be below zero: by its classification (an
        # amount, a count, a duration) when it has one, else by its name.
        _kind = _number_of(str(col), column_meta)
        _never_negative = (_kind in ("amount", "count", "duration")) if _kind else bool(_AMOUNT.search(str(col)))
        if pd.api.types.is_numeric_dtype(s) and s.dtype != bool and _never_negative:
            n = int((s < 0).sum())
            if n >= 1 and n / max(1, s.notna().sum()) <= RULE_MAX_SHARE:
                rule = f"{_q(col)} >= 0"
                out.append(_item(len(out), "warning", "negative", lang, column=col,
                                 what=_t(lang, "negative.what", n=f"{n:,}", col=col),
                                 why=_t(lang, "negative.why"), todo=_t(lang, "negative.todo"), rows=n,
                                 action={"kind": "exclude", "expression": _keep_rows(rule, [col]), "rule": rule,
                                         "label": _t(lang, "fix.exclude")}))
        elif pd.api.types.is_datetime64_any_dtype(s):
            try:
                ts = pd.to_datetime(s, errors="coerce", utc=True)
                n = int((ts > pd.Timestamp(datetime.utcnow() + timedelta(days=1), tz="UTC")).sum())
            except Exception:                                       # noqa: BLE001
                n = 0
            if n:
                out.append(_item(len(out), "warning", "future", lang, column=col,
                                 what=_t(lang, "future.what", n=f"{n:,}", col=col),
                                 why=_t(lang, "future.why"), todo=_t(lang, "future.todo"), rows=n))
            # Dates far outside the period the rest of the data covers: offered as
            # a fix to accept, never applied by itself (they may be true).
            from ..relative_dates import stray_dates
            stray = stray_dates(s)
            if stray:
                lo, hi = str(stray["lo"].date()), str((stray["hi"] + timedelta(days=1)).date())
                rule = f"{_q(col)} >= '{lo}' and {_q(col)} < '{hi}'"
                out.append(_item(len(out), "warning", "stray", lang, column=col,
                                 what=_t(lang, "stray.what", n=f"{stray['rows']:,}", col=col, lo=lo,
                                         hi=str(stray["hi"].date())),
                                 why=_t(lang, "stray.why"), todo=_t(lang, "stray.todo"), rows=stray["rows"],
                                 action={"kind": "exclude", "expression": _keep_rows(rule, [col]), "rule": rule,
                                         "label": _t(lang, "fix.exclude")}))
    try:
        out += subtotal_items(df, lang)
    except Exception:                                               # noqa: BLE001 -- a finding, never a gate
        pass
    try:
        out += odd_items(df, lang)
    except Exception:                                               # noqa: BLE001
        pass
    return out


#: A category value is a subtotal when its rows equal the sum of the other
#: values' rows (within 5%) in at least this share of the groups compared,
SUBTOTAL_MATCH_SHARE = 0.5
SUBTOTAL_TOLERANCE = 0.05
#: ...in at least this share of groups the total is not below its parts...
SUBTOTAL_COVERS = 0.9
#: ...and the totals differ by at most this share overall (a total may carry
#: a few rows its details lack, such as an unrecorded group).
SUBTOTAL_GAP = 0.12
SUBTOTAL_MAX_VALUES = 60
#: Larger tables, and more category columns, are not searched (cost).
SUBTOTAL_MAX_ROWS = 200_000
SUBTOTAL_MAX_COLUMNS = 8


def subtotal_members(df: pd.DataFrame) -> list[dict]:
    """[{"column", "value", "rows", "measure"}]: category values whose rows are
    the totals of their sibling values -- found by arithmetic, not by the
    word "all" or "total". Persona test 2026-10-12: population summed to
    162.8 million (twice the real 81.4) because each governorate had a row
    per gender AND a row for both."""
    numbers = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and df[c].dtype != bool
               and df[c].nunique(dropna=True) > 2]

    def year_like(c) -> bool:
        v = pd.to_numeric(df[c], errors="coerce").dropna()
        return bool(len(v)) and bool(((v % 1 == 0) & (v >= 1800) & (v <= 2200)).all())

    # The main amount only: the number with the largest total. An age or a
    # bound can "add up" by the symmetry of the layout (refugees by age band).
    numbers = [c for c in numbers if not year_like(c)]
    if not numbers:
        return []
    pool = numbers
    cats = []
    for c in df.columns:
        if c in numbers or pd.api.types.is_datetime64_any_dtype(df[c]):
            continue
        try:
            n = int(df[c].nunique(dropna=True))
        except TypeError:
            continue
        if 3 <= n <= SUBTOTAL_MAX_VALUES:
            cats.append(c)
    if len(df) > SUBTOTAL_MAX_ROWS:
        return []
    cats = cats[:SUBTOTAL_MAX_COLUMNS]
    # A number one category fixes (an age band's lower bound) describes the
    # band; it is not an amount to add up.
    pool = [c for c in pool if not any(df.groupby(o)[c].nunique().max() <= 1 for o in cats)]
    if not pool:
        return []
    numbers = [max(pool, key=lambda c: float(pd.to_numeric(df[c], errors="coerce").abs().sum()))]
    out = []
    for c in cats:
        for value in df[c].dropna().unique().tolist():
            is_v = df[c] == value
            # Totals nest: "both genders" rows may exist only for "all ages".
            # Such a companion column is held at its one value on both sides
            # and is not a group to compare within.
            fixed = {o: df.loc[is_v, o].iloc[0] for o in cats if o != c
                     and df.loc[is_v, o].nunique(dropna=False) == 1 and df[o].nunique(dropna=True) > 1}
            others = [o for o in cats if o != c and o not in fixed]
            same = pd.Series(True, index=df.index)
            for o, held in fixed.items():
                same &= df[o] == held
            for m in numbers:
                v = pd.to_numeric(df[m], errors="coerce")
                keys = [df[o].astype(str) for o in others] if others else [pd.Series("all", index=df.index)]
                part = v.where(is_v).groupby(keys).sum(min_count=1)
                rest = v.where(~is_v & df[c].notna() & same).groupby(keys).sum(min_count=1)
                both = pd.concat([part, rest], axis=1, keys=["p", "r"]).dropna()
                both = both[both["p"] != 0]
                if len(both) < (3 if others else 1):
                    continue
                # Weighted by size: small groups with rounded or suppressed
                # counts do not hide a total that holds for the bulk of the rows.
                gap = float((both["p"] - both["r"]).abs().sum()) / float(both["p"].abs().sum())
                close = ((both["p"] - both["r"]).abs() <= SUBTOTAL_TOLERANCE * both["p"].abs()).mean()
                # A total is never smaller than its parts: in almost every group.
                covers = (both["p"] >= (1 - SUBTOTAL_TOLERANCE) * both["r"]).mean()
                if gap <= SUBTOTAL_GAP and close >= SUBTOTAL_MATCH_SHARE and covers >= SUBTOTAL_COVERS:
                    out.append({"column": str(c), "value": value.item() if hasattr(value, "item") else value,
                                "rows": int(is_v.sum()), "measure": str(m)})
                    break
            if out and out[-1]["column"] == str(c):
                break                       # one subtotal value per column
    return out


def subtotal_items(df: pd.DataFrame, lang: str) -> list[dict]:
    out = []
    for i, sub in enumerate(subtotal_members(df)):
        col, value = sub["column"], sub["value"]
        lit = repr(value) if isinstance(value, str) else str(value)
        rule = f"{_q(col)} != {lit}"
        out.append(_item(i, "problem", "subtotal", lang, column=col,
                         what=_t(lang, "subtotal.what", n=f"{sub['rows']:,}", col=col, value=value,
                                 measure=sub["measure"]),
                         why=_t(lang, "subtotal.why"), todo=_t(lang, "subtotal.todo"), rows=sub["rows"],
                         action={"kind": "exclude", "expression": _keep_rows(rule, [col]), "rule": rule,
                                 "label": _t(lang, "fix.exclude")}))
    return out


#: A column is code-like when its two commonest value shapes cover this share
#: of its distinct values; a value whose shape is rarer than ODD_SHAPE_SHARE
#: is written unlike the rest, when such values are at most ODD_MAX_SHARE.
CODE_SHAPES_SHARE = 0.8
ODD_SHAPE_SHARE = 0.01
ODD_MAX_SHARE = 0.03
ODD_MIN_DISTINCT = 30
ODD_SHOWN = 6


def value_shape(v) -> str:
    """'85123A' -> '99999A', 'EGX 30' -> 'AAA_99': digits, letters, spaces."""
    t = re.sub(r"\d", "9", str(v).strip())
    t = re.sub(r"[^\W\d_]", "A", t)
    t = re.sub(r"\s", "_", t)
    return re.sub(r"[^\w]", ".", t)


def odd_members(df: pd.DataFrame) -> list[dict]:
    """[{"column", "values", "rows"}]: in a column of codes written one way
    (five digits; four letters), the few values written another way. Persona
    test 2026-10-12: index names ranked among stock tickers as "the most
    traded companies"; postage and fee lines among product codes as "top
    products"."""
    out = []
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s) or s.dtype == bool:
            continue
        try:
            distinct = pd.Series(s.dropna().astype(str).unique())
        except TypeError:
            continue
        n = len(distinct)
        if n < ODD_MIN_DISTINCT:
            continue
        shapes = distinct.map(value_shape)
        counts = shapes.value_counts()
        if float(counts.iloc[:2].sum()) < CODE_SHAPES_SHARE * n:
            continue                    # free text, not codes
        rare = counts[counts < max(1.0, ODD_SHAPE_SHARE * n)].index
        # A number of another length is the same kind of thing (an amount
        # written as text: 9,950 beside 10,772), not an odd one out.
        odd = [v for v in distinct[shapes.isin(rare)].tolist() if not re.fullmatch(r"-?\d+([.,]\d+)?", v.strip())]
        if not odd or len(odd) > ODD_MAX_SHARE * n:
            continue
        rows = int(s.astype(str).isin(odd).sum())
        out.append({"column": str(c), "values": odd, "rows": rows})
    return out


#: Members on another scale: their typical value is at least SCALE_GAP times
#: away from every other member's (a gap in the ranked medians, not a long
#: tail), and they are at most SCALE_MAX_SHARE of the members.
SCALE_GAP = 100.0
SCALE_MAX_SHARE = 0.10
SCALE_MIN_MEMBERS = 10
SCALE_MIN_ROWS = 3
SCALE_MAX_ROWS = 200_000


def scale_members(df: pd.DataFrame, skip: set[str] | None = None) -> list[dict]:
    """[{"column", "measure", "values", "rows"}]: members of a category whose
    typical value of a measure sits in a cluster of its own, orders of
    magnitude from the rest -- an index's traded value beside companies', a
    country total beside its regions. Read from the numbers only."""
    import numpy as np
    if len(df) > SCALE_MAX_ROWS:
        df = df.sample(SCALE_MAX_ROWS, random_state=0)
    from ..widget_data import _is_id_like_column
    # Amounts only: never an identifier, never a signed number (a profit near
    # zero is not on another scale).
    nums = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and df[c].dtype != bool
            and not _is_id_like_column(str(c)) and not (pd.to_numeric(df[c], errors="coerce") < 0).any()][:12]
    out = []
    for c in df.columns:
        s = df[c]
        if str(c) in (skip or set()) or c in nums or pd.api.types.is_numeric_dtype(s) \
                or pd.api.types.is_datetime64_any_dtype(s) or s.dtype == bool:
            continue
        keys = s.astype(str).where(s.notna())
        if not SCALE_MIN_MEMBERS <= keys.nunique() <= 5000:
            continue
        sample = keys.dropna().head(200)
        if len(sample) and pd.to_datetime(sample, errors="coerce", format="mixed").notna().mean() >= 0.9:
            continue                    # dates written as text: a calendar, not members
        for m in nums:
            v = pd.to_numeric(df[m], errors="coerce")
            pos = v[(v > 0) & keys.notna()]
            g = pos.groupby(keys[pos.index])
            med = g.median()[g.size() >= SCALE_MIN_ROWS]
            if len(med) < SCALE_MIN_MEMBERS:
                continue
            logs = np.log10(med.sort_values())
            gaps = logs.diff().iloc[1:]
            at = int(gaps.values.argmax()) + 1
            if float(gaps.max()) < np.log10(SCALE_GAP):
                continue
            low, high = list(logs.index[:at]), list(logs.index[at:])
            odd = high if len(high) <= len(low) else low
            if len(odd) > SCALE_MAX_SHARE * len(med):
                continue
            out.append({"column": str(c), "measure": str(m), "values": [str(x) for x in odd],
                        "rows": int(keys.isin(odd).sum())})
            break
    return out


def odd_items(df: pd.DataFrame, lang: str) -> list[dict]:
    out = []
    found = odd_members(df)
    try:
        found += [{**x, "scale": True} for x in scale_members(df, {o["column"] for o in found})]
    except Exception:                                               # noqa: BLE001 -- a finding, never a gate
        pass
    for i, odd in enumerate(found):
        col, values = odd["column"], odd["values"]
        shown = ", ".join(f"“{v}”" for v in values[:ODD_SHOWN]) + (" …" if len(values) > ODD_SHOWN else "")
        rule = f"{_q(col)} not in {[str(v) for v in values]!r}"
        out.append(_item(i, "warning", "odd", lang, column=col,
                         what=_t(lang, "odd.scale" if odd.get("scale") else "odd.what", k=f"{len(values):,}",
                                 col=col, values=shown, n=f"{odd['rows']:,}", m=odd.get("measure", "")),
                         why=_t(lang, "odd.why"), todo=_t(lang, "odd.todo"), rows=odd["rows"],
                         action={"kind": "exclude", "expression": _keep_rows(rule, [col]), "rule": rule,
                                 "label": _t(lang, "fix.exclude")}))
        out[-1]["values"] = [str(v) for v in values]
    return out


# ── rules the model proposes, kept only when the data agrees ─────────────────

RULES_SCHEMA = {
    "type": "object",
    "properties": {"rules": {"type": "array", "items": {
        "type": "object",
        "properties": {"columns": {"type": "array", "items": {"type": "string"}, "minItems": 2},
                       "relation": {"type": "string"},
                       "expression": {"type": "string"}, "what": {"type": "string"},
                       "why": {"type": "string"}, "todo": {"type": "string"}},
        "required": ["columns", "relation", "expression", "what", "why", "todo"]}}},
    "required": ["rules"],
}

_LANGUAGE = {"ar": "Arabic (Modern Standard, simple words)", "en": "English"}


#: A text column with at most this many different values is a category.
FEW_VALUES = 20


def _profile(df: pd.DataFrame, column_meta: dict | None = None) -> str:
    lines = []
    for col in list(df.columns)[:40]:
        s = df[col]
        if pd.api.types.is_numeric_dtype(s) and s.dtype != bool:
            q = s.dropna()
            _kind = _number_of(str(col), column_meta)
            kind = ("percentage" if _kind == "share" else _kind) if _kind \
                else "percentage" if _PERCENT.search(str(col)) else "number"
            desc = (f"{kind}, min {_num(q.min())}, median {_num(q.median())}, max {_num(q.max())}"
                    if len(q) else f"{kind}, empty")
        elif pd.api.types.is_datetime64_any_dtype(s):
            desc = f"date, {s.min()} to {s.max()}"
        else:
            # A CATEGORY's values are its labels and say what the column is; a
            # column of many different texts (names, addresses, notes) is
            # described by its shape, and none of its contents leave the
            # server.
            text = s.dropna().astype(str)
            distinct = int(text.nunique())
            if distinct <= FEW_VALUES:
                desc = "category, values: " + ", ".join(v[:40] for v in text.value_counts().head(6).index.tolist())
            else:
                lengths = text.str.len()
                desc = (f"text, {distinct:,} different values, {int(lengths.min())}-{int(lengths.max())} characters"
                        if len(text) else "text, empty")
        lines.append(f"- `{col}`: {desc}; {s.isna().mean():.0%} empty")
    return "\n".join(lines)


def build_rules_prompt(df: pd.DataFrame, brief: dict | None, lang: str,
                       column_meta: dict | None = None) -> list[dict]:
    # NO ROWS are sent: the model reasons about how the COLUMNS relate, and for
    # that their names, kinds, ranges and category labels are enough. (Until
    # 2026-10-10 the first five rows went too -- real values of real people.)
    system = (
        "You check a table for rows where two or more columns contradict each other. Every rule "
        "you write MUST name at least two different columns; a rule about one column is "
        "useless here (single-column checks are already done). Think about how the columns "
        "relate in the real world, for example:\n"
        "- an end comes after its start: `end_date` >= `start_date`\n"
        "- a part is not bigger than its whole: `discount` <= `price`;  `paid` <= `total`\n"
        "- two columns that say the same thing agree: `age` == 2026 - `birth_year`\n"
        "- a minimum is not above its maximum: `min_price` <= `max_price`\n"
        f"Propose up to {MAX_MODEL_RULES} such rules that EVERY correct row should satisfy, using only "
        "the columns listed. Write each as an expression with column names in backticks, using "
        "only comparisons (== != < <= > >=), arithmetic (+ - * /), numbers, quoted text and "
        "and/or/not -- no functions, and no 'implies' (write 'not A or B'). Columns marked "
        "'percentage' hold a percentage or a change, never an amount in the unit of other "
        "columns: do not compare them with prices or counts. Only rules true by the nature of the data, not "
        "preferences -- and never a promise or a target: a late completion, a missed deadline, an overrun budget or "
        "a failed service level is a real event the person needs to see, not a contradiction. "
        "what/why/todo are plain sentences for someone who never used a database, in "
        f"{_LANGUAGE.get(lang, 'English')}: what = what is wrong in the rows that break the rule, "
        "why = why it matters, todo = what to do. For each rule first list its `columns` (two or "
        "more) and the real-world `relation` between them in a few words, then the expression.")
    from ..llm import data_block
    user = (f"Columns:\n{data_block(_profile(df, column_meta), 'column summaries')}\n\n"
            f"About the person (hints): {brief or 'not given'}")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


_ALLOWED_NODES = (ast.Expression, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare, ast.Name, ast.Constant,
                  ast.And, ast.Or, ast.Not, ast.USub, ast.UAdd, ast.Add, ast.Sub, ast.Mult, ast.Div,
                  ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Load)


def normalise_rule(expr: str, columns: list[str]) -> str:
    """The model's rule in the filter syntax: "A implies B" becomes
    "not (A) or (B)", and a bare column name gets its backticks."""
    text = (expr or "").strip()
    parts = re.split(r"\s+implies\s+|\s*=>\s*", text, maxsplit=1, flags=re.I)
    if len(parts) == 2:
        text = f"not ({parts[0]}) or ({parts[1]})"
    for col in sorted(columns, key=len, reverse=True):
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", col):
            text = re.sub(rf"(?<![`\w]){re.escape(col)}(?![`\w])", f"`{col}`", text)
    return text


def rule_columns(expr: str, columns: list[str]) -> list[str] | None:
    """The columns a rule uses, or None when it is not a plain comparison rule."""
    names = {}
    text = expr
    for i, col in enumerate(sorted(columns, key=len, reverse=True)):
        token = f"__c{i}__"
        if f"`{col}`" in text:
            names[token] = col
            text = text.replace(f"`{col}`", token)
    if "`" in text:
        return None
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return None
    used = []
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            return None
        if isinstance(node, ast.Name):
            if node.id not in names:
                return None
            used.append(names[node.id])
    used = list(dict.fromkeys(used))
    return used if len(used) >= 2 else None


def verify_rule(df: pd.DataFrame, expr: str) -> tuple[int, int] | None:
    """(rows breaking the rule, rows it could judge), or None when it cannot run."""
    from ..widget_data import apply_filter_expr
    cols = rule_columns(expr, [str(c) for c in df.columns])
    if not cols:
        return None
    judged = df.dropna(subset=cols)
    if not len(judged):
        return None
    try:
        kept = apply_filter_expr(judged, expr, silent=False)
    except Exception:                                               # noqa: BLE001
        return None
    return len(judged) - len(kept), len(judged)


#: A rule whose broken rows are almost all one value of a category, and most
#: of that value's rows, describes how that group works rather than a mistake.
RULE_GROUP_SHARE = 0.8
RULE_GROUP_COVER = 0.5


def rule_describes_group(df: pd.DataFrame, expr: str) -> dict | None:
    """{"column", "value"} when the rows breaking `expr` are one group's own
    rows. Persona test 2026-10-12: "a no-charge trip with a fare" removed
    19,453 trips -- nearly every no-charge trip, since a waived fare is still
    recorded."""
    from ..widget_data import apply_filter_expr
    cols = rule_columns(expr, [str(c) for c in df.columns])
    if not cols:
        return None
    judged = df.dropna(subset=cols)
    try:
        kept = apply_filter_expr(judged, expr, silent=False)
    except Exception:                                               # noqa: BLE001
        return None
    broken = judged.loc[~judged.index.isin(kept.index)]
    if not len(broken):
        return None
    for c in judged.columns:
        if str(c) in cols:
            continue                # the rule's own columns say what broke, not which group
        s = judged[c]
        if pd.api.types.is_numeric_dtype(s) and s.dtype != bool and s.nunique(dropna=True) > 12:
            continue
        try:
            if not 2 <= int(s.nunique(dropna=True)) <= 60:
                continue
        except TypeError:
            continue
        top = broken[c].value_counts(dropna=True)
        if top.empty:
            continue
        value, n = top.index[0], int(top.iloc[0])
        group = int((s == value).sum())
        if n >= RULE_GROUP_SHARE * len(broken) and group and n >= RULE_GROUP_COVER * group:
            return {"column": str(c), "value": value.item() if hasattr(value, "item") else value}
    return None


async def model_rules(df: pd.DataFrame, brief: dict | None, lang: str, client,
                      column_meta: dict | None = None) -> list[dict]:
    if client is None or not getattr(client, "enabled", True) or df.empty:
        return []
    got = await client.complete_json(build_rules_prompt(df, brief, lang, column_meta), RULES_SCHEMA,
                                     max_tokens=1800, temperature=0.1, enforce=True)
    out = []
    for r in (got or {}).get("rules") or []:
        expr = normalise_rule(str(r.get("expression") or ""), [str(c) for c in df.columns])
        res = verify_rule(df, expr) if expr else None
        if res is None:
            continue
        broken, judged = res
        if broken < RULE_MIN_ROWS or broken / judged > RULE_MAX_SHARE:
            continue
        cols = rule_columns(expr, [str(c) for c in df.columns]) or []
        group = rule_describes_group(df, expr)
        note = _t(lang, "rule.group", col=group["column"], value=group["value"]) if group else ""
        out.append(_item(len(out), "warning", "rule", lang, column=", ".join(cols),
                         what=f"{str(r.get('what') or '').strip()} ({broken:,} / {judged:,}){note}",
                         why=str(r.get("why") or "").strip(), todo=str(r.get("todo") or "").strip(),
                         rows=broken,
                         action={"kind": "exclude", "expression": _keep_rows(expr, cols), "rule": expr,
                                 "label": _t(lang, "fix.exclude")}))
        if group:
            out[-1]["describes"] = group
    return out


# ── insights, in plain words ────────────────────────────────────────────────

WORDS_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"index": {"type": "integer"}, "what": {"type": "string"},
                       "why": {"type": "string"}, "todo": {"type": "string"}},
        "required": ["index", "what", "why"]}}},
    "required": ["items"],
}


def sensible(finding: dict, kinds: dict | None = None) -> bool:
    """False for a finding no reader should be shown.

    The statistics engine treats any number it does not know as additive, so
    on a stock table it reported "Stock_close in 2023-11 ran 325% above its
    monthly average" (a SUM of daily closing prices) and "outlying rows carry
    113% / -33% of stock_change" (EGX, 2026-10-07). Two generic tests:
    a share outside 0-100% is impossible, and a total or trend of a
    level-like measure the engine did not already average is meaningless."""
    from ..semantic_guard import is_intensive
    figures = finding.get("figures") or {}
    share = figures.get("share_pct")
    if isinstance(share, (int, float)) and not 0 <= share <= 100:
        return False
    if finding.get("kind") in ("trend", "outlier_impact"):
        for col in finding.get("columns") or []:
            # A column whose kind is stored (amount, count, level...) was
            # summed or averaged by the engine by that kind: its name decides
            # nothing. Only an unclassified one is judged by its words.
            if (kinds or {}).get(str(col)):
                continue
            if _LEVEL.search(str(col)) and not is_intensive(col):
                return False
    return True


#: Measures whose TOTAL means something. The statistics engine totals every
#: number; a month's total of delivery days or of delivery attempts is the
#: month's volume again, said as if it were a finding.
_ADDITIVE = re.compile(r"(amount|revenue|fee|cost|total|qty|quantity|value|paid|income|expense|profit|spend|budget|"
                       r"units|مبلغ|قيمة|كمية|إجمالي|اجمالي)", re.I)
_TOTALLED = ("trend", "standout", "laggard")
#: Said already by the check ("a few extreme values..."), and never an insight.
_NOT_INSIGHTS = ("data_quality", "outlier_impact")


def totals_mean_something(finding: dict, df: pd.DataFrame, kinds: dict | None = None) -> bool:
    """False for a finding built on the total of a number that is not an amount.

    `kinds`: what each column is, from the connection's Meaning map
    ({column: "amount" | "level" | ...}); the name is only the fallback for a
    column the map does not know."""
    if finding.get("kind") not in _TOTALLED:
        return True
    numbers = [c for c in finding.get("columns") or []
               if c in df.columns and pd.api.types.is_numeric_dtype(df[c]) and df[c].dtype != bool]
    return all((kinds or {}).get(c) in ("amount", "count") if (kinds or {}).get(c)
               else bool(_ADDITIVE.search(str(c))) for c in numbers)


#: A group's share of a total must differ from its share of the rows by this
#: many points before it is worth saying.
SIZE_MARGIN = 5.0
_NOTHING = {"", "nan", "none", "null", "nat"}


def beyond_size(finding: dict, df: pd.DataFrame) -> bool:
    """False for "Delivered carries 89% of delivery days" when 89% of the rows
    ARE delivered: the group is big, and that is all the line says (Nile
    Express, 2026-10-10 -- every insight shown was one of these). Also false
    for a line about the group of empty values."""
    member = (finding.get("figures") or {}).get("member")
    if member is None:
        return True
    if str(member).strip().casefold() in _NOTHING:
        return False
    share = (finding.get("figures") or {}).get("share_pct")
    cols = [c for c in finding.get("columns") or [] if c in df.columns]
    if finding.get("kind") not in ("standout", "laggard") or not isinstance(share, (int, float)) or not cols:
        return True
    of_rows = float((df[cols[0]].astype(str) == str(member)).mean() * 100)
    return abs(share - of_rows) >= SIZE_MARGIN


async def plain_insights(findings: list[dict], brief: dict | None, lang: str, client,
                         kinds: dict | None = None) -> list[dict]:
    """The strongest findings, reworded for the person's work when the model can."""
    picked = [f for f in sorted(findings, key=lambda f: -(f.get("score") or 0))
              if f.get("kind") not in _NOT_INSIGHTS and sensible(f, kinds)][:MAX_INSIGHTS]
    base = [{"id": f"insight:{i}", "tone": "insight", "kind": f.get("kind"),
             "what": f.get("title") or "", "why": f.get("detail") or "", "todo": None,
             # The computed sentences' keys: kept while the words are still the
             # engine's own, so a run opened in another language reads in it.
             "what_i18n": f.get("title_i18n"), "why_i18n": f.get("detail_i18n"),
             "columns": f.get("columns") or [], "action": None} for i, f in enumerate(picked)]
    if not base or client is None or not getattr(client, "enabled", True):
        return base
    listing = "\n".join(f"{i}. {f.get('title')} -- {f.get('detail')}" for i, f in enumerate(picked))
    msgs = [{"role": "system", "content":
             "Reword each finding for the person below, in "
             f"{_LANGUAGE.get(lang, 'English')}, plainly and briefly. Keep every number exactly as "
             "given; add no new facts. Describe the data as what it is, in its own words -- never "
             "call it the person's own stock, clients or records unless "
             "they said so. what = the finding in one sentence; why = what it means, only as far as "
             "the finding itself shows -- never guess a cause, and never link it to their problem "
             "unless the finding measures that link; todo = one thing they could check next, or "
             "empty."},
            {"role": "user", "content": f"About the person: {brief or 'not given'}\n\nFindings:\n{listing}"}]
    got = await client.complete_json(msgs, WORDS_SCHEMA, max_tokens=1500, temperature=0.2, enforce=True)
    for w in (got or {}).get("items") or []:
        i = w.get("index")
        if isinstance(i, int) and 0 <= i < len(base) and str(w.get("what") or "").strip():
            base[i].update(what_i18n=None, why_i18n=None)       # the model's words now
            base[i].update(what=str(w["what"]).strip(), why=str(w.get("why") or "").strip(),
                           todo=(str(w.get("todo")).strip() or None) if w.get("todo") else None)
    return base


def good_item(df: pd.DataFrame, lang: str) -> dict:
    return _item(0, "good", "good", lang, what=_t(lang, "good.what", rows=f"{len(df):,}", cols=len(df.columns)),
                 why=_t(lang, "good.why"), todo=None)


def prep_step_for(action: dict, lang: str) -> dict | None:
    """The prep step a "Fix it" action adds, or None when it is not a prep step."""
    kind = action.get("kind")
    col = action.get("column")
    if kind == "fill":
        return {"kind": "fill_nulls", "column": col, "method": "value", "value": _t(lang, "unknown")}
    if kind == "drop_column":
        return {"kind": "remove_columns", "columns": [col]}
    if kind == "exclude":
        return {"kind": "filter_rows", "expression": action["expression"]}
    if kind == "retype":
        return {"kind": "retype", "column": col, "to": "numeric"}
    if kind == "trim":
        return {"kind": "trim", "columns": [col]}
    if kind == "dedupe":
        return {"kind": "drop_duplicates"}
    return None
