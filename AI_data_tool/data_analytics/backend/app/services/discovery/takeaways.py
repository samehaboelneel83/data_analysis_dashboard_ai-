"""A dashboard page's key takeaways, said without a model
(docs/discovery/PLAN.md, phase 2 #16).

Each data widget on the page is computed exactly as the reader sees it, and
its result is read back into one sentence by the reader the suggestions
already use (services/readback.py) -- so a takeaway can only say what its
chart shows, with that chart's own numbers. The sentences are then put in the
order a person reads a page: the headline numbers, what changed over time,
how groups compare, what goes together.

Nothing here interprets, explains a cause or advises. A model may later
reword the list into a paragraph under the existing number check; this list
is what it would have to stay true to.
"""
from __future__ import annotations

from . import capabilities as caps

#: The order of a summary, by what kind of thing a widget shows.
_ORDER = ("basics", "forecast", "trend", "compare", "composition", "distribution", "place",
          "relationship", "pattern", "model", "flow", "table", "statistic", "anomaly", "scenario", "text")
_HEADING = {"basics": "headline", "trend": "over_time", "forecast": "over_time", "compare": "comparison",
            "composition": "comparison", "distribution": "spread", "place": "where", "relationship": "together",
            "pattern": "together", "model": "together", "flow": "together"}
#: Takeaways kept for one page; a longer list is not a summary.
MAX_LINES = 12


def _trend_sentence(result: dict) -> str | None:
    """What a KPI's history adds to its headline (widget_data.kpi_trend)."""
    trend = result.get("trend") if isinstance(result, dict) else None
    pct = (trend or {}).get("change_pct")
    if not isinstance(pct, (int, float)) or abs(pct) < 0.05:
        return None
    return (f"{trend['period']} was {abs(pct):.1f}% {'above' if pct > 0 else 'below'} {trend['previous_period']}.")


def summarise(items: list[dict]) -> dict:
    """`items`: [{"widget_id", "title", "widget_type", "config", "result"}] for
    the page's data widgets, results as the reader's. Returns the takeaways in
    reading order, and how many widgets had nothing to say."""
    from ..readback import as_i18n, takeaway
    lines, silent = [], 0
    for it in items:
        result, wt, cfg = it.get("result"), it.get("widget_type") or "", it.get("config") or {}
        if not isinstance(result, dict) or result.get("type") in ("error", "empty"):
            silent += 1
            continue
        try:
            said = takeaway(wt, cfg, result)
        except Exception:                                       # noqa: BLE001 -- one widget never sinks the page
            said = None
        extra = _trend_sentence(result)
        if not said and not extra:
            silent += 1
            continue
        cap = caps.widget(wt)
        family = cap.family if cap else "basics"
        sentence = " ".join(x for x in (str(said) if said else None, extra) if x)
        lines.append({
            "widget_id": it.get("widget_id"), "title": it.get("title") or "", "widget_type": wt,
            "family": family, "section": _HEADING.get(family, "other"),
            "claim": cap.claim if cap else "observation",
            "sentence": sentence, "sentence_i18n": as_i18n(said) if said and not extra else None,
            "sampled": bool(result.get("sampled")),
        })
    lines.sort(key=lambda x: (_ORDER.index(x["family"]) if x["family"] in _ORDER else len(_ORDER)))
    kept = lines[:MAX_LINES]
    return {"takeaways": kept, "widgets_read": len(items), "nothing_to_say": silent,
            "left_out": max(len(lines) - len(kept), 0), "source": "deterministic"}
