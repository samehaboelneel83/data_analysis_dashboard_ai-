"""A named measure, written as SQL for a DirectQuery source (E04).

Measures are Python-shaped expressions over aggregates -- `SUM(profit) /
SUM(revenue) * 100` -- evaluated by `measure_eval` at the widget's grain over
the rows the reader may see. On a DirectQuery dataset there are no rows here:
the source holds them. This module turns the part of the measure grammar that
SQL can express exactly into one SQL expression, so the database computes the
same number at the same grain, and the totals at no grain, without moving the
rows.

What translates, and how:

| Measure | SQL |
|---|---|
| `SUM(x)` | `COALESCE(SUM(x), 0)` -- pandas sums an all-missing group to 0 |
| `AVG(x)`, `COUNT(x)` | `AVG(x)`, `COUNT(x)` (non-missing values) |
| `COUNTD(x)` | `COUNT(DISTINCT x)` |
| `MEDIAN(x)` | `PERCENTILE_CONT(0.5) ...` on PostgreSQL and Oracle only |
| `a / b` | `(1.0 * a / NULLIF(b, 0))` -- never integer division; a zero denominator is no value, as in `measure_eval` |
| `+ - *`, unary `-` | the same operator |
| `IF(c, a, b)` | `CASE WHEN c THEN a ELSE b END` |
| `== != < <= > >=`, `in [...]`, `and`, `or`, `not` | the SQL comparison or connective |
| `abs(x)`, `round(x, n)` | `ABS`, `ROUND` |
| numbers, strings, `None` | literals (strings with quotes doubled) |

Anything else raises `MeasureNotTranslatable` -- `TOTAL`, `BYGROUP`, `CALC`,
`SCOPE`, `STDEV`, a column outside an aggregate, `%`, `**`. The caller then
fetches the rows and evaluates the measure with `measure_eval` itself, so a
measure is exact or explicitly sampled, never approximated by a different
formula.

Column names are allowlisted against the dataset before they are quoted; the
translator also returns every column it used, so the caller can check them
against column security.
"""
from __future__ import annotations

import ast

AGGREGATES = {"SUM", "AVG", "COUNT", "COUNTD", "MEDIAN"}
_DIALECTS_WITH_MEDIAN = {"postgresql", "oracle"}
_CMP = {ast.Eq: "=", ast.NotEq: "<>", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}


class MeasureNotTranslatable(Exception):
    """This measure cannot be written as one exact SQL expression."""


def _q(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        raise MeasureNotTranslatable("true/false literals")
    if isinstance(value, (int, float)):
        if value != value or value in (float("inf"), float("-inf")):
            raise MeasureNotTranslatable("a non-finite number")
        return repr(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    raise MeasureNotTranslatable(f"a {type(value).__name__} literal")


class _Translator:
    def __init__(self, known_columns: set[str], dialect: str):
        self.known = known_columns
        self.dialect = dialect
        self.columns: set[str] = set()

    def expr(self, node, in_agg: bool) -> str:
        if isinstance(node, ast.Constant):
            return _literal(node.value)
        if isinstance(node, ast.Name):
            if node.id not in self.known:
                raise MeasureNotTranslatable(f"'{node.id}' is not a column of this dataset")
            if not in_agg:
                # A bare column at the group grain is a per-row series in
                # measure_eval, not one value per group: nothing to translate.
                raise MeasureNotTranslatable(f"column '{node.id}' outside an aggregate")
            self.columns.add(node.id)
            return _q(node.id)
        if isinstance(node, ast.BinOp):
            left, right = self.expr(node.left, in_agg), self.expr(node.right, in_agg)
            if isinstance(node.op, ast.Div):
                return f"(1.0 * {left} / NULLIF({right}, 0))"
            op = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}.get(type(node.op))
            if op is None:
                raise MeasureNotTranslatable(f"operator {type(node.op).__name__}")
            return f"({left} {op} {right})"
        if isinstance(node, ast.UnaryOp):
            inner = self.expr(node.operand, in_agg)
            if isinstance(node.op, ast.USub):
                return f"(-{inner})"
            if isinstance(node.op, ast.UAdd):
                return inner
            if isinstance(node.op, ast.Not):
                return f"(NOT {inner})"
            raise MeasureNotTranslatable(f"operator {type(node.op).__name__}")
        if isinstance(node, ast.BoolOp):
            op = " AND " if isinstance(node.op, ast.And) else " OR "
            return "(" + op.join(self.expr(v, in_agg) for v in node.values) + ")"
        if isinstance(node, ast.Compare):
            if len(node.ops) != 1:
                raise MeasureNotTranslatable("a chained comparison")
            op, right = node.ops[0], node.comparators[0]
            left = self.expr(node.left, in_agg)
            if isinstance(op, (ast.In, ast.NotIn)):
                if not isinstance(right, (ast.List, ast.Tuple)) or not right.elts:
                    raise MeasureNotTranslatable("'in' needs a list of values")
                items = ", ".join(self.expr(e, in_agg) for e in right.elts)
                return f"({left} {'NOT IN' if isinstance(op, ast.NotIn) else 'IN'} ({items}))"
            sql_op = _CMP.get(type(op))
            if sql_op is None:
                raise MeasureNotTranslatable(f"comparison {type(op).__name__}")
            return f"({left} {sql_op} {self.expr(right, in_agg)})"
        if isinstance(node, ast.Call):
            return self.call(node, in_agg)
        raise MeasureNotTranslatable(f"{type(node).__name__}")

    def call(self, node: ast.Call, in_agg: bool) -> str:
        if not isinstance(node.func, ast.Name) or node.keywords:
            raise MeasureNotTranslatable("this call")
        name, args = node.func.id, node.args
        if name in AGGREGATES:
            if in_agg:
                raise MeasureNotTranslatable("an aggregate inside an aggregate")
            if len(args) != 1:
                raise MeasureNotTranslatable(f"{name} takes one argument")
            inner = self.expr(args[0], in_agg=True)
            if name == "SUM":
                return f"COALESCE(SUM({inner}), 0)"
            if name == "AVG":
                return f"AVG(1.0 * {inner})"
            if name == "COUNT":
                return f"COUNT({inner})"
            if name == "COUNTD":
                return f"COUNT(DISTINCT {inner})"
            if name == "MEDIAN":
                if self.dialect not in _DIALECTS_WITH_MEDIAN:
                    raise MeasureNotTranslatable(f"MEDIAN on {self.dialect}")
                return f"PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {inner})"
        if name == "IF":
            if len(args) != 3:
                raise MeasureNotTranslatable("IF takes three arguments")
            c, a, b = (self.expr(x, in_agg) for x in args)
            return f"(CASE WHEN {c} THEN {a} ELSE {b} END)"
        if name == "abs" and len(args) == 1:
            return f"ABS({self.expr(args[0], in_agg)})"
        if name == "round" and len(args) in (1, 2):
            digits = self.expr(args[1], in_agg) if len(args) == 2 else "0"
            return f"ROUND({self.expr(args[0], in_agg)}, {digits})"
        raise MeasureNotTranslatable(f"{name}()")


def measure_to_sql(expression: str, known_columns: set[str], dialect: str) -> tuple[str, set[str]]:
    """`(sql, columns_used)` for a measure expression, or MeasureNotTranslatable.

    The expression passes the same safety check measure_eval applies before
    anything else, so an expression that could never be evaluated is refused
    with the same message on either engine."""
    from .widget_data import _validate_expr_safety
    try:
        _validate_expr_safety(expression)
        tree = ast.parse(expression, mode="eval")
    except (ValueError, SyntaxError) as e:
        raise MeasureNotTranslatable(str(e)) from e
    t = _Translator(set(known_columns), dialect)
    sql = t.expr(tree.body, in_agg=False)
    if not t.columns:
        raise MeasureNotTranslatable("no aggregate over a column")
    return sql, t.columns


def referenced_names(expression: str) -> set[str]:
    """Every bare name in a measure expression: columns, and function names.
    Used to refuse a measure over a column the reader is denied."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return set()
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
