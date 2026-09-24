"""Stage 6 — schema fingerprinting and drift detection.

ARCHITECTURE.md: "On change, emit a drift event — do not resync silently.
Confirmed annotations on removed columns are orphaned and must be flagged."

Both halves of that matter, and the second is the one that is easy to get wrong.

WHY NOT SILENTLY RESYNC
------------------------
A schema change is a business event, not a technical one. A column that
disappeared may be the column a dozen widgets group by; a column whose type
changed from text to numeric may silently alter every comparison in a filter.
Quietly absorbing that and carrying on produces a system where reports change
their meaning overnight and nobody knows why. So drift is recorded and
surfaced, and a human decides.

WHY ORPHANED ANNOTATIONS ARE FLAGGED, NOT DELETED
--------------------------------------------------
Confirmed annotations are the most expensive data in the platform — they are the
only part a human actually typed. When the column beneath one vanishes, deleting
the annotation destroys that work on the strength of a schema read that may
itself be the mistake (a failed migration, a permissions change that hid a
column, a source pointed at the wrong database). Flagging keeps the work and
asks; deleting cannot be undone.
"""
from __future__ import annotations

import hashlib
import json


def fingerprint(columns: list[dict]) -> str:
    """A stable SHA-256 over a source's shape.

    Sorted before hashing because catalog queries do not guarantee ordering, and
    an unsorted hash would report drift every time the source happened to return
    its columns differently — the fastest way to train everyone to ignore drift
    alerts.

    Deliberately covers only (table, column, dtype, nullable). Row counts and
    statistics change constantly and are not schema; including them would make
    every sync look like a schema change.
    """
    rows = sorted(
        (
            str(c.get("table") or ""),
            str(c.get("name") or ""),
            str(c.get("dtype") or ""),
            bool(c.get("nullable", True)),
        )
        for c in columns
    )
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _key(column: dict) -> tuple[str, str]:
    return (str(column.get("table") or ""), str(column.get("name") or ""))


def diff_schemas(previous: list[dict], current: list[dict]) -> dict:
    """What changed between two schema reads.

    Returns added / removed / changed lists. `changed` reports only what
    actually differs on a column, so a review UI can say "dtype: text -> numeric"
    rather than "this column is different".
    """
    prev_by_key = {_key(c): c for c in previous or []}
    curr_by_key = {_key(c): c for c in current or []}

    added = [dict(curr_by_key[k]) for k in curr_by_key.keys() - prev_by_key.keys()]
    removed = [dict(prev_by_key[k]) for k in prev_by_key.keys() - curr_by_key.keys()]

    changed = []
    for key in prev_by_key.keys() & curr_by_key.keys():
        before, after = prev_by_key[key], curr_by_key[key]
        deltas = {}
        for field in ("dtype", "nullable"):
            if before.get(field) != after.get(field):
                deltas[field] = {"from": before.get(field), "to": after.get(field)}
        if deltas:
            changed.append({"table": key[0], "name": key[1], "changes": deltas})

    return {
        "added": sorted(added, key=_key),
        "removed": sorted(removed, key=_key),
        "changed": sorted(changed, key=lambda c: (c["table"], c["name"])),
    }


def find_orphaned_annotations(removed: list[dict], annotations: list[dict]) -> list[dict]:
    """Confirmed human work whose column no longer exists.

    Only CONFIRMED annotations are reported. An inferred description on a
    deleted column is worth nothing — it will simply not be regenerated. A
    confirmed one is a person's decision, and losing it silently is the outcome
    this whole function exists to prevent.
    """
    removed_keys = {_key(c) for c in removed or []}
    orphaned = []
    for annotation in annotations or []:
        if annotation.get("source") != "confirmed":
            continue
        if _key(annotation) in removed_keys:
            orphaned.append({
                "table": annotation.get("table"),
                "name": annotation.get("name"),
                "kind": annotation.get("kind", "column"),
                "detail": annotation.get("detail"),
            })
    return sorted(orphaned, key=lambda a: (a["table"] or "", a["name"] or ""))


def detect(
    previous_fingerprint: str | None,
    previous_columns: list[dict] | None,
    current_columns: list[dict],
    annotations: list[dict] | None = None,
) -> dict | None:
    """Compare a fresh schema read against the last recorded one.

    Returns None when nothing changed — the common case, and the caller writes
    no `schema_versions` row for it. A first-ever sync also returns a result,
    with everything in `added`, so the baseline is recorded explicitly rather
    than inferred from an absence later.
    """
    current_fingerprint = fingerprint(current_columns)
    if previous_fingerprint == current_fingerprint:
        return None

    delta = diff_schemas(previous_columns or [], current_columns)
    orphaned = find_orphaned_annotations(delta["removed"], annotations or [])

    return {
        "fingerprint": current_fingerprint,
        "previous_fingerprint": previous_fingerprint,
        "is_baseline": previous_fingerprint is None,
        "added": delta["added"],
        "removed": delta["removed"],
        "changed": delta["changed"],
        "orphaned_annotations": orphaned,
    }


def summarize(event: dict) -> str:
    """A one-line human summary for the notification body."""
    if event.get("is_baseline"):
        return f"Initial schema recorded: {len(event['added'])} column(s)."

    parts = []
    for label, key in (("added", "added"), ("removed", "removed"), ("changed", "changed")):
        count = len(event.get(key) or [])
        if count:
            parts.append(f"{count} column(s) {label}")

    summary = "Schema changed: " + ", ".join(parts) if parts else "Schema changed."
    orphaned = len(event.get("orphaned_annotations") or [])
    if orphaned:
        # Led with the consequence rather than the cause: the reader needs to
        # know their confirmed work is at risk, not merely that a column went.
        summary += f". {orphaned} confirmed annotation(s) now refer to missing columns."
    return summary
