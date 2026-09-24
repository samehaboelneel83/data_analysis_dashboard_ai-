"""
Filter-expression -> SQL translation
=====================================
Translates the same row-filter expression grammar used by
`widget_data.apply_filter_expr`/`apply_rls_filter` (AND/OR/NOT, comparisons,
`in`/`not in`, backtick-quoted column names) into a parameterized SQL WHERE
fragment, for DirectQuery pushdown -- most importantly for row-level security
rules, which under DirectQuery must become a SQL predicate rather than a
DataFrame filter (see docs/superpowers/specs/2026-08-15-directquery-design.md,
"Row-Level Security Pushdown").

Reuses `widget_data._validate_expr_safety`'s AST allowlist as the first gate
(the same allowlist that makes an expression safe to eval is the one that
makes it structurally translatable), then applies a second, stricter gate:
this translator only recognizes the subset of that allowlist with a direct
SQL equivalent for a row predicate. Aggregation/date/window function calls
(SUM, YEAR, IF, ...), chained comparisons (`0 < x < 10`), and `**`/`%`/`//`
are all syntactically permitted by `_validate_expr_safety` but have no sound
row-level SQL meaning here, so they raise rather than being silently dropped
or mistranslated.

Fail-closed is the whole point of this module: every raise here is meant to
propagate all the way up to "don't run the query," never to a fallback that
runs the query without the predicate.
"""
import ast
import re

from .widget_data import _validate_expr_safety

_ARITH_OPS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
_COMPARE_OPS = {
    ast.Eq: "=", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=",
}


class ExpressionTranslationError(Exception):
    """Raised when an expression can't be safely/soundly translated to SQL.
    Callers must treat this as fail-closed -- never run the query without
    the predicate, and never fall back to fetching rows and filtering them
    in Python instead."""


def _extract_backticked_columns(expr: str) -> tuple[str, dict[str, str]]:
    """Replace each `` `col name` `` with a unique placeholder identifier so the
    expression is valid Python to parse, tracking placeholder -> real name so
    the real (possibly space-containing) column name can be restored when
    emitting SQL."""
    mapping: dict[str, str] = {}

    def _replace(m: re.Match) -> str:
        key = f"__bt{len(mapping)}"
        mapping[key] = m.group(1)
        return key

    return re.sub(r"`([^`]+)`", _replace, expr), mapping


class _Translator:
    def __init__(self, known_columns: set[str], backtick_map: dict[str, str]):
        self._known_columns = known_columns
        self._backtick_map = backtick_map
        self.params: dict = {}
        self._n = 0
        #: How many `!=`, `not in` and `not` the expression carried. SQL
        #: three-valued logic drops NULL rows under every one of them;
        #: pandas keeps NaN rows. An engine held to pandas parity has to
        #: know, and the only place that knows is here.
        self.negations = 0
        #: Every column the expression read, in the order first seen. The
        #: only place that knows, and what index advice needs from an RLS rule.
        self.used_columns: list[str] = []

    def _param(self, value) -> str:
        key = f"r{self._n}"
        self._n += 1
        self.params[key] = value
        return f":{key}"

    def _column(self, name: str) -> str:
        real_name = self._backtick_map.get(name, name)
        if real_name not in self._known_columns:
            raise ExpressionTranslationError(f"unknown column '{real_name}'")
        if real_name not in self.used_columns:
            self.used_columns.append(real_name)
        return f'"{real_name}"'

    def translate(self, node: ast.AST) -> str:
        if isinstance(node, ast.Expression):
            return self.translate(node.body)
        if isinstance(node, ast.Constant):
            return self._param(node.value)
        if isinstance(node, ast.Name):
            return self._column(node.id)
        if isinstance(node, ast.BoolOp):
            sql_op = "AND" if isinstance(node.op, ast.And) else "OR"
            parts = [f"({self.translate(v)})" for v in node.values]
            return f" {sql_op} ".join(parts)
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                self.negations += 1
                return f"NOT ({self.translate(node.operand)})"
            if isinstance(node.op, ast.USub):
                return f"-({self.translate(node.operand)})"
            if isinstance(node.op, ast.UAdd):
                return self.translate(node.operand)
            raise ExpressionTranslationError(f"unsupported unary operator {type(node.op).__name__}")
        if isinstance(node, ast.BinOp):
            sql_op = _ARITH_OPS.get(type(node.op))
            if sql_op is None:
                raise ExpressionTranslationError(f"unsupported operator {type(node.op).__name__}")
            return f"({self.translate(node.left)} {sql_op} {self.translate(node.right)})"
        if isinstance(node, ast.Compare):
            if len(node.ops) != 1:
                raise ExpressionTranslationError("chained comparisons are not supported")
            op_node, comparator = node.ops[0], node.comparators[0]
            left_sql = self.translate(node.left)
            if isinstance(op_node, (ast.In, ast.NotIn)):
                if not isinstance(comparator, (ast.List, ast.Tuple)):
                    raise ExpressionTranslationError("'in' requires a literal list")
                values_sql = [self._literal_param(el) for el in comparator.elts]
                if isinstance(op_node, ast.NotIn):
                    self.negations += 1
                keyword = "NOT IN" if isinstance(op_node, ast.NotIn) else "IN"
                return f"{left_sql} {keyword} ({', '.join(values_sql)})"
            sql_op = _COMPARE_OPS.get(type(op_node))
            if sql_op is None:
                raise ExpressionTranslationError(f"unsupported comparison {type(op_node).__name__}")
            if isinstance(op_node, ast.NotEq):
                self.negations += 1
            return f"{left_sql} {sql_op} {self.translate(comparator)}"
        raise ExpressionTranslationError(f"unsupported construct {type(node).__name__}")

    def _literal_param(self, node: ast.AST) -> str:
        if not isinstance(node, ast.Constant):
            raise ExpressionTranslationError("'in' list elements must be literals")
        return self._param(node.value)


def translate_filter_expr(expr: str, known_columns: set[str]) -> tuple[str, dict]:
    """Translate a row-filter expression into a SQL WHERE-clause fragment and its
    bound parameters. Raises ExpressionTranslationError if any part can't be
    translated -- see module docstring on fail-closed handling."""
    if not expr or not expr.strip():
        return "", {}

    normalized = re.sub(r"\bAND\b", "and", expr, flags=re.IGNORECASE)
    normalized = re.sub(r"\bOR\b", "or", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bNOT\b", "not", normalized, flags=re.IGNORECASE)

    try:
        _validate_expr_safety(normalized)
    except ValueError as e:
        raise ExpressionTranslationError(str(e)) from e

    processed, backtick_map = _extract_backticked_columns(normalized)
    try:
        tree = ast.parse(processed, mode="eval")
    except SyntaxError as e:
        raise ExpressionTranslationError(f"expression is not valid: {e}") from e

    translator = _Translator(known_columns, backtick_map)
    sql = translator.translate(tree)
    return sql, translator.params


def expression_columns(expr: str, known_columns: set[str]) -> set[str]:
    """The columns an expression reads -- names only, nothing about values.

    Runs the real translator and keeps only what it visited, so this cannot
    disagree with translation about what a column reference is. An unknown
    column is refused the way translation refuses it, never guessed.
    """
    if not expr or not expr.strip():
        return set()
    normalized = re.sub(r"\bAND\b", "and", expr, flags=re.IGNORECASE)
    normalized = re.sub(r"\bOR\b", "or", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bNOT\b", "not", normalized, flags=re.IGNORECASE)
    try:
        _validate_expr_safety(normalized)
    except ValueError as e:
        raise ExpressionTranslationError(str(e)) from e
    processed, backtick_map = _extract_backticked_columns(normalized)
    try:
        tree = ast.parse(processed, mode="eval")
    except SyntaxError as e:
        raise ExpressionTranslationError(f"expression is not valid: {e}") from e
    translator = _Translator(known_columns, backtick_map)
    translator.translate(tree)
    return set(translator.used_columns)


def translate_filter_expr_null_safe(expr: str, known_columns: set[str]) -> tuple[str, dict]:
    """`translate_filter_expr` for an engine that must match pandas row for row.

    pandas keeps a NaN row under `region != 'North'`; SQL drops the NULL row,
    and likewise under `not in` and `not`. This translator has no null
    handling, so an expression with any negation would run correctly on the
    database and DIFFERENTLY from pandas -- the one outcome the DuckDB parity
    contract forbids. Refused here, so the caller falls back to pandas.

    `==`, `in`, `<`/`>` and `and`/`or` produce the same rows in both engines
    with nulls present (a NULL comparison is false in SQL and NaN compares
    false in pandas), so those pass through unchanged.

    DirectQuery keeps the plain translator: it is held to SQL semantics, not
    to pandas.
    """
    if not expr or not expr.strip():
        return "", {}
    normalized = re.sub(r"\bAND\b", "and", expr, flags=re.IGNORECASE)
    normalized = re.sub(r"\bOR\b", "or", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bNOT\b", "not", normalized, flags=re.IGNORECASE)
    try:
        _validate_expr_safety(normalized)
    except ValueError as e:
        raise ExpressionTranslationError(str(e)) from e
    processed, backtick_map = _extract_backticked_columns(normalized)
    try:
        tree = ast.parse(processed, mode="eval")
    except SyntaxError as e:
        raise ExpressionTranslationError(f"expression is not valid: {e}") from e
    translator = _Translator(known_columns, backtick_map)
    sql = translator.translate(tree)
    if translator.negations:
        raise ExpressionTranslationError(
            "negation is not null-safe across engines (!=, not in, not)")
    return sql, translator.params
