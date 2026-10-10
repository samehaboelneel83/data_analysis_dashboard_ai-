"""`and` / `or` / `not` for formulas over columns (2026-10-10).

Python's `and` asks for ONE truth value; on a column pandas refuses ("the truth
value of a Series is ambiguous"), so `IF(region == 'East' and revenue > 50, ...)`
failed in calculated columns AND in measures, although both editors offer
`and`/`or`/`not`. `ElementwiseLogic` rewrites them to `_AND_` / `_OR_` / `_NOT_`
calls that work row by row on columns and keep Python's meaning on single
values. The leading underscore keeps the helpers out of reach of a typed
formula (names starting with "_" are refused by the safety check).
"""
from __future__ import annotations

import ast as _ast

import numpy as np
import pandas as pd


def as_mask(v):
    """A truth value per row: a column becomes True/False (empty = False)."""
    if isinstance(v, pd.Series):
        return v.fillna(False).astype(bool)
    if isinstance(v, np.ndarray):
        return pd.Series(v).fillna(False).astype(bool).to_numpy()
    return v


def _logic_and(*vals):
    """`a and b` row by row when either side is a column (Python's `and` asks
    for ONE truth value and pandas refuses: "the truth value of a Series is
    ambiguous"), and plain Python `and` for single values."""
    if not any(isinstance(v, (pd.Series, np.ndarray)) for v in vals):
        out = vals[0]
        for v in vals[1:]:
            out = out and v
        return out
    out = as_mask(vals[0])
    for v in vals[1:]:
        out = out & as_mask(v)
    return out


def _logic_or(*vals):
    if not any(isinstance(v, (pd.Series, np.ndarray)) for v in vals):
        out = vals[0]
        for v in vals[1:]:
            out = out or v
        return out
    out = as_mask(vals[0])
    for v in vals[1:]:
        out = out | as_mask(v)
    return out


def _logic_not(v):
    if isinstance(v, (pd.Series, np.ndarray)):
        return ~as_mask(v)
    return not v


class ElementwiseLogic(_ast.NodeTransformer):
    """`a and b` -> _AND_(a, b), `a or b` -> _OR_(a, b), `not a` -> _NOT_(a), so
    IF(region == 'East' and revenue > 50, ...) works on columns."""

    def visit_BoolOp(self, node):  # noqa: N802
        self.generic_visit(node)
        fn = '_AND_' if isinstance(node.op, _ast.And) else '_OR_'
        return _ast.copy_location(_ast.Call(func=_ast.Name(id=fn, ctx=_ast.Load()),
                                            args=list(node.values), keywords=[]), node)

    def visit_UnaryOp(self, node):  # noqa: N802
        self.generic_visit(node)
        if isinstance(node.op, _ast.Not):
            return _ast.copy_location(_ast.Call(func=_ast.Name(id='_NOT_', ctx=_ast.Load()),
                                                args=[node.operand], keywords=[]), node)
        return node


LOGIC_NAMESPACE = {'_AND_': _logic_and, '_OR_': _logic_or, '_NOT_': _logic_not}


def compile_logic(expr: str):
    """`expr` parsed, its and/or/not rewritten, compiled for eval()."""
    tree = ElementwiseLogic().visit(_ast.parse(expr, mode='eval'))
    return compile(_ast.fix_missing_locations(tree), '<expression>', 'eval')
