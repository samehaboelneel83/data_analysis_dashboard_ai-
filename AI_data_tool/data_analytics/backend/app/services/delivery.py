"""Building and sending a scheduled report delivery.

The digest is an xlsx workbook with one sheet per data widget, resolved through the
same shaping pipeline the screen uses -- with row-level security resolved AS THE
SCHEDULE'S CREATOR. That identity choice is the module's security core: a scheduled
run has no viewer, and "no viewer" must never degrade to "no RLS".

Sending is stdlib smtplib in a thread. An unconfigured SMTP host records the failure
on the schedule row instead of raising: the loop's job is every schedule, not this
one.
"""
from __future__ import annotations

import asyncio
import io
import logging
import re
import smtplib
import time
from datetime import datetime
from email.message import EmailMessage

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..core.config import settings
from ..core.rls import resolve_rls_expr
from ..models.models import Dataset, Report, ReportPage, User
from .prep import prep_steps_of, resolve_join_frames
from .query_log import log_delivery_sync
from .widget_data import get_widget_data
from .display_rules import result_frame

log = logging.getLogger(__name__)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_WEBHOOK = re.compile(r"^https://[^\s]+$")

# Widgets with no tabular data to put on a sheet.
_SKIP_TYPES = {"text", "button", "image", "shape", "slicer"}


def valid_recipients(recipients) -> list[str]:
    """Emails and https:// webhook URLs both count: a Teams (or Slack-compatible)
    incoming webhook pasted as a recipient routes the delivery there. One list, two
    transports -- the schedule model needs no schema change, which matters because
    create_all never alters deployed tables."""
    return [r for r in (recipients or [])
            if isinstance(r, str) and (_EMAIL.match(r) or _WEBHOOK.match(r))]


def split_recipients(recipients: list[str]) -> tuple[list[str], list[str]]:
    emails = [r for r in recipients if _EMAIL.match(r)]
    hooks = [r for r in recipients if _WEBHOOK.match(r)]
    return emails, hooks


def post_webhook(url: str, title: str, text: str) -> str | None:
    """POST a simple message card; return an error string or None. Teams and Slack
    incoming webhooks both accept {"text": ...}."""
    import json as _json
    import urllib.request
    try:
        req = urllib.request.Request(
            url, data=_json.dumps({"title": title, "text": text}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status >= 300:
                return f"webhook returned {resp.status}"
        return None
    except Exception as e:  # noqa: BLE001 -- recorded on the schedule row
        return f"webhook failed: {e}"


async def build_digest(db, report: Report, creator: User,
                       context_label: str | None = None) -> tuple[bytes, int]:
    """The report's data as an xlsx workbook: one sheet per data widget.

    Returns (bytes, sheet_count). Widgets that fail to resolve are skipped rather
    than sinking the whole delivery -- a digest missing one broken widget beats no
    digest, and the sheet count in the status line makes the shortfall visible.
    """
    pages = (await db.execute(
        select(ReportPage).options(selectinload(ReportPage.widgets))
        .where(ReportPage.report_id == report.id)
        .order_by(ReportPage.position)
    )).scalars().all()

    buffer = io.BytesIO()
    sheets = 0
    used_names: set[str] = set()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for page in pages:
            for w in page.widgets:
                if w.widget_type in _SKIP_TYPES:
                    continue
                dataset_id = (w.config or {}).get("dataset_id") or report.dataset_id
                if not dataset_id:
                    continue
                ds = await db.get(Dataset, dataset_id)
                if ds is None or ds.org_id != report.org_id or not ds.filename:
                    continue
                # Access as of THIS run, not as of when the schedule was made:
                # a creator whose share was revoked must stop mailing the data.
                from ..core.capability import can_read_dataset
                if not await can_read_dataset(db, creator, ds.id, report_id=report.id):
                    continue
                try:
                    steps = prep_steps_of(ds)
                    aux = await resolve_join_frames(db, creator, steps) if steps else {}
                    rls = await resolve_rls_expr(db, creator, ds.id)
                    # Column security as the sender, like every read path --
                    # the digest used to put denied columns into the
                    # attachment -- plus sensitivity redaction (Phase 7.3).
                    from ..core.rls import resolve_denied_columns
                    from .sensitivity import redacted_columns
                    drop = sorted(set(await resolve_denied_columns(db, creator, ds.id) or [])
                                  | set(await redacted_columns(db, ds.id, context_label)))
                    # Off the scheduler's event loop: a slow parse here would
                    # otherwise delay every later schedule/alert in the tick.
                    result = await asyncio.to_thread(
                        get_widget_data,
                        ds.filename, dict(w.config or {}), widget_type=w.widget_type,
                        calculated_columns=ds.calculated_columns or None,
                        filter_expr=ds.default_filter_expr or None,
                        rls_filter_expr=rls, use_cache=False,
                        measures=ds.measures or None,
                        prep_steps=steps or None, prep_aux_frames=aux or None,
                        custom_functions=ds.custom_functions, drop_columns=drop or None,
                    )
                    frame = result_frame(result)
                    if frame is None or frame.empty:
                        continue
                    # Excel sheet names: <=31 chars, unique, no []:*?/\
                    base = re.sub(r"[\[\]:*?/\\]", "", w.title or w.widget_type)[:28] or "sheet"
                    name, n = base, 2
                    while name in used_names:
                        name, n = f"{base[:25]} {n}", n + 1
                    used_names.add(name)
                    frame.to_excel(writer, sheet_name=name, index=False)
                    sheets += 1
                except Exception as e:  # noqa: BLE001 -- see docstring
                    log.warning("Digest sheet failed for widget %s: %s", w.id, e)
        if sheets == 0:
            # An empty workbook is invalid xlsx; write a stub sheet stating the fact.
            pd.DataFrame({"note": ["No widget produced tabular data."]}).to_excel(
                writer, sheet_name="empty", index=False)
    buffer.seek(0)
    return buffer.read(), sheets


def send_email(recipients: list[str], subject: str, body: str,
               attachment: tuple[str, bytes] | None = None) -> str | None:
    """Send synchronously; return an error string or None. Called via to_thread."""
    if not settings.smtp_host:
        return "SMTP is not configured (smtp_host is empty)"
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)
    if attachment:
        name, payload = attachment
        msg.add_attachment(
            payload, maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=name)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
            if settings.smtp_starttls:
                s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
        return None
    except Exception as e:  # noqa: BLE001 -- recorded on the schedule row
        return f"send failed: {e}"


async def run_schedule(db, schedule) -> None:
    """Execute one due schedule end to end, recording the outcome on the row.

    Also writes one Delivery log row per attempt (T3), fire-and-forget: every
    return path below logs before returning, and the log write itself can
    never raise (see log_delivery_sync) -- a logging failure must never fail
    the delivery it describes.
    """
    t0 = time.monotonic()

    def _log(status: str, error: str | None = None, artifact_kind: str = "none") -> None:
        log_delivery_sync(
            org_id=schedule.org_id, schedule_id=schedule.id, report_id=schedule.report_id,
            kind="schedule", status=status, error=(error[:2000] if error else None),
            artifact_kind=artifact_kind, duration_ms=int((time.monotonic() - t0) * 1000),
            created_at=datetime.utcnow(),
        )

    report = await db.get(Report, schedule.report_id)
    # Role eager-loaded: build_digest asks can_read_dataset, which reads
    # `creator.role`, and a lazy load there fails under the async session.
    creator = (await db.execute(
        select(User).options(selectinload(User.role))
        .where(User.id == schedule.creator_user_id))).scalar_one_or_none()
    schedule.last_run_at = datetime.utcnow()
    if report is None or creator is None:
        schedule.last_status = "disabled: report or creator no longer exists"
        await db.commit()
        _log("error", schedule.last_status)
        return

    recipients = valid_recipients(schedule.recipients)
    if not recipients:
        schedule.last_status = "no valid recipients"
        await db.commit()
        _log("error", schedule.last_status)
        return

    # Attachment format rides in the reserved recipients entry alongside the
    # calendar spec -- the same create_all-safe channel: {"__format__": "pdf"}.
    fmt = "xlsx"
    for r in (schedule.recipients or []):
        if isinstance(r, dict) and r.get("__format__") in ("xlsx", "pdf"):
            fmt = r["__format__"]
    # Sensitivity (Phase 7.3): a Restricted report's rows are not e-mailed;
    # a Confidential one goes out with personal-data columns redacted.
    from .sensitivity import rank as s_rank, report_effective
    label, reasons = await report_effective(db, report)
    if s_rank(label) >= s_rank("Restricted"):
        schedule.last_status = ("blocked: the report is Restricted"
                                + (f" ({reasons[0]})" if reasons else "")
                                + " -- e-mail would send its rows outside the product")
        await db.commit()
        _log("error", schedule.last_status)
        return
    try:
        if fmt == "pdf":
            from .pdf_export import build_report_pdf
            from ..routers.reports import _resolve_report_sections, _visible_page_ids
            # The creator's page visibility applies to what they send, as it
            # does to what they can open.
            sections = await _resolve_report_sections(
                db, report, creator, allowed_page_ids=await _visible_page_ids(db, report, creator),
                context_label=label)
            payload = await asyncio.to_thread(build_report_pdf, report.name, report.description, sections)
            attach = (f"{report.name[:40]}.pdf", payload)
            count_note = f"{sum(len(sec['widgets']) for sec in sections)} visuals"
        else:
            payload, sheets = await build_digest(db, report, creator, context_label=label)
            attach = (f"{report.name[:40]}.xlsx", payload)
            count_note = f"{sheets} data sheet{'s' if sheets != 1 else ''}"
    except Exception as e:  # noqa: BLE001 -- a broken build must not sink the scheduler tick
        schedule.last_status = f"build failed: {e}"[:200]
        await db.commit()
        _log("error", schedule.last_status, artifact_kind=fmt)
        raise

    link = f"{settings.public_base_url}/reports/{report.id}/print"
    body = (f"Scheduled delivery of \"{report.name}\" ({count_note} attached).\n\n"
            f"Open the report for the live view: {link}\n")

    emails, hooks = split_recipients(recipients)
    outcomes = []
    if emails:
        err = await asyncio.to_thread(
            send_email, emails, schedule.subject or f"Report: {report.name}", body, attach)
        outcomes.append(err or f"emailed {len(emails)}")
    for hook in hooks:
        # Webhooks get the summary and the link, not the attachment: Teams incoming
        # webhooks accept text, and the digest is one click away behind auth.
        err = await asyncio.to_thread(
            post_webhook, hook, schedule.subject or f"Report: {report.name}", body)
        outcomes.append(err or "posted to webhook")
    schedule.last_status = ("; ".join(outcomes))[:200] or "nothing to send"
    failures = [o for o in outcomes if "failed" in o or "not configured" in o or "returned" in o]
    if failures:
        # Failures notify in-app; successes stay quiet -- a bell that rings on
        # every routine delivery trains its owner to ignore it.
        from .notifications import notify
        await notify(db, report.org_id, creator.id, "schedule",
                     f'Scheduled delivery of "{report.name}" had problems: {"; ".join(failures)}'[:500],
                     f"/reports/{report.id}")
    await db.commit()
    _log("error" if failures else "ok", "; ".join(failures) or None, artifact_kind=fmt)
