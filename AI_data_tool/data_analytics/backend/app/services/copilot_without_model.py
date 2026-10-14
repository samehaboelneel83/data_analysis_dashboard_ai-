"""The page copilot's answer when no model may be called, or none answers.

The copilot changes a page from a sentence, and reading a sentence needs a
model. With "Allow AI" off for the data (services/ai_policy.py) it used to
refuse outright (409). It now says what the platform can do by itself for
what was typed (docs/discovery/PLAN.md §AW): which columns the words point
at, and which charts the platform has ALREADY built and checked on this data
for those columns -- each of them can be added from Suggest, no AI involved.

Nothing here guesses an edit: the page is not changed.
"""
from __future__ import annotations

from types import SimpleNamespace

from .agent.without_model import _mentioned

MAX_CHARTS = 5


def _columns_of(config: dict) -> set[str]:
    out: set[str] = set()
    for key in ("dimension", "dimension2", "measure", "measure2", "date_column", "target", "x", "y"):
        v = (config or {}).get(key)
        if isinstance(v, str) and v:
            out.add(v.casefold())
    for key in ("columns", "factors", "predictors"):
        for v in (config or {}).get(key) or []:
            if isinstance(v, str):
                out.add(v.casefold())
    return out


_WORDS = {
    "en": {"lead": "I could not use the AI model for this{why}, so the page was not changed. "
                   "Here is what can be done without AI.",
           "columns": "Columns your words point at: {cols}.",
           "none": "None of your words matched a column name in this data; try the name of a column as it is written.",
           "ready": "Charts the platform has already built and checked on this data{for_them}:",
           "for_them": " for those columns",
           "add": "Add any of them from Suggest in the builder, or drag the columns onto the page from Fields.",
           "drag": "Drag the columns onto the page from Fields, or open Suggest for charts built from this data.",
           "sep": ", "},
    "ar": {"lead": "تعذّر استخدام نموذج الذكاء الاصطناعي لهذا{why}، فلم تتغيّر الصفحة. "
                   "إليك ما يمكن فعله دون ذكاء اصطناعي.",
           "columns": "الأعمدة التي تشير إليها كلماتك: {cols}.",
           "none": "لم تطابق أيٌّ من كلماتك اسم عمود في هذه البيانات؛ جرّب اسم عمود كما هو مكتوب.",
           "ready": "مخططات بنتها المنصة وتحققت منها على هذه البيانات{for_them}:",
           "for_them": " لتلك الأعمدة",
           "add": "أضف أيًّا منها من «اقترح» في المنشئ، أو اسحب الأعمدة إلى الصفحة من «الحقول».",
           "drag": "اسحب الأعمدة إلى الصفحة من «الحقول»، أو افتح «اقترح» لمخططات مبنية من هذه البيانات.",
           "sep": "، "},
}
#: The reasons the router gives, in Arabic.
_REASONS_AR = {"AI is switched off for the data this dashboard reads": "الذكاء الاصطناعي موقوف للبيانات التي تقرؤها هذه اللوحة"}


def answer(message: str, columns_by_table: dict[str, dict[str, str]], cards: list[dict] | None,
           reason: str | None = None) -> dict:
    """{"reply": plain words in the language of the message, "suggestions": charts ready to add}."""
    from .agent.without_model import language_of
    from .readback import as_i18n
    lang = language_of(message)
    w = _WORDS[lang]
    why = (reason or "").strip()
    if lang == "ar":
        why = _REASONS_AR.get(why, why)
    lines = [w["lead"].format(why=f" ({why})" if why else "")]
    ctx = SimpleNamespace(objects={t: SimpleNamespace(columns=cols) for t, cols in (columns_by_table or {}).items()})
    hits = _mentioned(message, ctx)
    named = {c.casefold() for _t, c, _k in hits}
    lines += ["", w["columns"].format(cols=w["sep"].join(c for _t, c, _k in hits)) if hits else w["none"]]

    ready = []
    for card in cards or []:
        action = card.get("action") or {}
        if action.get("kind") != "add_widget" or not isinstance(action.get("config"), dict):
            continue
        used = _columns_of(action["config"])
        if named and not (used & named):
            continue
        ready.append({"title": str(card.get("title") or ""), "sentence": str(card.get("sentence") or ""),
                      # The card's own words as key + pieces, for a reader's language.
                      "title_i18n": card.get("title_i18n"), "sentence_i18n": card.get("sentence_i18n"),
                      "widget_type": action.get("widget_type"), "config": action["config"]})
        if len(ready) >= MAX_CHARTS:
            break
    lead = "\n".join(lines + (["", w["ready"].format(for_them=w["for_them"] if named else "")] if ready else []))
    if ready:
        lines += ["", w["ready"].format(for_them=w["for_them"] if named else "")]
        lines += [f"- {r['title']}" + (f": {r['sentence']}" if r["sentence"] else "") for r in ready]
        lines += ["", w["add"]]
    else:
        lines += ["", w["drag"]]
    # `reply` is the whole answer as text; `lead` is the same words without the
    # list, for a screen that shows each chart as a button to add it.
    return {"reply": "\n".join(lines), "lead": lead if ready else "\n".join(lines),
            "suggestions": ready, "language": lang}
