"""Evaluating data alerts on their schedule.

An alert's condition is an aggregate expression over its dataset ("SUM(revenue) <
100000"), evaluated by the same sandbox the widgets use -- with row-level security
resolved as the alert's creator, for the same reason schedules do: no viewer must
never mean no RLS.

Rising-edge firing: an email goes out when the condition BECOMES true, and the state
arms again only after a clear evaluation. An alert emailing every tick while true
trains its recipients to delete it, which is worse than no alert.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from ..core.config import settings
from ..core.rls import resolve_denied_columns, resolve_rls_expr
from ..models.models import Dataset, User
from .analytics import load_file
from .query_log import log_delivery_sync
from .widget_data import _eval_expr, _validate_expr_safety, apply_rls_filter
from .delivery import send_email, valid_recipients

log = logging.getLogger(__name__)


def condition_holds(df, expression: str) -> bool:
    """Evaluate the condition to one boolean. A Series result means the author wrote a
    row-level condition; any row qualifying counts as firing, matching how a
    widget-level display rule treats row matches."""
    _validate_expr_safety(expression)
    verdict = _eval_expr(expression, df)
    if hasattr(verdict, "__len__") and not isinstance(verdict, (str, bytes)):
        return bool(getattr(verdict, "any", lambda: any(verdict))())
    return bool(verdict)


async def check_alert(db, alert) -> None:
    """Evaluate one due alert, firing on the rising edge. Outcome lands on the row.

    Also writes one Delivery log row per attempt (T3), fire-and-forget: every
    return path logs before returning, and the write itself can never raise
    (see log_delivery_sync) -- a logging failure must never stop the alert loop.
    Alerts have neither a schedule nor a report, so both those Delivery
    columns are NULL here (see Delivery's docstring).
    """
    t0 = time.monotonic()

    def _log(status: str, error: str | None = None) -> None:
        log_delivery_sync(
            org_id=alert.org_id, schedule_id=None, report_id=None,
            kind="alert", status=status, error=(error[:2000] if error else None),
            artifact_kind="none", duration_ms=int((time.monotonic() - t0) * 1000),
            created_at=datetime.utcnow(),
        )

    ds = await db.get(Dataset, alert.dataset_id)
    creator = await db.get(User, alert.creator_user_id)
    alert.last_checked_at = datetime.utcnow()
    if ds is None or creator is None or not ds.filename:
        alert.last_status = "disabled: dataset or creator no longer exists"
        await db.commit()
        _log("error", alert.last_status)
        return

    try:
        df = await asyncio.to_thread(load_file, ds.filename)
        rls = await resolve_rls_expr(db, creator, ds.id)
        # S1: apply_rls_filter, not apply_filter_expr(silent=True) -- a broken RLS
        # rule must hide rows (fail CLOSED), not silently evaluate the condition
        # over the full unfiltered table (fail OPEN, the bug this line used to have).
        df = apply_rls_filter(df, rls)
        from .prep import apply_prep_steps, prep_steps_of, resolve_join_frames
        _steps = prep_steps_of(ds)
        _aux = await resolve_join_frames(db, creator, _steps) if _steps else {}
        df = await asyncio.to_thread(apply_prep_steps, df, _steps, _aux)
        # The frame is secured as the CREATOR (nobody is at the keyboard), so
        # the creator's column rules apply too: an alert conditioned on a
        # column its creator cannot see must not evaluate -- the fired/quiet
        # signal alone answers a predicate about the hidden values.
        denied = await resolve_denied_columns(db, creator, ds.id)
        present = [c for c in denied if c in df.columns]
        if present:
            df = df.drop(columns=present)
        firing = await asyncio.to_thread(condition_holds, df, alert.expression)
    except Exception as e:  # noqa: BLE001 -- a broken alert must not stop the loop
        alert.last_status = f"evaluation failed: {e}"[:200]
        await db.commit()
        _log("error", alert.last_status)
        return

    was = alert.last_state
    alert.last_state = "firing" if firing else "clear"
    if firing and was != "firing":
        # The bell fires alongside email: email may be unconfigured, and an alert
        # only an SMTP log knows about is an alert nobody knows about.
        from .notifications import notify
        await notify(db, ds.org_id, creator.id, "alert",
                     f'Alert "{alert.name}" is firing: {alert.expression}')
        recipients = valid_recipients(alert.recipients)
        if recipients:
            err = await asyncio.to_thread(
                send_email, recipients, f"Alert: {alert.name}",
                f"The condition for \"{alert.name}\" is now true:\n\n    {alert.expression}\n\n"
                f"Dataset: {ds.name}\n{settings.public_base_url}\n")
            alert.last_status = err or f"fired, emailed {len(recipients)}"
        else:
            alert.last_status = "fired, no valid recipients"
    elif firing:
        alert.last_status = "still firing (no re-send)"
    else:
        alert.last_status = "clear"
    await db.commit()
    # `error` carries only failure detail; ok rows keep it NULL (delivery.py's
    # `... or None` convention for the shared Delivery table).
    if "failed" in (alert.last_status or ""):
        _log("error", alert.last_status)
    else:
        _log("ok")
