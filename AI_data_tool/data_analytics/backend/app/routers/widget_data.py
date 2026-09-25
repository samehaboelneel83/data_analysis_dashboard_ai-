import asyncio
import io
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from ..core.database import get_db
from ..core.capability import require_dataset_read
from ..core.org_scope import check_org
from ..core.rls import expand_author_expressions, resolve_denied_columns, resolve_rls_expr
from ..dependencies import get_current_user
from ..models.models import DataSource, Dataset, Report, ReportParameter, User
from ..schemas.schemas import WidgetDataRequest
from ..services.display_rules import result_frame
from ..services.parameters import ParameterError, encode_literal, substitute
from ..services.measure_eval import evaluate_measure
from ..services import quotas
from ..services.semantic_guard import config_refusal

_EXPORT_FORMATS = {"csv": "csv", "tsv": "tsv", "xlsx": "xlsx"}


def _safe_filename(name: str) -> str:
    """A filename the Content-Disposition header can carry safely.

    Widget titles are user input and reach this header, so anything outside a
    conservative allowlist -- quotes, semicolons, newlines, path separators -- is
    stripped rather than escaped: a header injection here would be a response-splitting
    bug, and no title needs those characters."""
    cleaned = re.sub(r"[^A-Za-z0-9 _.-]", "", name).strip() or "widget"
    return cleaned[:60]

from ..core.widget_errors import CodedHTTPException, widget_error
from ..services.direct_query import DirectQueryUnsupported, SourceUnavailable, run_direct_query
from ..services.prep import prep_steps_of, resolve_join_frames
from ..services.widget_data import (ImportRowCapExceeded, apply_rls_filter, sums_measure_by_default,
                                    get_widget_data, load_file)

router = APIRouter(prefix="/datasets", tags=["widget-data"])

# One gate per event loop (not per process): an asyncio.Semaphore belongs to
# the loop its waiters run on, and the test suite creates a fresh loop per
# test. Keyed weakly so a finished loop's gate is collectable.
import weakref

_widget_work_gates: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = (
    weakref.WeakKeyDictionary())


def _work_gate() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    gate = _widget_work_gates.get(loop)
    if gate is None:
        from ..core.config import settings
        gate = asyncio.Semaphore(settings.widget_work_max_concurrency)
        _widget_work_gates[loop] = gate
    return gate


def _config_uses_measure(config: dict, measures: list[dict]) -> bool:
    """True when any role in the widget config names a dataset measure. Checked so a
    DirectQuery dataset fails loudly rather than silently falling back to a column."""
    if not measures:
        return False
    names = {m.get("name") for m in measures}
    candidates = [config.get("measure"), config.get("measure2")]
    candidates += list(config.get("measures") or [])
    roles = config.get("roles") or {}
    if isinstance(roles, dict):
        candidates += [roles.get("measure"), roles.get("measure2")]
        candidates += list(roles.get("measures") or [])
    return any(c in names for c in candidates if c)


async def _apply_report_parameters(req: WidgetDataRequest, db: AsyncSession, current_user: User) -> WidgetDataRequest:
    """Substitute this viewer's parameter values before anything is evaluated.

    Two surfaces, two treatments:
      * structured filter VALUES ("@name" as a filter's value, or inside its list) --
        replaced with the typed value directly. Filters compare as data, never as
        code, so no literal encoding is involved.
      * calculated-column EXPRESSIONS -- routed through substitute(), which encodes
        each value as a literal of the parameter's declared type. That encoding is the
        entire injection story; see services/parameters.py.

    An unknown @name in a filter is a 400, not a pass-through: a filter comparing a
    column against the literal string "@budget" matches nothing and looks like a data
    bug rather than the config bug it is.
    """
    if not req.report_id:
        return req

    report = await db.get(Report, req.report_id)
    check_org(report, current_user, "Report not found")
    defs = (await db.execute(
        select(ReportParameter).where(ReportParameter.report_id == report.id)
    )).scalars().all()
    if not defs:
        return req
    by_name = {d.name: d for d in defs}

    # Expression parameters: value computed over the WHOLE source (RLS-scoped, but
    # immune to report/widget filters) at query time, so a benchmark or a
    # self-updating slider range reflects the data rather than a typed constant. The
    # expression rides in default_value; the computed scalar wins over any viewer
    # value. Import datasets only — a warehouse benchmark would need a SQL aggregate.
    expr_defs = [d for d in defs if d.param_type == "expression"]
    computed: dict[str, float] = {}
    if expr_defs:
        ds = await db.get(Dataset, report.dataset_id) if report.dataset_id else None
        if ds is None:
            raise widget_error(400, "parameter", "Expression parameters need the report to have a primary dataset")
        if ds.mode == "directquery":
            raise widget_error(400, "parameter", "Expression parameters require an import dataset")
        rls = await resolve_rls_expr(db, current_user, ds.id)
        # Column security as well: an expression parameter over a denied column
        # would hand this viewer its aggregate as a benchmark value.
        denied = await resolve_denied_columns(db, current_user, ds.id)

        def _compute() -> dict[str, float]:
            frame = apply_rls_filter(load_file(ds.filename), rls)
            present = [c for c in denied if c in frame.columns]
            if present:
                frame = frame.drop(columns=present)
            out: dict[str, float] = {}
            for d in expr_defs:
                out[d.name] = float(evaluate_measure(d.default_value or "", frame, []))
            return out
        try:
            computed = await asyncio.to_thread(_compute)
        except Exception as e:
            raise widget_error(400, "parameter", f"Expression parameter could not be evaluated: {e}")

    # Computed expression values win over a viewer-supplied value (a benchmark is not
    # something a viewer overrides); everything else takes the viewer value or default.
    effective = {**req.parameters, **computed}

    def typed(name: str):
        d = by_name.get(name)
        if d is None:
            raise widget_error(400, "parameter", f"Unknown report parameter @{name}")
        raw = effective.get(name, d.default_value)
        if raw is None:
            raise widget_error(400, "parameter", f"Parameter @{name} has no value and no default")
        if d.param_type in ("number", "expression"):
            try:
                return float(raw)
            except (TypeError, ValueError):
                raise widget_error(400, "parameter", f"Parameter @{name} expects a number")
        return str(raw)[:500]

    config = dict(req.config or {})

    # rank.n may be parameter-driven ("@name"): SAS drives the rank count from
    # a parameter, and a slider bound to top-N is the natural use. Typed as a
    # number and floored to an int like any count.
    rank_cfg = config.get("rank")
    if isinstance(rank_cfg, dict) and isinstance(rank_cfg.get("n"), str) and rank_cfg["n"].startswith("@"):
        rank_cfg = dict(rank_cfg)
        resolved = typed(rank_cfg["n"][1:])
        try:
            rank_cfg["n"] = int(float(resolved))
        except (TypeError, ValueError):
            raise widget_error(400, "parameter", f"Parameter {rank_cfg['n']} is not a number usable as a rank count")
        config["rank"] = rank_cfg

    filters = []
    for f in (config.get("filters") or []):
        f = dict(f)
        v = f.get("value")
        if isinstance(v, str) and v.startswith("@"):
            f["value"] = typed(v[1:])
        elif isinstance(v, list):
            f["value"] = [typed(x[1:]) if isinstance(x, str) and x.startswith("@") else x for x in v]
        filters.append(f)
    if filters:
        config["filters"] = filters

    calc_cols = []
    for c in (req.calculated_columns or []):
        c = dict(c)
        expr = c.get("expression")
        if isinstance(expr, str) and "@" in expr:
            try:
                c["expression"] = substitute(expr, effective, defs)
            except ParameterError as e:
                raise widget_error(400, "parameter", str(e))
        calc_cols.append(c)

    return req.model_copy(update={"config": config, "calculated_columns": calc_cols})


def _direct_query_relative_dates(req: WidgetDataRequest) -> WidgetDataRequest:
    """DirectQuery gets relative date filters as a plain >= / < pair, resolved
    against today. Anchoring to the latest date would need a MAX() round trip
    per filter; until that exists it is refused with a sentence rather than
    quietly anchored to today -- a silent anchor is the defect this feature
    exists to fix."""
    from datetime import date
    from ..services.relative_dates import RelativeDateError, has_relative, validate_spec, window
    filters = (req.config or {}).get("filters") or []
    if not has_relative(filters):
        return req
    out = []
    for f in filters:
        if not (isinstance(f, dict) and f.get("op") == "relative"):
            out.append(f)
            continue
        try:
            spec = validate_spec(f.get("value"))
        except RelativeDateError as e:
            raise widget_error(400, "bad_filter", str(e))
        if spec["anchor"] == "data_max":
            raise widget_error(400, "unsupported",
                               "On a live (DirectQuery) source, relative dates count back from today; "
                               "anchoring to the latest date in the data needs an import dataset")
        start, end, _label, _inc = window(spec, date.today())
        out.append({"column": f.get("column"), "op": "gte", "value": start.isoformat()})
        out.append({"column": f.get("column"), "op": "lt", "value": end.isoformat()})
    return req.model_copy(update={"config": {**req.config, "filters": out}})


async def _clear_scoring_model(req: WidgetDataRequest, db: AsyncSession, current_user: User,
                               dataset_id: int) -> WidgetDataRequest:
    """Security-check a canvas scoring widget's saved model, as the score
    endpoint does (same helper), then hand the shaper a key to it."""
    from .prediction_models import load_usable_model
    from ..services.model_widgets import register_scoring_model
    try:
        model_id = int(req.config["prediction_model_id"])
        model, pkg = await load_usable_model(db, current_user, dataset_id, model_id)
    except (TypeError, ValueError):
        raise widget_error(400, "bad_request", "prediction_model_id must be a number")
    except HTTPException as e:
        raise widget_error(e.status_code, "not_found" if e.status_code == 404 else "forbidden", str(e.detail))
    key = f"{model.id}:{model.created_at.isoformat() if model.created_at else ''}"
    register_scoring_model(key, pkg, model.name)
    return req.model_copy(update={"config": {**req.config, "__model__": key}})


async def _resolve_widget_data(
    dataset_id: int, req: WidgetDataRequest, db: AsyncSession, current_user: User,
    *, email_override: str | None = None, org_id_override: int | None = None,
    via_report_id: int | None = None,
    redact_columns: list[str] | None = None,
) -> dict:
    """Shape one widget's data for this user.

    Extracted so that the export endpoint runs THIS code rather than its own copy.
    Row-level security, calculated columns, measures and the DirectQuery pushdown all
    live in here; an export that resolved data by any other route would be a second
    place for those to be applied, and the one that gets forgotten is the security
    control. Exported bytes are the displayed result, by construction.

    `email_override`/`org_id_override` (Task E1): passed straight through to
    `expand_author_expressions` for USEREMAIL()/ORGID() expansion inside the
    dataset's OWN author expressions -- never used for tenancy (`check_org`
    above always keys strictly on `current_user.org_id`), only for what a
    host-signed embed JWT declared as its viewer's identity. None for every
    other caller (unchanged behaviour)."""
    result = await db.execute(
        select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == dataset_id)
    )
    ds = result.scalar_one_or_none()
    # check_org is shared by every router and raises a plain 404; re-raised
    # coded here, like require_dataset_read below, so the widget endpoint keeps
    # its contract without a shared helper having to know about widgets.
    try:
        check_org(ds, current_user, "Dataset not found")
    except HTTPException as e:
        raise widget_error(e.status_code, "not_found", str(e.detail))

    # WHO MAY READ THIS DATA. `check_org` above only proves the dataset belongs
    # to the caller's tenant; until this line any member could shape a request
    # against any dataset id in their org. `via_report_id` is the dashboard the
    # widget belongs to -- a viewer who can open that report can read what it
    # draws on, which is what makes a shared dashboard (and a share link
    # resolved as its same-org viewer) work without opening the whole shelf.
    # require_dataset_read is shared by every router and raises a plain
    # HTTPException; re-raised here with a code so the contract holds at THIS
    # endpoint without a shared dependency having to know about widgets.
    try:
        await require_dataset_read(
            db, current_user, dataset_id,
            report_id=via_report_id if via_report_id is not None else req.report_id)
    except CodedHTTPException:
        raise
    except HTTPException as e:
        raise widget_error(e.status_code,
                           "not_found" if e.status_code == 404 else "forbidden",
                           str(e.detail))

    # Task E2: every widget-data resolution is one "query" against the org's
    # daily quota -- checked here so both the live widget path and the export
    # endpoint (which resolves through this same function) are covered by a
    # single enforcement point, before any real work happens.
    await quotas.enforce_query_quota(db, current_user.org_id)

    # Constitution rule 3: a year, a coordinate or an identifier is never
    # summed. Refused HERE, the one path every surface resolves through --
    # builder, share link, embed, export, API -- so a widget saved before the
    # builder warned, or built by hand against the API, cannot slip past. The
    # refusal names the fix; marking the column a measure is the override.
    veto = config_refusal(req.config or {}, ds.column_meta,
                          sums_by_default=sums_measure_by_default(req.widget_type or "bar"))
    if veto:
        raise widget_error(422, "semantic_veto", veto["message"])

    req = await _apply_report_parameters(req, db, current_user)

    calc_cols = list(req.calculated_columns or []) + list(ds.calculated_columns or [])
    measure_defs = list(ds.measures or [])

    if ds.mode == "directquery":
        if calc_cols:
            raise widget_error(400, "unsupported", "Calculated columns are not yet supported for DirectQuery datasets")
        if _config_uses_measure(req.config, measure_defs):
            raise widget_error(400, "unsupported", "Measures are not yet supported for DirectQuery datasets")
        if ds.default_filter_expr:
            raise widget_error(400, "unsupported", "Report-level filter expressions are not yet supported for DirectQuery datasets")

        req = _direct_query_relative_dates(req)
        if (req.config or {}).get("animate_by"):
            raise widget_error(400, "unsupported",
                               "Animation needs an import dataset for now; on a live (DirectQuery) "
                               "source, filter the chart by one period instead")
        if (req.config or {}).get("lattice_rows") or (req.config or {}).get("lattice_columns"):
            raise widget_error(400, "unsupported",
                               "Lattice rows/columns need an import dataset for now; on a live "
                               "(DirectQuery) source, use a small-multiples widget or a filter per chart")

        source = await db.get(DataSource, ds.data_source_id)
        # Re-check org on the DataSource itself, not just the Dataset -- data_source_id
        # is a plain FK, so without this a DirectQuery dataset could become a lateral
        # path to another org's connection credentials.
        check_org(source, current_user, "Data source not found")
        source_cfg = dict(source.config or {})
        source_cfg["type"] = source.type

        # Same helper import mode uses -- None for org-admin roles (RLS bypass) or a
        # role with no rule for this dataset (unrestricted within the org).
        rls_filter_expr = await resolve_rls_expr(db, current_user, dataset_id)

        # Column security on DirectQuery FAILS CLOSED: the SQL is built from column
        # names, and silently rewriting a query is worse than refusing it. A widget
        # referencing a denied column gets a 403 naming nothing about the data.
        denied = sorted(set(await resolve_denied_columns(db, current_user, dataset_id) or [])
                        | set(redact_columns or []))
        if denied:
            # Every string ANYWHERE in the config, not just top-level values:
            # `measures: [...]`, `roles: {...}` and filter entries name columns
            # one or more levels down, and the SQL is built from them. Walking
            # the whole tree rather than a list of known keys means a new
            # nested field is covered the day it ships. The cost is that a
            # title equal to a denied column's name is refused too -- the
            # fail-closed side, as above.
            referenced: set[str] = set()
            stack: list = [req.config]
            while stack:
                node = stack.pop()
                if isinstance(node, str):
                    referenced.add(node)
                elif isinstance(node, dict):
                    stack.extend(node.values())
                elif isinstance(node, (list, tuple)):
                    stack.extend(node)
            if referenced & set(denied):
                raise widget_error(403, "forbidden_column", "This widget references a column your role cannot access")

        try:
            # to_thread keeps the sync SQLAlchemy round-trip off the event loop --
            # one slow customer database must not stall every other request on
            # this worker. Only plain data crosses the thread boundary (dicts,
            # strings, ints pre-read from ORM rows above); never pass `db` or a
            # lazy ORM attribute into the thread.
            async with _work_gate():
                return await asyncio.to_thread(
                    run_direct_query,
                    source_cfg, ds, req.config, widget_type=req.widget_type, rls_filter_expr=rls_filter_expr,
                    cache_ttl_seconds=source.cache_ttl_seconds, cache_epoch=source.cache_epoch,
                    org_id=current_user.org_id, drop_columns=denied or None,
                )
        except DirectQueryUnsupported as e:
            raise widget_error(400, "unsupported", str(e))
        except SourceUnavailable:
            # 502, not 500: this application is fine and the source it was
            # asked to query is not. A 500 sends the reader to our logs for
            # somebody else's outage. The source is NAMED so they know where
            # to look; the driver's text is not repeated, because a connection
            # error embeds the DSN and a DSN embeds the password.
            raise widget_error(
                502, "source_unavailable",
                f"Could not reach the data source '{source.name}'. It may be "
                f"down or unreachable from this server; the dashboard will work "
                f"again once it responds.")

    if not ds.filename:
        raise widget_error(404, "not_found", "Dataset not found")

    if req.widget_type == "model_score" and (req.config or {}).get("prediction_model_id"):
        req = await _clear_scoring_model(req, db, current_user, dataset_id)

    rls_filter_expr = await resolve_rls_expr(db, current_user, dataset_id)
    # Sensitivity redaction (Phase 7.3) rides the column-security path: a
    # redacted column ceases to exist for this read exactly like a denied one.
    denied = sorted(set(await resolve_denied_columns(db, current_user, dataset_id) or [])
                    | set(redact_columns or []))
    steps = prep_steps_of(ds)
    aux = await resolve_join_frames(db, current_user, steps) if steps else {}

    author_filter_expr, calc_cols, measure_defs = await expand_author_expressions(
        db, current_user, ds.default_filter_expr, calc_cols, measure_defs,
        email_override=email_override, org_id_override=org_id_override,
    )

    try:
        # The whole pandas pipeline (CSV parse, RLS, prep, calc columns, shaping)
        # runs off the event loop: one 1M-row parse must not stall every other
        # request on this worker. Exceptions propagate through to_thread
        # unchanged, so the FileNotFoundError -> 404 mapping below still fires.
        # The result cache inside get_widget_data is lock-guarded with deepcopy
        # isolation, so concurrent worker threads are safe. The semaphore
        # bounds how many pipelines run at once: the GIL serializes the pandas
        # work regardless, so extra parallelism only starves the loop
        # (measured -- see widget_work_max_concurrency in config.py).
        async with _work_gate():
            return await asyncio.to_thread(
                get_widget_data,
                ds.filename, req.config, widget_type=req.widget_type,
                calculated_columns=calc_cols or None, filter_expr=author_filter_expr or None,
                rls_filter_expr=rls_filter_expr, measures=measure_defs or None,
                drop_columns=denied or None, prep_steps=steps or None,
                prep_aux_frames=aux or None,
                org_id=current_user.org_id, dataset_id=ds.id,
                custom_functions=ds.custom_functions,
            )
    except FileNotFoundError:
        raise widget_error(404, "not_found", "Dataset file not found on server — please re-upload the file")
    except ImportRowCapExceeded as e:
        # 413: the request is well-formed, the dataset is simply larger than this
        # deployment will materialise in memory. Same shape as the
        # DirectQueryUnsupported mapping above -- an explicit refusal the user can
        # act on, never a truncated result presented as a complete one.
        raise widget_error(413, "row_cap", str(e))


async def _guard_script_execution(db: AsyncSession, current_user: User,
                                  req: WidgetDataRequest) -> None:
    """Only code an org admin SAVED may run for anyone else.

    reports._guard_script_authoring gates who may write a script tile, but these
    two endpoints take the widget type and config from the caller -- without
    this, any member who can read a dataset could post their own code here and
    run it as the server user, never touching the authoring gate.

    An admin may run unsaved code (the builder previews a draft). Anyone else
    runs a script only when its code is exactly that of a saved script tile in
    their own org, which is what a viewer of an admin-written tile sends. The
    shared, embed, package and review routes resolve saved widgets themselves
    and never come through here."""
    if req.widget_type != "script":
        return
    if current_user.role and current_user.role.is_org_admin:
        return
    code = (req.config or {}).get("code")
    if code:
        from ..models.models import ReportPage, ReportWidget
        saved = (await db.execute(
            select(ReportWidget.config)
            .join(ReportPage, ReportPage.id == ReportWidget.page_id)
            .join(Report, Report.id == ReportPage.report_id)
            .where(Report.org_id == current_user.org_id,
                   ReportWidget.widget_type == "script"))).scalars().all()
        if any(isinstance(c, dict) and c.get("code") == code for c in saved):
            return
    raise widget_error(
        403, "forbidden",
        "A script tile runs code on the server, so only code an organisation "
        "admin has saved can run. Ask an admin to review and save it.")


@router.post("/{dataset_id}/widget-data")
async def query_widget(
    dataset_id: int, req: WidgetDataRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    await _guard_script_execution(db, current_user, req)
    return await _resolve_widget_data(dataset_id, req, db, current_user)


@router.post("/{dataset_id}/widget-data/export")
async def export_widget(
    dataset_id: int, req: WidgetDataRequest, format: str = "csv",
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Download one widget's data as CSV or Excel.

    Resolves through `_resolve_widget_data`, so what downloads is exactly what the
    widget shows -- same filters, same aggregation, same row-level security.
    """
    fmt = (format or "csv").lower()
    if fmt not in _EXPORT_FORMATS:
        raise widget_error(400, "unsupported", f"Unsupported export format: {format}")
    await _guard_script_execution(db, current_user, req)

    ds_check = (await db.execute(select(Dataset).where(Dataset.id == dataset_id))).scalar_one_or_none()
    from .datasets import _dataset_has_security, _exports_disabled, _policy_dataset
    if ds_check is not None and _exports_disabled(
            await _policy_dataset(db, ds_check), fmt, await _dataset_has_security(db, dataset_id)):
        raise widget_error(403, "export_disabled", "Exports are disabled for this dataset")

    from ..services.sensitivity import redacted_columns
    from .shared import download_gate
    report = await db.get(Report, req.report_id) if req.report_id else None
    if report is not None and report.org_id != current_user.org_id:
        report = None
    label = await download_gate(db, current_user, report=report, dataset_id=dataset_id)
    data = await _resolve_widget_data(dataset_id, req, db, current_user,
                                      redact_columns=await redacted_columns(db, dataset_id, label))

    # result_frame is the display-rules engine's own lifter, so it already understands
    # every shaped result the app produces -- table, crosstab, gauge, waterfall and the
    # generic {name, value} rows -- rather than a second interpretation that would drift.
    frame = result_frame(data)
    if frame is None or frame.empty:
        raise widget_error(400, "export_no_data", "This widget has no tabular data to export")

    name = _safe_filename(req.widget_type or "widget")
    def _serialize() -> tuple[io.BytesIO, str]:
        # Serialization of a large frame is CPU-bound (xlsx especially) -- run it
        # on a worker thread like the resolve step above, not on the event loop.
        buf = io.BytesIO()
        if fmt == "csv":
            buf.write(frame.to_csv(index=False).encode("utf-8-sig"))
            m = "text/csv"
        elif fmt == "tsv":
            buf.write(frame.to_csv(index=False, sep="	").encode("utf-8-sig"))
            m = "text/tab-separated-values"
        else:
            frame.to_excel(buf, index=False, sheet_name=(req.widget_type or "data")[:31])
            m = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        buf.seek(0)
        return buf, m

    buffer, media = await asyncio.to_thread(_serialize)

    return StreamingResponse(
        buffer, media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}.{_EXPORT_FORMATS[fmt]}"'},
    )
