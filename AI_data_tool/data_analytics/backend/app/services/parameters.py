"""Typed substitution of report parameters into expressions.

`@name` references are replaced with LITERALS of the parameter's declared type before
any expression reaches the eval sandbox. This is the entire security story: the
sandbox already refuses `@`-resolution (pinned empty resolvers), so an expression
containing `@name` simply fails to evaluate unless it passed through here first --
and here, a number is emitted as a float literal, text as a quoted literal with the
quoting done by repr, and a date as a quoted ISO string. A value that cannot be
coerced to its declared type is rejected, not passed through.
"""
import re

import pandas as pd

_REF = re.compile(r"@([A-Za-z_][A-Za-z0-9_]*)")

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,59}$")


class ParameterError(ValueError):
    pass


def encode_literal(param_type: str, raw) -> str:
    """One value -> one safe literal, or ParameterError."""
    if raw is None:
        raise ParameterError("parameter has no value")
    if param_type in ("number", "expression"):
        # An expression parameter's raw value is the scalar the widget-data path
        # already computed from the source; it encodes as the number it is.
        try:
            return repr(float(raw))
        except (TypeError, ValueError):
            raise ParameterError(f"not a number: {raw!r}")
    if param_type == "date":
        try:
            ts = pd.Timestamp(str(raw))
        except Exception:
            raise ParameterError(f"not a date: {raw!r}")
        if pd.isna(ts):
            raise ParameterError(f"not a date: {raw!r}")
        return repr(ts.date().isoformat())
    # text: repr does the quoting AND the escaping, so a value carrying quotes or
    # backslashes cannot terminate the literal it is embedded in.
    return repr(str(raw)[:500])


def substitute(expr: str, values: dict, definitions: list) -> str:
    """Replace every @name in `expr` using `values` (falling back to each
    definition's default). Unknown names raise: silently leaving `@x` in place would
    push the failure into the sandbox where it surfaces as an unrelated eval error."""
    defs = {d.name: d for d in definitions}

    def _one(m: re.Match) -> str:
        name = m.group(1)
        d = defs.get(name)
        if d is None:
            raise ParameterError(f"unknown parameter @{name}")
        raw = values.get(name, d.default_value)
        return encode_literal(d.param_type, raw)

    return _REF.sub(_one, expr)


async def apply_report_parameters(db, user, report, config: dict | None,
                                  calculated_columns: list | None,
                                  values: dict | None) -> tuple[dict, list]:
    """Substitute a report's parameter values into one widget's config (and any
    request-level calculated columns) before anything is evaluated. Returns
    (config, calculated_columns); raises ParameterError with a sentence.

    Moved here from routers/widget_data.py (which keeps the report lookup, the
    org check and the HTTP error) so every path that computes a widget --
    the live chart, the PDF, the scheduled Excel digest -- applies parameters
    the same way; a service cannot import a router.

    Two surfaces, two treatments:
      * structured filter VALUES ("@name" as a filter's value, or inside its list) --
        replaced with the typed value directly. Filters compare as data, never as
        code, so no literal encoding is involved.
      * calculated-column EXPRESSIONS -- routed through substitute(), which encodes
        each value as a literal of the parameter's declared type. That encoding is the
        entire injection story (see the module docstring).

    An unknown @name in a filter is an error, not a pass-through: a filter comparing a
    column against the literal string "@budget" matches nothing and looks like a data
    bug rather than the config bug it is.
    """
    import asyncio

    from sqlalchemy import select

    from ..core.rls import resolve_denied_columns, resolve_rls_expr
    from ..models.models import Dataset, ReportParameter
    from .measure_eval import evaluate_measure
    from .widget_data import apply_rls_filter, load_file

    config = dict(config or {})
    calculated_columns = list(calculated_columns or [])
    defs = (await db.execute(
        select(ReportParameter).where(ReportParameter.report_id == report.id)
    )).scalars().all()
    if not defs:
        return config, calculated_columns
    by_name = {d.name: d for d in defs}

    # Expression parameters: value computed over the WHOLE source (RLS-scoped, but
    # immune to report/widget filters) at query time, so a benchmark or a
    # self-updating slider range reflects the data rather than a typed constant. The
    # expression rides in default_value; the computed scalar wins over any viewer
    # value. Import datasets only -- a warehouse benchmark would need a SQL aggregate.
    expr_defs = [d for d in defs if d.param_type == "expression"]
    computed: dict[str, float] = {}
    if expr_defs:
        ds = await db.get(Dataset, report.dataset_id) if report.dataset_id else None
        if ds is None:
            raise ParameterError("Expression parameters need the report to have a primary dataset")
        if ds.mode == "directquery":
            raise ParameterError("Expression parameters require an import dataset")
        rls = await resolve_rls_expr(db, user, ds.id)
        # Column security as well: an expression parameter over a denied column
        # would hand this viewer its aggregate as a benchmark value.
        denied = await resolve_denied_columns(db, user, ds.id)

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
            raise ParameterError(f"Expression parameter could not be evaluated: {e}")

    # Computed expression values win over a viewer-supplied value (a benchmark is not
    # something a viewer overrides); everything else takes the viewer value or default.
    effective = {**(values or {}), **computed}

    def typed(name: str):
        d = by_name.get(name)
        if d is None:
            raise ParameterError(f"Unknown report parameter @{name}")
        raw = effective.get(name, d.default_value)
        if raw is None:
            raise ParameterError(f"Parameter @{name} has no value and no default")
        if d.param_type in ("number", "expression"):
            try:
                return float(raw)
            except (TypeError, ValueError):
                raise ParameterError(f"Parameter @{name} expects a number")
        return str(raw)[:500]

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
            raise ParameterError(f"Parameter {rank_cfg['n']} is not a number usable as a rank count")
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
    for c in calculated_columns:
        c = dict(c)
        expr = c.get("expression")
        if isinstance(expr, str) and "@" in expr:
            c["expression"] = substitute(expr, effective, defs)
        calc_cols.append(c)
    return config, calc_cols
