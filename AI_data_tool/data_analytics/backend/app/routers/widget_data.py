import asyncio
import io
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from ..core.database import get_db
from ..core.capability import require_dataset_read
from ..core.org_scope import check_org
from ..core.rls import expand_author_expressions, resolve_denied_columns, resolve_rls_expr
from ..dependencies import get_current_user
from ..models.models import DataSource, Dataset, Organization, Report, User
from ..schemas.schemas import WidgetDataRequest
from ..services.display_rules import result_frame
from ..services.parameters import ParameterError, apply_report_parameters
from ..services import quotas
from ..services.semantic_guard import config_refusal
from ..services.multi_measure import measure_list, merge_measure_series

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
from ..services.direct_query import DirectQueryUnsupported, SourceBusy, SourceUnavailable, run_direct_query
from ..services.prep import prep_steps_of, resolve_join_frames
from ..services.widget_data import (ImportRowCapExceeded, sums_measure_by_default,
                                    get_widget_data, infer_date_filter_grains)

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


import logging

_log = logging.getLogger(__name__)

#: Requests whose reader left while they waited for a slot: never run (E14).
#: Per process, like the gate; read by tests and the performance notes.
abandoned_before_start = 0


async def _client_gone(request: Request) -> None:
    """Returns when the connection closes. The body has been read by now, so
    the server's next message is the disconnect. Not `is_disconnected()`:
    that peeks without waiting, and through the app's HTTP middlewares the
    peek never reaches the server, so it never saw a reader leave (checked
    against real uvicorn: 0 of 5 closed connections noticed)."""
    while True:
        message = await request.receive()
        if message.get("type") == "http.disconnect":
            return


async def _run_gated(request: Request | None, fn, *args, **kwargs):
    """Run `fn` on a worker thread once a work slot is free -- unless the
    person who asked has gone by then (E14).

    A dashboard of thirty widgets queues thirty requests behind the gate;
    closing the page, or changing a filter that makes them stale, used to
    leave every one of them to run to the end, holding slots that the next
    page's readers were waiting for. The browser now aborts what it no
    longer needs, and a request whose connection closed while it waited is
    dropped without running. One already running finishes (a pandas
    pipeline cannot be stopped from outside its thread), and its result
    lands in the result cache, so it is not wasted if the reader comes back.

    `request=None` (exports, deliveries, the review pane) always runs: a
    download or a background job has no page to leave.
    """
    global abandoned_before_start
    gate = _work_gate()
    if request is None:
        async with gate:
            return await asyncio.to_thread(fn, *args, **kwargs)
    acquire = asyncio.ensure_future(gate.acquire())
    gone = asyncio.ensure_future(_client_gone(request))

    def _give_back(f: asyncio.Future) -> None:
        # The wait was abandoned; if the slot was granted anyway (in the same
        # instant), it goes straight back -- a slot kept by nobody would
        # shrink the gate for the life of the process.
        if not f.cancelled() and f.exception() is None:
            gate.release()

    try:
        done, _ = await asyncio.wait({acquire, gone}, return_when=asyncio.FIRST_COMPLETED)
    except BaseException:          # this request was cancelled while queued
        acquire.cancel()
        acquire.add_done_callback(_give_back)
        raise
    finally:
        gone.cancel()
    if acquire not in done:
        acquire.cancel()
        acquire.add_done_callback(_give_back)
        abandoned_before_start += 1
        _log.info("widget request dropped before it ran: the reader left (%d in this process)",
                  abandoned_before_start)
        raise widget_error(499, "client_closed", "The page that asked for this data was closed")
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    finally:
        gate.release()


def _config_names(config: dict, name: str) -> bool:
    """Whether any string anywhere in the config is exactly `name`."""
    stack: list = [config]
    while stack:
        node = stack.pop()
        if node == name:
            return True
        if isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, (list, tuple)):
            stack.extend(node)
    return False



class _DirectQueryCalcView:
    """Read-only stand-in for a DirectQuery Dataset whose base query carries
    calculated columns as extra SELECT layers. Everything but `columns` and
    `source_query` is the real dataset's; nothing is written to the ORM row
    (appending to `Dataset.columns` would INSERT a dataset_columns row)."""

    def __init__(self, ds, source_query: str, extra_columns: list, calc_reads: set[str]):
        self._ds = ds
        self.source_query = source_query
        self.columns = list(ds.columns) + extra_columns
        self.calc_reads = calc_reads

    def __getattr__(self, name):
        return getattr(self._ds, name)


def _directquery_calc_view(ds, calc_cols: list, used: list[str], dialect: str | None = None):
    from types import SimpleNamespace
    from ..services.direct_query import _base_query_sql, _quote
    from ..services.sql_expr import ExpressionTranslationError, calc_column_to_sql
    try:
        from ..services.custom_functions import expand_custom_functions
    except ImportError:  # pragma: no cover
        expand_custom_functions = None
    known = {c.name for c in ds.columns}
    by_name = {c.get("name"): c for c in calc_cols if isinstance(c, dict) and c.get("name")}
    sql = _base_query_sql(ds)
    extra: list = []
    reads: set[str] = set()
    # Declaration order, so a column may build on an earlier one. A calc column
    # the widget does not need is still layered when a used one depends on it;
    # a broken unused one is simply left out.
    needed = set(used)
    for name, col in reversed(list(by_name.items())):
        if name in needed:
            needed |= set(re.findall(r"`([^`]+)`", col.get("expression") or "")) & set(by_name)
            needed |= {n for n in by_name if re.search(r"\b" + re.escape(n) + r"\b", col.get("expression") or "")}
    for name, col in by_name.items():
        if name not in needed or name in known:
            continue
        expr = (col.get("expression") or "").strip()
        if expand_custom_functions and getattr(ds, "custom_functions", None):
            expr = expand_custom_functions(expr, ds.custom_functions)
        try:
            col_sql, used_cols = calc_column_to_sql(expr, known, dialect)
        except ExpressionTranslationError as e:
            raise widget_error(400, "unsupported",
                               f"Calculated column '{name}' can't run on this live (DirectQuery) "
                               f"source yet: {e}. Switch the dataset to Import, or simplify the formula.")
        reads |= set(used_cols) - set(by_name)
        sql = f"SELECT calc_src.*, {col_sql} AS {_quote(name)} FROM ({sql}) AS calc_src"
        is_bool = bool(re.search(r"(==|!=|<|>|\bin\b|\band\b|\bor\b|\bnot\b)", expr, re.I)) and not expr.upper().startswith("IF(")
        extra.append(SimpleNamespace(name=name, dtype="boolean" if is_bool else "numeric"))
        known.add(name)
    return _DirectQueryCalcView(ds, sql, extra, reads)

def _bin_kind(ds_like, req: WidgetDataRequest) -> str | None:
    """'date' | 'number' when this widget should be auto-binned, else None."""
    from ..services import auto_bin
    cfg = req.config or {}
    col = next((c for c in (getattr(ds_like, "columns", None) or [])
                if c.name == cfg.get("dimension")), None)
    kind = auto_bin.column_kind(getattr(col, "dtype", None)) if col is not None else None
    if kind is None or not auto_bin.wants_bins(cfg, req.widget_type or "bar", kind):
        return None
    return kind


def _without_bin_keys(req: WidgetDataRequest) -> WidgetDataRequest:
    from ..services import auto_bin
    cfg = req.config or {}
    if not any(k in cfg for k in auto_bin.CONFIG_KEYS) and cfg.get("dimension_granularity") != "auto":
        return req
    return req.model_copy(update={"config": auto_bin.strip_keys(cfg)})


def _bin_stats_filters(cfg: dict, column: str, kind: str):
    from ..services import auto_bin
    window = auto_bin.parse_window(cfg, kind)
    return window, (auto_bin.same_column_bounds(cfg, column, kind)
                    + auto_bin.window_filters(column, kind, window))


#: Keys that make the shaper need the raw rows even with the grain pushed
#: down (direct_query._ROW_LEVEL_KEYS minus the grain itself).
_GRAIN_PUSHDOWN_BLOCKERS = ("having", "suppress_below", "quick_calc", "sort_custom", "dimension_levels",
                            "running", "dimension2", "rows_extra", "columns_extra", "extra_measures",
                            "rank", "dimension_bin", "animate_by", "lattice_rows", "lattice_columns")


def _author_grain_plan(dq_ds, req: WidgetDataRequest, source_cfg: dict, denied: list[str]):
    """A pushdown plan for a date grain the author chose, or None."""
    from ..services import auto_bin
    from ..services import connectors as _connectors
    cfg = req.config or {}
    grain, dim = cfg.get("dimension_granularity"), cfg.get("dimension")
    if grain not in ("hour", "day", "week", "month", "quarter", "year") or not dim or dim in denied:
        return None
    if (req.widget_type or "bar") not in auto_bin.DEFAULT_TARGETS and req.widget_type not in ("table", "kpi"):
        return None
    if any(cfg.get(k) not in (None, "", [], {}) for k in _GRAIN_PUSHDOWN_BLOCKERS):
        return None
    col = next((c for c in (getattr(dq_ds, "columns", None) or []) if c.name == dim), None)
    if col is None or auto_bin.column_kind(getattr(col, "dtype", None)) != "date":
        return None
    plan = auto_bin.BinPlan(column=dim, kind="date", target=0, distinct=0, grain=grain, announce=False)
    if not auto_bin.bucket_sql(_connectors.sql_family_of(source_cfg) or "", '"x"', plan):
        return None
    return plan


class _DirectQueryBinView(_DirectQueryCalcView):
    """The dataset with one more SELECT layer: the bucket each row falls in,
    as the column auto_bin.BIN_COL. The raw column stays, so filters and
    cross-filters on it still read real values."""

    def __init__(self, ds, bucket_expr: str, kind: str):
        from types import SimpleNamespace
        from ..services.auto_bin import BIN_COL
        from ..services.direct_query import _base_query_sql, _quote
        sql = f"SELECT bin_src.*, {bucket_expr} AS {_quote(BIN_COL)} FROM ({_base_query_sql(ds)}) AS bin_src"
        super().__init__(ds, sql, [SimpleNamespace(name=BIN_COL, dtype="datetime" if kind == "date" else "numeric")],
                         set(getattr(ds, "calc_reads", None) or set()))


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

    The substitution itself lives in services.parameters.apply_report_parameters,
    so the PDF and the scheduled Excel digest apply parameters exactly as this
    route does (a service cannot import a router). Kept here: the report lookup,
    the org check, and turning a ParameterError into the widget's 400.
    """
    if not req.report_id:
        return req
    report = await db.get(Report, req.report_id)
    check_org(report, current_user, "Report not found")
    # E09: the parameter definitions of the version this reader is served.
    from ..services.report_release import served_release
    release = await served_release(db, report.id, current_user)
    try:
        config, calc_cols = await apply_report_parameters(
            db, current_user, report, req.config, req.calculated_columns, req.parameters,
            release=release)
    except ParameterError as e:
        raise widget_error(400, "parameter", str(e))
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
    from .prediction_models import champion_of, load_usable_model
    from ..services.model_widgets import register_scoring_model
    try:
        model_id = int(req.config["prediction_model_id"])
        model, pkg = await load_usable_model(db, current_user, dataset_id, model_id)
        # E13: a widget set to follow the champion scores with whichever
        # version of the model's name is champion now, so a promotion or a
        # rollback reaches the dashboard without editing it.
        if req.config.get("model_follows") == "champion":
            champ = await champion_of(db, model.org_id, dataset_id, model.name)
            if champ is not None and champ.id != model.id:
                model, pkg = await load_usable_model(db, current_user, dataset_id, champ.id)
    except (TypeError, ValueError):
        raise widget_error(400, "bad_request", "prediction_model_id must be a number")
    except HTTPException as e:
        raise widget_error(e.status_code, "not_found" if e.status_code == 404 else "forbidden", str(e.detail))
    key = f"{model.id}:{model.created_at.isoformat() if model.created_at else ''}"
    register_scoring_model(key, pkg, model.name)
    return req.model_copy(update={"config": {
        **req.config, "__model__": key,
        "__model_meta__": {"id": model.id, "version": model.version or 1}}})


async def _apply_fiscal_start(req: WidgetDataRequest, db: AsyncSession, org_id: int) -> WidgetDataRequest:
    """E10: a fiscal year or quarter starts in the org's month (or the
    widget's own). Carried on the granularity token from here on, so the
    dimension, a drill filter on a clicked bucket and every engine agree."""
    from ..services.fiscal import with_fiscal_start
    config = req.config or {}
    if with_fiscal_start(config, 1) is config:       # nothing fiscal: no lookup
        return req
    org = await db.get(Organization, org_id)
    return req.model_copy(update={"config": with_fiscal_start(
        config, org.fiscal_year_start_month if org else 1)})


def _infer_date_filter_grains(req: WidgetDataRequest, ds) -> WidgetDataRequest:
    """A clicked date bucket names its grain before any engine sees the filter
    (see services.widget_data.infer_date_filter_grains)."""
    config = req.config or {}
    dates = {c.name for c in (ds.columns or []) if c.dtype == "datetime"}
    filters = config.get("filters")
    inferred = infer_date_filter_grains(filters, dates)
    if inferred is filters or inferred == filters:
        return req
    return req.model_copy(update={"config": {**config, "filters": inferred}})


async def _resolve_widget_data(
    dataset_id: int, req: WidgetDataRequest, db: AsyncSession, current_user: User,
    *, email_override: str | None = None, org_id_override: int | None = None,
    via_report_id: int | None = None,
    redact_columns: list[str] | None = None,
    request: Request | None = None,
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
    # Several measures on one axis: each resolved through THIS function (so
    # security, engines, parameters and caching are the single-measure ones),
    # then merged into the split-series shape the renderers already draw.
    measures = measure_list(req.widget_type, req.config)
    if measures is not None:
        parts = []
        for m in measures:
            one = req.model_copy(update={"config": {**req.config, "measure": m, "extra_measures": []}})
            parts.append(await _resolve_widget_data(
                dataset_id, one, db, current_user, email_override=email_override,
                org_id_override=org_id_override, via_report_id=via_report_id,
                redact_columns=redact_columns, request=request))
        return merge_measure_series(parts, measures)
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
    req = await _apply_fiscal_start(req, db, current_user.org_id)
    req = _infer_date_filter_grains(req, ds)

    calc_cols = list(req.calculated_columns or []) + list(ds.calculated_columns or [])
    measure_defs = list(ds.measures or [])

    # Before the live branch, not after it: a Score widget on a live dataset
    # reached the shaper without its model loaded and read "The saved model
    # could not be loaded" (HR re-test 2026-10-01). Both modes need it.
    if req.widget_type == "model_score" and (req.config or {}).get("prediction_model_id"):
        req = await _clear_scoring_model(req, db, current_user, dataset_id)

    if ds.mode == "directquery":
        # Calculated columns the widget uses are computed BY THE SOURCE: each
        # one becomes a SELECT layer over the dataset's base query (see
        # services/sql_expr.calc_column_to_sql). Ones the widget never names
        # are skipped -- they cannot change its SQL (QA 2026-09-26).
        dq_ds = ds
        used_calc = sorted({c.get("name") for c in calc_cols
                            if isinstance(c, dict) and c.get("name")
                            and (_config_names(req.config or {}, c["name"])
                                 or _config_names(getattr(req, "filters", None) or [], c["name"]))})
        if used_calc:
            # The source's SQL family: a date difference is written per dialect.
            from ..services.connectors import sql_family_of
            calc_source = await db.get(DataSource, ds.data_source_id)
            dialect = sql_family_of({**dict(calc_source.config or {}), "type": calc_source.type}) \
                if calc_source is not None and calc_source.org_id == current_user.org_id else None
            dq_ds = _directquery_calc_view(ds, calc_cols, used_calc, dialect)
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
            if getattr(dq_ds, "calc_reads", None) and set(dq_ds.calc_reads) & set(denied):
                raise widget_error(403, "forbidden_column", "This widget references a column your role cannot access")
            # A measure the widget names reads columns its config never
            # mentions: the SQL is built from the measure's formula, so a
            # formula over a denied column is refused the same way (E04).
            from ..services.measure_sql import referenced_names
            for m in measure_defs:
                if (_config_names(req.config, m.get("name"))
                        and referenced_names(m.get("expression") or "") & set(denied)):
                    raise widget_error(403, "forbidden_column",
                                       "This widget references a column your role cannot access")

        # Auto-bin (services/auto_bin.py): too many values on the axis are
        # grouped BY THE SOURCE -- one small stats query picks the buckets,
        # and the chart's GROUP BY runs over the bucket column, so a donut
        # over 5,670 prices brings back 12 ranges instead of 5,670 rows.
        bin_plan = None
        unbinned = (dq_ds, req)          # the safety net below runs this if bucket SQL fails
        bin_kind = _bin_kind(dq_ds, req) if (req.config or {}).get("dimension") not in denied else None
        if bin_kind:
            from ..services import auto_bin
            from ..services import connectors as _connectors
            from ..services.direct_query import _quote
            import json as _json
            cfg = req.config or {}
            dim = cfg["dimension"]
            window, stat_filters = _bin_stats_filters(cfg, dim, bin_kind)
            # The connection's own settings and the table are in the key, not
            # just ids: a stats entry must never outlive the thing it measured.
            key = _json.dumps(["dq", ds.id, source.id, source.cache_epoch, source_cfg,
                               getattr(dq_ds, "source_table", None), dq_ds.source_query,
                               dim, stat_filters, rls_filter_expr], sort_keys=True, default=str)
            import hashlib as _hashlib
            key = _hashlib.sha256(key.encode()).hexdigest()   # no credential kept as a key
            try:
                stats = await asyncio.to_thread(
                    auto_bin.stats_cached, key,
                    lambda: auto_bin.dq_stats(source_cfg, dq_ds, dim, bin_kind, stat_filters, rls_filter_expr))
            except Exception as e:  # noqa: BLE001 -- binning is an optimisation; the chart still draws
                _log.info("auto-bin stats declined for dataset %s: %s", ds.id, type(e).__name__)
                stats = None
            if stats is not None:
                bin_plan = auto_bin.plan_bins(cfg, req.widget_type or "bar", bin_kind, stats, window)
                expr = (auto_bin.bucket_sql(_connectors.sql_family_of(source_cfg) or "", _quote(dim), bin_plan)
                        if bin_plan.grouped and bin_kind != "text" else None)
                if bin_kind == "text" and bin_plan.top_n:
                    # Top N at the source; "All Other" is one more query after it.
                    measure_names = {m.get("name") for m in measure_defs}
                    new_cfg = (auto_bin.import_config(cfg, bin_plan) if cfg.get("measure") in measure_names
                               else auto_bin.dq_top_config(cfg, bin_plan))
                elif bin_plan.grouped and expr:
                    dq_ds = _DirectQueryBinView(dq_ds, expr, bin_kind)
                    new_cfg = auto_bin.dq_config(cfg, bin_plan)
                else:
                    # Raw values fit, or no bucket SQL for this dialect: the
                    # shaper buckets fetched rows (slower, same answer).
                    new_cfg = auto_bin.import_config(cfg, bin_plan)
                req = req.model_copy(update={"config": new_cfg})
        if bin_plan is None:
            req = _without_bin_keys(req)
            # The AUTHOR's date grain, pushed to the source the same way.
            # Without this a "by month" line on a live table fetched every row
            # (up to the analysis cap) to group them in Python -- 2.2s for 25
            # points on dashboard 213. Now the source returns the 25 rows.
            bin_plan = _author_grain_plan(dq_ds, req, source_cfg, denied)
            if bin_plan is not None:
                from ..services import auto_bin
                from ..services import connectors as _connectors
                from ..services.direct_query import _quote
                expr = auto_bin.bucket_sql(_connectors.sql_family_of(source_cfg) or "",
                                           _quote(bin_plan.column), bin_plan)
                dq_ds = _DirectQueryBinView(dq_ds, expr, "date")
                cfg = dict(req.config or {})
                cfg.pop("dimension_granularity", None)
                req = req.model_copy(update={"config": auto_bin.dq_config(cfg, bin_plan)})

        try:
            # to_thread keeps the sync SQLAlchemy round-trip off the event loop --
            # one slow customer database must not stall every other request on
            # this worker. Only plain data crosses the thread boundary (dicts,
            # strings, ints pre-read from ORM rows above); never pass `db` or a
            # lazy ORM attribute into the thread.
            run = lambda d, r: _run_gated(  # noqa: E731
                request, run_direct_query,
                source_cfg, d, r.config, widget_type=r.widget_type, rls_filter_expr=rls_filter_expr,
                cache_ttl_seconds=source.cache_ttl_seconds, cache_epoch=source.cache_epoch,
                org_id=current_user.org_id, drop_columns=denied or None,
                measures=measure_defs or None,
            )
            if isinstance(dq_ds, _DirectQueryBinView):
                try:
                    result = await run(dq_ds, req)
                except (DirectQueryUnsupported, SourceUnavailable, CodedHTTPException):
                    raise
                except Exception as e:  # noqa: BLE001
                    # The bucket SQL is ours, not the author's: a database that
                    # rejects it (an odd column type, an old server) must cost
                    # speed, never the chart. The shaper groups fetched rows.
                    _log.warning("bucket SQL declined by the source for dataset %s (%s); "
                                 "grouping fetched rows instead", ds.id, type(e).__name__)
                    from ..services import auto_bin
                    base_ds, base_req = unbinned
                    cfg0 = base_req.config or {}
                    if bin_plan.announce:
                        cfg1 = auto_bin.import_config(cfg0, bin_plan)
                    else:
                        cfg1 = auto_bin.strip_keys(cfg0)
                    result = await run(base_ds, base_req.model_copy(update={"config": cfg1}))
                    if not bin_plan.announce:
                        bin_plan = None
            else:
                result = await run(dq_ds, req)
            if (bin_plan is not None and bin_plan.kind == "text" and bin_plan.top_n
                    and (req.config or {}).get("limit") == bin_plan.top_n and isinstance(result, dict)
                    and isinstance(result.get("rows"), list)):
                from ..services import auto_bin
                from ..services import connectors as _connectors
                shown = [r.get("name") for r in result["rows"] if isinstance(r, dict)]
                try:
                    other = await asyncio.to_thread(
                        auto_bin.dq_other, source_cfg, dq_ds, req.config, shown, rls_filter_expr,
                        _connectors.sql_family_of(source_cfg) or "")
                except Exception as e:  # noqa: BLE001 -- the top N still stand on their own
                    _log.info("All Other declined for dataset %s: %s", ds.id, type(e).__name__)
                    other = None
                if other is not None:
                    result["rows"].append({"name": auto_bin.OTHER_LABEL, "value": other[0]})
            if bin_plan is not None:
                from ..services import auto_bin
                result = auto_bin.finish(result, bin_plan)
            return result
        except DirectQueryUnsupported as e:
            raise widget_error(400, "unsupported", str(e))
        except SourceBusy:
            raise widget_error(
                503, "source_busy",
                f"The data source '{source.name}' is reachable but ran short of "
                f"memory answering this. Refresh in a moment.")
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

    # Auto-bin for an uploaded file: the grain comes from one DuckDB scan of
    # the dimension column; the config then carries an ordinary granularity
    # (DuckDB-eligible) or a number-range bucket (pandas).
    bin_plan = None
    bin_kind = _bin_kind(ds, req) if (req.config or {}).get("dimension") not in denied else None
    if bin_kind and not steps:
        from ..services import auto_bin
        import json as _json
        import os as _os
        cfg = req.config or {}
        dim = cfg["dimension"]
        window, stat_filters = _bin_stats_filters(cfg, dim, bin_kind)
        try:
            st = _os.stat(ds.filename)
            stamp = (st.st_mtime, st.st_size)
        except OSError:
            stamp = None
        key = _json.dumps(["import", ds.filename, stamp, dim, stat_filters], sort_keys=True, default=str)
        try:
            stats = await asyncio.to_thread(
                auto_bin.stats_cached, key,
                lambda: auto_bin.import_stats(ds.filename, dim, bin_kind, stat_filters))
        except Exception as e:  # noqa: BLE001 -- binning is an optimisation; the chart still draws
            _log.info("auto-bin stats declined for dataset %s: %s", ds.id, type(e).__name__)
            stats = None
        if stats is not None:
            bin_plan = auto_bin.plan_bins(cfg, req.widget_type or "bar", bin_kind, stats, window)
            req = req.model_copy(update={"config": auto_bin.import_config(cfg, bin_plan)})
    if bin_plan is None:
        req = _without_bin_keys(req)

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
        result = await _run_gated(
            request, get_widget_data,
            ds.filename, req.config, widget_type=req.widget_type,
            calculated_columns=calc_cols or None, filter_expr=author_filter_expr or None,
            rls_filter_expr=rls_filter_expr, measures=measure_defs or None,
            drop_columns=denied or None, prep_steps=steps or None,
            prep_aux_frames=aux or None,
            org_id=current_user.org_id, dataset_id=ds.id,
            custom_functions=ds.custom_functions,
        )
        if bin_plan is not None:
            from ..services import auto_bin
            result = auto_bin.finish(result, bin_plan)
        return result
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
    dataset_id: int, req: WidgetDataRequest, request: Request,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    await _guard_script_execution(db, current_user, req)
    return await _resolve_widget_data(dataset_id, req, db, current_user, request=request)


def _export_frame(data: dict, config: dict):
    """The widget's table as the reader sees it (E08).

    - the row subtotal column is headed "Total", not its internal name;
    - the totals row the widget draws is the file's last row, in the scope
      the widget shows ("shown" or every row), labelled "Total" -- a file
      without the totals the screen showed is a different table;
    - a heatmap, which is a grid too, exports as its grid: it had no table
      the export could find, so it could not be downloaded at all.
    """
    import pandas as pd
    frame = result_frame(data)
    if frame is None and data.get("type") == "heatmap" and data.get("cells"):
        label = config.get("dimension") or (config.get("roles") or {}).get("category") or "category"
        frame = pd.DataFrame([[r, *cells] for r, cells in zip(data.get("rows_axis") or [], data["cells"])],
                             columns=[str(label), *[str(c) for c in data.get("cols_axis") or []]])
    if frame is None:
        return None
    frame = frame.rename(columns={"__total__": "Total"})
    totals = data.get("totals_shown") if config.get("totals_scope") == "shown" \
        and isinstance(data.get("totals_shown"), list) else data.get("totals")
    if isinstance(totals, list) and len(totals) == len(frame.columns):
        row = list(totals)
        if row[0] is None:
            row[0] = "Total"
        frame = pd.concat([frame, pd.DataFrame([row], columns=frame.columns)], ignore_index=True)
    return frame


#: A report's export is a table, not a warehouse: kept small enough to read
#: whole and compare row by row in a request.
_RECONCILE_MAX_BYTES = 10 * 1024 * 1024


def _read_reconcile_file(name: str, raw: bytes):
    """The owner's export as text cells (so the decimals it shows are known),
    whatever its encoding or separator; Excel cells as they are."""
    import os
    import tempfile

    import pandas as pd

    from ..services.csv_dialect import canonicalize_csv
    lower = (name or "").lower()
    if lower.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(io.BytesIO(raw), dtype=object)
    if not lower.endswith((".csv", ".txt", ".tsv")):
        raise widget_error(400, "unsupported", "Reconcile with a CSV or Excel file")
    fd, path = tempfile.mkstemp(suffix=".csv")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        found = canonicalize_csv(path) or {}
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    finally:
        os.unlink(path)
    if found.get("separator") == ";":
        # The European convention: "1.234,5" is one thousand two hundred
        # and thirty-four and a half. The rewrite converts a column only
        # when every cell has that shape; a column mixing "150,25" and
        # "300" is still one of numbers.
        # A column with no comma at all is left alone ("1.5" stays one and a half).
        euro = frame.apply(lambda col: col.str.contains(",", regex=False).any()
                           and col.str.fullmatch(r"-?[\d.\s]*\d,\d+|-?[\d.\s]*\d").all())
        for c in euro[euro].index:
            frame[c] = frame[c].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return frame


@router.post("/{dataset_id}/widget-data/reconcile")
async def reconcile_widget(
    dataset_id: int, widget: str = Form(...), mapping: str | None = Form(None),
    file: UploadFile = File(...), migration_item: int | None = Form(None),
    widget_key: str | None = Form(None), widget_title: str | None = Form(None),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """E17: compare the widget with the old report's export of the same table.

    The widget resolves exactly as it draws for this reader (row and column
    rules, filters, parameters), through `_resolve_widget_data`; its table is
    the one its CSV export would write. See services/reconcile.py for how
    rows pair and when two numbers agree. Returns nothing the reader could
    not already see on the widget, so it needs read, not the export gate.

    With `migration_item`, the result is also kept on that inventory item as
    evidence for its sign-off (services/migration.py): the item must link to
    this report, and only its owner or an admin records against it. Checked
    before the comparison runs, so a refused recording costs nothing.
    """
    import json

    from ..services.audit import record as audit
    from ..services.reconcile import reconcile
    try:
        req = WidgetDataRequest(**json.loads(widget))
        wanted = json.loads(mapping) if mapping else None
    except (ValueError, TypeError) as e:
        raise widget_error(400, "unsupported", f"Could not read the request: {e}")
    raw = await file.read(_RECONCILE_MAX_BYTES + 1)
    if len(raw) > _RECONCILE_MAX_BYTES:
        raise widget_error(400, "unsupported", "The file is over 10 MB; export the table itself, not the data under it")
    item = None
    if migration_item is not None:
        from ..models.models import MigrationItem
        item = await db.get(MigrationItem, migration_item)
        if item is None or item.org_id != current_user.org_id:
            raise widget_error(404, "not_found", "Item not found")
        if not (current_user.role and current_user.role.is_org_admin) and item.owner_id != current_user.id:
            raise widget_error(403, "forbidden", "Only the item's owner or an admin records comparisons on it")
        if req.report_id is None or item.report_id != req.report_id:
            raise widget_error(400, "unsupported", "That inventory item is not linked to this report")
    await _guard_script_execution(db, current_user, req)
    data = await _resolve_widget_data(dataset_id, req, db, current_user)
    actual = _export_frame(data, req.config or {})
    if actual is None or actual.empty:
        raise widget_error(400, "export_no_data", "This widget has no table to reconcile")
    try:
        expected = await asyncio.to_thread(_read_reconcile_file, file.filename or "", raw)
        result = await asyncio.to_thread(reconcile, actual, expected, wanted)
    except CodedHTTPException:
        raise
    except ValueError as e:
        raise widget_error(400, "unsupported", str(e))
    except Exception:                                   # noqa: BLE001 -- an unreadable file
        raise widget_error(400, "unsupported", "Could not read that file as a table")
    c = result["counts"]
    await audit(db, current_user, "widget.reconcile", "report" if req.report_id else "dataset",
                req.report_id or dataset_id,
                f"{file.filename}: {c['match']} match, {c['mismatch']} differ, "
                f"{c['missing_in_widget']} only in the file, {c['missing_in_file']} only in the widget")
    recorded = None
    if item is not None:
        from ..services.migration import record_reconcile
        report = await db.get(Report, req.report_id)
        recorded = record_reconcile(
            item, key=(widget_key or widget_title or "widget").strip() or "widget", title=widget_title,
            counts=c, file=file.filename, user=current_user, revision=report.revision if report else None)
        await audit(db, current_user, "migration.reconcile", "migration_item", item.id,
                    f"{item.name[:120]}: {c['match']} match, {c['mismatch']} differ")
        if recorded.pop("withdrew_sign_off", False):
            await audit(db, current_user, "migration.sign_off_withdrawn", "migration_item", item.id,
                        f"{item.name[:120]}: a later comparison differs")
    await db.commit()
    return {**result, "file": file.filename, "recorded_on": item.id if recorded else None}


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
    frame = _export_frame(data, req.config or {})
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
