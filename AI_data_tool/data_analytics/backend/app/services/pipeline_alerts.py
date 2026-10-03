"""Tell someone when a pipeline breaks, recovers, or goes stale (pipeline plan, phase 2).

Phase 1 made every refresh leave a `RefreshRun`. This turns state CHANGES in
those runs into messages:

* the first failure of a streak -> one "failed" notice;
* the first success after a failure (or after a stale notice) -> one
  "working again" notice;
* a dataset older than its freshness target -> one "stale" notice, until the
  next successful refresh.

Never one message per retry: `PipelineWatch.state` remembers what was last
said. Alert fatigue is how alerts stop being read.

The OWNER is the item's creator; with none (or one who has left) it is the
org's admins, so a failure is never addressed to nobody. The owner always gets
an in-app notice; `PipelineWatch.recipients` adds emails and https webhooks.

Like everything the scheduler calls, nothing here may raise into the refresh
it reports on.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

log = logging.getLogger(__name__)

#: Choices offered for a freshness target, in hours.
FRESHNESS_CHOICES = (2, 6, 26, 72, 192)


def _naive(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo is None else dt.astimezone(timezone.utc).replace(tzinfo=None)


async def get_watch(session, kind: str, item_id: int, *, create: bool = False,
                    org_id: int | None = None):
    from ..models.models import PipelineWatch
    row = (await session.execute(select(PipelineWatch).where(
        PipelineWatch.kind == kind, PipelineWatch.item_id == item_id))).scalars().first()
    if row is None and create:
        row = PipelineWatch(kind=kind, item_id=item_id, org_id=org_id, state="ok",
                            recipients=[])
        session.add(row)
        await session.flush()
    return row


async def _item(session, kind: str, item_id: int):
    """(org_id, name, in-app link, creator id) for a dataset or dataflow, or None."""
    from ..models.models import Dataflow, Dataset
    if kind == "dataset":
        ds = await session.get(Dataset, item_id)
        if ds is None:
            return None
        return ds.org_id, ds.name, f"/datasets/{ds.id}", ds.created_by
    flow = await session.get(Dataflow, item_id)
    if flow is None:
        return None
    return flow.org_id, flow.name, f"/dataflows?flow={flow.id}", flow.created_by


async def owner_ids(session, org_id: int | None, creator_id: int | None) -> list[int]:
    """The creator if still an active member of the org, else every org admin."""
    from ..models.models import Role, User
    if creator_id is not None:
        u = await session.get(User, creator_id)
        if u is not None and u.is_active and u.org_id == org_id:
            return [u.id]
    if org_id is None:
        return []
    rows = (await session.execute(
        select(User.id).join(Role, Role.id == User.role_id)
        .where(User.org_id == org_id, User.is_active.is_(True), Role.is_org_admin.is_(True))
    )).all()
    return [r for (r,) in rows]


async def _announce(session, kind: str, item_id: int, watch, subject: str, text: str) -> None:
    from .delivery import send_email, split_recipients, valid_recipients
    from .alerts import post_webhook
    from .notifications import notify
    item = await _item(session, kind, item_id)
    if item is None:
        return
    org_id, _name, link, creator = item
    for uid in await owner_ids(session, org_id, creator):
        await notify(session, org_id, uid, "refresh", text, link)
    await session.commit()
    emails, hooks = split_recipients(valid_recipients((watch.recipients if watch else None) or []))
    if emails:
        err = await asyncio.to_thread(send_email, emails, subject, text)
        if err:
            log.warning("Pipeline alert email for %s %s not sent: %s", kind, item_id, err)
    for url in hooks:
        err = await asyncio.to_thread(post_webhook, url, text)
        if err:
            log.warning("Pipeline alert webhook for %s %s: %s", kind, item_id, err)


def _short(error: str | None) -> str:
    """The first line of an error, without SQLAlchemy's background-link tail."""
    first = (error or "unknown error").strip().splitlines()[0]
    # The run's error already says what failed ("Refresh failed: ..."); the
    # notice says it too, so the prefix would read twice.
    import re as _re
    first = _re.sub(r"^((Refresh|Rebuild|Dataflow) failed|Not published):\s*", "", first) or first
    return first[:300]


async def on_run_finished(session, kind: str, item_id: int, status: str,
                          error: str | None = None) -> None:
    """Called once a RefreshRun closes. Announces state changes only."""
    if kind == "dataset":
        forget_brief(item_id)
    try:
        item = await _item(session, kind, item_id)
        if item is None:
            return
        org_id, name, _link, _creator = item
        noun = "Dataflow" if kind == "dataflow" else "Refresh of"
        if status in ("failed", "blocked"):
            watch = await get_watch(session, kind, item_id, create=True, org_id=org_id)
            if watch.state == "failing":
                await session.commit()
                return
            watch.state, watch.state_since = "failing", datetime.utcnow()
            await session.commit()
            if status == "blocked":
                # Phase 3: the refresh ran, but a blocking check refused the
                # new data. Nothing in the pipeline is broken -- the DATA needs
                # a look, or an editor's "publish anyway".
                await _announce(
                    session, kind, item_id, watch, f"Refresh blocked by a check: {name}",
                    f"New data for “{name}” was not published. {_short(error)}. "
                    f"Dashboards keep showing the previous data; open the dataset to "
                    f"review its checks or publish anyway.")
            else:
                await _announce(
                    session, kind, item_id, watch, f"Refresh failed: {name}",
                    f"{noun} “{name}” failed: {_short(error)}. Dashboards built on "
                    f"it keep showing the last good data until it works again.")
        elif status == "ok":
            watch = await get_watch(session, kind, item_id)
            if watch is None or (watch.state != "failing" and watch.stale_alerted_at is None):
                return
            was_failing = watch.state == "failing"
            watch.state, watch.state_since, watch.stale_alerted_at = "ok", datetime.utcnow(), None
            await session.commit()
            await _announce(
                session, kind, item_id, watch, f"Working again: {name}",
                f"“{name}” refreshed successfully again"
                + (" after failing." if was_failing else ", and its data is up to date."))
    except Exception as e:  # noqa: BLE001 -- an alert must never break a refresh
        log.warning("Pipeline alert for %s %s failed: %s", kind, item_id, e)
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass


def is_stale(last_refreshed_at, freshness_hours: int | None, now: datetime) -> bool:
    if not freshness_hours:
        return False
    last = _naive(last_refreshed_at)
    return last is None or _naive(now) - last > timedelta(hours=freshness_hours)


async def check_freshness(session, now: datetime | None = None) -> int:
    """Announce each dataset that has just gone past its freshness target.
    Returns how many were announced. Called once per scheduler tick."""
    from ..models.models import Dataset, PipelineWatch
    now = now or datetime.utcnow()
    said = 0
    try:
        watches = (await session.execute(select(PipelineWatch).where(
            PipelineWatch.kind == "dataset", PipelineWatch.freshness_hours.isnot(None),
            PipelineWatch.stale_alerted_at.is_(None)))).scalars().all()
        for w in watches:
            ds = await session.get(Dataset, w.item_id)
            if ds is None or ds.mode == "directquery":
                continue
            last = ds.last_refreshed_at or ds.created_at
            if not is_stale(last, w.freshness_hours, now):
                continue
            w.stale_alerted_at = now
            await session.commit()
            age = int((_naive(now) - _naive(last)).total_seconds() // 3600) if last else None
            await _announce(
                session, "dataset", ds.id, w, f"Data is stale: {ds.name}",
                f"“{ds.name}” has not refreshed for "
                f"{age if age is not None else 'over'} hours; its target is "
                f"{w.freshness_hours} hours. Dashboards on it are showing old data.")
            said += 1
    except Exception as e:  # noqa: BLE001 -- never break the tick
        log.warning("Freshness check failed: %s", e)
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass
    return said


async def owner_emails(session, kind: str, item_id: int) -> list[str]:
    """Who the in-app notices go to, by email: shown to editors so "the owner
    is told" names someone."""
    from ..models.models import User
    item = await _item(session, kind, item_id)
    if item is None:
        return []
    org_id, _n, _l, creator = item
    ids = await owner_ids(session, org_id, creator)
    if not ids:
        return []
    return [e for (e,) in (await session.execute(select(User.email).where(User.id.in_(ids)))).all()]


async def health(session, ds) -> dict:
    """One dataset's pipeline health, for its page, its widgets and lineage.

    `state`: ok | failing | stale | unknown. Failing wins over stale: a broken
    refresh is the cause, staleness the symptom."""
    from ..models.models import RefreshRun, ScheduleFailure
    watch = await get_watch(session, "dataset", ds.id)
    last_run = (await session.execute(select(RefreshRun).where(
        RefreshRun.kind == "dataset", RefreshRun.item_id == ds.id
    ).order_by(RefreshRun.id.desc()).limit(1))).scalars().first()
    failure = (await session.execute(select(ScheduleFailure).where(
        ScheduleFailure.kind == "dataset", ScheduleFailure.item_id == ds.id))).scalars().first()
    target = watch.freshness_hours if watch else None
    if last_run is not None and last_run.status in ("failed", "blocked"):
        state = "failing"
    elif is_stale(ds.last_refreshed_at or ds.created_at, target, datetime.utcnow()):
        state = "stale"
    elif last_run is None and not target:
        state = "unknown"
    else:
        state = "ok"
    return {
        "state": state,
        "last_refreshed_at": ds.last_refreshed_at,
        "freshness_hours": target,
        "recipients": list((watch.recipients if watch else None) or []),
        "last_run": None if last_run is None else {
            "status": last_run.status, "trigger": last_run.trigger,
            "started_at": last_run.started_at, "rows": last_run.rows,
            "duration_ms": last_run.duration_ms, "error": last_run.error},
        "next_retry_at": failure.next_attempt_at if failure else None,
    }


#: dataset id -> (expires monotonic, brief). Widgets ask on every render; the
#: answer changes at most once per refresh, so 30 s of staleness is harmless.
_BRIEF_CACHE: dict[int, tuple[float, dict | None]] = {}
_BRIEF_TTL_S = 30.0


async def health_brief(session, dataset_id: int) -> dict | None:
    """What a widget on this dataset should say about its data: None when the
    data is healthy (or nothing is known), else {state, last_refreshed_at,
    freshness_hours}. Cached briefly; never raises."""
    import time
    from ..models.models import Dataset
    hit = _BRIEF_CACHE.get(dataset_id)
    now_m = time.monotonic()
    if hit and hit[0] > now_m:
        return hit[1]
    brief = None
    try:
        ds = await session.get(Dataset, dataset_id)
        if ds is not None and ds.mode != "directquery":
            h = await health(session, ds)
            if h["state"] in ("failing", "stale"):
                # No error text: a dashboard reader may not be someone who
                # should see a connection's host or file path. The dataset's
                # owner gets the error in the notice and on the dataset page.
                brief = {"state": h["state"], "last_refreshed_at": h["last_refreshed_at"],
                         "freshness_hours": h["freshness_hours"]}
    except Exception as e:  # noqa: BLE001 -- a badge must never break a chart
        log.debug("health brief for dataset %s failed: %s", dataset_id, e)
    if len(_BRIEF_CACHE) > 5000:
        _BRIEF_CACHE.clear()
    _BRIEF_CACHE[dataset_id] = (now_m + _BRIEF_TTL_S, brief)
    return brief


def forget_brief(dataset_id: int) -> None:
    """Drop a cached brief: called when a run finishes or settings change."""
    _BRIEF_CACHE.pop(dataset_id, None)
