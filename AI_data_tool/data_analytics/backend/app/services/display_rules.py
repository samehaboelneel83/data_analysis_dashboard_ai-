"""Display rules: expression-driven restyling of an already-shaped widget result.

Rules evaluate AFTER shaping, never before. A rule like `value > 1000` refers to the
aggregated value a mark displays, which is what shape_series already produced — so the
engine reads the shaped result, not the dataframe. That placement is what makes rules
work identically for import and DirectQuery, and what makes them re-evaluate correctly
when a cross-filter narrows the context.

FAILURE SEMANTICS — deliberately the opposite of app.services.widget_data.apply_rls_filter,
which fails CLOSED to zero rows because a broken security control must hide data. Display
rules are cosmetic, so a broken rule must never blank or break a widget: each rule is
evaluated in isolation, failures are collected in `errors`, and every other rule still
applies. Do not "make these consistent" — the asymmetry is the point.

The `visibility` target is PRESENTATIONAL ONLY. It hides a widget in the client, but the
rows it would have shown are still serialised into the response the client already
received — nothing here removes them. And because rules fail open (see above), a
visibility rule that errors reveals the widget rather than hiding it. Never rely on this
target to keep data from a viewer; that is what row-level security (apply_rls_filter) is
for, and it fails the opposite way for exactly that reason.
"""
import numpy as np
import pandas as pd

from app.services.widget_data import _eval_expr, _validate_expr_safety


def result_frame(result: dict) -> pd.DataFrame | None:
    """Lift a shaped widget result into a frame whose columns are what a rule may name.

    Returns None when the result carries nothing a rule could address, in which case
    rules are ignored rather than erroring."""
    rtype = result.get("type")
    rows = result.get("rows") or []

    if rtype == "gauge":
        return pd.DataFrame([{"value": result.get("value"), "target": result.get("target")}])

    if rtype in ("table", "crosstab"):
        cols = result.get("columns") or []
        return pd.DataFrame(rows, columns=cols) if rows and cols else None

    if rtype == "waterfall":
        # shape_waterfall (app.services.widget_data) keys its per-bar data as "bars",
        # not "rows" -- the generic dict-rows fallback below never sees it.
        bars = result.get("bars") or []
        return pd.DataFrame(bars) if bars else None

    # series, scalar, and shapers that return {name, value} rows without a `type`
    # (shape_card is the current example) all share the same row shape.
    if rows and isinstance(rows[0], dict):
        return pd.DataFrame(rows)

    return None


def _match_mask(expression: str, frame: pd.DataFrame) -> list[bool]:
    """Evaluate a boolean expression to one bool per frame row. A scalar result applies
    to every row, which is what makes `SUM(value) > 100` usable as a widget-level rule."""
    _validate_expr_safety(expression)
    verdict = _eval_expr(expression, frame)
    if hasattr(verdict, "__len__") and not isinstance(verdict, (str, bytes)):
        series = pd.Series(list(verdict), index=frame.index)
        return [bool(v) for v in series.fillna(False)]
    return [bool(verdict)] * len(frame)


def _value_map_candidates(rule: dict, frame: pd.DataFrame) -> list[str]:
    """Columns a value_map rule reads, in precedence order.

    Shared by nothing else today, but kept separate from the matching itself because
    it is where the rule's *errors* are decided, and those are load-bearing: every
    other rule kind raises when it names a column the shaped result lacks, so the
    failure lands in `rule_errors` and the author can see it. value_map used to be the
    one kind that returned None for every row instead -- a rule that had simply stopped
    applying (subtotals turned off, a column dropped from a raw table) was
    indistinguishable from one that matched nothing. Fail-open is unchanged: this is
    recorded, not raised to the caller, and every other rule still applies."""
    if rule.get("any_category"):
        return [c for c in frame.columns if c != "value"]
    column = rule.get("column")
    if not column:
        raise ValueError("Colour map rule has no column selected")
    if column not in frame.columns:
        raise ValueError(f"Colour map rule names a column that is not in the result: {column}")
    return [column]


def _is_tabular(result: dict) -> bool:
    """Only table-shaped results have addressable cells; a bar chart's mark is its row."""
    return result.get("type") in ("table", "crosstab")


_WIDGET_TARGETS = ("background", "visibility")

# Rules are attacker-choosable client input -- config["display_rules"] travels straight
# from the request body -- and every rule runs an _eval_expr sandbox pass over the
# frame on every widget render. An unbounded rule list or an unbounded expression
# string is a cheap way to burn CPU with no meaningful authoring use case behind it
# (the panel-authored expressions this UI actually emits are a few dozen characters;
# a handful of rules per widget covers every real scenario). Capped, not rejected
# outright -- consistent with the fail-open contract: an overflow is recorded in
# `errors` like any other broken rule, and everything within the cap still evaluates.
MAX_RULES = 100
MAX_EXPRESSION_LENGTH = 1000


def _apply_style(styles: dict, i: int, column: str | None, style: dict, cell_scoped: bool) -> None:
    """Merge one resolved mark style into `styles`, at a cell or a whole row."""
    if cell_scoped:
        key = str(i)
        styles["cells"].setdefault(key, {})
        styles["cells"][key][column] = {**styles["cells"][key].get(column, {}), **style}
    else:
        styles["rows"][i] = {**(styles["rows"][i] or {}), **style}


def _value_map_styles(rule: dict, frame: pd.DataFrame) -> list[dict | None]:
    """Resolve a value_map rule for every row at once.

    Precedence is preserved exactly: for any row the candidate columns are tried in
    order, and within a column the mappings are tried in order, first match winning.
    Iterating columns outer / mappings inner and only ever writing where nothing has
    been assigned yet reproduces that, because a cell already claimed by an earlier
    column or mapping is skipped."""
    # Ordered before candidate resolution because the per-row form validated nothing on
    # an empty frame -- its comprehension simply never ran a row, so a rule naming an
    # absent column stayed silent rather than erroring. Validating first would turn that
    # silence into a rule_errors entry on every empty widget.
    if not len(frame):
        return []

    mappings = rule.get("mappings") or []
    candidates = _value_map_candidates(rule, frame)

    out: list[dict | None] = [None] * len(frame)
    assigned = np.zeros(len(frame), dtype=bool)

    for column in candidates:
        # Stringify both sides, so a mapping value of 1 matches a cell of "1" and vice
        # versa -- the editor stores whatever the category picker produced. Read from
        # the COLUMN, which is what makes the comparison depend only on the column the
        # rule names. The per-row form this replaced read the cell out of a row Series
        # spanning every column, so an all-numeric frame upcast an int64 column to
        # float and stringified "1.0", and the same rule matched or missed depending
        # on the dtypes of columns it never mentioned.
        text = frame[column].astype(str)
        for mapping in mappings:
            if assigned.all():
                return out
            hit = (text == str(mapping.get("value"))).to_numpy() & ~assigned
            if hit.any():
                style = {"fill": mapping.get("color")}
                for i in np.flatnonzero(hit):
                    out[i] = style
                assigned |= hit
    return out


def _interval_styles(rule: dict, frame: pd.DataFrame) -> list[dict | None]:
    """Resolve an interval rule for every row at once.

    Band order and the lower-inclusive / upper-exclusive convention are preserved,
    including the last band's inclusive upper bound. Coercion moves from per-cell
    `float(cell)` to one `to_numeric(errors="raise")`: a non-numeric column still
    raises, so a rule pointed at a text column still lands in `rule_errors` and stays
    visible to the author rather than silently matching nothing."""
    # Empty first, for the same reason as _value_map_styles: the per-row form never ran
    # a row on an empty frame, so it never validated the column either.
    if not len(frame):
        return []

    column = rule.get("column") or "value"
    if column not in frame.columns:
        raise ValueError(f"Interval rule names a column that is not in the result: {column}")

    out: list[dict | None] = [None] * len(frame)
    values = pd.to_numeric(frame[column], errors="raise")
    known = values.notna().to_numpy()
    assigned = np.zeros(len(frame), dtype=bool)

    bands = rule.get("bands") or []
    for i, band in enumerate(bands):
        # A band's bounds are coerced only once a row actually reaches it, matching the
        # per-row form, where a row broke out of the band loop on its first match and
        # a NaN row returned before the loop entirely. So a malformed band beyond the
        # last one any row needs stays uncoerced and cannot raise.
        if not (known & ~assigned).any():
            break
        low, high = float(band.get("min")), float(band.get("max"))
        within = ((values >= low) & (values < high)).to_numpy()
        if i == len(bands) - 1:
            # The maximum is inclusive on the final band only, so a value equal to the
            # top of the range lands in a band instead of falling through unstyled.
            within |= (values == high).to_numpy()
        hit = within & known & ~assigned
        if hit.any():
            style: dict = {"fill": band.get("color")}
            # Opt-in, not unconditional: an icon-less band must not gain an
            # `icon: None` key, or every interval characterization test above
            # (pinned to an exact `{"fill": ...}` dict) would break for a
            # feature it never opted into.
            if band.get("icon"):
                style["icon"] = band.get("icon")
            for j in np.flatnonzero(hit):
                out[j] = style
            assigned |= hit
    return out


def _data_bar_styles(rule: dict, frame: pd.DataFrame) -> list[dict | None]:
    """Resolve a data_bar rule for every row at once: an in-cell proportional bar,
    Excel/Power-BI style, scaled 0..1 against either an author-set min/max or the
    column's own observed range when neither is given.

    Unlike value_map/interval, every numeric row gets a style (there is no
    condition to match) -- only a NaN cell stays unstyled, since there is no
    proportion to draw for a value that is not there."""
    if not len(frame):
        return []

    column = rule.get("column") or "value"
    if column not in frame.columns:
        raise ValueError(f"Data bar rule names a column that is not in the result: {column}")

    values = pd.to_numeric(frame[column], errors="raise")
    known = values.notna()

    lo = rule.get("min")
    hi = rule.get("max")
    lo = float(lo) if lo is not None else (float(values[known].min()) if known.any() else 0.0)
    hi = float(hi) if hi is not None else (float(values[known].max()) if known.any() else 0.0)

    # A flat column (or a single-row frame) has nothing to compare against.
    # Reading every present value as "at the maximum" (a full bar) is the same
    # choice Excel/Power BI make, rather than dividing by zero or leaving a
    # real, present value unstyled.
    span = hi - lo
    if span <= 0:
        pct = pd.Series(np.where(known, 1.0, np.nan), index=frame.index)
    else:
        pct = ((values - lo) / span).clip(lower=0.0, upper=1.0)

    color = rule.get("color")
    out: list[dict | None] = [None] * len(frame)
    for i in range(len(frame)):
        if not known.iloc[i]:
            continue
        style: dict = {"bar": float(pct.iloc[i])}
        if color:
            style["fill"] = color
        out[i] = style
    return out


def _rule_row_styles(rule: dict, frame: pd.DataFrame) -> list[dict | None]:
    """One resolved style per frame row for a single rule, or None where it does not match.

    All three kinds resolve a whole column at a time. The per-row form this replaced
    called `frame.iloc[i][column]` once per row, which builds a Series per row: one
    interval rule over 10k rows cost 137ms, and five cost 668ms, on every render."""
    kind = rule.get("kind") or "expression"
    if kind == "value_map":
        return _value_map_styles(rule, frame)
    if kind == "interval":
        return _interval_styles(rule, frame)
    if kind == "data_bar":
        return _data_bar_styles(rule, frame)
    style = rule.get("style") or {}
    return [style if matched else None for matched in _match_mask(rule.get("expression") or "", frame)]


def evaluate_rules(result: dict, rules: list[dict]) -> dict:
    """Resolve rules against a shaped result. Never mutates `result`.

    Rules apply in list order and a later rule wins for the same target, so the caller
    orders report-level rules before widget-level ones and gets widget-wins for free."""
    frame = result_frame(result)
    row_count = 0 if frame is None else len(frame)
    styles: dict = {"rows": [None] * row_count, "cells": {}, "widget": {}, "errors": []}
    if frame is None or not rules:
        return styles

    overflow_count = max(0, len(rules) - MAX_RULES)
    if overflow_count:
        styles["errors"].append({
            "id": None,
            "message": f"{overflow_count} rule(s) beyond the {MAX_RULES}-rule limit were skipped",
        })
    rules = rules[:MAX_RULES]

    for rule in rules:
        try:
            expression = rule.get("expression")
            if expression and len(expression) > MAX_EXPRESSION_LENGTH:
                raise ValueError(f"expression exceeds the {MAX_EXPRESSION_LENGTH}-character limit")

            # Widget-level targets are a statement about the widget, not a mark, so they
            # short-circuit before row/cell painting and use any-row-matching: one
            # qualifying row is enough. Must run before the mark-painting branch below —
            # a widget-level rule must never also paint a row.
            target = rule.get("target") or "mark"
            if target in _WIDGET_TARGETS:
                row_styles = _rule_row_styles(rule, frame)
                matched = any(s is not None for s in row_styles)
                if target == "visibility":
                    # Always write the key, even on no match, so a non-matching rule
                    # yields an explicit False rather than an absent key — the renderer
                    # never has to distinguish "no rule" from "rule said visible".
                    styles["widget"]["hidden"] = styles["widget"].get("hidden", False) or matched
                elif matched:
                    styles["widget"].update(rule.get("style") or {})
                continue

            column = rule.get("column")
            # A column-scoped rule paints one cell; an unscoped rule paints the row.
            # value_map/interval rules use `column` to READ from, not to paint, so they
            # only ever paint cells on table-shaped results where cells exist.
            cell_scoped = bool(column) and column in frame.columns and _is_tabular(result)
            for i, style in enumerate(_rule_row_styles(rule, frame)):
                if style:
                    _apply_style(styles, i, column, style, cell_scoped)
        except Exception as e:  # noqa: BLE001 — cosmetic feature, see module docstring
            styles["errors"].append({"id": rule.get("id"), "message": str(e)})

    return styles
