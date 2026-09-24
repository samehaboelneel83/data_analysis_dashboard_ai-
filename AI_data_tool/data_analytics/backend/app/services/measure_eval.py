"""Post-aggregation measure evaluation.

A *measure* is a named expression stored on a dataset that evaluates **after** filters
and row-level calculated columns, at the **grouping grain of the requesting widget**.
That is what makes `SUM(sales) / TOTAL(SUM(sales)) * 100` a real percent-of-total which
changes when the visual's dimension crossing changes — unlike a row-level calculated
column, whose `PCT_TOTAL` is fixed at definition time.

Two things distinguish this namespace from `widget_data._build_safe_ns`:

1. Aggregation functions are **group-aware**. `SUM(sales)` returns one value per group
   (a Series indexed by the grouping columns), not a scalar broadcast over every row.
2. `TOTAL(expr)` escapes the grouping grain and evaluates `expr` over the whole filter
   context, yielding a scalar that broadcasts back across the groups.
3. `SCOPE(default, "level", expr, ...)` picks a different expression per grain --
   the product rows, the region subtotal and the grand total of one crosstab can
   each show what suits them (DAX's ISINSCOPE pattern). `ISINSCOPE("col")` is the
   boolean form.
4. `BYGROUP(expr, col, ...)` evaluates `expr` grouped by the NAMED columns instead of
   the widget's grain, then broadcasts each value back to the outer groups — SAS's
   per-aggregation ByGroup context declared inside one expression. So
   `SUM(sales) / BYGROUP(SUM(sales), region)` is each group's share of ITS region,
   re-basing per region whatever the visual groups by.

`TOTAL` and `BYGROUP` cannot be ordinary functions: by the time Python called them, the
`SUM(sales)` inside would already have been evaluated at the outer grain. So both are
handled by rewriting the AST — each subtree is evaluated separately at its own grain and
substituted (a scalar for TOTAL, an outer-grain-aligned Series for BYGROUP) before the
outer expression runs.

Expression safety reuses `widget_data._validate_expr_safety` unchanged: the same AST
allowlist, and the same structural ban on attribute access.
"""
from __future__ import annotations

import ast
import math
import re as _re

import pandas as pd

# Names bound for TOTAL substitution. No leading underscore, so the substituted
# expression still passes _validate_expr_safety if it is ever re-validated.
_TOTAL_PREFIX = "TOTALV"


_BYGROUP_PREFIX = "BYGROUPV"


class _TotalCollector(ast.NodeTransformer):
    """Replace each TOTAL(inner) call with a Name node, recording the inner source."""

    def __init__(self) -> None:
        self.inners: list[str] = []

    def visit_Call(self, node: ast.Call):  # noqa: N802
        if isinstance(node.func, ast.Name) and node.func.id == "TOTAL":
            if len(node.args) != 1:
                raise ValueError("TOTAL() takes exactly one argument")
            inner = node.args[0]
            self.inners.append(ast.unparse(inner))
            placeholder = ast.Name(id=f"{_TOTAL_PREFIX}{len(self.inners) - 1}", ctx=ast.Load())
            return ast.copy_location(placeholder, node)
        self.generic_visit(node)
        return node


class _ByGroupCollector(ast.NodeTransformer):
    """Replace each BYGROUP(inner, col, ...) call with a Name node, recording the
    inner source and the columns that override the grouping context.

    BYGROUP is SAS's per-aggregation ByGroup declared INSIDE one expression: the
    outer expression evaluates at the widget's grain, but `BYGROUP(SUM(sales),
    region)` evaluates its inner grouped by `region` regardless of that grain and
    broadcasts the region-level value back to each outer group. So
    `SUM(sales) / BYGROUP(SUM(sales), region)` is "each group's share of its
    region", the ratio re-basing per region no matter what the visual groups by.
    """

    def __init__(self) -> None:
        self.specs: list[tuple[str, list[str]]] = []  # (inner_src, [col, ...])

    def visit_Call(self, node: ast.Call):  # noqa: N802
        if isinstance(node.func, ast.Name) and node.func.id == "BYGROUP":
            if len(node.args) < 2:
                raise ValueError("BYGROUP() takes an expression and at least one grouping column")
            inner = node.args[0]
            cols: list[str] = []
            for arg in node.args[1:]:
                if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                    raise ValueError("BYGROUP() grouping columns must be quoted column names")
                cols.append(arg.value)
            self.specs.append((ast.unparse(inner), cols))
            placeholder = ast.Name(id=f"{_BYGROUP_PREFIX}{len(self.specs) - 1}", ctx=ast.Load())
            return ast.copy_location(placeholder, node)
        self.generic_visit(node)
        return node


_CALC_PREFIX = "CALCV"


class _CalcCollector(ast.NodeTransformer):
    """Replace each CALC(inner, "filter expr") call with a Name node.

    This is the filter-context manipulation the capability audit named as the
    modelling gap -- DAX's CALCULATE, reduced to the one thing people actually
    reach for it for: evaluate an aggregate under a DIFFERENT row filter than the
    visual's, then compare the two.

        SUM(revenue) / CALC(SUM(revenue), `region` == 'EMEA')

    The filter is written in the SAME grammar `apply_filter_expr` and every
    row-security rule already use -- deliberately, and it is the whole design:
    that grammar is already safety-validated, already understood by users who
    have written a filter or an RLS rule, and already translatable to SQL by
    `sql_expr` for DirectQuery pushdown. Inventing a second filter language here
    would have meant a second parser, a second validator and a second thing to
    keep in step with the first.
    """

    def __init__(self) -> None:
        self.specs: list[tuple[str, str]] = []  # (inner_src, filter_expr)

    def visit_Call(self, node: ast.Call):  # noqa: N802
        if isinstance(node.func, ast.Name) and node.func.id == "CALC":
            if len(node.args) != 2:
                raise ValueError(
                    "CALC() takes an expression and a filter, e.g. "
                    "CALC(SUM(sales), \"`region` == 'EMEA'\")")
            inner = node.args[0]
            filt = node.args[1]
            if not (isinstance(filt, ast.Constant) and isinstance(filt.value, str)):
                raise ValueError("CALC()'s second argument must be a quoted filter expression")
            self.specs.append((ast.unparse(inner), filt.value))
            placeholder = ast.Name(id=f"{_CALC_PREFIX}{len(self.specs) - 1}", ctx=ast.Load())
            return ast.copy_location(placeholder, node)
        self.generic_visit(node)
        return node


def _eval_calc(inner: str, filter_expr: str, df: pd.DataFrame, group_cols: list[str]):
    """Evaluate `inner` over `df` narrowed by `filter_expr`, aligned to the outer grain.

    SECURITY: `df` is the caller's ALREADY row-security-filtered frame -- the
    shapers receive it post-`apply_rls_filter`, which the base-frame choke-point
    test pins. So a CALC filter can only ever narrow the slice the caller may
    already see; no expression here widens it back to rows RLS removed. That is
    why this needs no permission model of its own.

    THE ALIGNMENT RULE, which is the whole semantic question:

      * When the filter constrains a GROUPING column, the result is per-group and
        groups the filter excluded are genuinely outside the context -> NaN.
        `CALC(SUM(x), "`region` == 'EMEA'")` grouped BY region gives EMEA its
        value and the others nothing, which is correct: there is no "APAC row
        that is also EMEA".

      * Otherwise the filtered context does not vary by group, so its value is a
        fixed comparison BASE and broadcasts to every group. That is the common
        case and the reason people reach for CALCULATE: `SUM(x) /
        CALC(SUM(x), "`segment` == 'Enterprise'")` grouped by region asks "how
        does each region compare against total Enterprise revenue", and a NaN
        for every region but one would make that unanswerable.

    Reindexing unconditionally (the obvious implementation) silently produces the
    second case as NaN, which looks like missing data rather than a wrong
    alignment -- so the distinction is made explicitly here.
    """
    from .widget_data import apply_filter_expr

    # silent=False: a bad filter must RAISE. The widget path defaults to
    # silent=True, which returns the frame unfiltered -- here that would compute
    # an UNRESTRICTED total and present it as a filtered one, which is worse
    # than an error the author can see and fix.
    narrowed = apply_filter_expr(df, filter_expr, silent=False)

    if not group_cols:
        return _eval(inner, narrowed, [], None)

    outer_index = df.groupby(group_cols, sort=False).size().index

    if narrowed.empty:
        return pd.Series([float("nan")] * len(outer_index), index=outer_index)

    # Does the filter mention any grouping column? Backticked or bare.
    constrains_grain = any(
        (f"`{c}`" in filter_expr) or _re.search(rf"{_re.escape(c)}", filter_expr)
        for c in group_cols)

    if constrains_grain:
        inner_vals = _eval(inner, narrowed, group_cols, None)
        if isinstance(inner_vals, pd.Series):
            return inner_vals.reindex(outer_index)
        return pd.Series([inner_vals] * len(outer_index), index=outer_index)

    # A fixed base: evaluate once over the narrowed frame, broadcast everywhere.
    scalar = _eval(inner, narrowed, [], None)
    return pd.Series([scalar] * len(outer_index), index=outer_index)


def _agg_namespace(df: pd.DataFrame, group_cols: list[str]) -> dict:
    """Build the function namespace. Aggregations close over the grouping keys, so
    `SUM(series)` groups that series by the visual's grain (or reduces to a scalar
    when there is no grain)."""
    if group_cols:
        keys = [df[c] for c in group_cols]

        def _grouped(series: pd.Series, how: str):
            return getattr(series.groupby(keys, sort=False), how)()

        def SUM(s):      return _grouped(s, "sum")        # noqa: E704,N802
        def AVG(s):      return _grouped(s, "mean")       # noqa: E704,N802
        def MEDIAN(s):   return _grouped(s, "median")     # noqa: E704,N802
        def COUNT(s):    return _grouped(s, "count")      # noqa: E704,N802
        def COUNTD(s):   return _grouped(s, "nunique")    # noqa: E704,N802
        def STDEV(s):    return _grouped(s, "std")        # noqa: E704,N802
        def VARIANCE(s): return _grouped(s, "var")        # noqa: E704,N802
    else:
        def SUM(s):      return s.sum()                   # noqa: E704,N802
        def AVG(s):      return s.mean()                  # noqa: E704,N802
        def MEDIAN(s):   return s.median()                # noqa: E704,N802
        def COUNT(s):    return s.count()                 # noqa: E704,N802
        def COUNTD(s):   return s.nunique()               # noqa: E704,N802
        def STDEV(s):    return s.std()                   # noqa: E704,N802
        def VARIANCE(s): return s.var()                   # noqa: E704,N802

    def IF(cond, true_val, false_val):  # noqa: N802
        if isinstance(cond, pd.Series):
            return cond.map(lambda c: true_val if c else false_val)
        return true_val if cond else false_val

    def SWITCH(value, *pairs):  # noqa: N802
        default = pairs[-1] if len(pairs) % 2 else None
        it = list(zip(pairs[0::2], pairs[1::2]))
        for candidate, result in it:
            if value == candidate:
                return result
        return default

    def isnull(v):
        return pd.isna(v)

    return {
        "SUM": SUM, "AVG": AVG, "MEDIAN": MEDIAN, "COUNT": COUNT,
        "COUNTD": COUNTD, "STDEV": STDEV, "VARIANCE": VARIANCE,
        "IF": IF, "SWITCH": SWITCH, "isnull": isnull,
        "abs": abs, "round": round, "min": min, "max": max,
        "int": int, "float": float, "str": str, "len": len, "pow": pow,
        "log": math.log, "sqrt": math.sqrt, "exp": math.exp,
        "floor": math.floor, "ceil": math.ceil,
    }


def _eval(expr: str, df: pd.DataFrame, group_cols: list[str], extra: dict | None = None):
    ns = _agg_namespace(df, group_cols)
    if extra:
        ns.update(extra)
    # Column bindings last so a column can never shadow a function name silently —
    # a collision would already have been rejected by the name-validation on save.
    local_ns = {str(c): df[c] for c in df.columns}
    try:
        return eval(expr, {"__builtins__": {}, **ns}, local_ns)  # noqa: S307
    except ValueError:
        raise
    except NameError as e:
        raise ValueError(f"Unknown column or function in measure expression: {e}") from e
    except Exception as e:
        raise ValueError(f"Measure expression failed to evaluate: {e}") from e


class _ScopeResolver(ast.NodeTransformer):
    """Resolve SCOPE(...) and ISINSCOPE(...) against the grain being evaluated.

    ``SCOPE(default, "region", when_region, "region,product", when_both, "", at_total)``
    picks the branch whose column list is EXACTLY the set of columns this value
    is grouped by -- ``""`` is the grand total -- and falls back to ``default``.
    It is DAX's ISINSCOPE pattern made one function: a measure that shows a
    share at the product level, a growth rate at the region level and a count
    at the total, in one definition that every visual and every subtotal row
    evaluates at its own grain.

    It is resolved in the AST BEFORE anything is evaluated, so the branches not
    taken are never run -- which matters: a branch using BYGROUP() cannot even
    evaluate at the grand total. ``ISINSCOPE("col")`` becomes a constant
    True/False the same way, for use inside IF() (whose branches ARE both
    evaluated; SCOPE is the one to use when a branch cannot run everywhere).
    """

    def __init__(self, group_cols: list[str]) -> None:
        self.grain = frozenset(group_cols)
        self.used = False

    @staticmethod
    def _cols(node) -> frozenset[str]:
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            raise ValueError('SCOPE() levels must be quoted column lists, e.g. "region" or "region,product" '
                             '("" is the grand total)')
        return frozenset(c.strip() for c in node.value.split(",") if c.strip())

    def visit_Call(self, node: ast.Call):  # noqa: N802
        if isinstance(node.func, ast.Name) and node.func.id == "ISINSCOPE":
            if len(node.args) != 1 or not (isinstance(node.args[0], ast.Constant)
                                           and isinstance(node.args[0].value, str)):
                raise ValueError('ISINSCOPE() takes one quoted column name, e.g. ISINSCOPE("product")')
            self.used = True
            return ast.copy_location(ast.Constant(value=node.args[0].value in self.grain), node)
        if isinstance(node.func, ast.Name) and node.func.id == "SCOPE":
            args = node.args
            if len(args) < 3 or len(args) % 2 == 0:
                raise ValueError('SCOPE() takes a default, then pairs of level and expression: '
                                 'SCOPE(default, "region", expr, "", expr_at_total)')
            self.used = True
            chosen = args[0]
            seen: set[frozenset] = set()
            for level, branch in zip(args[1::2], args[2::2]):
                cols = self._cols(level)
                if cols in seen:
                    raise ValueError(f"SCOPE() lists the level \"{', '.join(sorted(cols)) or 'grand total'}\" twice")
                seen.add(cols)
                if cols == self.grain:
                    chosen = branch
            return self.visit(chosen)
        self.generic_visit(node)
        return node


def resolve_scope(expr: str, group_cols: list[str]) -> str:
    """The expression with SCOPE/ISINSCOPE resolved for this grain (unchanged if unused)."""
    if "SCOPE" not in expr:
        return expr
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _CONTEXT_FNS:
            for arg in node.args:
                for sub in ast.walk(arg):
                    if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                            and sub.func.id in ("SCOPE", "ISINSCOPE")):
                        raise ValueError(f"{node.func.id}() cannot contain SCOPE() or ISINSCOPE(): "
                                         f"put the SCOPE outside, choosing between whole expressions")
    resolver = _ScopeResolver(group_cols)
    out = resolver.visit(tree)
    ast.fix_missing_locations(out)
    return ast.unparse(out) if resolver.used else expr


# CALC belongs here too: it is a context function with its own grain, so
# composing it with TOTAL/BYGROUP would need the same nested group-then-
# regroup this engine deliberately does not model.
_CONTEXT_FNS = ("TOTAL", "BYGROUP", "CALC")


def _reject_context_nesting(tree: ast.AST) -> None:
    """No context function (TOTAL/BYGROUP/CALC) may appear inside another's argument.

    Checked on the ORIGINAL AST, before either collector rewrites its calls into
    placeholder Names -- once TOTAL(...) has become TOTALV0 the nesting is
    invisible, so this pre-pass is the one place the rule can be enforced.
    Each has a distinct grain, and composing their grains would need a nested
    group-then-regroup this engine does not model; refused rather than guessed."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _CONTEXT_FNS:
            for arg in node.args:
                for sub in ast.walk(arg):
                    if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                            and sub.func.id in _CONTEXT_FNS):
                        raise ValueError(
                            f"{node.func.id}() cannot contain another TOTAL(), BYGROUP() or CALC()")


def _broadcast_bygroup(inner: str, cols: list[str], df: pd.DataFrame, group_cols: list[str]):
    """Evaluate `inner` grouped by `cols`, then place each value at the outer grain.

    Returns a Series indexed by `group_cols` (so it aligns with the outer
    aggregations), or a scalar when the widget has no grain. Broadcasting maps
    each outer group to its value of `cols` and looks the aggregate up there --
    well-defined when `cols` is constant within each outer group (the coarser-
    or-equal grouping SAS's ByGroup assumes, e.g. region within city). When an
    outer group spans several `cols` values the first is taken, matching how a
    label column resolves under any ambiguous rollup."""
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"BYGROUP column not found in data: {missing[0]}")

    if not group_cols:
        # No outer grain to broadcast to: a per-region value cannot collapse to one
        # KPI number honestly. ByGroup is meaningful only RELATIVE to an outer
        # grouping, so this is refused rather than guessed.
        raise ValueError("BYGROUP() needs the widget to be grouped by a dimension")

    sub = _eval(inner, df, cols, None)  # Series indexed by cols (single or MultiIndex)
    if not isinstance(sub, pd.Series):
        # inner used no aggregation -- it is already a scalar over the frame.
        return sub

    outer_index = df.groupby(group_cols, sort=False).size().index
    # Each outer group's cols value (first occurrence): a frame indexed by group_cols.
    key_map = df.groupby(group_cols, sort=False)[cols].first()
    lookup = key_map.iloc[:, 0] if len(cols) == 1 else key_map.apply(lambda r: tuple(r), axis=1)
    values = [sub.get(k, float("nan")) for k in lookup]
    return pd.Series(values, index=outer_index)


def evaluate_measure(expr: str, df: pd.DataFrame, group_cols: list[str]):
    """Evaluate a measure expression at the given grouping grain.

    Returns a Series indexed by the grouping columns when `group_cols` is non-empty,
    otherwise a scalar. Raises ValueError for unsafe, malformed, or unresolvable
    expressions — never returns a silently wrong value.
    """
    # Imported lazily: widget_data's shapers call into this module, so a module-level
    # import here would be circular. The safety check stays where it is rather than
    # being relocated, since sql_expr also imports it from widget_data.
    from .widget_data import _validate_expr_safety

    _validate_expr_safety(expr)

    group_cols = [c for c in (group_cols or [])]
    missing = [c for c in group_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Grouping column not found in data: {missing[0]}")

    # SCOPE first: it chooses WHICH expression runs at this grain; everything
    # below then evaluates only the chosen one.
    expr = resolve_scope(expr, group_cols)
    tree = ast.parse(expr, mode="eval")
    _reject_context_nesting(tree)
    total_collector = _TotalCollector()
    rewritten = total_collector.visit(tree)
    bygroup_collector = _ByGroupCollector()
    rewritten = bygroup_collector.visit(rewritten)
    calc_collector = _CalcCollector()
    rewritten = calc_collector.visit(rewritten)
    ast.fix_missing_locations(rewritten)

    subs: dict = {}
    # Each TOTAL(inner) becomes a scalar computed with no grouping.
    for i, inner in enumerate(total_collector.inners):
        subs[f"{_TOTAL_PREFIX}{i}"] = _eval(inner, df, [], None)

    # Each BYGROUP(inner, cols...) is evaluated at ITS OWN grain and broadcast back
    # to the outer group index, so it aligns in arithmetic with the group-aware
    # aggregations around it.
    for i, (inner, cols) in enumerate(bygroup_collector.specs):
        subs[f"{_BYGROUP_PREFIX}{i}"] = _broadcast_bygroup(inner, cols, df, group_cols)

    # Each CALC(inner, filter) is evaluated over the frame NARROWED by its own
    # filter, then aligned back onto the outer groups.
    for i, (inner, filter_expr) in enumerate(calc_collector.specs):
        subs[f"{_CALC_PREFIX}{i}"] = _eval_calc(inner, filter_expr, df, group_cols)

    result = _eval(ast.unparse(rewritten), df, group_cols, subs)

    if group_cols and not isinstance(result, pd.Series):
        # A constant expression (or one using only TOTALs) still needs one value per
        # group so downstream shapers can build rows.
        index = df.groupby(group_cols, sort=False).size().index
        return pd.Series([result] * len(index), index=index)
    return result


def resolve_measure(name: str | None, measures: list[dict] | None) -> dict | None:
    """Return the measure definition matching `name`, or None."""
    if not name or not measures:
        return None
    for m in measures:
        if m.get("name") == name:
            return m
    return None


def preview_measure(expr: str, df: pd.DataFrame, group_by: str | None = None, limit: int = 10) -> dict:
    """Evaluate a measure for the preview endpoint. Never raises — reports the error."""
    try:
        group_cols = [group_by] if group_by else []
        result = evaluate_measure(expr, df, group_cols)
    except Exception as e:
        return {"ok": False, "error": str(e), "dtype": None, "sample": []}

    if isinstance(result, pd.Series):
        head = result.head(limit)
        sample = [
            {"group": _jsonable(idx), "value": _jsonable(val)}
            for idx, val in head.items()
        ]
        dtype = str(result.dtype)
    else:
        sample = [{"group": None, "value": _jsonable(result)}]
        dtype = type(result).__name__

    return {"ok": True, "error": None, "dtype": dtype, "sample": sample}


def _jsonable(v):
    if isinstance(v, tuple):
        return " / ".join(str(x) for x in v)
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    if hasattr(v, "item"):
        try:
            v = v.item()
        except Exception:
            return str(v)
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, (int, str, bool)):
        return v
    return str(v)
