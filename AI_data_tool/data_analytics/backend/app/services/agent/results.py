"""Result snapshots: the rows a sink step returned, made small and JSON-safe.

Until this existed only a row COUNT survived a run (`AgentStep.rows_returned`),
so the chat could describe a result in prose but never show it, and "present
that as a table" had nothing to present. A snapshot rides on the sink step's
row, comes back with the answer, and is redrawn when a conversation is
reopened.

Capped, not complete: the chat draws a grid, not a data export. The TRUE
count is kept beside the sample (`total`, `truncated`) so nothing downstream
mistakes the sample for the whole -- the same lesson explain.py's `_facts`
learned when prose contradicted its own figures.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime, time
from decimal import Decimal

#: Rows kept per sink step. Enough for a grid to scroll through; small enough
#: that a conversation's worth of snapshots stays a few kilobytes each.
RESULT_ROW_CAP = 200

#: Column names whose VALUES are secrets, not data. Found live: "give my
#: sample" over a source pointing at an application database selected
#: users.password_hash, and the hashes flowed into the answer, the prompt
#: explain() builds, and the stored snapshot. Deliberately narrow -- bare
#: "hash" or "key" would mask legitimate analytics columns.
CREDENTIAL_RE = re.compile(
    r"password|passwd|secret|credential|api_key|apikey|private_key|access_token",
    re.IGNORECASE)

REDACTED = "•••"


def redact_credentials(rows: list[dict] | None) -> list[dict] | None:
    """Rows with credential-named columns masked, others untouched.

    Applied once, right after execution (graph.py), so EVERYTHING downstream
    -- parent facts, explain's prompt, the memory examples, the snapshot the
    chat draws -- sees the mask, not the secret. The column still appears,
    honestly named, so the reader knows it exists and was withheld."""
    if not rows:
        return rows
    hot = {k for r in rows[:20] for k in r.keys() if CREDENTIAL_RE.search(str(k))}
    if not hot:
        return rows
    return [{k: (REDACTED if k in hot and r.get(k) is not None else r.get(k))
             for k in r.keys()} for r in rows]


def coerce_scalar(v):
    """One cell, as something `json.dumps` accepts and a chart can plot.

    Numbers stay numbers (Decimal and numpy scalars included -- a bar chart
    over the snapshot needs floats, not strings), dates become ISO strings,
    NaN/inf become null, and anything else falls back to `str`."""
    if v is None or isinstance(v, bool):
        return v
    if isinstance(v, (int, str)):
        return v
    if isinstance(v, float):
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(v, Decimal):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return v.hex()
    if hasattr(v, "item"):  # numpy scalars
        try:
            return coerce_scalar(v.item())
        except Exception:
            return str(v)
    return str(v)


def snapshot_rows(rows: list[dict] | None, cap: int | None = None) -> dict | None:
    """`{columns, rows, total, truncated}` for a step's rows, or None when the
    step produced none (failed, or never ran).

    Columns are taken in first-appearance order across the kept rows, so a
    ragged result (a key missing from some rows) still yields one consistent
    header. An empty result has no rows to read a header from and comes back
    with `columns: []` -- honest, and the chat renders it as "no rows"."""
    if rows is None:
        return None
    cap = RESULT_ROW_CAP if cap is None else cap
    kept = rows[:cap]
    columns: list[str] = []
    seen: set[str] = set()
    for r in kept:
        for k in r.keys():
            name = str(k)
            if name not in seen:
                seen.add(name)
                columns.append(name)
    body = [[coerce_scalar(r.get(c)) for c in columns] for r in kept]
    return {"columns": columns, "rows": body, "total": len(rows),
            "truncated": len(rows) > cap}
