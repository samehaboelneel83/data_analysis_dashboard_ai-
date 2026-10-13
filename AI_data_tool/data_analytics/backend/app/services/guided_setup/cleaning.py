"""Check & discover cleans for the person (docs/guided-setup/PLAN_V2.md, part 2).

The check used to hand over a list of problems, each waiting for a click.
Someone who does not know data cannot judge "numbers stored as text"; they
want the data ready and to be told what was done. So what the check can fix
safely it fixes itself, says so in one summary, and keeps every decision
reversible:

* each automatic fix is an ordinary prep step on the dataset, marked
  `{"origin": "setup", "origin_id": ...}` -- the same step the person could
  have added by hand, visible on the dataset's own Prepare tab;
* Undo removes exactly that step; what was undone is remembered, so "Check
  again" never re-applies a fix the person took back;
* extreme values and future dates are never removed -- they may be true --
  only told to the person and to the dashboard designer.

Owner's decisions (2026-10-10): rows that break a rule the AI proposed are
left out automatically too, always named in the summary; copied rows are
removed in every case. Only datasets the setup itself created are cleaned:
an adopted dataset already has dashboards that count on its rows.
"""
from __future__ import annotations

import uuid

from . import health

#: The order fixes are applied in: tidy values first (so copies that differ
#: only by a space are caught), rows next, whole columns and copies last.
_ORDER = ("spaces", "textnum", "empty", "placeholder", "negative", "subtotal", "rule", "useless", "constant", "dups")

T = {
    "en": {
        "dups": "removed {n} copied rows",
        "subtotal": "left out {n} rows where “{col}” holds the totals of the other rows",
        "spaces": "removed extra spaces in “{col}”",
        "textnum": "turned “{col}” into numbers",
        "empty": "showed empty “{col}” as “Unknown”",
        "placeholder": "left out {n} rows where “{col}” holds a code for “unknown”",
        "negative": "left out {n} rows with a negative “{col}”",
        "rule": "left out rows that contradict themselves: {what}",
        "useless": "left out “{col}”, which is almost all empty",
        "constant": "left out “{col}”, which has one value in every row",
    },
    "ar": {
        "dups": "حذفنا {n} صفًا مكررًا",
        "subtotal": "استبعدنا {n} صفًا يحمل فيها «{col}» مجاميع الصفوف الأخرى",
        "spaces": "حذفنا المسافات الزائدة في «{col}»",
        "textnum": "حوّلنا «{col}» إلى أرقام",
        "empty": "أظهرنا الفارغ في «{col}» على أنه «غير معروف»",
        "placeholder": "استبعدنا {n} صفًا يحمل فيها «{col}» رمزًا لـ«غير معروف»",
        "negative": "استبعدنا {n} صفًا فيها «{col}» سالب",
        "rule": "استبعدنا صفوفًا تتناقض قيمها: {what}",
        "useless": "استبعدنا «{col}» لأنه فارغ تقريبًا بالكامل",
        "constant": "استبعدنا «{col}» لأن له قيمة واحدة في كل الصفوف",
    },
}


#: A rule the AI proposed is applied by itself only when it touches at most
#: this share of the rows. Above it the rule may describe something real --
#: "Same Day, yet took a day or more" was 4% of a courier's returns, and those
#: were its late parcels (Nile Express, 2026-10-10) -- so it is shown with
#: "Fix it" and left to the person.
AI_RULE_AUTO_SHARE = 0.01


def _auto_share() -> float:
    """The admin setting (Platform settings), else the default above."""
    from ...core.config import settings
    return float(getattr(settings, "setup_ai_rule_auto_share", AI_RULE_AUTO_SHARE))


def key_of(item: dict) -> str:
    """What a finding is about, stable across checks (its id carries a position)."""
    rule = (item.get("action") or {}).get("rule") or ""
    return f"{item.get('kind')}|{item.get('column') or ''}|{rule}"


def _said(lang: str, item: dict) -> str:
    table = T.get(lang, T["en"])
    n = f"{int(item.get('rows') or 0):,}"
    return table[item["kind"]].format(n=n, col=item.get("column") or "", what=item.get("what") or "")


def plan(items: list[dict], lang: str, *, undone: set[str] | None = None,
         protect: set[str] | None = None, rows: int | None = None) -> list[dict]:
    """The automatic fixes for these findings, in the order to apply them.

    `undone`: keys the person took back -- never planned again.
    `protect`: columns the person's request names -- never left out, however empty.
    `rows`: the dataset's size, for the share an AI rule may touch by itself."""
    undone, protect = undone or set(), {str(c).casefold() for c in (protect or set())}
    out = []
    for item in items:
        kind, action = item.get("kind"), item.get("action")
        if kind not in _ORDER or not action or key_of(item) in undone:
            continue
        if action.get("kind") == "drop_column" and str(action.get("column") or "").casefold() in protect:
            continue
        if kind == "rule" and rows and (item.get("rows") or 0) / rows > _auto_share():
            continue
        if kind == "dups" and item.get("keyed") is False:
            continue        # nothing names each row: "possible copies" are the person's call
        if kind == "rule" and item.get("describes"):
            continue        # one group's own rows: shown with "Fix it", never removed by itself
        step = health.prep_step_for(action, lang)
        if step is None:
            continue
        aid = uuid.uuid4().hex[:10]
        out.append({"id": aid, "key": key_of(item), "kind": kind, "column": item.get("column"),
                    "said": _said(lang, item), "rows": item.get("rows"), "ai": kind == "rule",
                    "step": {**step, "origin": "setup", "origin_id": aid},
                    "item": item, "state": "applied"})
    return sorted(out, key=lambda a: _ORDER.index(a["kind"]))


def steps_without(steps: list[dict], action_ids: set[str]) -> list[dict]:
    """The dataset's prep steps, minus the ones these automatic fixes added."""
    return [s for s in steps if not (isinstance(s, dict) and s.get("origin") == "setup"
                                     and s.get("origin_id") in action_ids)]


def steps_with(steps: list[dict], actions: list[dict]) -> list[dict]:
    """The steps plus these fixes, each once, automatic ones in `_ORDER`."""
    have = {s.get("origin_id") for s in steps if isinstance(s, dict) and s.get("origin") == "setup"}
    return list(steps) + [a["step"] for a in actions if a["id"] not in have]


def summary(state: dict | None, health_items: list[dict]) -> dict:
    """What the step says first: what was fixed, and what is still worth knowing."""
    actions = [a for a in (state or {}).get("actions") or [] if a.get("state") == "applied"]
    know = [i for i in health_items if i.get("tone") in ("problem", "warning", "info")]
    return {"fixed": [{"id": a["id"], "said": a["said"], "ai": bool(a.get("ai"))} for a in actions],
            "know": [{"id": i["id"], "what": i["what"]} for i in know[:3]],
            "more": max(0, len(know) - 3),
            "rows_before": (state or {}).get("rows_before"), "rows_after": (state or {}).get("rows_after")}
