"""Sensitivity labels that propagate and ENFORCE (Phase 7.3).

SAS shows a classification badge and does nothing with it. Here a label is a
rule the product keeps:

  * **It propagates.** A dataset's EFFECTIVE label is the highest of its own
    and every dataset it was built from (a materialized pipeline's recipe) or
    joins in (a prep join step brings the other dataset's rows along). A
    report's effective label is the highest of its own and every dataset its
    widgets draw on. The badge therefore cannot claim "Internal" over rows that
    came from a "Restricted" source.
  * **It cannot be set lower than its data.** Classifying a report below its
    datasets' floor is refused with the dataset named.
  * **It changes what leaves the building.**
      Confidential -> no ANONYMOUS share-link access (a signed-in member of
                      the org still opens the link as themselves), and
                      personal-data columns (email, phone, national id, IBAN...)
                      are redacted from shared links, embeds and exported files.
      Restricted   -> additionally no share links or embeds at all, and no
                      downloads (CSV, PDF, offline package) for anyone below
                      data-level access.

Labels live in `column_meta["__sensitivity__"]` on a dataset (no schema change)
and in `report_classifications` for a report.
"""
from __future__ import annotations

from ..services.pii import is_pii

LEVELS = ["Public", "Internal", "Confidential", "Restricted"]
META_KEY = "__sensitivity__"


def rank(label: str | None) -> int:
    return LEVELS.index(label) if label in LEVELS else -1


def higher(a: str | None, b: str | None) -> str | None:
    return a if rank(a) >= rank(b) else b


def own_label(dataset) -> str | None:
    meta = getattr(dataset, "column_meta", None) or {}
    v = meta.get(META_KEY)
    return v if v in LEVELS else None


async def dataset_effective(db, dataset_id: int, _seen: set[int] | None = None) -> tuple[str | None, list[str]]:
    """(label, reasons) -- the highest label over this dataset and its lineage."""
    from ..models.models import Dataset
    from .prep import collect_join_dataset_ids, derived_from_of, derived_source_ids, prep_steps_of

    seen = _seen if _seen is not None else set()
    if dataset_id in seen:
        return None, []
    seen.add(dataset_id)
    ds = await db.get(Dataset, dataset_id)
    if ds is None:
        return None, []
    label = own_label(ds)
    reasons = [f"{ds.name} is labelled {label}"] if label else []
    upstream = set(derived_source_ids(derived_from_of(ds))) | set(collect_join_dataset_ids(prep_steps_of(ds)))
    for sid in sorted(upstream):
        up, up_reasons = await dataset_effective(db, sid, seen)
        if up and rank(up) > rank(label):
            label = up
            reasons = [f"{ds.name} is built from or joins data labelled {up}"] + up_reasons
    return label, reasons


async def report_dataset_ids(db, report) -> set[int]:
    from sqlalchemy import select

    from ..models.models import ReportPage, ReportWidget
    ids: set[int] = set()
    if report.dataset_id:
        ids.add(int(report.dataset_id))
    for extra in (report.additional_dataset_ids or []):
        if isinstance(extra, int):
            ids.add(extra)
    rows = (await db.execute(select(ReportWidget.config).join(ReportPage, ReportWidget.page_id == ReportPage.id)
                             .where(ReportPage.report_id == report.id))).scalars().all()
    for cfg in rows:
        did = (cfg or {}).get("dataset_id") if isinstance(cfg, dict) else None
        if isinstance(did, int):
            ids.add(did)
    return ids


async def report_floor(db, report) -> tuple[str | None, list[str]]:
    """The lowest label this report may carry: the highest of its datasets'."""
    floor, reasons = None, []
    for did in sorted(await report_dataset_ids(db, report)):
        lab, why = await dataset_effective(db, did)
        if lab and rank(lab) > rank(floor):
            floor, reasons = lab, why
    return floor, reasons


async def report_effective(db, report) -> tuple[str | None, list[str]]:
    from sqlalchemy import select

    from ..models.models import ReportClassification
    own = (await db.execute(select(ReportClassification.label)
                            .where(ReportClassification.report_id == report.id))).scalar_one_or_none()
    floor, reasons = await report_floor(db, report)
    if rank(floor) > rank(own):
        return floor, reasons
    return own, ([f"the report is labelled {own}"] if own else [])


async def redacted_columns(db, dataset_id: int, context_label: str | None = None) -> list[str]:
    """Personal-data columns to drop when this dataset's rows leave the org
    (share links, embeds, exports) -- empty below Confidential. The label that
    counts is the higher of the dataset's own effective label and the context
    (the report being shared), so a Confidential report redacts even over an
    unlabelled dataset."""
    from sqlalchemy import select

    from ..models.models import DatasetColumn
    label, _ = await dataset_effective(db, dataset_id)
    if rank(higher(label, context_label)) < rank("Confidential"):
        return []
    rows = (await db.execute(select(DatasetColumn.name, DatasetColumn.semantic_type)
                             .where(DatasetColumn.dataset_id == dataset_id))).all()
    return sorted(name for name, sem in rows if is_pii(sem))

