"""Reconcile a widget with the numbers it is meant to reproduce (E17).

Migrating a report means showing its owner that the new dashboard says what
the old one said. The owner has the old report's export -- a CSV or Excel
file of the same table -- and this compares it with the widget, row by row:
which rows match, which differ and by how much, which are missing on either
side, and whether the totals agree.

- Rows are paired by key columns (the table's categories), compared after
  trimming and case-folding, so "Europe " and "europe" are the same row; a
  whole-number key matches whether it was written 2024 or 2024.0.
- A value matches within half a unit of the last decimal the FILE shows: an
  export that rounds to 1,234.57 agrees with 1234.5678. A value typed as a
  number in Excel (no shown decimals) must agree to a millionth of itself.
  Thousands separators, a trailing %, a leading currency sign and
  (parentheses) negatives are read as the numbers they are.
- Columns are paired by name (case and spacing ignored); with no names in
  common and two columns on each side, the first is the key and the second
  the value. The caller can say otherwise.

Pure: the router resolves the widget (as the reader, with every security
rule) and reads the file.
"""
from __future__ import annotations

import math
import re

import pandas as pd

_CURRENCY = re.compile(r"^[^\d\-\(\.]*")
_MAX_ROWS = 20_000


def _norm(name) -> str:
    return re.sub(r"[\s_]+", " ", str(name)).strip().casefold()


def parse_number(v) -> tuple[float | None, int | None]:
    """(value, decimals shown) -- decimals None when the value was a number
    already, so its precision is the machine's, not a display's."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None, None
    if isinstance(v, bool):
        return None, None
    if isinstance(v, (int, float)):
        return float(v), None
    s = str(v).strip()
    if not s:
        return None, None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").strip()
    pct = s.endswith("%")
    s = s.rstrip("%").strip()
    s = _CURRENCY.sub("", s).replace(",", "").replace("٬", "").replace(" ", "")
    s = s.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789."))
    try:
        x = float(s)
    except ValueError:
        return None, None
    decimals = len(s.split(".")[1]) if "." in s else 0
    if neg:
        x = -x
    if pct:
        x, decimals = x / 100, decimals + 2
    return x, decimals


def _key(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    if re.fullmatch(r"-?\d+\.0+", s):
        s = s.split(".")[0]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]00:00:00", s):
        s = s[:10]
    return s.casefold()


def default_mapping(actual_cols: list[str], expected_cols: list[str]) -> dict:
    """{"keys": [[actual, expected], ...], "values": [[actual, expected], ...]}."""
    by_name = {_norm(c): c for c in expected_cols}
    pairs = [(a, by_name[_norm(a)]) for a in actual_cols if _norm(a) in by_name]
    if not pairs and len(actual_cols) == 2 and len(expected_cols) == 2:
        pairs = list(zip(actual_cols, expected_cols))
    if not pairs:
        return {"keys": [], "values": []}
    first_actual = actual_cols[0]
    keys = [p for p in pairs if p[0] == first_actual] or [pairs[0]]
    values = [p for p in pairs if p not in keys]
    return {"keys": [list(p) for p in keys], "values": [list(p) for p in values]}


def reconcile(actual: pd.DataFrame, expected: pd.DataFrame, mapping: dict | None = None) -> dict:
    if len(expected) > _MAX_ROWS:
        raise ValueError(f"The file has {len(expected):,} rows; reconcile up to {_MAX_ROWS:,} at a time")
    mapping = mapping or default_mapping([str(c) for c in actual.columns], [str(c) for c in expected.columns])
    keys, values = mapping.get("keys") or [], mapping.get("values") or []
    missing = [a for a, _ in keys + values if a not in actual.columns] + \
              [e for _, e in keys + values if e not in expected.columns]
    if missing:
        raise ValueError(f"Not a column here: {', '.join(map(str, missing))}")
    if not keys or not values:
        raise ValueError("Say which columns identify a row and which to compare")

    def keyed(frame, cols):
        out: dict[tuple, dict] = {}
        dupes = 0
        for _, row in frame.iterrows():
            k = tuple(_key(row[c]) for c in cols)
            if k in out:
                dupes += 1
                continue
            out[k] = row
        return out, dupes

    act, act_dupes = keyed(actual, [a for a, _ in keys])
    exp, exp_dupes = keyed(expected, [e for _, e in keys])
    rows, counts = [], {"match": 0, "mismatch": 0, "missing_in_widget": 0, "missing_in_file": 0}
    totals = {a: {"column": str(e), "expected": 0.0, "actual": 0.0} for a, e in values}

    for k in list(exp) + [k for k in act if k not in exp]:
        e_row, a_row = exp.get(k), act.get(k)
        label = {e: (e_row[e] if e_row is not None else a_row[a]) for a, e in keys}
        if a_row is None or e_row is None:
            status = "missing_in_widget" if a_row is None else "missing_in_file"
            counts[status] += 1
            rows.append({"key": {str(e): _plain(v) for e, v in label.items()}, "status": status, "values": []})
            continue
        cells, ok_all = [], True
        for a, e in values:
            want, shown = parse_number(e_row[e])
            got, _ = parse_number(a_row[a])
            if want is None or got is None:
                ok = _key(e_row[e]) == _key(a_row[a])
                diff = None
            else:
                tol = 0.5 * 10 ** (-shown) if shown is not None else max(abs(want) * 1e-6, 1e-9)
                diff = got - want
                ok = abs(diff) <= tol + 1e-12
            ok_all &= ok
            cells.append({"column": str(e), "expected": _plain(e_row[e]), "actual": _plain(a_row[a]),
                          "difference": None if diff is None else round(diff, 10), "ok": ok})
        status = "match" if ok_all else "mismatch"
        counts[status] += 1
        rows.append({"key": {str(e): _plain(v) for e, v in label.items()}, "status": status, "values": cells})

    # The totals are each side's whole column, rows missing from the other
    # side included: an owner compares the report's grand total first.
    for a, e in values:
        totals[a]["expected"] = sum(v for v, _ in map(parse_number, expected[e]) if v is not None)
        totals[a]["actual"] = sum(v for v, _ in map(parse_number, actual[a]) if v is not None)
    order = {"mismatch": 0, "missing_in_widget": 1, "missing_in_file": 2, "match": 3}
    rows.sort(key=lambda r: order[r["status"]])
    for t in totals.values():
        t["difference"] = round(t["actual"] - t["expected"], 10)
    return {
        "mapping": {"keys": [list(p) for p in keys], "values": [list(p) for p in values]},
        "columns": {"widget": [str(c) for c in actual.columns], "file": [str(c) for c in expected.columns]},
        "counts": counts, "rows": rows, "totals": list(totals.values()),
        "duplicate_keys": {"widget": act_dupes, "file": exp_dupes},
        "reconciled": counts["mismatch"] == 0 and counts["missing_in_widget"] == 0 and counts["missing_in_file"] == 0,
    }


def _plain(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if hasattr(v, "item"):
        v = v.item()
    return v if isinstance(v, (int, float, str, bool)) else str(v)
