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


_COMPARISON = None


def _split_comparison(expression: str):
    """('COUNT(emp_no)', '<', '99000') for a top-level comparison, else None --
    so a test can say WHAT the left side is right now, not only fire/quiet."""
    import re
    global _COMPARISON
    if _COMPARISON is None:
        _COMPARISON = re.compile(r"(<=|>=|==|!=|<|>)")
    depth, i = 0, 0
    text = expression
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0:
            m = _COMPARISON.match(text, i)
            if m:
                return text[:i].strip(), m.group(1), text[m.end():].strip()
        i += 1
    return None


def metric_value(df, expression: str) -> float | None:
    """The number an aggregate expression evaluates to, or None."""
    _validate_expr_safety(expression)
    v = _eval_expr(expression, df)
    try:
        if hasattr(v, "__len__") and not isinstance(v, (str, bytes)):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _num(v: float) -> str:
    """A number as the alert's reader writes it. HR re-test 2026-10-01: a
    headcount read "Now 2.401e+05" -- `.4g` switches to exponent notation
    from 10,000 up. Whole values get separators; large ones two decimals."""
    f = float(v)
    if f.is_integer() and abs(f) < 1e15:
        return f"{int(f):,}"
    if abs(f) >= 100:
        return f"{f:,.2f}"
    return f"{f:.4g}"


def evaluate(df, alert) -> dict:
    """{firing, value, message} for one alert over a secured frame.

    A CHANGE alert (change_pct set) compares its metric with `last_value`; a
    condition alert evaluates its expression and also reports the current value
    of its left side when it has one."""
    change_pct = getattr(alert, "change_pct", None)
    if change_pct:
        value = metric_value(df, alert.expression)
        prev = getattr(alert, "last_value", None)
        if value is None:
            return {"firing": False, "value": None,
                    "message": "The metric did not evaluate to one number."}
        if prev in (None, 0):
            return {"firing": False, "value": value,
                    "message": f"Now {_num(value)}. The first check sets the baseline; "
                               f"it fires on a {change_pct:g}% move from here."}
        delta = (value - prev) / abs(prev) * 100
        direction = (getattr(alert, "change_direction", None) or "any").lower()
        hit = (delta >= change_pct if direction == "up" else
               delta <= -change_pct if direction == "down" else abs(delta) >= change_pct)
        return {"firing": bool(hit), "value": value,
                "message": f"Now {_num(value)}, {delta:+.1f}% against {_num(prev)} at the last check "
                           f"(fires at {'+' if direction == 'up' else '-' if direction == 'down' else '±'}"
                           f"{change_pct:g}%)."}
    firing = condition_holds(df, alert.expression)
    value = None
    parts = _split_comparison(alert.expression)
    if parts:
        try:
            value = metric_value(df, parts[0])
        except Exception:  # noqa: BLE001 -- the value is a courtesy
            value = None
    msg = ("The condition is TRUE now -- it would fire." if firing
           else "The condition is false now -- it would not fire.")
    if value is not None and parts:
        msg = f"{parts[0]} is {_num(value)} now. " + msg
    return {"firing": bool(firing), "value": value, "message": msg}


async def alert_frame(db, ds, user):
    """The rows an alert sees: the dataset, secured as `user` -- a file, or a
    LIVE dataset read through its own SQL with the row rule pushed down (live
    datasets used to be skipped by every alert)."""
    rls = await resolve_rls_expr(db, user, ds.id)
    denied = await resolve_denied_columns(db, user, ds.id)
    if ds.mode == "directquery" or not ds.filename:
        from .analysis_frame import load_directquery_frame
        got = await load_directquery_frame(db, ds, rls_filter_expr=rls, denied=set(denied or ()),
                                           row_cap=int(settings.import_row_cap or 0) or None)
        return got.frame
    df = await asyncio.to_thread(load_file, ds.filename)
    # S1: apply_rls_filter, not apply_filter_expr(silent=True) -- a broken RLS
    # rule must hide rows (fail CLOSED).
    df = apply_rls_filter(df, rls)
    from .prep import apply_prep_steps, prep_steps_of, resolve_join_frames
    _steps = prep_steps_of(ds)
    _aux = await resolve_join_frames(db, user, _steps) if _steps else {}
    df = await asyncio.to_thread(apply_prep_steps, df, _steps, _aux)
    present = [c for c in (denied or []) if c in df.columns]
    if present:
        df = df.drop(columns=present)
    return df


def post_webhook(url: str, text: str) -> str | None:
    """Post a message to an incoming webhook (Teams, Slack, or anything that
    accepts {"text": ...}). Returns an error string or None. https only."""
    if not url or not url.lower().startswith("https://"):
        return "webhook skipped: only https:// URLs are allowed"
    try:
        import httpx
        r = httpx.post(url, json={"text": text}, timeout=10)
        if r.status_code >= 400:
            return f"webhook answered {r.status_code}"
    except Exception as e:  # noqa: BLE001
        return f"webhook failed: {e}"[:200]
    return None


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
        # 5.18: an alert row has no report, so it names the alert and who hears it.
        to = [str(r) for r in (alert.recipients or []) if isinstance(r, str)]
        if getattr(alert, "webhook_url", None):
            to.append("webhook")
        log_delivery_sync(
            org_id=alert.org_id, schedule_id=None, report_id=None,
            kind="alert", status=status, error=(error[:2000] if error else None),
            artifact_kind="none", duration_ms=int((time.monotonic() - t0) * 1000),
            created_at=datetime.utcnow(),
            subject=f"Alert: {alert.name}"[:255], recipients=", ".join(to)[:2000] or None,
        )

    ds = await db.get(Dataset, alert.dataset_id)
    # Role loaded WITH the user: resolve_rls_expr reads `creator.role`, and a
    # lazy load of it cannot run in async code. Loaded with `db.get` it raised
    # MissingGreenlet inside the alert's first query, so no alert had ever
    # been checked -- 22 failed attempts on one since 2026-09-14 (HR re-test
    # 2026-10-01). delivery.py and delivery_jobs.py already load it this way.
    from sqlalchemy import select as _select
    from sqlalchemy.orm import selectinload as _selectinload
    creator = (await db.execute(
        _select(User).options(_selectinload(User.role))
        .where(User.id == alert.creator_user_id))).scalar_one_or_none()
    alert.last_checked_at = datetime.utcnow()
    if ds is None or creator is None or not (ds.filename or ds.mode == "directquery"):
        alert.last_status = "disabled: dataset or creator no longer exists"
        await db.commit()
        _log("error", alert.last_status)
        return

    try:
        # The frame is secured as the CREATOR (nobody is at the keyboard): row
        # AND column rules, so a predicate about a hidden column never runs.
        df = await alert_frame(db, ds, creator)
        # A plain copy crosses into the worker thread, never the ORM row. The
        # row carries a pending change (last_checked_at, above); if anything
        # had expired it, reading an attribute in the thread lazy-loaded it,
        # the session autoflushed from outside the event loop, and the check
        # died with MissingGreenlet -- every alert, every tick, since
        # 2026-09-14 (HR re-test 2026-10-01: alert 18 at 22 failed attempts,
        # never once checked).
        from types import SimpleNamespace
        snapshot = SimpleNamespace(
            expression=alert.expression,
            change_pct=getattr(alert, "change_pct", None),
            change_direction=getattr(alert, "change_direction", None),
            last_value=getattr(alert, "last_value", None),
        )
        result = await asyncio.to_thread(evaluate, df, snapshot)
        firing = result["firing"]
        if result.get("value") is not None:
            alert.last_value = result["value"]
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
        body = (f"The alert \"{alert.name}\" fired.\n\n    {alert.expression}\n\n"
                f"{result.get('message', '')}\nDataset: {ds.name}\n{settings.public_base_url}\n")
        status = []
        if recipients:
            err = await asyncio.to_thread(send_email, recipients, f"Alert: {alert.name}", body)
            status.append(err or f"fired, emailed {len(recipients)}")
        if getattr(alert, "webhook_url", None):
            err = await asyncio.to_thread(post_webhook, alert.webhook_url, body)
            status.append(err or "posted to webhook")
        alert.last_status = ("; ".join(status) or "fired, no valid recipients")[:200]
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
