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

_AMOUNT = re.compile(r"(price|amount|cost|salary|wage|fee|qty|quantity|mileage|km|kilometer|age|"
                     r"revenue|sales|total|count|area|weight|height|rooms|bedrooms|bathrooms|duration)",
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
        "outliers.what": "“{col}” goes from {lo} to {hi}, and {n} values are far from the rest.",
        "outliers.why": "A few extreme values pull the average away from the typical value ({median}).",
        "outliers.todo": "Prefer the median to the average, and look at the extreme values before trusting totals.",
        "outliers.many.what": "{n} number columns have extreme values far from the rest: {cols}.",
        "outliers.many.why": "A few extreme values pull averages and totals away from what is typical.",
        "textnum.what": "“{col}” holds numbers stored as text.",
        "textnum.why": "Text cannot be added up, averaged or charted as an amount.",
        "textnum.todo": "Turn it into a number column.",
        "spaces.what": "{n} values of “{col}” have extra spaces.",
        "spaces.why": "“Cairo” and “Cairo ” are counted as two different values.",
        "spaces.todo": "Remove the extra spaces.",
        "constant.what": "“{col}” has the same value in every row.",
        "constant.why": "It cannot tell rows apart, so it adds nothing to a chart.",
        "constant.todo": "Leave this column out.",
        "dups.what": "{n} rows are exact copies of other rows.",
        "dups.why": "Counts and totals include them twice.",
        "dups.todo": "Remove the copies.",
        "negative.what": "{n} rows have a negative “{col}”.",
        "negative.why": "An amount like this cannot be below zero, so these are most likely entry mistakes.",
        "negative.todo": "Leave those rows out.",
        "future.what": "{n} rows of “{col}” are dates in the future.",
        "future.why": "Records cannot be dated later than today, so the dates are probably wrong.",
        "future.todo": "Check where these dates come from before charting by date.",
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
        "negative.what": "{n} صفًا بها «{col}» سالب.",
        "negative.why": "قيمة كهذه لا تكون أقل من الصفر، فهي على الأرجح أخطاء إدخال.",
        "negative.todo": "استبعد هذه الصفوف.",
        "future.what": "{n} صفًا من «{col}» تواريخ في المستقبل.",
        "future.why": "لا يمكن أن تكون السجلات بتاريخ بعد اليوم، فالتواريخ غالبًا خاطئة.",
        "future.todo": "تحقق من مصدر هذه التواريخ قبل الرسم حسب التاريخ.",
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


def column_items(report: dict, df: pd.DataFrame, lang: str) -> list[dict]:
    """Plain lines from the quality report, worst first."""
    rows = int(report.get("rows") or len(df))
    out: list[dict] = []
    if report.get("duplicate_rows"):
        n = int(report["duplicate_rows"])
        out.append(_item(len(out), "problem", "dups", lang, what=_t(lang, "dups.what", n=f"{n:,}"),
                         why=_t(lang, "dups.why"), todo=_t(lang, "dups.todo"), rows=n,
                         action={"kind": "dedupe", "label": _t(lang, "fix.dedupe")}))
    for c in report.get("column_report") or []:
        col, pct = c["column"], float(c.get("missing_pct") or 0) / 100
        numeric = col in df.columns and pd.api.types.is_numeric_dtype(df[col]) and df[col].dtype != bool
        issues = " ".join(c.get("issues") or [])
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
            act = None if numeric else {"kind": "fill", "column": col, "label": _t(lang, "fix.fill")}
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
        if numeric and rows and n_out / rows >= OUTLIER_SHARE:
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


def generic_rules(df: pd.DataFrame, lang: str, skip: set[str] | None = None) -> list[dict]:
    """Rules any database can break: negative amounts, dates in the future.
    `skip`: columns already explained (a -1 "unknown" code is not ALSO a
    negative amount)."""
    out: list[dict] = []
    for col in df.columns:
        if skip and col in skip:
            continue
        s = df[col]
        if pd.api.types.is_numeric_dtype(s) and s.dtype != bool and _AMOUNT.search(str(col)):
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


def _profile(df: pd.DataFrame) -> str:
    lines = []
    for col in list(df.columns)[:40]:
        s = df[col]
        if pd.api.types.is_numeric_dtype(s) and s.dtype != bool:
            q = s.dropna()
            kind = "percentage" if _PERCENT.search(str(col)) else "number"
            desc = (f"{kind}, min {_num(q.min())}, median {_num(q.median())}, max {_num(q.max())}"
                    if len(q) else f"{kind}, empty")
        elif pd.api.types.is_datetime64_any_dtype(s):
            desc = f"date, {s.min()} to {s.max()}"
        else:
            top = s.dropna().astype(str).value_counts().head(4).index.tolist()
            desc = "text, e.g. " + ", ".join(top)
        lines.append(f"- `{col}`: {desc}; {s.isna().mean():.0%} empty")
    return "\n".join(lines)


def build_rules_prompt(df: pd.DataFrame, brief: dict | None, lang: str) -> list[dict]:
    sample = df.head(5).to_dict(orient="records")
    system = (
        "You check a table for rows where two or more columns contradict each other. Every rule "
        "you write MUST name at least two different columns; a rule about one column is "
        "useless here (single-column checks are already done). Think about how the columns "
        "relate in the real world, for example:\n"
        "- a car several years old has been driven: `mileage_km` >= 1000 or `car_age_years` <= 1\n"
        "- an end comes after its start: `end_date` >= `start_date`\n"
        "- a part is not bigger than its whole: `discount` <= `price`;  `paid` <= `total`\n"
        "- two columns that say the same thing agree: `age` == 2026 - `birth_year`\n"
        "- a minimum is not above its maximum: `min_price` <= `max_price`\n"
        f"Propose up to {MAX_MODEL_RULES} such rules that EVERY correct row should satisfy, using only "
        "the columns listed. Write each as an expression with column names in backticks, using "
        "only comparisons (== != < <= > >=), arithmetic (+ - * /), numbers, quoted text and "
        "and/or/not -- no functions, and no 'implies' (write 'not A or B'). Columns marked "
        "'percentage' hold a percentage or a change, never an amount in the unit of other "
        "columns: do not compare them with prices or counts. Only rules true by the nature of the data, not preferences. "
        "what/why/todo are plain sentences for someone who never used a database, in "
        f"{_LANGUAGE.get(lang, 'English')}: what = what is wrong in the rows that break the rule, "
        "why = why it matters, todo = what to do. For each rule first list its `columns` (two or "
        "more) and the real-world `relation` between them in a few words, then the expression.")
    user = (f"Columns:\n{_profile(df)}\n\nFirst rows:\n{sample}\n\n"
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


async def model_rules(df: pd.DataFrame, brief: dict | None, lang: str, client) -> list[dict]:
    if client is None or not getattr(client, "enabled", True) or df.empty:
        return []
    got = await client.complete_json(build_rules_prompt(df, brief, lang), RULES_SCHEMA,
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
        out.append(_item(len(out), "warning", "rule", lang, column=", ".join(cols),
                         what=f"{str(r.get('what') or '').strip()} ({broken:,} / {judged:,})",
                         why=str(r.get("why") or "").strip(), todo=str(r.get("todo") or "").strip(),
                         rows=broken,
                         action={"kind": "exclude", "expression": _keep_rows(expr, cols), "rule": expr,
                                 "label": _t(lang, "fix.exclude")}))
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


def sensible(finding: dict) -> bool:
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
            if _LEVEL.search(str(col)) and not is_intensive(col):
                return False
    return True


async def plain_insights(findings: list[dict], brief: dict | None, lang: str, client) -> list[dict]:
    """The strongest findings, reworded for the person's work when the model can."""
    picked = [f for f in sorted(findings, key=lambda f: -(f.get("score") or 0))
              if f.get("kind") != "data_quality" and sensible(f)][:MAX_INSIGHTS]
    base = [{"id": f"insight:{i}", "tone": "insight", "kind": f.get("kind"),
             "what": f.get("title") or "", "why": f.get("detail") or "", "todo": None,
             "columns": f.get("columns") or [], "action": None} for i, f in enumerate(picked)]
    if not base or client is None or not getattr(client, "enabled", True):
        return base
    listing = "\n".join(f"{i}. {f.get('title')} -- {f.get('detail')}" for i, f in enumerate(picked))
    msgs = [{"role": "system", "content":
             "Reword each finding for the person below, in "
             f"{_LANGUAGE.get(lang, 'English')}, plainly and briefly. Keep every number exactly as "
             "given; add no new facts. Describe the data as what it is (for example market listings, "
             "cases, patients) -- never call it the person's own stock, clients or records unless "
             "they said so. what = the finding in one sentence; why = why it matters for their "
             "work; todo = one thing they could do or check next."},
            {"role": "user", "content": f"About the person: {brief or 'not given'}\n\nFindings:\n{listing}"}]
    got = await client.complete_json(msgs, WORDS_SCHEMA, max_tokens=1500, temperature=0.2, enforce=True)
    for w in (got or {}).get("items") or []:
        i = w.get("index")
        if isinstance(i, int) and 0 <= i < len(base) and str(w.get("what") or "").strip():
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
