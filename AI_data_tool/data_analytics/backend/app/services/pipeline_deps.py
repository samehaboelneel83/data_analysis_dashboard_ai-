"""Run a dataflow, or a dataset rebuilt from another, when its source refreshes (pipeline plan, phase 4).

Before this each dataflow and each rebuilt dataset ran on its own timer. An
hourly rollup over a dataset refreshed at 06:00 read stale input until 07:00,
or ran twice on the same input. With `run_after_source`, a successful refresh
of the source marks the item pending, and the scheduler runs it on its next
tick (within a minute). The item's outputs are datasets too, so their own
dependents follow: a chain runs in order, one link per tick.

The dependency graph has two kinds of edge:

* a dataflow F reads its source dataset S and writes its outputs (the
  datasets whose `__derived_from__.dataflow_id` is F): S -> F -> outputs;
* a rebuilt dataset D (materialized from S, not by a dataflow): S -> D.

A loop (an item whose outputs lead back to its own source) would run forever,
so turning run-after-source on for one is refused, not detected at run time.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

log = logging.getLogger(__name__)


def _source_of(meta: dict | None) -> int | None:
    v = (meta or {}).get("source_dataset_id")
    return v if isinstance(v, int) else None


async def _graph(session, org_id: int | None):
    """(dataflows, rebuilt datasets, outputs by flow id) for one org."""
    from ..models.models import Dataflow, Dataset
    from .prep import derived_from_of
    flows = (await session.execute(select(Dataflow).where(Dataflow.org_id == org_id))).scalars().all()
    datasets = (await session.execute(select(Dataset).where(Dataset.org_id == org_id))).scalars().all()
    outputs: dict[int, list[int]] = {}
    rebuilt: dict[int, int] = {}          # rebuilt dataset id -> its source id
    for d in datasets:
        prov = derived_from_of(d)
        if not prov:
            continue
        if isinstance(prov.get("dataflow_id"), int):
            outputs.setdefault(prov["dataflow_id"], []).append(d.id)
        elif _source_of(prov) is not None:
            rebuilt[d.id] = _source_of(prov)
    return flows, rebuilt, outputs


def _downstream(start: set[int], flows, rebuilt: dict[int, int], outputs: dict[int, list[int]]) -> set[int]:
    """Every dataset a change to `start` can reach."""
    seen, frontier = set(start), list(start)
    while frontier:
        ds = frontier.pop()
        nxt = [o for f in flows if f.source_dataset_id == ds for o in outputs.get(f.id, [])]
        nxt += [d for d, src in rebuilt.items() if src == ds]
        for n in nxt:
            if n not in seen:
                seen.add(n)
                frontier.append(n)
    return seen


async def would_loop(session, kind: str, item_id: int, org_id: int | None) -> bool:
    """True when running this item after its source would feed back into
    that source -- a cycle that would refresh forever."""
    flows, rebuilt, outputs = await _graph(session, org_id)
    if kind == "dataflow":
        flow = next((f for f in flows if f.id == item_id), None)
        if flow is None or flow.source_dataset_id is None:
            return False
        source, outs = flow.source_dataset_id, set(outputs.get(item_id, []))
    else:
        source, outs = rebuilt.get(item_id), {item_id}
        if source is None:
            return False
    return source in outs or source in _downstream(outs, flows, rebuilt, outputs)


async def mark_dependents(session, dataset_id: int) -> int:
    """A dataset just refreshed successfully: mark every item set to run
    after it as pending. Returns how many. Never raises."""
    from ..models.models import Dataset, PipelineWatch
    try:
        ds = await session.get(Dataset, dataset_id)
        if ds is None:
            return 0
        flows, rebuilt, _outputs = await _graph(session, ds.org_id)
        targets = [("dataflow", f.id) for f in flows if f.source_dataset_id == dataset_id]
        targets += [("dataset", d) for d, src in rebuilt.items() if src == dataset_id]
        n = 0
        for kind, item in targets:
            w = (await session.execute(select(PipelineWatch).where(
                PipelineWatch.kind == kind, PipelineWatch.item_id == item))).scalars().first()
            if w is not None and w.run_after_source and not w.trigger_pending:
                w.trigger_pending = True
                n += 1
        if n:
            await session.commit()
        return n
    except Exception as e:  # noqa: BLE001 -- a follow-on must never break the refresh
        log.warning("Could not mark the dependents of dataset %s: %s", dataset_id, e)
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return 0


async def flow_outputs(session, flow_id: int, org_id: int | None) -> list[int]:
    _flows, _rebuilt, outputs = await _graph(session, org_id)
    return outputs.get(flow_id, [])


async def pending_items(session) -> list[tuple[str, int]]:
    """Items whose source has refreshed since they last ran."""
    from ..models.models import PipelineWatch
    rows = (await session.execute(select(PipelineWatch).where(
        PipelineWatch.run_after_source.is_(True), PipelineWatch.trigger_pending.is_(True)
    ).order_by(PipelineWatch.id))).scalars().all()
    return [(w.kind, w.item_id) for w in rows]


async def clear_pending(session, kind: str, item_id: int) -> None:
    from ..models.models import PipelineWatch
    w = (await session.execute(select(PipelineWatch).where(
        PipelineWatch.kind == kind, PipelineWatch.item_id == item_id))).scalars().first()
    if w is not None and w.trigger_pending:
        w.trigger_pending = False
        await session.commit()
