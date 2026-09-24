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
