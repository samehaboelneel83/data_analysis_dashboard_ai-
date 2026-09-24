# Custom calculated-column functions — design

## Context

Phase 5 of the platform-enhancement roadmap is "Extensibility." That phase
covers four largely independent subsystems (custom widget/plugin SDK,
public/partner API, custom connector framework, custom calculated-column
functions); this spec covers only the first slice, chosen as lowest-risk and
highest immediate value: **letting a dataset editor define their own named
functions for the calculated-column expression language**, e.g.

    PROFIT_MARGIN(revenue, cost) = (revenue - cost) / revenue

used afterward as `PROFIT_MARGIN(revenue, cost)` inside any calculated-column
expression on that dataset, alongside the built-in `YEAR()`, `CONCAT()`, etc.

The other three Phase 5 slices (widget SDK, public API, connector framework)
are explicitly out of scope here and will each get their own design when
picked up.

## Why this shape, not arbitrary code

The existing expression engine (`backend/app/services/widget_data.py`) is
deliberately locked down: `_validate_expr_safety` (2304-2337) whitelists AST
node types and **excludes `ast.Attribute` entirely**, structurally blocking
both dunder escapes (`x.__globals__`) and ordinary method calls (`x.to_csv()`)
rather than blocklisting names. `_eval_expr` (2674-2700) pins
`__builtins__: {}` and disables pandas' `@name` external-variable resolution,
specifically because that syntax was a confirmed RCE vector
(`_validate_expr_safety`'s SyntaxError-is-rejection comment, 2319-2327).
Dedicated regression tests (`test_expression_sandbox_escape.py`) pin all of
this.

There is no precedent anywhere in this codebase for executing literal
org-supplied Python/JS at query time — the one existing precedent for
"let a tenant define their own logic," measures' `TOTAL`/`BYGROUP`/`CALC`
context functions (`measure_eval.py`), works by **rewriting the AST into the
existing safe primitives**, never by adding a new execution primitive.

This design follows that precedent exactly: a custom function is a named,
parameterized **expression template** built entirely from the existing safe
vocabulary. It is expanded (parameter names substituted with the caller's
argument subtrees) into the outer expression *before* that expression reaches
`_validate_expr_safety`/`_eval_expr`, which then run completely unchanged. No
new execution primitive is introduced at any point.

## Scope & authorization

Custom functions are **dataset-scoped**, modeled identically to calculated
columns and measures (`Dataset.calculated_columns`, `Dataset.measures` —
both per-dataset JSON columns today). A new `Dataset.custom_functions` JSON
column holds a list of `{name, params, expression}` objects.

- **Write** (create/edit/delete): `require_dataset_capability(db, user,
  dataset_id, "data")` — the identical gate `calculated-columns` and
  `measures` already use. No new authorization concept.
- **Read** (seeing/using a function while authoring an expression on that
  dataset): the existing dataset-read resolver
  (`readable_dataset_ids`/`can_read_dataset`, `core/capability.py`).
- **No per-function ownership.** Any editor with "data" capability on the
  dataset can edit or delete any function on it — matching how calculated
  columns work today (no per-column ownership either). Adding per-function
  ownership would be a new concept this feature doesn't need.

**Named limitation, stated explicitly:** a function is defined once per
dataset. The same logical function needed on two datasets is defined twice.
No cross-dataset function registry exists in v1 — that would need its own
sharing/visibility model (akin to `DatasetShare`) and is deferred.

**v1 covers calculated columns only, not measures.** Measures already have
their own AST-rewrite mechanism; wiring custom functions into it too is a
straightforward follow-on, not bundled here to keep the first version's test
surface bounded.

## Function definition shape

```json
{"name": "PROFIT_MARGIN", "params": ["revenue", "cost"],
 "expression": "(revenue - cost) / revenue"}
```

The body is written using the **parameter names as placeholders**, not real
dataset columns — that's what makes the function reusable across different
calc-column expressions on the dataset, the same way a built-in like
`CONCAT()` doesn't know a dataset's column names.

## Save-time validation

All of the following are checked when a function is created or edited,
before it is persisted:

1. The body must itself pass the existing `_validate_expr_safety` unchanged
   (same AST whitelist — no attribute access, no dunders, no `@name` syntax).
2. Every bare `ast.Name` in the body must be either a declared parameter or
   an existing built-in name (a key of `_build_safe_ns`'s `safe_globals`,
   extracted once via `_build_safe_ns(pd.DataFrame())` — building it touches
   `df` only via `df.columns`, so an empty frame is safe to introspect).
   This blocks two things at once: a function silently hardcoding a real
   dataset column (breaking reusability across expressions) and a function
   calling another custom function (no recursion/cycles to reason about).
3. Parameter names must be distinct, must not start with `_`, and must not
   collide with a built-in name (case-insensitive).
4. The function name must not collide with a built-in, a dataset column, an
   existing calculated column, or an existing measure (case-insensitive) —
   the identical rule `_validate_measure` already enforces for measures
   (`datasets.py:840-841`: `if measure.name in column_names or measure.name
   in calc_names: raise HTTPException(400, ...)`), extended to also check
   custom-function names and vice versa.

A SyntaxError while parsing the body (including one from `@name` syntax
`ast.parse` would otherwise accept via `df.eval`) is a save-time rejection,
matching `_validate_expr_safety`'s existing treatment. Backtick-quoted
identifiers in the body are normalized the same way
(`widget_data.py:2312-2317`) before parsing, so validation can't be skipped
by a would-be-SyntaxError expression that backticks hide.

## Expansion mechanism

When a calculated-column expression contains a call to a name that matches a
defined custom function, expansion runs **before** the expression reaches
`_eval_expr`:

1. Parse the calling expression's AST (after the same backtick
   normalization used elsewhere).
2. For each `Call` node whose `func` is a `Name` matching a custom function:
   - **Arity check.** The call's positional-argument count must exactly
     match the function's declared parameter count. Any keyword argument at
     the call site is rejected outright. Either failure is a hard error, not
     partial substitution — partial substitution could leave an
     un-substituted parameter name that happens to match a real dataset
     column, producing a silently wrong result instead of an error.
   - **Hygienic, simultaneous substitution.** Build a `{param_name:
     deep_copy(arg_ast_node)}` map for this call, then run a
     `NodeTransformer` over a **copy** of the function body that replaces
     each parameter `Name` with its mapped argument subtree in one pass,
     without recursing into the freshly-substituted subtree. This must be
     pinned by two tests: swapped arguments
     (`PROFIT_MARGIN(cost, revenue)` must not produce the same result as
     `PROFIT_MARGIN(revenue, cost)`), and an argument subtree that itself
     contains a parameter name of the same function
     (`PROFIT_MARGIN(revenue + cost, cost)` must not re-substitute the
     `cost` inside the already-injected `revenue + cost` subtree).
   - Splice the substituted subtree back in place of the original `Call`
     node.
3. `ast.unparse` the fully-expanded tree back to text (Python 3.12 backend,
   confirmed available) and feed it to the existing `_eval_expr` completely
   unchanged — preserving its `df.eval` → restricted-`eval` dual path with
   no modification.

**This expansion step is called only from `apply_calculated_columns`.** It
is not added inside `_eval_expr`/`_build_safe_ns` itself, and
`apply_filter_expr`/`apply_rls_filter` are not touched by this feature at
all. This is the load-bearing safety property of the whole design: if
expansion lived in the shared evaluator, a custom function would become
silently usable inside an RLS rule, and since there is no per-function
ownership, any editor with "data" capability could later edit that
function's body and change what a security rule evaluates to — a privilege
escalation, not a cosmetic bug.

**This is already structurally enforced at save time, verified by test
rather than by new production code.** `admin.py`'s `_validate_filter_expr`
(184-213), the single choke point both `create_rule` and `update_rule` for
row-security rules call before persisting, *eagerly evaluates* the filter
expression against a real loaded frame via `apply_filter_expr(df,
filter_expr, silent=False)`. Since expansion is never wired into
`_eval_expr`/`apply_filter_expr` (see above), a filter expression that calls
a custom function name hits an ordinary `NameError` inside `eval()` — the
same as calling any other undefined name — which `_validate_filter_expr`
already turns into a 400 "Invalid filter expression". No RLS rule calling an
unrecognized name, custom-function or otherwise, can be saved today. A test
pins this directly (save an RLS rule referencing a real, previously-defined
custom function name; assert 400) so a future refactor that accidentally
moves expansion into the shared evaluator — the one change this design
depends on never happening — is caught immediately. Column-security rules
have no expression field at all (`denied_columns` is a plain name list), so
they carry no equivalent risk.

`sql_expr.py`'s translator has no `ast.Call` support at all today (any
function call already falls through to `ExpressionTranslationError`), so
DirectQuery/pushdown translation is unaffected by this feature either way —
custom functions, like all function calls, simply aren't translatable to
SQL and fall back to the existing pandas evaluation path, exactly as every
other function call already does.

## Editing or deleting a function that's already in use

Expansion re-reads the function's current definition from
`Dataset.custom_functions` on every evaluation — there is no compiled/cached
copy, matching how calculated columns themselves are already re-evaluated
from stored text on every request (`widget_data.py` calls
`apply_calculated_columns` fresh per `widget-data` request). So:

- **Editing** a function's body immediately changes the result of every
  calculated column that calls it — expected, and no different from editing
  a calculated column's own expression directly.
- **Deleting** a function that a saved calculated column still calls leaves
  that calculated column referencing an unknown name. This falls through to
  `apply_calculated_columns`'s existing swallow-on-error behavior
  (`except Exception: pass`, 2753-2754) — the column silently stops
  producing a value, identically to what already happens today if a
  calculated column references a real dataset column that gets renamed or
  removed. No new failure mode; no special-cased "in use" guard is added in
  v1.

## Backend API

Mirrors the calculated-columns endpoints:

- `GET /datasets/{id}/custom-functions` — list (dataset-read).
- `PUT /datasets/{id}/custom-functions` — create/update by name
  (dataset "data" capability + all save-time validation above).
- `DELETE /datasets/{id}/custom-functions/{name}` — delete (dataset "data"
  capability).
- `POST /datasets/{id}/custom-functions/preview` — test a definition before
  saving. Since there is no row context for a function in isolation (unlike
  calc-column preview, which runs against real sample rows), the caller
  supplies literal sample values per declared parameter
  (`{"revenue": 100, "cost": 40}`) and receives the computed result or the
  validation error.

## Frontend

`CalcColumnsPanel`/`ExpressionBuilder` currently render a hardcoded palette
(`FUNC_CATS`). This adds one new, dynamically-fetched "Custom" category
(from the list endpoint) alongside the existing static categories — it does
not change how the built-in categories are sourced.

A small management surface, added to the existing calc-columns area (where
dataset editors already are): list of existing functions; "+ New function"
opens a form (name, params, expression body, inline preview/test against
sample values, save) with the backend's validation errors surfaced inline.
Once saved, a function appears in the "Custom" palette group and inserts
into expressions the same click-to-insert way built-ins already do — the
author then fills in real column names as the arguments.

## Testing plan

**Backend:**
- Substitution hygiene: swapped arguments; an argument subtree containing a
  parameter name of the same function.
- Arity mismatch rejected (too few/many positional args); any keyword
  argument at a call site rejected.
- Every save-time validation rule: unsafe body (reuses
  `_validate_expr_safety`'s existing rejections), a bare `Name` that is
  neither a parameter nor a builtin (blocks hardcoded columns and
  function-calling-function), duplicate/underscore-prefixed/builtin-colliding
  parameter names, function name colliding with a builtin/column/calc
  column/measure.
- Saving a row-security rule that calls a defined custom-function name is
  rejected with 400 (proves the structural guarantee above, not new
  production code).
- End-to-end: a saved function computes the correct value through the real
  `GET .../widget-data` path when used inside a calculated column.
- An addition to `test_expression_sandbox_escape.py`'s style of coverage,
  specifically exercising the new expansion step (e.g. a function body that
  would be unsafe if expansion bypassed `_validate_expr_safety`, confirming
  it's still caught).

**Frontend:**
- Palette renders the "Custom" category when functions exist for the
  dataset, and omits it when none do.
- Management form: create, edit, delete, and each validation error surfaced
  inline.
- One round-trip test: insert a custom function's snippet into an
  expression, preview it, save it, and confirm it's usable in a saved
  calculated column.
