"""The dashboard page copilot: chat that edits the OPEN page, or answers
about its data — never "not answerable by SQL" on this surface.

One endpoint, one LLM call (the app's shared client), then either:

- page ACTIONS, validated per-action and applied here through the same
  writes the GUI endpoints perform (same `check_org` scoping, same revision
  bump — the copilot can do exactly what the GUI can, nothing more); or
- a DATA QUESTION, delegated to the existing agent (`run_agent`) over the
  report's datasets, its answer and result snapshots returned inline.

Validation is per-action and forgiving: an unknown widget type, a column
not in the dataset, or a widget id not on the page skips THAT action and
appends a note — the model's other edits still land, and the user reads
why one did not. The chat itself is not persisted: the record of a page
command is the page, plus the report's revision counter.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..core.capability import max_dataset_capability, rank, require_capability
from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user
from ..models.models import (Dataset, DataSource, Report, ReportPage,
                             ReportWidget, User)
from ..services import llm as llm_service
from ..services import quotas
from ..services.agent.context import load_dataset_context
from ..services.agent.graph import run_agent
from ..services.agent.nodes.copilot import (COLUMN_KEYS, CREATABLE_TYPES,
                                            resolve_copilot)
from ..services.widget_data import _validate_expr_safety

router = APIRouter(prefix="/reports", tags=["reports"])


class CopilotIn(BaseModel):
    message: str
    history: list[dict] = Field(default_factory=list)
    # The widget selected in the builder, so "the selected chart" and "it"
    # resolve without guessing. Validated against the page before use.
    selected_widget_id: int | None = None


async def _page_columns(db: AsyncSession, report: Report, user: User) -> dict[str, dict[str, str]]:
    """{table: {column: dtype}} for the report's datasets, via the agent's
    own context loader — minus any columns this user's role is denied
    (column security, R1): the copilot must not offer a column the charts
    themselves would refuse. Empty when the report has no dataset."""
    from ..core.rls import resolve_denied_columns
    ids = [i for i in [report.dataset_id, *(report.additional_dataset_ids or [])]
           if i is not None]
    if not ids:
        return {}
    ctx = await load_dataset_context(db, ids, user.org_id)
    denied_all: set[str] = set()
    for did in ids:
        denied_all.update(c.casefold() for c in await resolve_denied_columns(db, user, did))
    return {name: {c: dt for c, dt in obj.columns.items()
                   if c.casefold() not in denied_all}
            for name, obj in ctx.objects.items()}


async def _page_calculated_columns(
        db: AsyncSession, report: Report, user: User) -> tuple[list[dict], str | None]:
    """Saved fx formulas on the report's datasets, plus the primary dataset's
    mode (DirectQuery cannot store them). Same org check as _page_columns."""
    ids = [i for i in [report.dataset_id, *(report.additional_dataset_ids or [])]
           if i is not None]
    out: list[dict] = []
    seen: set[str] = set()
    mode: str | None = None
    for i, did in enumerate(ids):
        ds = await db.get(Dataset, did)
        if ds is None or ds.org_id != user.org_id:
            continue
        if i == 0:
            mode = ds.mode
        for c in ds.calculated_columns or []:
            name = (c.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            out.append({"name": name,
                        "expression": (c.get("expression") or "").strip()})
    return out, mode


def _clamped_layout(patch: dict | None, base: dict) -> dict:
    """The GUI's grid is 12 columns; a model asking for w=40 gets w=12, not
    an error. Only x/y/w/h pass, only as ints."""
    out = dict(base)
    for key, lo, hi in (("x", 0, 11), ("y", 0, 10_000), ("w", 1, 12), ("h", 1, 40)):
        v = (patch or {}).get(key)
        if isinstance(v, int) and not isinstance(v, bool):
            out[key] = max(lo, min(hi, v))
    if out.get("x", 0) + out.get("w", 1) > 12:
        out["x"] = max(0, 12 - out["w"])
    return out


def _clean_config(cfg: dict | None, columns: set[str], notes: list[str], *,
                  keep_removals: bool = False) -> dict | None:
    """Scalars only (the schema already enforces that), `dataset_id` dropped
    (a chart must not be silently repointed at other data), and column-naming
    keys checked against the dataset. A bad column fails the whole action --
    a chart of a misspelled column would render as an empty box that looks
    like a data problem.

    `keep_removals` (updates only): a null value means REMOVE THE SETTING.
    Found live -- an Arabic "remove the auto-reload" got a confident reply
    while dropping the null silently left the value in place, a fake success
    of exactly the kind the settings-honesty rule exists to prevent."""
    if not cfg:
        return {}
    out = {}
    for k, v in cfg.items():
        if k == "dataset_id":
            continue
        # The prompt examples say `agg`; widgets and the shaper read
        # `aggregation`. Same setting — writing the alias would look like a
        # successful edit that the engine never sees.
        if k == "agg":
            k = "aggregation"
        if v is None:
            if keep_removals:
                out[k] = None
            continue
        if k in COLUMN_KEYS and columns and v not in columns:
            match = next((c for c in columns
                          if str(c).casefold() == str(v).casefold()), None)
            if match is None:
                notes.append(f'Skipped an edit: no column named "{v}".')
                return None
            v = match
        out[k] = v
    return out


@router.post("/{report_id}/pages/{page_id}/copilot")
async def page_copilot(report_id: int, page_id: int, body: CopilotIn,
                       db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, user, "Report not found")
    page = (await db.execute(select(ReportPage).where(
        ReportPage.id == page_id, ReportPage.report_id == report_id))).scalar_one_or_none()
    if not page:
        raise HTTPException(404, "Page not found")

    # Edit capability UP FRONT, not only inside _bump_revision at apply time:
    # this is an editing surface (the builder mounts it in edit mode only),
    # and a view-only caller must be refused before an LLM call is spent on
    # planning edits that would then be rolled back.
    await require_capability(db, user, report_id, "edit")

    # Same daily cap as the chat agent: both are one LLM call per message.
    await quotas.enforce_agent_quota(db, user.org_id)

    widgets = (await db.execute(select(ReportWidget).where(
        ReportWidget.page_id == page_id).order_by(ReportWidget.id))).scalars().all()
    columns_by_table = await _page_columns(db, report, user)
    calc_cols, dataset_mode = await _page_calculated_columns(db, report, user)
    page_ctx = {
        "report_name": report.name, "page_name": page.name,
        "widgets": [{"id": w.id, "widget_type": w.widget_type, "title": w.title,
                     "config": w.config or {}, "layout": w.layout or {}}
                    for w in widgets],
        "columns": columns_by_table,
        "calculated_columns": calc_cols,
        "dataset_mode": dataset_mode,
        # Only a selection that is really on this page: a stale id from
        # another page must not make "it" point somewhere invisible.
        "selected_widget_id": (body.selected_widget_id
                               if any(w.id == body.selected_widget_id for w in widgets)
                               else None),
    }
    history = [{"role": h.get("role"), "content": h.get("content")}
               for h in (body.history or [])[-8:]]

    resolved = await resolve_copilot(body.message, history, page_ctx,
                                     llm_service.get_client())
    if resolved is None:
        raise HTTPException(502, "the model endpoint could not answer")

    notes: list[str] = []

    # ── A data question: the agent answers it, this chat shows the rows ─────
    if resolved["data_question"]:
        ids = [i for i in [report.dataset_id, *(report.additional_dataset_ids or [])]
               if i is not None]
        datasets = []
        for did in ids:
            ds = await db.get(Dataset, did)
            if ds is not None and ds.org_id == user.org_id:
                datasets.append(ds)
        if not datasets:
            return {"reply": "This dashboard has no dataset to ask about.",
                    "applied": [], "notes": [], "results": []}
        # Same routing rule as the builder's own chat pane: a report whose
        # primary dataset is backed by a live connection asks THAT SOURCE --
        # a DirectQuery dataset has no file for the dataset-mode executor
        # to load, so the datasets path would fail at execution.
        source = None
        if datasets[0].data_source_id is not None:
            src = await db.get(DataSource, datasets[0].data_source_id)
            if src is not None and src.org_id == user.org_id:
                source = src
        agent_history = [{**h, "sql": [], "results": []} for h in history]
        async with quotas.concurrent_ask_slot(db, user.org_id):
            run = await run_agent(db, question=resolved["data_question"],
                                  source=source,
                                  datasets=None if source else datasets,
                                  user=user,
                                  client=llm_service.get_client(),
                                  history=agent_history)
        await db.commit()
        from ..routers.agent import _run_payload
        from ..models.models import AgentStep
        steps = (await db.execute(select(AgentStep).where(
            AgentStep.agent_run_id == run.id).order_by(AgentStep.id))).scalars().all()
        payload = _run_payload(run, steps)
        return {"reply": run.answer or run.error or "", "applied": [],
                "notes": [], "results": payload["results"]}

    # ── Page actions, applied like the GUI would ────────────────────────────
    by_id = {w.id: w for w in widgets}
    applied: list[dict] = []
    next_y = max((w.layout or {}).get("y", 0) + (w.layout or {}).get("h", 4)
                 for w in widgets) if widgets else 0
    physical_names = {c for cols in columns_by_table.values() for c in cols}
    column_names = set(physical_names)
    column_names.update(c["name"] for c in calc_cols if c.get("name"))

    for action in resolved["actions"]:
        op = action.get("op")
        if op == "create":
            wtype = action.get("widget_type")
            if wtype not in CREATABLE_TYPES:
                notes.append(f'Skipped: "{wtype}" is not a widget type I can create.')
                continue
            cfg = _clean_config(action.get("config"), column_names, notes)
            if cfg is None:
                continue
            dw, dh = CREATABLE_TYPES[wtype]
            layout = _clamped_layout(action.get("layout"),
                                     {"x": 0, "y": next_y, "w": dw, "h": dh})
            layout["y"] = max(layout["y"], next_y) if action.get("layout") is None else layout["y"]
            widget = ReportWidget(page_id=page_id, widget_type=wtype,
                                  title=action.get("title") or wtype.title(),
                                  config=cfg, layout=layout)
            db.add(widget)
            await db.flush()
            next_y = layout["y"] + layout["h"]
            applied.append({"op": "create", "widget_id": widget.id,
                            "title": widget.title})
        elif op in ("update", "delete"):
            widget = by_id.get(action.get("widget_id"))
            if widget is None:
                notes.append("Skipped: that widget is not on this page.")
                continue
            if op == "delete":
                applied.append({"op": "delete", "widget_id": widget.id,
                                "title": widget.title})
                del by_id[widget.id]
                await db.delete(widget)
                continue
            wtype = action.get("widget_type")
            changed = False
            if wtype:
                if wtype not in CREATABLE_TYPES:
                    notes.append(f'Skipped: cannot convert to "{wtype}".')
                    continue
                widget.widget_type = wtype
                changed = True
            patch = _clean_config(action.get("config"), column_names, notes,
                                  keep_removals=True)
            if patch is None:
                continue
            if patch:
                merged = dict(widget.config or {})
                for k, v in patch.items():
                    if v is None:
                        # null = remove the setting ("turn off auto-reload").
                        merged.pop(k, None)
                    else:
                        merged[k] = v
                widget.config = merged
                changed = True
            if action.get("title"):
                widget.title = action["title"]
                changed = True
            if action.get("layout"):
                widget.layout = _clamped_layout(action["layout"], widget.layout or {})
                changed = True
            if not changed:
                # Reporting "Updated X" for a no-op would be a fake success.
                notes.append(f'"{widget.title}": that request changed no setting.')
                continue
            applied.append({"op": "update", "widget_id": widget.id,
                            "title": widget.title})
        elif op == "add_calculated_column":
            # Same write as PUT /datasets/{id}/calculated-columns: JSON list
            # on the primary dataset, data-level capability, safety sandbox.
            cfg = action.get("config") or {}
            name = str(cfg.get("name") or "").strip()
            expression = str(cfg.get("expression") or "").strip()
            if not name or not expression:
                notes.append("Skipped: a calculated column needs a name and an expression.")
                continue
            ds_id = report.dataset_id
            if ds_id is None:
                notes.append("Skipped: this dashboard has no dataset to add a formula to.")
                continue
            ds = await db.get(Dataset, ds_id)
            if ds is None or ds.org_id != user.org_id:
                notes.append("Skipped: this dashboard has no dataset to add a formula to.")
                continue
            if (ds.mode or "import") == "directquery":
                notes.append("Skipped: DirectQuery datasets cannot store calculated columns.")
                continue
            if rank(await max_dataset_capability(db, user, ds.id)) < rank("data"):
                notes.append("Skipped: you do not have data-level access to add formulas on this dataset.")
                continue
            if name in physical_names:
                notes.append(f'Skipped: "{name}" is already a dataset column.')
                continue
            try:
                _validate_expr_safety(expression)
            except Exception as e:
                notes.append(f'Skipped: expression is not valid ({e}).')
                continue
            cols = [c for c in (ds.calculated_columns or []) if c.get("name") != name]
            cols.append({"name": name, "expression": expression})
            ds.calculated_columns = cols
            flag_modified(ds, "calculated_columns")
            column_names.add(name)
            applied.append({"op": "add_calculated_column", "widget_id": None,
                            "title": name})
        else:
            notes.append(f'Skipped an action I did not understand: "{op}".')

    before_version_id = None
    summary = None
    if applied:
        # One revision bump for the batch, same collaborative-edit counter
        # the GUI endpoints bump (reports._bump_revision). The snapshot it
        # takes is the state BEFORE the copilot's change, labelled as such, so
        # version history attributes the change and one restore undoes it.
        from ..routers.reports import _bump_revision
        verbs = {"create": "added", "delete": "removed", "update": "changed",
                 "add_calculated_column": "added the formula"}
        summary = "; ".join(f'{verbs.get(a["op"], a["op"])} "{a.get("title") or a.get("widget_id")}"'
                            for a in applied)
        version = await _bump_revision(report_id, db, user, via="copilot",
                                       note=f"Before the copilot {summary}")
        await db.flush()
        before_version_id = version.id if version is not None else None
        from ..services.audit import record as _audit
        await _audit(db, user, "report.copilot_edit", "report", report_id, summary[:300])
    await db.commit()
    return {"reply": resolved["reply"], "applied": applied, "notes": notes,
            "results": [], "before_version_id": before_version_id, "summary": summary}
