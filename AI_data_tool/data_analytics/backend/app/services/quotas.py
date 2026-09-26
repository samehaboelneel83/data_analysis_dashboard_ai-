"""Task E2: per-tenant quota enforcement.

Independent limits (models.Quota), all nullable = unlimited:
  * max_queries_per_day     -- counted from query_runs, midnight UTC window
  * max_agent_asks_per_day  -- counted from agent_runs, midnight UTC window
  * max_storage_mb          -- sum of Dataset.file_size for the org's current
                                (non-deleted -- deletes are hard in this
                                schema) datasets
  * max_concurrent_asks     -- an in-process counter, NOT a DB count; gated
                                by `concurrent_ask_slot` below
  * max_ai_tokens_per_day / max_ai_tokens_per_month (E11)
                             -- the model's tokens, summed from ai_usage
                                since midnight UTC / the 1st of the month;
                                metered by `metered` and `run_metered` below

No quota row for an org (the common case) or a null field on an existing row
means unlimited -- exactly today's behavior, unchanged. `get_quota` is the
only DB read that's memoized (a short TTL cache): it runs on every
widget-data/agent-ask/upload request, so a full SELECT per request would be
wasteful. The per-request COUNT/SUM queries below are deliberately NOT
memoized -- a cached count would defeat the whole point of a quota.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import logging

from ..core import telemetry
from ..models.models import AgentRun, AiUsage, Dataset, QueryRun, Quota
from .llm import UsageMeter, release_meter, use_meter

logger = logging.getLogger(__name__)


class QuotaExceeded(Exception):
    """An org hit one of its limits.

    A domain exception, not `HTTPException`: quotas are enforced from the
    schedulers and (potentially) a CLI as well as from routers, and a service
    that raises a web-framework error is unusable anywhere a Request does not
    exist. `main.py` registers a handler that turns this into the right
    response, so the wire behaviour -- status code and `Retry-After` -- is
    unchanged for API callers.

    `status_code` and `headers` live here rather than in the handler because
    the DOMAIN knows which limit was hit and when it resets; the handler only
    knows how to write a response.
    """

    def __init__(self, detail: str, status_code: int = 429,
                 headers: dict[str, str] | None = None, kind: str = "unknown"):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.headers = headers or {}
        self.kind = kind
        # Counted at the raise site rather than in the handler: quotas are
        # enforced from schedulers too, and a rejection there is just as real as
        # one on an HTTP request. `kind` (not the message) is the label, so the
        # metric stays low-cardinality and survives copy edits to the text.
        telemetry.quota_rejections.add(1, {"quota": kind})


_QUOTA_CACHE_TTL_SECONDS = 30.0
# org_id -> (cached Quota row or None, expiry monotonic timestamp)
_quota_cache: dict[int, tuple[Quota | None, float]] = {}

# In-process concurrent-ask counters, keyed by org_id. Single-worker/per-process
# like widget_data.py's own work gate -- no cross-process ceiling, documented
# tradeoff, not a bug (see routers/agent.py concurrent_ask_slot usage).
_concurrent_counts: dict[int, int] = {}


def invalidate_quota_cache(org_id: int | None = None) -> None:
    """Drop one org's cached quota row (or every row, when org_id is None).
    Called by the admin quota-CRUD endpoints after every write, and by tests
    that seed/mutate a Quota row directly through the db session rather than
    through those endpoints."""
    if org_id is None:
        _quota_cache.clear()
    else:
        _quota_cache.pop(org_id, None)


def reset_concurrent_counts() -> None:
    """Test hook: clear all in-process concurrent-ask counters between tests."""
    _concurrent_counts.clear()


async def get_quota(db: AsyncSession, org_id: int) -> Quota | None:
    now = time.monotonic()
    cached = _quota_cache.get(org_id)
    if cached is not None and cached[1] > now:
        return cached[0]
    row = (await db.execute(
        select(Quota).where(Quota.org_id == org_id)
    )).scalar_one_or_none()
    _quota_cache[org_id] = (row, now + _QUOTA_CACHE_TTL_SECONDS)
    return row


def _midnight_utc() -> datetime:
    return datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)


def _seconds_until_next_midnight_utc() -> int:
    tomorrow_midnight = _midnight_utc() + timedelta(days=1)
    return max(1, int((tomorrow_midnight - datetime.utcnow()).total_seconds()))


async def enforce_query_quota(db: AsyncSession, org_id: int) -> None:
    """429 + Retry-After once today's query_runs count for this org has
    reached its daily cap. Boundary is value-pinned: the (n-1)th query in a
    day still passes (count < max at check time), the nth is blocked
    (count == max)."""
    quota = await get_quota(db, org_id)
    if quota is None or quota.max_queries_per_day is None:
        return
    count = (await db.execute(
        select(func.count()).select_from(QueryRun)
        .where(QueryRun.org_id == org_id, QueryRun.created_at >= _midnight_utc())
    )).scalar_one()
    if count >= quota.max_queries_per_day:
        raise QuotaExceeded("Daily query quota exceeded for this organization",
                            headers={"Retry-After": str(_seconds_until_next_midnight_utc())},
                            kind="queries_per_day")


async def enforce_agent_quota(db: AsyncSession, org_id: int) -> None:
    """Same contract as enforce_query_quota, counted from agent_runs."""
    quota = await get_quota(db, org_id)
    if quota is None or quota.max_agent_asks_per_day is None:
        return
    count = (await db.execute(
        select(func.count()).select_from(AgentRun)
        .where(AgentRun.org_id == org_id, AgentRun.created_at >= _midnight_utc())
    )).scalar_one()
    if count >= quota.max_agent_asks_per_day:
        raise QuotaExceeded("Daily agent-ask quota exceeded for this organization",
                            headers={"Retry-After": str(_seconds_until_next_midnight_utc())},
                            kind="agent_asks_per_day")


async def enforce_storage_quota(db: AsyncSession, org_id: int, incoming_bytes: int) -> None:
    """413 when adding `incoming_bytes` would push the org's total dataset
    storage past its cap. Sums Dataset.file_size across every dataset row
    the org currently has -- deletes in this schema are hard deletes, so a
    plain SUM over live rows already excludes anything removed."""
    quota = await get_quota(db, org_id)
    if quota is None or quota.max_storage_mb is None:
        return
    used = (await db.execute(
        select(func.coalesce(func.sum(Dataset.file_size), 0))
        .where(Dataset.org_id == org_id)
    )).scalar_one()
    limit_bytes = quota.max_storage_mb * 1024 * 1024
    if used + incoming_bytes > limit_bytes:
        raise QuotaExceeded(f"Storage quota exceeded ({quota.max_storage_mb} MB limit for this organization)", status_code=413, kind="storage_mb")


@asynccontextmanager
async def concurrent_ask_slot(db: AsyncSession, org_id: int):
    """Gate live concurrent agent asks for one org. Acquire happens before
    `yield`, raising 429 without ever incrementing the counter when the org
    is already at its cap -- so a rejected request never needs (or gets) a
    release. Once acquired, the release always runs in `finally`, so an
    agent run that raises mid-flight still frees its slot; null quota (no
    row, or a null max_concurrent_asks) skips the counter entirely."""
    quota = await get_quota(db, org_id)
    limit = quota.max_concurrent_asks if quota is not None else None
    if limit is not None:
        current = _concurrent_counts.get(org_id, 0)
        if current >= limit:
            raise QuotaExceeded("Too many concurrent agent asks for this organization",
                                kind="concurrent_asks")
        _concurrent_counts[org_id] = current + 1
    try:
        yield
    finally:
        if limit is not None:
            _concurrent_counts[org_id] = max(0, _concurrent_counts.get(org_id, 0) - 1)


# ---------------------------------------------------------------------------
# E11: AI budgets
# ---------------------------------------------------------------------------

def _month_start_utc() -> datetime:
    return _midnight_utc().replace(day=1)


def _seconds_until_next_month_utc() -> int:
    start = _month_start_utc()
    nxt = start.replace(year=start.year + 1, month=1) if start.month == 12 \
        else start.replace(month=start.month + 1)
    return max(1, int((nxt - datetime.utcnow()).total_seconds()))


async def ai_tokens_used(db: AsyncSession, org_id: int, since: datetime) -> int:
    return int((await db.execute(
        select(func.coalesce(func.sum(AiUsage.tokens_in + AiUsage.tokens_out), 0))
        .where(AiUsage.org_id == org_id, AiUsage.created_at >= since)
    )).scalar_one())


async def ai_budget(db: AsyncSession, org_id: int) -> tuple[int | None, str | None, int]:
    """(tokens remaining, the limit that binds, seconds until it resets).

    The tighter of the day and month limits; (None, None, 0) when the org has
    neither, which costs one cached quota lookup and no count."""
    quota = await get_quota(db, org_id)
    if quota is None or (quota.max_ai_tokens_per_day is None
                         and quota.max_ai_tokens_per_month is None):
        return None, None, 0
    best: tuple[int | None, str | None, int] = (None, None, 0)
    if quota.max_ai_tokens_per_day is not None:
        left = quota.max_ai_tokens_per_day - await ai_tokens_used(db, org_id, _midnight_utc())
        best = (left, "ai_tokens_per_day", _seconds_until_next_midnight_utc())
    if quota.max_ai_tokens_per_month is not None:
        left = quota.max_ai_tokens_per_month - await ai_tokens_used(db, org_id, _month_start_utc())
        if best[0] is None or left < best[0]:
            best = (left, "ai_tokens_per_month", _seconds_until_next_month_utc())
    return best


async def open_ai_meter(db: AsyncSession, org_id: int, user_id: int | None,
                        feature: str) -> UsageMeter:
    remaining, kind, resets_in = await ai_budget(db, org_id)
    return UsageMeter(org_id=org_id, user_id=user_id, feature=feature,
                      remaining=remaining, limit_kind=kind, resets_in=resets_in)


def enforce_ai_budget(meter: UsageMeter) -> None:
    """429 + Retry-After before a model-first request (a question, the
    copilot) when the org's budget is already spent. Features where the model
    is an embellishment are not refused: their calls return None and they
    fall back, as they do when the model is down."""
    if not meter.spent:
        return
    kind = meter.limit_kind or "ai_tokens"
    period = "this month" if kind == "ai_tokens_per_month" else "today"
    raise QuotaExceeded(f"This organization's AI budget for {period} is used up",
                        headers={"Retry-After": str(meter.resets_in or 60)},
                        kind=kind)


async def record_ai_usage(db: AsyncSession, meter: UsageMeter, *, commit: bool = True) -> None:
    """One ai_usage row, when the meter saw a call or a refusal. Never raises:
    the answer has been produced, and losing a usage row must not turn it
    into an error. `commit=False` leaves the row to the caller's transaction
    (a step that commits its own work)."""
    if not (meter.calls or meter.refused):
        return
    try:
        db.add(AiUsage(org_id=meter.org_id, user_id=meter.user_id, feature=meter.feature,
                       calls=meter.calls, refused=meter.refused,
                       tokens_in=meter.tokens_in, tokens_out=meter.tokens_out))
        if commit:
            await db.commit()
    except Exception:                                         # noqa: BLE001
        logger.exception("could not record AI usage for org %s (%s)", meter.org_id, meter.feature)
        try:
            await db.rollback()
        except Exception:                                     # noqa: BLE001
            pass


@asynccontextmanager
async def metered(db: AsyncSession, org_id: int, user_id: int | None, feature: str,
                  *, commit: bool = True):
    """Meter the model calls made inside the block, on the caller's session."""
    meter = await open_ai_meter(db, org_id, user_id, feature)
    token = use_meter(meter)
    try:
        yield meter
    finally:
        release_meter(token)
        await record_ai_usage(db, meter, commit=commit)


async def run_metered(session_factory, meter: UsageMeter, coro):
    """Await `coro` (a detached background run) under `meter`.

    The meter is opened by the request that starts the run (`open_ai_meter`
    on its session), so the run starts at once; owned by no request, the run
    records its usage on a session of its own when it ends."""
    token = use_meter(meter)
    try:
        return await coro
    finally:
        release_meter(token)
        async with session_factory() as db:
            await record_ai_usage(db, meter)
