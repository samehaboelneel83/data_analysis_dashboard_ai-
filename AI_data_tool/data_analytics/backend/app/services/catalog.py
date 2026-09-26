"""What a dataset is and how current it is, for the catalog (E06).

The Datasets list showed a name, sizes and a date; only a live connection
carried a chip. Whether the rows were uploaded once, copied from a database
on a schedule (and whether that schedule is keeping up), built from other
datasets, or pre-aggregated, was on each dataset's own page or nowhere. This
says it once, for every row of the list:

- ``kind``: ``upload`` (a file someone uploaded), ``connection`` (rows copied
  from a connected database), ``live`` (queried from the database on every
  read; nothing stored), ``derived`` (built from other datasets by a pipeline
  or a dataflow, or scored by a saved model) or ``aggregate`` (a summary of
  another dataset kept for speed).
- ``freshness``: ``live`` (always current), ``on_schedule`` (refreshed on a
  schedule and within it), ``due`` (its refresh time has passed; the
  scheduler picks it up on its next tick), ``overdue`` (a whole interval
  late: refreshes are failing or not running), ``manual`` (copied, refreshed
  only when someone asks) or ``fixed`` (an upload: it changes when someone
  uploads again). ``as_of`` is when its rows were last taken; ``next_due``
  when the next refresh is expected.

Pure: the caller resolves the names the reader may see (a connection behind
a dataset they can read; a source dataset only if they can read it).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .prep import DERIVED_FROM_KEY

#: A dataset of predictions made by a saved model (services/model_scoring.py).
SCORED_BY_KEY = "__scored_by__"


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat().replace("+00:00", "Z") if dt else None


def kind_of(ds) -> str:
    meta = ds.column_meta if isinstance(getattr(ds, "column_meta", None), dict) else {}
    if getattr(ds, "mode", None) == "directquery":
        return "live"
    if getattr(ds, "aggregate_of_dataset_id", None):
        return "aggregate"
    if isinstance(meta.get(DERIVED_FROM_KEY), dict) or isinstance(meta.get(SCORED_BY_KEY), dict):
        return "derived"
    if getattr(ds, "data_source_id", None) and (ds.source_table or ds.source_query or ds.query_model):
        return "connection"
    return "upload"


def origin_ids(ds) -> list[int]:
    """The datasets a derived or aggregate dataset was built from."""
    if getattr(ds, "aggregate_of_dataset_id", None):
        return [int(ds.aggregate_of_dataset_id)]
    meta = ds.column_meta if isinstance(getattr(ds, "column_meta", None), dict) else {}
    prov = meta.get(DERIVED_FROM_KEY)
    if not isinstance(prov, dict):
        prov = meta.get(SCORED_BY_KEY)
    if not isinstance(prov, dict):
        return []
    ids = [prov.get("source_dataset_id"), *(prov.get("join_dataset_ids") or [])]
    return [int(i) for i in ids if isinstance(i, int) or (isinstance(i, str) and i.isdigit())]


def catalog_entry(ds, *, now: datetime, source_name: str | None = None,
                  origin_names: list[str] | None = None) -> dict:
    kind = kind_of(ds)
    now = _utc(now)
    last = _utc(getattr(ds, "last_refreshed_at", None))
    interval = getattr(ds, "refresh_interval_minutes", None) or 0
    taken = last or _utc(getattr(ds, "created_at", None))
    next_due = None
    if kind == "live":
        status, taken = "live", None
    elif interval > 0 and kind in ("connection", "derived", "aggregate"):
        if last is None:
            status = "due"
        else:
            next_due = last + timedelta(minutes=interval)
            if now < next_due:
                status = "on_schedule"
            elif now < next_due + timedelta(minutes=interval):
                status = "due"
            else:
                status = "overdue"
    elif kind == "upload":
        status = "fixed"
    else:
        status = "manual"
    out = {"kind": kind, "freshness": status, "as_of": _iso(taken), "next_due": _iso(next_due),
           "refresh_every_minutes": interval or None}
    if source_name:
        out["source"] = source_name
    if origin_names is not None:
        out["built_from"] = origin_names
    return out
