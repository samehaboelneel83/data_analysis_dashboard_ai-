"""E17: where an inventory item stands, derived from its evidence.

An item's status is never stored. It follows from the row:

    retired      the decision is "retire"
    signed_off   the owner signed off (and the linked report is still the one signed)
    reconciled   every widget compared against the old export agreed
    differences  a comparison was recorded and something disagreed
    mapped       a Datalytics report replaces it; nothing compared yet
    to_map       nothing replaces it yet

so a status cannot claim more than the evidence shows. A sign-off records its
basis: "reconciled" (every recorded comparison agreed), "accepted" (the owner
accepted recorded differences, with a note saying why) or "no_comparison"
(there was nothing to compare -- a job, a dataset -- with a note saying so).
The report's revision is kept with the sign-off: when the report changes
afterwards the item says so rather than silently standing on an old check.
A comparison recorded after the sign-off that disagrees withdraws it.
"""
from __future__ import annotations

from datetime import datetime, timezone

STATUSES = ("to_map", "mapped", "differences", "reconciled", "signed_off", "retired")

#: One entry per widget compared; an item replacing a 60-widget report is
#: already unusual, so this bounds a runaway client, not a real migration.
MAX_RECONCILES = 100


def clean(entry: dict) -> bool:
    c = entry.get("counts") or {}
    return bool(c) and not (c.get("mismatch") or c.get("missing_in_widget") or c.get("missing_in_file"))


def current_reconciles(item) -> dict:
    """The comparisons recorded against the report the item links to now;
    ones made against a report it no longer links to are history."""
    return {k: v for k, v in (item.reconciles or {}).items()
            if item.report_id is not None and v.get("report_id") == item.report_id}


def status_of(item) -> str:
    if item.decision == "retire":
        return "retired"
    so = item.sign_off or None
    if so and item.report_id is not None and so.get("report_id") == item.report_id:
        return "signed_off"
    if so and so.get("basis") == "no_comparison" and item.report_id is None:
        return "signed_off"
    if item.report_id is None:
        return "to_map"
    recs = current_reconciles(item)
    if not recs:
        return "mapped"
    return "reconciled" if all(clean(v) for v in recs.values()) else "differences"


def sign_off_basis(item, note: str | None, accept_differences: bool) -> str:
    """The basis a sign-off would have now, or ValueError saying what is
    missing. The rules are the module docstring's."""
    note = (note or "").strip()
    if item.decision == "retire":
        raise ValueError("A retired item is not signed off; change the decision to migrate first")
    if item.kind == "report" and item.report_id is None:
        raise ValueError("Link the Datalytics report that replaces it first")
    recs = current_reconciles(item)
    if recs:
        if all(clean(v) for v in recs.values()):
            return "reconciled"
        if not accept_differences:
            raise ValueError("The comparison found differences: reconcile again, or accept them with a note")
        if not note:
            raise ValueError("Say in the note why the differences are acceptable")
        return "accepted"
    if item.kind == "report":
        raise ValueError("Reconcile the report with the old export before signing off")
    if not note:
        raise ValueError("Nothing was compared: say in the note why no comparison is needed")
    return "no_comparison"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_reconcile(item, *, key: str, title: str | None, counts: dict, file: str | None,
                     user, revision: int | None) -> dict:
    """Keep one comparison on the item: the latest per widget, against the
    report it links to. A new dict, so the JSON column sees the change."""
    entry = {"title": (title or "")[:200] or None, "counts": dict(counts), "file": (file or "")[:255] or None,
             "at": now_iso(), "by": user.id, "by_email": user.email,
             "report_id": item.report_id, "revision": revision}
    key = key[:80]
    recs = {k: v for k, v in (item.reconciles or {}).items() if k != key}
    recs[key] = entry
    if len(recs) > MAX_RECONCILES:
        oldest = sorted(recs, key=lambda k: recs[k].get("at", ""))[: len(recs) - MAX_RECONCILES]
        for k in oldest:
            recs.pop(k)
    item.reconciles = recs
    # A sign-off stands on the evidence it was given on. A later comparison
    # that disagrees takes it away: the item must not say "signed off" beside
    # a comparison that says otherwise. One that agrees leaves it.
    if item.sign_off and item.sign_off.get("report_id") == item.report_id and not clean(entry):
        item.sign_off = None
        entry["withdrew_sign_off"] = True
    return entry
