# Custom Calculated-Column Functions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a dataset editor define named, parameterized functions (e.g. `PROFIT_MARGIN(revenue, cost)`) usable inside that dataset's calculated-column expressions, without introducing any new code-execution primitive.

**Architecture:** A custom function is a `{name, params, expression}` template stored per-dataset (`Dataset.custom_functions`, a new JSON column, exactly like `calculated_columns`/`measures`). At evaluation time, a call to a defined function is macro-expanded — parameter names substituted with the caller's argument AST subtrees — into the calling expression *before* that expression reaches the existing `_validate_expr_safety`/`_eval_expr` pipeline in `backend/app/services/widget_data.py`, which then run completely unchanged. Expansion is wired into exactly one call site family (`apply_calculated_columns` and its callers) and never into `apply_filter_expr`/`apply_rls_filter`, which is the property that keeps a custom function from ever being usable inside a security rule.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async / Alembic (backend), React / TypeScript / Vitest (frontend). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-08-custom-calc-functions-design.md`

## Global Constraints

- No new AST node types are ever added to `_ALLOWED_AST_NODES` (`widget_data.py:2294-2301`). Expansion only rearranges existing, already-validated subtrees.
- Expansion is called ONLY from `apply_calculated_columns` (`widget_data.py:2742`). It must never be added inside `_eval_expr`, `_build_safe_ns`, `apply_filter_expr`, or `apply_rls_filter`.
- Every save-time validation rule in the spec's "Save-time validation" section must be enforced before a function is persisted — no partial implementation.
- v1 covers calculated columns only. Do not wire expansion into `measure_eval.py`.
- `custom_functions` is NOT added to `DatasetOut` — it gets its own list endpoint, matching how `measures` already works (measures are absent from `DatasetOut` too; fetched via `/datasets/{id}/measures`).
- Write capability gate for create/update/delete: `require_dataset_capability(db, user, dataset_id, "data")` — identical to calculated columns and measures. No new authorization concept.

---

## File structure

**Backend — new:**
- `backend/alembic/versions/0022_dataset_custom_functions.py` — migration.
- `backend/app/services/custom_functions.py` — validation + expansion, the entire new execution-adjacent logic.
- `backend/tests/test_custom_functions.py` — service-level and API-level tests.

**Backend — modified:**
- `backend/app/models/models.py` — add `Dataset.custom_functions` column.
- `backend/app/services/widget_data.py` — `apply_calculated_columns` gains an optional `custom_functions` parameter.
- `backend/app/routers/datasets.py`, `backend/app/routers/reports.py`, `backend/app/services/refresh_scheduler.py` — thread `ds.custom_functions` through existing `apply_calculated_columns` call sites; add the four new custom-functions endpoints in `datasets.py`.
- `backend/app/schemas/schemas.py` — `CustomFunctionDef`, `CustomFunctionPreviewRequest`.

**Frontend — new:**
- `frontend/src/components/report/CustomFunctionsPanel.tsx` — list/create/edit/delete/preview UI, one clear responsibility, kept separate from the already-large `CalcColumnsPanel.tsx`.

**Frontend — modified:**
- `frontend/src/services/api.ts` — `CustomFunction` interface, `customFunctionsApi`.
- `frontend/src/components/report/CalcColumnsPanel.tsx` — fetch custom functions, render `CustomFunctionsPanel`, merge a "Custom" category into the `functionsCatalog` passed to `ExpressionBuilder`.

---

### Task 1: Data model + migration

**Files:**
- Modify: `backend/app/models/models.py:19` area (near `calculated_columns`)
- Create: `backend/alembic/versions/0022_dataset_custom_functions.py`
- Test: `backend/tests/test_alembic_migrations.py` (existing file, no new test needed — its parametrized `test_upgrade_head_matches_create_all_tables` and `test_double_upgrade_head_is_idempotent` automatically cover any new revision)

**Interfaces:**
- Produces: `Dataset.custom_functions` — `list[dict]`, each `{"name": str, "params": list[str], "expression": str}`. Default `[]`.

- [ ] **Step 1: Add the column to the model**

In `backend/app/models/models.py`, right after line 19 (`calculated_columns  = Column(JSON, default=list)`):

```python
    calculated_columns  = Column(JSON, default=list)
    # Named, parameterized expression templates usable from calculated-column
    # expressions on this dataset -- see services/custom_functions.py. Each
    # item: {"name": str, "params": list[str], "expression": str}. Never
    # wired into apply_filter_expr/apply_rls_filter -- see that module's
    # docstring for why.
    custom_functions    = Column(JSON, default=list)
```

- [ ] **Step 2: Write the migration**

```python
"""Custom calculated-column functions: `datasets.custom_functions`.

Chained on 0021_schedule_failures.

Revision ID: 0022_dataset_custom_functions
Revises: 0021_schedule_failures
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0022_dataset_custom_functions'
down_revision: Union[str, None] = '0021_schedule_failures'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('datasets') as batch_op:
        batch_op.add_column(sa.Column('custom_functions', sa.JSON(), nullable=True))
    op.execute(sa.text("UPDATE datasets SET custom_functions = '[]' WHERE custom_functions IS NULL"))


def downgrade() -> None:
    with op.batch_alter_table('datasets') as batch_op:
        batch_op.drop_column('custom_functions')
```

Note: `op.batch_alter_table` is used here for consistency with `0020_dataset_ownership.py` (the SQLite-compatibility fix applied earlier this session) even though this column has no foreign key — it costs nothing on Postgres and keeps the pattern uniform across migrations that touch `datasets`.

- [ ] **Step 3: Confirm the migration matches the ORM model**

Run (from `AI_data_tool/data_analytics`, replace `$P` with `pwd -W` on Git Bash / Windows):
```bash
P=$(pwd -W)
MSYS_NO_PATHCONV=1 docker run --rm --network data_analytics_datalytics_net \
  -v "$P/backend:/app" -v "$P/frontend:/frontend" \
  -v "$P/docker-compose.yml:/docker-compose.yml:ro" \
  -v "$P/ARCHITECTURE.md:/ARCHITECTURE.md:ro" -v "$P/ARCHITECTURE.html:/ARCHITECTURE.html:ro" \
  -w /app data_analytics-backend \
  sh -c "python -m pytest -q -p no:warnings tests/test_alembic_migrations.py tests/test_architecture_doc.py 2>/dev/null | tail -20"
```
Expected: all pass. `test_architecture_doc.py`'s "tables" count will NOT change (this is a new column, not a new table) — if it unexpectedly fails, do not touch `ARCHITECTURE.md`/`.html` as a reflex; re-check what actually changed first.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/models.py backend/alembic/versions/0022_dataset_custom_functions.py
git commit -m "feat: add Dataset.custom_functions column and migration"
```

---

### Task 2: Core validation logic

**Files:**
- Create: `backend/app/services/custom_functions.py`
- Test: `backend/tests/test_custom_functions.py`

**Interfaces:**
- Consumes: `widget_data._build_safe_ns(df) -> tuple[dict, dict]`, `widget_data._validate_expr_safety(expr: str) -> None` (raises `ValueError`).
- Produces: `CustomFunctionError(ValueError)`; `validate_custom_function_def(name: str, params: list[str], expression: str, column_names: set[str], calc_names: set[str], measure_names: set[str], other_functions: dict[str, dict]) -> None` (raises `CustomFunctionError`).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_custom_functions.py`:

```python
"""Custom calculated-column functions: validation and expansion.

See docs/superpowers/specs/2026-09-08-custom-calc-functions-design.md.
"""
import pytest

from app.services.custom_functions import CustomFunctionError, validate_custom_function_def


def _validate(name="PROFIT_MARGIN", params=None, expression="(revenue - cost) / revenue",
              column_names=None, calc_names=None, measure_names=None, other_functions=None):
    validate_custom_function_def(
        name, params if params is not None else ["revenue", "cost"], expression,
        column_names or set(), calc_names or set(), measure_names or set(),
        other_functions or {})


class TestValidDefinitionsPass:
    def test_a_well_formed_definition_is_accepted(self):
        _validate()  # must not raise


class TestNameCollisions:
    def test_rejects_a_name_colliding_with_a_builtin(self):
        with pytest.raises(CustomFunctionError, match="built-in"):
            _validate(name="SUM")

    def test_rejects_a_name_colliding_with_a_builtin_case_insensitively(self):
        with pytest.raises(CustomFunctionError, match="built-in"):
            _validate(name="sum")

    def test_rejects_a_name_colliding_with_a_dataset_column(self):
        with pytest.raises(CustomFunctionError, match="column or measure"):
            _validate(column_names={"PROFIT_MARGIN"})

    def test_rejects_a_name_colliding_with_a_calculated_column(self):
        with pytest.raises(CustomFunctionError, match="column or measure"):
            _validate(calc_names={"PROFIT_MARGIN"})

    def test_rejects_a_name_colliding_with_a_measure(self):
        with pytest.raises(CustomFunctionError, match="column or measure"):
            _validate(measure_names={"PROFIT_MARGIN"})

    def test_rejects_a_name_colliding_with_another_custom_function(self):
        with pytest.raises(CustomFunctionError, match="custom function"):
            _validate(other_functions={"PROFIT_MARGIN": {"params": [], "expression": "1"}})


class TestParameterRules:
    def test_rejects_duplicate_parameter_names(self):
        with pytest.raises(CustomFunctionError, match="more than once"):
            _validate(params=["revenue", "revenue"], expression="revenue")

    def test_rejects_a_parameter_starting_with_underscore(self):
        with pytest.raises(CustomFunctionError, match="cannot start with"):
            _validate(params=["_revenue"], expression="_revenue")

    def test_rejects_a_parameter_colliding_with_a_builtin(self):
        with pytest.raises(CustomFunctionError, match="built-in"):
            _validate(params=["SUM"], expression="SUM")

    def test_rejects_a_parameter_that_is_not_a_valid_identifier(self):
        with pytest.raises(CustomFunctionError, match="not a valid parameter"):
            _validate(params=["not valid!"], expression="1")


class TestBodySafety:
    def test_rejects_an_unsafe_body_via_the_existing_ast_whitelist(self):
        # Attribute access is never in _ALLOWED_AST_NODES.
        with pytest.raises(CustomFunctionError):
            _validate(expression="revenue.sum()")

    def test_rejects_a_body_referencing_a_real_dataset_column_by_name(self):
        # 'tax' is neither a declared parameter nor a builtin -- rejected so
        # the function stays reusable and never silently hardcodes a column.
        with pytest.raises(CustomFunctionError, match="'tax'"):
            _validate(params=["revenue"], expression="revenue - tax")

    def test_rejects_a_body_calling_another_custom_function(self):
        with pytest.raises(CustomFunctionError, match="'OTHER_FN'"):
            _validate(params=["revenue"], expression="OTHER_FN(revenue)")

    def test_allows_a_body_that_only_uses_parameters_and_builtins(self):
        _validate(params=["revenue", "cost"], expression="ROUND((revenue - cost) / revenue, 2)")
```

- [ ] **Step 2: Run to verify RED**

```bash
P=$(pwd -W)
MSYS_NO_PATHCONV=1 docker run --rm --network data_analytics_datalytics_net \
  -v "$P/backend:/app" -v "$P/frontend:/frontend" \
  -v "$P/docker-compose.yml:/docker-compose.yml:ro" \
  -v "$P/ARCHITECTURE.md:/ARCHITECTURE.md:ro" -v "$P/ARCHITECTURE.html:/ARCHITECTURE.html:ro" \
  -w /app data_analytics-backend \
  sh -c "python -m pytest -q -p no:warnings tests/test_custom_functions.py 2>/dev/null | tail -20"
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.custom_functions'`.

- [ ] **Step 3: Implement**

Create `backend/app/services/custom_functions.py`:

```python
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

import pandas as pd


class CustomFunctionError(ValueError):
    """A custom function definition, or a call to one, is invalid."""


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
```

- [ ] **Step 4: Run to verify GREEN**

Same command as Step 2. Expected: all tests in `TestValidDefinitionsPass`, `TestNameCollisions`, `TestParameterRules`, `TestBodySafety` pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/custom_functions.py backend/tests/test_custom_functions.py
git commit -m "feat: add custom-function definition validation"
```

---

### Task 3: Expansion mechanism

**Files:**
- Modify: `backend/app/services/custom_functions.py`
- Test: `backend/tests/test_custom_functions.py`

**Interfaces:**
- Consumes: nothing new (pure `ast` manipulation).
- Produces: `expand_custom_functions(expression: str, custom_functions: list[dict]) -> str`. Raises `CustomFunctionError` on arity mismatch or a keyword argument at a call site. Returns `expression` unchanged if `custom_functions` is empty.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_custom_functions.py`:

```python
from app.services.custom_functions import expand_custom_functions

PROFIT_MARGIN = {"name": "PROFIT_MARGIN", "params": ["revenue", "cost"],
                  "expression": "(revenue - cost) / revenue"}


class TestExpansion:
    def test_returns_the_expression_unchanged_when_there_are_no_custom_functions(self):
        assert expand_custom_functions("revenue * 2", []) == "revenue * 2"

    def test_expands_a_call_into_its_body_with_arguments_substituted(self):
        out = expand_custom_functions("PROFIT_MARGIN(rev, cst)", [PROFIT_MARGIN])
        assert out == "(rev - cst) / rev"

    def test_leaves_an_expression_with_no_matching_call_unchanged(self):
        out = expand_custom_functions("revenue * 2", [PROFIT_MARGIN])
        assert out == "revenue * 2"

    def test_swapped_arguments_produce_a_correspondingly_different_expansion(self):
        forward = expand_custom_functions("PROFIT_MARGIN(rev, cst)", [PROFIT_MARGIN])
        swapped = expand_custom_functions("PROFIT_MARGIN(cst, rev)", [PROFIT_MARGIN])
        assert forward == "(rev - cst) / rev"
        assert swapped == "(cst - rev) / cst"

    def test_hygienic_when_an_argument_subtree_contains_a_parameter_name(self):
        # 'cost' must NOT be re-substituted inside the already-injected
        # 'revenue + cost' subtree standing in for the 'revenue' parameter.
        out = expand_custom_functions("PROFIT_MARGIN(revenue + cost, cost)", [PROFIT_MARGIN])
        assert out == "(revenue + cost - cost) / (revenue + cost)"

    def test_rejects_too_few_arguments(self):
        with pytest.raises(CustomFunctionError, match="2 argument"):
            expand_custom_functions("PROFIT_MARGIN(rev)", [PROFIT_MARGIN])

    def test_rejects_too_many_arguments(self):
        with pytest.raises(CustomFunctionError, match="2 argument"):
            expand_custom_functions("PROFIT_MARGIN(rev, cst, extra)", [PROFIT_MARGIN])

    def test_rejects_keyword_arguments(self):
        with pytest.raises(CustomFunctionError, match="keyword"):
            expand_custom_functions("PROFIT_MARGIN(revenue=rev, cost=cst)", [PROFIT_MARGIN])

    def test_expands_nested_calls_to_two_different_custom_functions(self):
        discount = {"name": "DISCOUNT", "params": ["x"], "expression": "x * 0.9"}
        out = expand_custom_functions("PROFIT_MARGIN(rev, DISCOUNT(cst))", [PROFIT_MARGIN, discount])
        assert out == "(rev - cst * 0.9) / rev"
```

- [ ] **Step 2: Run to verify RED**

Same docker command as Task 2, targeting `tests/test_custom_functions.py -k TestExpansion`. Expected: `ImportError: cannot import name 'expand_custom_functions'`.

- [ ] **Step 3: Implement**

Append to `backend/app/services/custom_functions.py`:

```python
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
    tree = ast.parse(expression, mode='eval')
    expanded = _FunctionExpander(functions).visit(tree)
    ast.fix_missing_locations(expanded)
    return ast.unparse(expanded)
```

- [ ] **Step 4: Run to verify GREEN**

Same command as Step 2, dropping `-k`. Expected: all `TestExpansion` tests pass, and Task 2's tests still pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/custom_functions.py backend/tests/test_custom_functions.py
git commit -m "feat: add custom-function call expansion"
```

---

### Task 4: Wire expansion into `apply_calculated_columns` and every call site

**Files:**
- Modify: `backend/app/services/widget_data.py:2742-2755`
- Modify: `backend/app/routers/datasets.py:912, 1042, 1137, 1208, 1257, 2019, 2106`
- Modify: `backend/app/routers/reports.py:1001, 1061`
- Modify: `backend/app/services/refresh_scheduler.py:575`
- Test: `backend/tests/test_custom_functions.py`

**Interfaces:**
- Consumes: `custom_functions.expand_custom_functions`.
- Produces: `apply_calculated_columns(df: pd.DataFrame, calc_cols: list[dict], custom_functions: list[dict] | None = None) -> pd.DataFrame` — same signature as before plus one new, optional, keyword-compatible parameter. Every existing caller and test that doesn't pass it keeps working unchanged.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_custom_functions.py`:

```python
import pandas as pd

from app.services.widget_data import apply_calculated_columns


class TestAppliedThroughCalculatedColumns:
    def test_a_calculated_column_can_call_a_custom_function(self):
        df = pd.DataFrame({"revenue": [100.0, 200.0], "cost": [40.0, 50.0]})
        out = apply_calculated_columns(
            df, [{"name": "margin", "expression": "PROFIT_MARGIN(revenue, cost)"}],
            custom_functions=[PROFIT_MARGIN])
        assert list(out["margin"]) == [0.6, 0.75]

    def test_an_unrecognized_call_with_no_custom_functions_given_drops_the_column_silently(self):
        # Matches apply_calculated_columns' existing swallow-on-error contract
        # (widget_data.py:2753-2754) for any other broken expression.
        df = pd.DataFrame({"revenue": [100.0], "cost": [40.0]})
        out = apply_calculated_columns(
            df, [{"name": "margin", "expression": "PROFIT_MARGIN(revenue, cost)"}])
        assert "margin" not in out.columns
```

- [ ] **Step 2: Run to verify RED**

Same docker command, `-k TestAppliedThroughCalculatedColumns`. Expected: FAIL — `apply_calculated_columns() got an unexpected keyword argument 'custom_functions'`.

- [ ] **Step 3: Implement**

In `backend/app/services/widget_data.py`, replace the function at lines 2742-2755:

```python
def apply_calculated_columns(df: pd.DataFrame, calc_cols: list[dict],
                              custom_functions: list[dict] | None = None) -> pd.DataFrame:
    """Evaluate expression-based calculated columns and append them to the
    dataframe. custom_functions, when given, are macro-expanded into each
    expression before evaluation (services/custom_functions.py).

    This is the ONLY call site where custom-function expansion happens.
    apply_filter_expr/apply_rls_filter never receive custom_functions -- that
    is what keeps a custom function from ever being usable inside a security
    rule (see the design doc's "Editing or deleting a function" and RLS
    sections)."""
    from .custom_functions import expand_custom_functions
    for col in calc_cols:
        name = (col.get('name') or '').strip()
        expr = (col.get('expression') or '').strip()
        if not name or not expr:
            continue
        try:
            if custom_functions:
                expr = expand_custom_functions(expr, custom_functions)
            result = _eval_expr(expr, df)
            df = df.copy()
            df[name] = result
        except Exception:
            pass
    return df
```

Then thread `ds.custom_functions` through every call site that has a `Dataset` object in scope. Each is the same one-line change, `apply_calculated_columns(df, X)` → `apply_calculated_columns(df, X, ds.custom_functions)`:

| File | Line | Before | After |
|---|---|---|---|
| `routers/datasets.py` | 912 | `apply_calculated_columns(df, ds.calculated_columns)` | `apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)` |
| `routers/datasets.py` | 1042 | `apply_calculated_columns(df, ds.calculated_columns)` | `apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)` |
| `routers/datasets.py` | 1137 | `apply_calculated_columns(df, ds.calculated_columns)` | `apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)` |
| `routers/datasets.py` | 1208 | `apply_calculated_columns(df, ds.calculated_columns)` | `apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)` |
| `routers/datasets.py` | 1257 | `apply_calculated_columns(df, ds.calculated_columns)` | `apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)` |
| `routers/datasets.py` | 2019 | `apply_calculated_columns(df, calc_defs)` | `apply_calculated_columns(df, calc_defs, ds.custom_functions)` |
| `routers/datasets.py` | 2106 | `apply_calculated_columns(df, calc_defs)` | `apply_calculated_columns(df, calc_defs, ds.custom_functions)` |
| `routers/reports.py` | 1001 | `apply_calculated_columns(df, ds.calculated_columns)` | `apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)` |
| `routers/reports.py` | 1061 | `apply_calculated_columns(df, ds.calculated_columns)` | `apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)` |
| `services/refresh_scheduler.py` | 575 | `apply_calculated_columns(df, ds.calculated_columns)` | `apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)` |
| `services/widget_data.py` | 2942 | `apply_calculated_columns(df, calculated_columns)` | `apply_calculated_columns(df, calculated_columns, ds.custom_functions)` — confirm the enclosing function (the main `get_widget_data` pipeline) already has a `ds: Dataset` in scope at that point; it resolves the dataset earlier to read `calculated_columns` itself, so `ds.custom_functions` is the identical access pattern one line away |

At each of the 11 sites, re-read 5 lines of surrounding context before editing (line numbers may have drifted slightly from earlier tasks' edits) — search for the exact `apply_calculated_columns(` call text shown in the "Before" column at that file rather than trusting the line number alone, since two different call sites in `datasets.py` share the identical "Before" text (`ds.calculated_columns` appears 5 times) and only differ by surrounding function.

- [ ] **Step 4: Run to verify GREEN**

```bash
P=$(pwd -W)
MSYS_NO_PATHCONV=1 docker run --rm --network data_analytics_datalytics_net \
  -v "$P/backend:/app" -v "$P/frontend:/frontend" \
  -v "$P/docker-compose.yml:/docker-compose.yml:ro" \
  -v "$P/ARCHITECTURE.md:/ARCHITECTURE.md:ro" -v "$P/ARCHITECTURE.html:/ARCHITECTURE.html:ro" \
  -w /app data_analytics-backend \
  sh -c "python -m pytest -q -p no:warnings tests/test_custom_functions.py tests/test_custom_category_expressions.py tests/test_demo_features.py tests/test_text_functions.py tests/test_time_intelligence_periods.py 2>/dev/null | tail -20"
```
Expected: all pass — the last four files exercise `apply_calculated_columns` without the new parameter and must be completely unaffected.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/widget_data.py backend/app/routers/datasets.py backend/app/routers/reports.py backend/app/services/refresh_scheduler.py backend/tests/test_custom_functions.py
git commit -m "feat: wire custom-function expansion into calculated-column evaluation"
```

---

### Task 5: RLS structural-guarantee regression test

**Files:**
- Modify: `backend/tests/test_admin_row_security_rules.py` (the existing home for row-security-rule-save tests — confirmed real fixtures: `_seed_dataset_with_file(db_session, tmp_path, org_id, rows, name=...)`, `two_orgs["a"]["role"].id`, endpoint `POST /api/v1/admin/row-security-rules` with body `{"role_id", "dataset_id", "filter_expr"}`, per `test_create_rule_valid_expression`/`test_create_rule_invalid_expression_returns_400` already in that file)

**Interfaces:**
- Consumes: `two_orgs`, `auth_headers`, `client`, `db_session`, `tmp_path` fixtures (already used throughout this file); `_seed_dataset_with_file` (already defined at the top of this file).

- [ ] **Step 1: Write the test**

Append to `backend/tests/test_admin_row_security_rules.py`:

```python
async def test_an_rls_rule_cannot_call_a_defined_custom_function(client, db_session, two_orgs, auth_headers, tmp_path):
    """Proves the structural guarantee the design relies on: expansion
    (services/custom_functions.py) is wired only into apply_calculated_columns,
    never into apply_filter_expr/apply_rls_filter. So a filter expression
    calling a custom function fails exactly like calling any other
    undefined name -- a 400 at save time -- never a rule that silently means
    something different than what the admin who saved it, and who may no
    longer be able to edit the function, once wrote."""
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"revenue": 100, "cost": 40}], name="Sales",
    )
    ds.custom_functions = [{"name": "PROFIT_MARGIN", "params": ["revenue", "cost"],
                            "expression": "(revenue - cost) / revenue"}]
    await db_session.commit()

    resp = await client.post(
        "/api/v1/admin/row-security-rules",
        json={"role_id": two_orgs["a"]["role"].id, "dataset_id": ds.id,
              "filter_expr": "PROFIT_MARGIN(revenue, cost) > 0"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 400
```

- [ ] **Step 2: Run to verify it passes**

```bash
P=$(pwd -W)
MSYS_NO_PATHCONV=1 docker run --rm --network data_analytics_datalytics_net \
  -v "$P/backend:/app" -v "$P/frontend:/frontend" \
  -v "$P/docker-compose.yml:/docker-compose.yml:ro" \
  -v "$P/ARCHITECTURE.md:/ARCHITECTURE.md:ro" -v "$P/ARCHITECTURE.html:/ARCHITECTURE.html:ro" \
  -w /app data_analytics-backend \
  sh -c "python -m pytest -q -p no:warnings tests/test_admin_row_security_rules.py -k custom_function 2>/dev/null | tail -20"
```
Expected: PASS. It should pass immediately since no production code changed for this task — it is pinning existing (and, after Task 4, still-existing) behavior: `_validate_filter_expr` (`admin.py:184-213`) eagerly evaluates the filter expression via `apply_filter_expr(df, filter_expr, silent=False)`, which never receives `custom_functions`, so `PROFIT_MARGIN` resolves to an ordinary `NameError` there, caught and turned into the 400. If this test instead fails, that is a real finding — it means expansion leaked somewhere it shouldn't have. Stop and investigate why before continuing to Task 6, per the systematic-debugging approach; do not patch around it without understanding the cause.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_admin_row_security_rules.py
git commit -m "test: pin that RLS rules cannot call a custom function"
```

---

### Task 6: Schemas

**Files:**
- Modify: `backend/app/schemas/schemas.py` (near `CalcColumnDef`/`MeasureDef`, lines 31-49)

**Interfaces:**
- Produces: `CustomFunctionDef(BaseModel)` — `{name: str, params: list[str], expression: str}`. `CustomFunctionPreviewRequest(BaseModel)` — `{params: list[str], expression: str, sample_values: dict[str, Any]}`.

- [ ] **Step 1: Add the schemas**

In `backend/app/schemas/schemas.py`, after `MeasureDef` (line 48):

```python
class CustomFunctionDef(BaseModel):
    """A named, parameterized expression template — see
    services/custom_functions.py for the safety model."""
    name: str
    params: list[str] = []
    expression: str


class CustomFunctionPreviewRequest(BaseModel):
    """Test-drives a function definition against literal sample values for
    each parameter, since there is no row context for a function in
    isolation (unlike calc-column preview, which runs against real
    sample rows)."""
    params: list[str] = []
    expression: str
    sample_values: dict[str, Any] = {}
```

Check the top of `schemas.py` for `Any` already being imported from `typing` (it is used elsewhere, e.g. `column_meta: dict = {}`-adjacent fields) — add the import if it's missing.

- [ ] **Step 2: Verify it imports cleanly**

```bash
P=$(pwd -W)
MSYS_NO_PATHCONV=1 docker run --rm --network data_analytics_datalytics_net \
  -v "$P/backend:/app" -v "$P/frontend:/frontend" \
  -v "$P/docker-compose.yml:/docker-compose.yml:ro" \
  -v "$P/ARCHITECTURE.md:/ARCHITECTURE.md:ro" -v "$P/ARCHITECTURE.html:/ARCHITECTURE.html:ro" \
  -w /app data_analytics-backend \
  sh -c "python -c 'from app.schemas.schemas import CustomFunctionDef, CustomFunctionPreviewRequest; print(\"ok\")'"
```
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/schemas.py
git commit -m "feat: add custom-function request/response schemas"
```

---

### Task 7: Backend API endpoints

**Files:**
- Modify: `backend/app/routers/datasets.py` (add after the measures section, i.e. after line 903-ish where `preview_measure_expr` ends — read the file around there first to find the exact insertion point)
- Test: `backend/tests/test_custom_functions.py`

**Interfaces:**
- Consumes: `CustomFunctionDef`, `CustomFunctionPreviewRequest` (Task 6); `validate_custom_function_def`, `CustomFunctionError`, `expand_custom_functions` (Tasks 2-3); `require_dataset_capability`, `check_org` (already imported in `datasets.py`).
- Produces: `GET/PUT/DELETE /datasets/{id}/custom-functions[/{name}]`, `POST /datasets/{id}/custom-functions/preview`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_custom_functions.py` — reuse the `_source`-style fixture pattern from `test_dataflows_api.py` (a numeric dataset is needed here, unlike that file's text-only one):

```python
import pandas as pd
import pytest

from app.models.models import Dataset, DatasetColumn


async def _numeric_dataset(db, org_id, tmp_path, name="Sales"):
    path = tmp_path / f"{name}.csv"
    pd.DataFrame({"revenue": [100.0, 200.0], "cost": [40.0, 50.0]}).to_csv(path, index=False)
    ds = Dataset(name=name, filename=str(path), org_id=org_id, mode="import",
                 row_count=2, col_count=2, custom_functions=[])
    db.add(ds)
    await db.flush()
    for c in ("revenue", "cost"):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="numeric"))
    await db.commit()
    return ds


class TestCustomFunctionsApi:
    @pytest.mark.asyncio
    async def test_create_then_list_it_back(self, client, db_session, two_orgs, auth_headers, _uploads):
        ds = await _numeric_dataset(db_session, two_orgs["a"]["org"].id, _uploads)
        r = await client.put(f"/api/v1/datasets/{ds.id}/custom-functions",
                             json={"name": "PROFIT_MARGIN", "params": ["revenue", "cost"],
                                   "expression": "(revenue - cost) / revenue"},
                             headers=auth_headers["a"])
        assert r.status_code == 200, r.text

        got = await client.get(f"/api/v1/datasets/{ds.id}/custom-functions", headers=auth_headers["a"])
        assert got.status_code == 200
        assert got.json() == [{"name": "PROFIT_MARGIN", "params": ["revenue", "cost"],
                                "expression": "(revenue - cost) / revenue"}]

    @pytest.mark.asyncio
    async def test_an_invalid_definition_is_rejected_with_400(self, client, db_session, two_orgs, auth_headers, _uploads):
        ds = await _numeric_dataset(db_session, two_orgs["a"]["org"].id, _uploads)
        r = await client.put(f"/api/v1/datasets/{ds.id}/custom-functions",
                             json={"name": "SUM", "params": [], "expression": "1"},
                             headers=auth_headers["a"])
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_removes_it(self, client, db_session, two_orgs, auth_headers, _uploads):
        ds = await _numeric_dataset(db_session, two_orgs["a"]["org"].id, _uploads)
        await client.put(f"/api/v1/datasets/{ds.id}/custom-functions",
                         json={"name": "PROFIT_MARGIN", "params": ["revenue", "cost"],
                               "expression": "(revenue - cost) / revenue"},
                         headers=auth_headers["a"])
        r = await client.delete(f"/api/v1/datasets/{ds.id}/custom-functions/PROFIT_MARGIN",
                                headers=auth_headers["a"])
        assert r.status_code == 200
        assert r.json() == []

    @pytest.mark.asyncio
    async def test_preview_evaluates_against_sample_values(self, client, db_session, two_orgs, auth_headers, _uploads):
        ds = await _numeric_dataset(db_session, two_orgs["a"]["org"].id, _uploads)
        r = await client.post(f"/api/v1/datasets/{ds.id}/custom-functions/preview",
                              json={"params": ["revenue", "cost"], "expression": "(revenue - cost) / revenue",
                                    "sample_values": {"revenue": 100, "cost": 40}},
                              headers=auth_headers["a"])
        assert r.status_code == 200
        assert r.json() == {"ok": True, "result": 0.6}

    @pytest.mark.asyncio
    async def test_preview_of_an_unsafe_expression_reports_the_error_not_a_500(self, client, db_session, two_orgs, auth_headers, _uploads):
        ds = await _numeric_dataset(db_session, two_orgs["a"]["org"].id, _uploads)
        r = await client.post(f"/api/v1/datasets/{ds.id}/custom-functions/preview",
                              json={"params": ["revenue"], "expression": "revenue.sum()",
                                    "sample_values": {"revenue": 100}},
                              headers=auth_headers["a"])
        assert r.status_code == 200
        assert r.json()["ok"] is False
```

Reuse this test file's own `_source`/`_uploads`/`two_orgs`/`auth_headers`/`client`/`db_session` fixtures — confirm their exact origin (likely `conftest.py` for the shared ones, and `test_dataflows_api.py`'s own module for `_uploads`/`_source` — copy `_uploads` into this file too since fixtures aren't shared across test modules unless defined in `conftest.py`).

- [ ] **Step 2: Run to verify RED**

Same docker pytest invocation, `-k TestCustomFunctionsApi`. Expected: 404s (routes don't exist yet).

- [ ] **Step 3: Implement**

In `backend/app/routers/datasets.py`, add after the measures section (find `preview_measure_expr`'s closing and insert after it — read that area first):

```python
# ── Custom functions ──────────────────────────────────────────────────────────

@router.get("/{dataset_id}/custom-functions")
async def list_custom_functions(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    return ds.custom_functions or []


@router.put("/{dataset_id}/custom-functions")
async def save_custom_function(dataset_id: int, fn: CustomFunctionDef, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..services.custom_functions import CustomFunctionError, validate_custom_function_def
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_capability(db, current_user, dataset_id, "data")

    result = await db.execute(select(DatasetColumn.name).where(DatasetColumn.dataset_id == ds.id))
    column_names = {r[0] for r in result.all()}
    calc_names = {c.get("name") for c in (ds.calculated_columns or [])}
    measure_names = {m.get("name") for m in (ds.measures or [])}
    existing = {f["name"]: f for f in (ds.custom_functions or []) if f.get("name") != fn.name}

    try:
        validate_custom_function_def(fn.name, fn.params, fn.expression,
                                      column_names, calc_names, measure_names, existing)
    except CustomFunctionError as e:
        raise HTTPException(400, str(e))

    items = [f for f in (ds.custom_functions or []) if f.get("name") != fn.name]
    items.append(fn.model_dump())
    ds.custom_functions = items
    flag_modified(ds, "custom_functions")
    await db.commit()
    return items


@router.delete("/{dataset_id}/custom-functions/{name}")
async def delete_custom_function(dataset_id: int, name: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_capability(db, current_user, dataset_id, "data")
    items = [f for f in (ds.custom_functions or []) if f.get("name") != name]
    ds.custom_functions = items
    flag_modified(ds, "custom_functions")
    await db.commit()
    return items


@router.post("/{dataset_id}/custom-functions/preview")
async def preview_custom_function(dataset_id: int, req: CustomFunctionPreviewRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..services.custom_functions import CustomFunctionError, validate_custom_function_def
    from ..services.widget_data import _eval_expr, _safe
    import pandas as pd

    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")

    try:
        validate_custom_function_def("__preview__", req.params, req.expression, set(), set(), set(), {})
    except CustomFunctionError as e:
        return {"ok": False, "error": str(e)}

    try:
        row = {p: [req.sample_values.get(p)] for p in req.params}
        df = pd.DataFrame(row) if row else pd.DataFrame({"_": [0]})
        result = _eval_expr(req.expression, df)
        value = result.iloc[0] if hasattr(result, "iloc") else result
        return {"ok": True, "result": _safe(value)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
```

Add `CustomFunctionDef, CustomFunctionPreviewRequest` to the existing `from ..schemas.schemas import (...)` block at the top of `datasets.py` (find it and extend the tuple rather than adding a second import line). `_safe` (JSON-safe value coercion) is already imported locally from `..services.widget_data` at several other points in this file (e.g. `datasets.py:1250`, `1555`) — the code above imports it the same way, as a function-local import.

- [ ] **Step 4: Run to verify GREEN**

Same docker invocation as Step 2, dropping `-k`. Expected: all of Task 2, 3, 4, 7's tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/datasets.py backend/tests/test_custom_functions.py
git commit -m "feat: add custom-function CRUD and preview endpoints"
```

---

### Task 8: Full backend regression check

**Files:** none (verification-only task)

- [ ] **Step 1: Run the entire backend suite**

```bash
P=$(pwd -W)
MSYS_NO_PATHCONV=1 docker run --rm --network data_analytics_datalytics_net \
  -v "$P/backend:/app" -v "$P/frontend:/frontend" \
  -v "$P/docker-compose.yml:/docker-compose.yml:ro" \
  -v "$P/ARCHITECTURE.md:/ARCHITECTURE.md:ro" -v "$P/ARCHITECTURE.html:/ARCHITECTURE.html:ro" \
  -w /app data_analytics-backend \
  sh -c "python -m pytest -q -p no:warnings 2>/dev/null | tail -15"
```
Expected: 0 failures. If `test_architecture_doc.py`'s "backend test modules" count fails, update `ARCHITECTURE.md`/`.html`'s module count the same way it was corrected earlier this session (derive the real count via `ls backend/tests/test_*.py | wc -l` and update both documents' stated numbers — do not touch any other claim in those files).

- [ ] **Step 2: Commit only if the architecture-doc counts needed updating**

```bash
git add ARCHITECTURE.md ARCHITECTURE.html
git commit -m "docs: update backend test module count for the new test file"
```
(Skip this step entirely if Step 1 was already green.)

---

### Task 9: Frontend API client

**Files:**
- Modify: `frontend/src/services/api.ts` (near `calcColumnsApi`, lines 94-100 and 695-700)
- Test: none dedicated — covered by Task 10/11's component tests, which mock this module

**Interfaces:**
- Produces: `CustomFunction { name: string; params: string[]; expression: string }`, `customFunctionsApi = { list, save, delete, preview }`.

- [ ] **Step 1: Add the interface and client**

In `frontend/src/services/api.ts`, after the `CalcColumn` interface (line 99):

```typescript
export interface CustomFunction {
  name: string
  params: string[]
  expression: string
}
```

After `calcColumnsApi` (line 700):

```typescript
export const customFunctionsApi = {
  list:    (dsId: number)                => api.get<CustomFunction[]>(`/datasets/${dsId}/custom-functions`).then(r => r.data),
  save:    (dsId: number, fn: CustomFunction) => api.put<CustomFunction[]>(`/datasets/${dsId}/custom-functions`, fn).then(r => r.data),
  delete:  (dsId: number, name: string)  => api.delete<CustomFunction[]>(`/datasets/${dsId}/custom-functions/${encodeURIComponent(name)}`).then(r => r.data),
  preview: (dsId: number, params: string[], expression: string, sampleValues: Record<string, unknown>) =>
    api.post<{ok:boolean; result?: unknown; error?: string}>(
      `/datasets/${dsId}/custom-functions/preview`, { params, expression, sample_values: sampleValues }
    ).then(r => r.data),
}
```

- [ ] **Step 2: Verify the frontend still type-checks**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat: add customFunctionsApi client"
```

---

### Task 10: `CustomFunctionsPanel` component

**Files:**
- Create: `frontend/src/components/report/CustomFunctionsPanel.tsx`
- Test: `frontend/src/components/report/CustomFunctionsPanel.test.tsx`

**Interfaces:**
- Consumes: `customFunctionsApi` (Task 9).
- Produces: `export default function CustomFunctionsPanel({ datasetId, onChanged }: { datasetId: number; onChanged: (fns: CustomFunction[]) => void })`.

- [ ] **Step 1: Write the failing tests**

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import CustomFunctionsPanel from './CustomFunctionsPanel'

vi.mock('../../services/api', () => ({
  customFunctionsApi: { list: vi.fn(), save: vi.fn(), delete: vi.fn(), preview: vi.fn() },
}))

import { customFunctionsApi } from '../../services/api'

const PROFIT_MARGIN = { name: 'PROFIT_MARGIN', params: ['revenue', 'cost'], expression: '(revenue - cost) / revenue' }

describe('CustomFunctionsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(customFunctionsApi.list).mockResolvedValue([])
  })

  it('lists existing functions and notifies the parent on load', async () => {
    vi.mocked(customFunctionsApi.list).mockResolvedValue([PROFIT_MARGIN])
    const onChanged = vi.fn()
    render(<CustomFunctionsPanel datasetId={5} onChanged={onChanged} />)

    expect(await screen.findByText('PROFIT_MARGIN')).toBeInTheDocument()
    expect(onChanged).toHaveBeenCalledWith([PROFIT_MARGIN])
  })

  it('shows an empty state when there are none', async () => {
    render(<CustomFunctionsPanel datasetId={5} onChanged={vi.fn()} />)
    expect(await screen.findByText(/no custom functions/i)).toBeInTheDocument()
  })

  it('creates a new function and shows the validation error inline on failure', async () => {
    vi.mocked(customFunctionsApi.save).mockRejectedValue({ response: { data: { detail: "'SUM' is already a built-in function — pick another name" } } })
    render(<CustomFunctionsPanel datasetId={5} onChanged={vi.fn()} />)

    fireEvent.click(await screen.findByRole('button', { name: /new function/i }))
    fireEvent.change(screen.getByLabelText(/function name/i), { target: { value: 'SUM' } })
    fireEvent.change(screen.getByLabelText(/^expression$/i), { target: { value: '1' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    expect(await screen.findByText(/already a built-in function/)).toBeInTheDocument()
  })

  it('deletes a function', async () => {
    vi.mocked(customFunctionsApi.list).mockResolvedValue([PROFIT_MARGIN])
    vi.mocked(customFunctionsApi.delete).mockResolvedValue([])
    const onChanged = vi.fn()
    render(<CustomFunctionsPanel datasetId={5} onChanged={onChanged} />)

    fireEvent.click(await screen.findByTitle('Delete'))

    await waitFor(() => expect(customFunctionsApi.delete).toHaveBeenCalledWith(5, 'PROFIT_MARGIN'))
    expect(onChanged).toHaveBeenLastCalledWith([])
  })

  it('previews a definition against sample values before saving', async () => {
    vi.mocked(customFunctionsApi.preview).mockResolvedValue({ ok: true, result: 0.6 })
    render(<CustomFunctionsPanel datasetId={5} onChanged={vi.fn()} />)

    fireEvent.click(await screen.findByRole('button', { name: /new function/i }))
    fireEvent.change(screen.getByLabelText(/function name/i), { target: { value: 'PROFIT_MARGIN' } })
    fireEvent.change(screen.getByLabelText(/parameters/i), { target: { value: 'revenue, cost' } })
    fireEvent.change(screen.getByLabelText(/^expression$/i), { target: { value: '(revenue - cost) / revenue' } })
    fireEvent.change(screen.getByLabelText(/sample value for revenue/i), { target: { value: '100' } })
    fireEvent.change(screen.getByLabelText(/sample value for cost/i), { target: { value: '40' } })
    fireEvent.click(screen.getByRole('button', { name: /test/i }))

    expect(await screen.findByText('0.6')).toBeInTheDocument()
    // Sample values are coerced to numbers where parseable before the request
    // goes out -- the real backend evaluates them arithmetically
    // ((revenue - cost) / revenue), and a raw string '100' would fail that
    // arithmetic where a real dataset column never would (pandas coerces a
    // numeric CSV column to a numeric dtype on load; a hand-typed sample
    // value has no such pipeline).
    expect(customFunctionsApi.preview).toHaveBeenCalledWith(5, ['revenue', 'cost'], '(revenue - cost) / revenue', { revenue: 100, cost: 40 })
  })
})
```

- [ ] **Step 2: Run to verify RED**

```bash
cd frontend && npx vitest run src/components/report/CustomFunctionsPanel.test.tsx
```
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```typescript
import { useEffect, useState } from 'react'
import { customFunctionsApi } from '../../services/api'
import type { CustomFunction } from '../../services/api'
import { useConfirm } from '../ui/ConfirmDialog'

/**
 * Management surface for a dataset's custom calculated-column functions --
 * named, parameterized expression templates (services/custom_functions.py
 * on the backend). Kept separate from CalcColumnsPanel, which already
 * merges this panel's list into the expression palette it hands to
 * ExpressionBuilder.
 */
const BLANK = { name: '', params: '', expression: '' }

export default function CustomFunctionsPanel({ datasetId, onChanged }: {
  datasetId: number
  onChanged: (fns: CustomFunction[]) => void
}) {
  const confirm = useConfirm()
  const [functions, setFunctions] = useState<CustomFunction[]>([])
  const [editing, setEditing] = useState<typeof BLANK | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sampleValues, setSampleValues] = useState<Record<string, string>>({})
  const [previewResult, setPreviewResult] = useState<string | null>(null)
  const [testing, setTesting] = useState(false)

  useEffect(() => {
    customFunctionsApi.list(datasetId).then(fns => { setFunctions(fns); onChanged(fns) })
  }, [datasetId])

  const params = (editing?.params ?? '').split(',').map(p => p.trim()).filter(Boolean)

  const save = async () => {
    if (!editing || !editing.name.trim() || !editing.expression.trim()) return
    setError(null)
    try {
      const updated = await customFunctionsApi.save(datasetId,
        { name: editing.name.trim(), params, expression: editing.expression.trim() })
      setFunctions(updated); onChanged(updated); setEditing(null)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Could not save this function')
    }
  }

  const del = async (name: string) => {
    if (!await confirm({
      title: `Delete the custom function "${name}"?`,
      body: 'Any calculated column calling it stops working. This cannot be undone.',
    })) return
    const updated = await customFunctionsApi.delete(datasetId, name)
    setFunctions(updated); onChanged(updated)
  }

  const test = async () => {
    if (!editing) return
    setTesting(true); setPreviewResult(null)
    try {
      // Coerce each sample value to a number where parseable: the backend
      // evaluates them arithmetically, and a real dataset column arriving
      // through pandas is already numeric -- a hand-typed '100' must behave
      // the same way here, or a perfectly valid numeric function fails its
      // own preview.
      const coerced = Object.fromEntries(Object.entries(sampleValues).map(([k, v]) => {
        const n = Number(v)
        return [k, v.trim() !== '' && !Number.isNaN(n) ? n : v]
      }))
      const r = await customFunctionsApi.preview(datasetId, params, editing.expression.trim(), coerced)
      setPreviewResult(r.ok ? String(r.result) : (r.error ?? 'Preview failed'))
    } catch (err: any) {
      setPreviewResult(err?.response?.data?.detail ?? 'Preview failed')
    } finally {
      setTesting(false)
    }
  }

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
        <span style={{ fontSize:10, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em' }}>
          Custom functions
        </span>
        <button className="btn btn-ghost btn-sm" onClick={() => { setEditing({ ...BLANK }); setError(null); setPreviewResult(null); setSampleValues({}) }}
          style={{ fontSize:10, padding:'2px 7px' }}>
          + New function
        </button>
      </div>

      {functions.map(fn => (
        <div key={fn.name} style={{ display:'flex', alignItems:'center', gap:5, padding:'5px 7px',
          background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:5, marginBottom:4 }}>
          <div style={{ flex:1, minWidth:0 }}>
            <div style={{ fontSize:12, fontWeight:600 }}>{fn.name}({fn.params.join(', ')})</div>
            <div style={{ fontSize:10, color:'var(--muted)', fontFamily:'var(--mono)' }}>{fn.expression}</div>
          </div>
          <button title="Delete" onClick={() => del(fn.name)}
            style={{ background:'none', border:'none', cursor:'pointer', color:'var(--muted)', fontSize:14 }}>×</button>
        </div>
      ))}

      {functions.length === 0 && (
        <p style={{ fontSize:11, color:'var(--muted)', textAlign:'center', padding:'8px 0' }}>
          No custom functions yet
        </p>
      )}

      {editing !== null && (
        <div style={{ border:'1px solid var(--border)', borderRadius:7, padding:10, marginTop:8 }}>
          <label htmlFor="cf-name" style={{ display:'block', fontSize:10, color:'var(--muted)', marginBottom:3 }}>Function name</label>
          <input id="cf-name" value={editing.name} onChange={e => setEditing({ ...editing, name: e.target.value })}
            style={{ width:'100%', fontSize:12, marginBottom:6 }} />

          <label htmlFor="cf-params" style={{ display:'block', fontSize:10, color:'var(--muted)', marginBottom:3 }}>Parameters (comma-separated)</label>
          <input id="cf-params" value={editing.params} onChange={e => setEditing({ ...editing, params: e.target.value })}
            placeholder="revenue, cost" style={{ width:'100%', fontSize:12, marginBottom:6 }} />

          <label htmlFor="cf-expr" style={{ display:'block', fontSize:10, color:'var(--muted)', marginBottom:3 }}>Expression</label>
          <textarea id="cf-expr" value={editing.expression} onChange={e => setEditing({ ...editing, expression: e.target.value })}
            style={{ width:'100%', fontSize:12, fontFamily:'var(--mono)', marginBottom:6 }} rows={2} />

          {params.map(p => (
            <div key={p} style={{ marginBottom: 4 }}>
              <label htmlFor={`cf-sample-${p}`} style={{ fontSize:10, color:'var(--muted)' }}>Sample value for {p}</label>
              <input id={`cf-sample-${p}`} value={sampleValues[p] ?? ''}
                onChange={e => setSampleValues({ ...sampleValues, [p]: e.target.value })}
                style={{ width:'100%', fontSize:12 }} />
            </div>
          ))}

          {error && <p role="alert" style={{ fontSize:11, color:'var(--danger)' }}>{error}</p>}
          {previewResult !== null && <p style={{ fontSize:12 }}>{previewResult}</p>}

          <div style={{ display:'flex', gap:6, marginTop:6 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => setEditing(null)} style={{ fontSize:11 }}>Cancel</button>
            <button className="btn btn-ghost btn-sm" onClick={test} disabled={testing || !editing.expression.trim()} style={{ fontSize:11 }}>
              {testing ? 'Testing…' : 'Test'}
            </button>
            <button className="btn btn-primary btn-sm" onClick={save} style={{ fontSize:11, marginInlineStart:'auto' }}>Save</button>
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run to verify GREEN**

Same vitest command as Step 2. Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/CustomFunctionsPanel.tsx frontend/src/components/report/CustomFunctionsPanel.test.tsx
git commit -m "feat: add CustomFunctionsPanel"
```

---

### Task 11: Wire into `CalcColumnsPanel` and the expression palette

**Files:**
- Modify: `frontend/src/components/report/CalcColumnsPanel.tsx`
- Create: `frontend/src/components/report/CalcColumnsPanel.test.tsx` (confirmed via `Glob` that no component-level test file exists today for this component — only the static-source `CalcColumnsPanel.palette.test.ts`, which regex-scans the file's `snippet:` literals directly and needs no changes here since the new custom-function palette items are built at runtime, not as source literals)

**Interfaces:**
- Consumes: `CustomFunctionsPanel` (Task 10), `customFunctionsApi` (Task 9), `ExpressionBuilder`'s existing `functionsCatalog: FuncCat[]` prop (unchanged shape).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/report/CalcColumnsPanel.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders as render, screen } from '../../test/renderWithProviders'
import CalcColumnsPanel from './CalcColumnsPanel'

vi.mock('../../services/api', () => ({
  columnsApi: { duplicate: vi.fn() },
  calcColumnsApi: { list: vi.fn().mockResolvedValue([]), save: vi.fn(), delete: vi.fn(), preview: vi.fn() },
  customFunctionsApi: { list: vi.fn().mockResolvedValue([]), save: vi.fn(), delete: vi.fn(), preview: vi.fn() },
}))

// ExpressionBuilder is a large, independent component -- stubbed here to a
// summary of the one prop this task changes, so this file tests
// CalcColumnsPanel's own responsibility (building functionsCatalog) rather
// than re-testing ExpressionBuilder's internals.
vi.mock('../expr/ExpressionBuilder', () => ({
  default: (props: { functionsCatalog: { label: string; items: { label: string }[] }[] }) => (
    <div data-testid="expr-builder">
      {props.functionsCatalog.map(cat => (
        <div key={cat.label} data-testid={`cat-${cat.label}`}>
          {cat.items.map(item => <span key={item.label}>{item.label}</span>)}
        </div>
      ))}
    </div>
  ),
}))

import { customFunctionsApi } from '../../services/api'

describe('CalcColumnsPanel custom functions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(customFunctionsApi.list).mockResolvedValue([])
  })

  it('renders the custom-functions management panel', async () => {
    render(<CalcColumnsPanel datasetId={5} columns={[]} onChanged={vi.fn()} />)
    expect(await screen.findByText('Custom functions')).toBeInTheDocument()
  })

  it('offers a saved custom function in the expression palette', async () => {
    vi.mocked(customFunctionsApi.list).mockResolvedValue([
      { name: 'PROFIT_MARGIN', params: ['revenue', 'cost'], expression: '(revenue - cost) / revenue' },
    ])
    render(<CalcColumnsPanel datasetId={5} columns={[]} onChanged={vi.fn()} />)

    fireEvent.click(await screen.findByRole('button', { name: '+ Add' }))
    await waitFor(() => expect(screen.getByTestId('cat-Custom')).toBeInTheDocument())
    expect(screen.getByText('PROFIT_MARGIN(revenue, cost)')).toBeInTheDocument()
  })

  it('does not add a "Custom" category when there are no custom functions', async () => {
    render(<CalcColumnsPanel datasetId={5} columns={[]} onChanged={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: '+ Add' }))
    await screen.findByTestId('expr-builder')
    expect(screen.queryByTestId('cat-Custom')).toBeNull()
  })
})
```

- [ ] **Step 2: Run to verify RED**

```bash
cd frontend && npx vitest run src/components/report/CalcColumnsPanel.test.tsx
```
Expected: FAIL — `customFunctionsApi` has no export from `../../services/api` yet if Task 9 were undone, but since Task 9 already ran, the actual failure here is "Custom functions" text not found and `cat-Custom` not found, since `CalcColumnsPanel` doesn't yet fetch or render any of it.

- [ ] **Step 3: Implement**

In `frontend/src/components/report/CalcColumnsPanel.tsx`:

1. Add the import: `import { columnsApi, calcColumnsApi, customFunctionsApi } from '../../services/api'` and `import type { CalcColumn, CalcColumnFormat, CustomFunction, DatasetColumn } from '../../services/api'`.
2. Add `import CustomFunctionsPanel from './CustomFunctionsPanel'`.
3. In `CalcColumnsPanel`, add state and a builder for the custom-functions palette category:

```typescript
const [customFunctions, setCustomFunctions] = useState<CustomFunction[]>([])

useEffect(() => {
  customFunctionsApi.list(datasetId).then(setCustomFunctions)
}, [datasetId])

const customCat: FuncCat | null = customFunctions.length === 0 ? null : {
  label: 'Custom', color: '#818cf8',
  items: customFunctions.map(fn => {
    const n = fn.params.length
    return {
      label: `${fn.name}(${fn.params.join(', ')})`,
      snippet: `${fn.name}(${', '.repeat(Math.max(n - 1, 0))})`,
      back: n === 0 ? 0 : 2 * n - 1,
      hint: fn.expression,
    }
  }),
}

const functionsCatalog = customCat ? [...FUNC_CATS, customCat] : FUNC_CATS
```

4. Pass `functionsCatalog={functionsCatalog}` instead of `functionsCatalog={FUNC_CATS}` to the `<ExpressionBuilder>` inside `BuilderModal` — this means threading `functionsCatalog` down as a new prop on `BuilderModal` (it currently hardcodes `FUNC_CATS` directly at line 381), since `FUNC_CATS` is a module-level constant `BuilderModal` currently references directly rather than receiving as a prop. Add `functionsCatalog: FuncCat[]` to `BuilderProps` and pass it from the parent's render call (`<BuilderModal ... functionsCatalog={functionsCatalog} ... />`).
5. Render `<CustomFunctionsPanel datasetId={datasetId} onChanged={setCustomFunctions} />` in `CalcColumnsPanel`'s returned JSX, after the existing calculated-columns list and before the `BuilderModal` portal.

- [ ] **Step 4: Run to verify GREEN**

Same vitest command as Step 2, then the full frontend suite:

```bash
cd frontend && npx vitest run
```
Expected: 0 failures.

- [ ] **Step 5: Verify types**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/CalcColumnsPanel.tsx frontend/src/components/report/CalcColumnsPanel.test.tsx
git commit -m "feat: surface custom functions in the calc-column expression palette"
```

---

### Task 12: Final full-stack verification

**Files:** none (verification-only task)

- [ ] **Step 1: Full backend suite**

```bash
P=$(pwd -W)
MSYS_NO_PATHCONV=1 docker run --rm --network data_analytics_datalytics_net \
  -v "$P/backend:/app" -v "$P/frontend:/frontend" \
  -v "$P/docker-compose.yml:/docker-compose.yml:ro" \
  -v "$P/ARCHITECTURE.md:/ARCHITECTURE.md:ro" -v "$P/ARCHITECTURE.html:/ARCHITECTURE.html:ro" \
  -w /app data_analytics-backend \
  sh -c "python -m pytest -q -p no:warnings 2>/dev/null | tail -10"
```
Expected: 0 failures.

- [ ] **Step 2: Full frontend suite + typecheck**

```bash
cd frontend && npx vitest run && npx tsc --noEmit
```
Expected: 0 failures, no type errors.

- [ ] **Step 3: Live verification**

Using the same headless-Chrome + `/sso/callback#token=` technique established earlier this session: open a dataset's calculated-columns editor, create a custom function, insert it into a calculated column's expression, save, and confirm the computed value renders correctly in the dataset's Data tab or a widget. Screenshot the palette showing the new "Custom" category and the management panel.

- [ ] **Step 4: Report**

Summarize what shipped, the final test counts, and the screenshot(s), matching this session's established verification style — no completion claim without the fresh command output backing it.
