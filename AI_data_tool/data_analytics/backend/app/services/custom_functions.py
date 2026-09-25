"""Custom calculated-column functions: named, parameterized expression
templates built entirely from the existing safe vocabulary in
services.widget_data. A custom function never introduces a new execution
primitive -- calling one expands its body into the caller's expression
(parameter names substituted with the caller's argument subtrees) BEFORE
that expression reaches widget_data._validate_expr_safety/_eval_expr, which
then run completely unchanged.

See docs/superpowers/specs/2026-09-08-custom-calc-functions-design.md.

This module is imported lazily (inside functions, not at module load time)
by widget_data.apply_calculated_columns, to avoid a circular import: this
module imports FROM widget_data.
"""
from __future__ import annotations

import ast
import copy
import keyword

import pandas as pd


class CustomFunctionError(ValueError):
    """A custom function definition, or a call to one, is invalid."""


_MAX_EXPANDED_NODES = 2000
"""Generous for any legitimate formula; catches runaway expansion caused by
nested custom-function calls whose bodies reuse a parameter multiple times
(node count grows exponentially with nesting depth in that case)."""


def _builtin_names() -> set[str]:
    """Names already usable in any expression. Building _build_safe_ns only
    touches the frame via `.columns` (see widget_data.py:2670), so an empty
    DataFrame is safe to introspect without a real dataset."""
    from .widget_data import _build_safe_ns
    safe_globals, _ = _build_safe_ns(pd.DataFrame())
    return set(safe_globals.keys())


def validate_custom_function_def(
        name: str, params: list[str], expression: str,
        column_names: set[str], calc_names: set[str], measure_names: set[str],
        other_functions: dict[str, dict]) -> None:
    """Raise CustomFunctionError if this definition could never resolve
    safely or reusably. Mirrors _validate_measure's name-collision checks
    (routers/datasets.py:821-847), extended to cover custom-function names
    on both sides of the collision."""
    from .widget_data import _validate_expr_safety

    builtins_lower = {b.lower() for b in _builtin_names()}

    if not name or not name.isidentifier():
        raise CustomFunctionError(f"'{name}' is not a valid function name")
    if keyword.iskeyword(name):
        raise CustomFunctionError(f"'{name}' is a reserved Python keyword and cannot be used as a function name")
    if name.lower() in builtins_lower:
        raise CustomFunctionError(f"'{name}' is already a built-in function — pick another name")
    if name in column_names or name in calc_names or name in measure_names:
        raise CustomFunctionError(f"'{name}' is already a column or measure on this dataset — pick another name")
    if name in other_functions:
        raise CustomFunctionError(f"'{name}' is already a custom function on this dataset — edit it instead")

    seen: set[str] = set()
    for p in params:
        if not p or not p.isidentifier():
            raise CustomFunctionError(f"'{p}' is not a valid parameter name")
        if p.startswith('_'):
            raise CustomFunctionError("Parameter names cannot start with '_'")
        if p.lower() in builtins_lower:
            raise CustomFunctionError(f"Parameter '{p}' collides with a built-in function name")
        if p in seen:
            raise CustomFunctionError(f"Parameter '{p}' is declared more than once")
        seen.add(p)

    try:
        _validate_expr_safety(expression)
    except ValueError as e:
        raise CustomFunctionError(str(e)) from e

    builtins_exact = _builtin_names()
    param_set = set(params)
    tree = ast.parse(expression, mode='eval')
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in param_set and node.id not in builtins_exact:
            raise CustomFunctionError(
                f"'{node.id}' is not a parameter of this function and not a built-in function — "
                f"a custom function body can only use its own parameters and built-in functions, "
                f"not real dataset columns or other custom functions")


def _call_argument_map(func_name: str, params: list[str], call: ast.Call) -> dict[str, ast.AST]:
    if call.keywords:
        raise CustomFunctionError(f"'{func_name}' does not accept keyword arguments")
    if len(call.args) != len(params):
        raise CustomFunctionError(f"'{func_name}' takes {len(params)} argument(s), got {len(call.args)}")
    return {p: copy.deepcopy(a) for p, a in zip(params, call.args)}


class _ParamSubstituter(ast.NodeTransformer):
    """Replaces each parameter Name with its mapped argument subtree in one
    pass. Returning the mapped node directly (without calling generic_visit
    on it) is what makes substitution hygienic: a parameter name that
    happens to appear INSIDE an already-substituted argument subtree is not
    visited again and so is never re-substituted."""
    def __init__(self, mapping: dict[str, ast.AST]):
        self.mapping = mapping

    def visit_Name(self, node: ast.Name) -> ast.AST:
        return self.mapping.get(node.id, node)


def _expand_one_call(func_name: str, params: list[str], body_expression: str, call: ast.Call) -> ast.expr:
    mapping = _call_argument_map(func_name, params, call)
    body_tree = ast.parse(body_expression, mode='eval').body
    substituted = _ParamSubstituter(mapping).visit(copy.deepcopy(body_tree))
    return ast.copy_location(substituted, call)


class _FunctionExpander(ast.NodeTransformer):
    def __init__(self, functions: dict[str, dict]):
        self.functions = functions

    def visit_Call(self, node: ast.Call) -> ast.AST:
        # Bottom-up: expand any nested calls (e.g. a custom function passed
        # as another custom function's argument) before this node itself, so
        # a nested call's own substitution is already resolved by the time
        # the outer call is expanded.
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id in self.functions:
            fn = self.functions[node.func.id]
            return _expand_one_call(node.func.id, fn["params"], fn["expression"], node)
        return node


def expand_custom_functions(expression: str, custom_functions: list[dict]) -> str:
    """Rewrite every call to a defined custom function into the caller's
    expression, using only the substituted argument subtrees the caller
    already provided. Returns text, ready for widget_data._eval_expr
    unchanged -- which independently re-runs _validate_expr_safety on
    whatever text it receives, so the expanded result is validated exactly
    like any other expression regardless of what this function produces."""
    if not custom_functions:
        return expression
    functions = {f["name"]: f for f in custom_functions}
    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError:
        # Not parseable as plain Python -- e.g. a backtick-quoted column name
        # (`net revenue`), which _eval_expr handles on its own separately.
        # Since this expression can't contain a Python-syntax call to any
        # custom function either, passing it through unchanged is a safe
        # no-op, not a silent failure.
        return expression
    expanded = _FunctionExpander(functions).visit(tree)
    ast.fix_missing_locations(expanded)
    node_count = sum(1 for _ in ast.walk(expanded))
    if node_count > _MAX_EXPANDED_NODES:
        raise CustomFunctionError("Expression is too complex after expanding custom functions")
    return ast.unparse(expanded)
