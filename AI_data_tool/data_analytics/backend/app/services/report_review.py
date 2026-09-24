"""Report quality as CI (Phase 7.4): the review's HIGH findings, server-side.

The builder's Review pane runs a long checklist in the browser. The subset
that visibly misleads or excludes a reader -- the ones it marks `error` --
lives here too, so the server can hold a publish gate on them: a check that
only runs in the author's browser is advice, not a gate.

  * a data widget with no title and no alt text (a screen reader announces nothing)
  * an image with no alt text
  * an unfinished widget: required roles missing, so readers see a placeholder
  * an action aimed at a widget that no longer exists
  * a filter action aimed at another page without "sync across pages" (it can never apply)

Same wording as the pane, so the author sees one story in both places.
"""
from __future__ import annotations

DATA_TYPES_EXEMPT = {"text", "button", "image", "shape", "container", "slicer",
                     "web_content", "custom_visual"}


def high_findings(pages: list[dict]) -> list[dict]:
    """`pages`: [{id, name, widgets: [{id, widget_type, title, config}]}]."""
    from .widget_roles import missing_roles

    where: dict[int, int] = {}
    for p in pages:
        for w in p.get("widgets") or []:
            where[int(w["id"])] = int(p["id"])
    out: list[dict] = []
    for p in pages:
        for w in p.get("widgets") or []:
            cfg = w.get("config") or {}
            wt = w.get("widget_type") or ""
            name = w.get("title") or wt
            base = {"severity": "error", "widget_id": w["id"], "page_id": p["id"], "page": p.get("name")}
            if not w.get("title") and not cfg.get("alt_text") and wt not in DATA_TYPES_EXEMPT:
                out.append({**base, "category": "a11y",
                            "message": f"Untitled {wt} has no alt text — a screen reader announces nothing useful"})
            if wt == "image" and not cfg.get("alt"):
                out.append({**base, "category": "a11y", "message": "Image has no alt text"})
            if wt not in DATA_TYPES_EXEMPT and wt != "text":
                missing = missing_roles(wt, cfg)
                if missing:
                    out.append({**base, "category": "construction",
                                "message": f'"{name}" is unfinished — readers see a placeholder until '
                                           f'{", ".join(missing)} is set'})
            it = cfg.get("interaction") or {}
            for a in (it.get("actions") or []) if isinstance(it, dict) else []:
                if not isinstance(a, dict):
                    continue
                target = a.get("targetId")
                if target not in where:
                    out.append({**base, "category": "wiring",
                                "message": f'"{name}" has an action pointing at a widget that no longer exists '
                                           f'(#{target}) — the target was deleted and the action can never fire'})
                elif where[target] != p["id"] and not it.get("syncAllPages"):
                    out.append({**base, "category": "wiring",
                                "message": f'"{name}" filters a widget on another page, but is not set to sync '
                                           f'across pages — the filter can never apply there'})
    return out
