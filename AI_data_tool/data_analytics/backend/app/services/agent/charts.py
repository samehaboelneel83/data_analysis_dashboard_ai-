"""Which two columns a chart of this result should use -- or why it cannot.

"i need chart" says what to draw with, not what to draw. Until this module the
frontend guessed: first non-numeric column labels the bars, first numeric one
sizes them. Over a result whose columns are all numeric that guess drew the id
column against itself, and over one whose numbers never change it drew
thirty-three identical bars. Both are in the screenshots that started this.

A guess is the wrong shape of answer to a request that genuinely does not say.
So there are three outcomes and the caller renders each differently:

* `ok`       -- the rows determine one sensible pair; draw it.
* `ambiguous`-- several pairs would work; ASK, offering the real pairs as
                ready-to-send messages the person can click.
* `flat`     -- no pair would show anything (every number is constant, or only
                one column varies at all); say so, in terms of the actual
                columns, rather than drawing a flat picture of nothing.

Everything here is computed from the snapshot the chat already holds -- no
model call, no invented column name. An option this module offers is always a
column the person is looking at.
"""
from __future__ import annotations

#: Options offered at once. Past a handful a choice stops being a choice.
MAX_OPTIONS = 5

#: Past this many distinct label values a bar chart is a smear, not a chart.
#: Measured live: "how many users get this grade" grouped a continuous score
#: into 5,000 distinct values, and "draw this chart" drew 5,000 bars. The
#: data was right and the picture said nothing. What such a column needs is
#: to be put into ranges first, and only the person can say which.
MAX_MARKS = 200

#: A column with one distinct value cannot label anything (every bar gets the
#: same name) and cannot size anything (every bar gets the same height). It is
#: not a candidate for either axis, however interesting it is otherwise.
_MIN_DISTINCT = 2


def _is_number(v) -> bool:
    """Snapshot cells are already coerced (results.coerce_scalar), so a number
    is a real int or float here. `bool` is excluded: True is not a measure."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _facts(columns: list[str], rows: list[list]) -> list[dict]:
    """Per column: is every value a number, and how many distinct values."""
    out = []
    for i, name in enumerate(columns):
        values = [r[i] for r in rows if i < len(r) and r[i] is not None]
        out.append({
            "name": name,
            "numeric": bool(values) and all(_is_number(v) for v in values),
            "distinct": len({str(v) for v in values}),
        })
    return out


def pick_axes(columns: list[str], rows: list[list],
              truncated: bool = False) -> dict:
    """`{"outcome": "ok", "x", "y"}` | `{"outcome": "ambiguous"|"flat",
    "question", "options"}`.

    `x` labels the marks, `y` sizes them -- the pair an option names as
    "Chart <y> by <x>", which is how a person says it out loud.

    The rules, in full:

    * A column with fewer than two distinct values is out of the running for
      both axes -- it would draw one name, or one height, repeated.
    * The label is a varying NON-numeric column when there is one; the
      measure is any varying numeric column that is not already the label.
    * With no non-numeric column at all, every varying numeric column is a
      candidate label as well as a candidate measure -- which is precisely the
      "id against itself" case, and precisely why it is ASKED rather than
      guessed. Ties are not broken silently: they are what makes it ambiguous.
    * One label and one measure is not a choice, it is the answer: draw it.
      This is the ordinary two-column result ("city, n"), which keeps behaving
      exactly as it did.
    """
    if not columns or not rows:
        return _flat("There are no rows here to chart.", [])

    # The snapshot is a capped sample (results.RESULT_ROW_CAP), and a column
    # that is constant across it may well vary in row 201. The decision is
    # still right -- the chart draws these rows -- but the SENTENCE must not
    # claim more than was looked at.
    scope = "every row shown" if truncated else "every row"
    facts = _facts(columns, rows)
    varying = [f for f in facts if f["distinct"] >= _MIN_DISTINCT]
    constant = [f["name"] for f in facts if f["distinct"] < _MIN_DISTINCT]

    if not varying:
        return _flat(
            f"Every column in this result has the same value in {scope} "
            f"({', '.join(constant)}), so a chart of it would be one flat "
            "bar. There is nothing here that varies to draw.", [])

    labels = [f["name"] for f in varying if not f["numeric"]] \
        or [f["name"] for f in varying if f["numeric"]]
    measures = [f["name"] for f in varying if f["numeric"]]

    distinct = {f["name"]: f["distinct"] for f in facts}
    pairs = [(x, y) for x in labels for y in measures if y != x]

    # A label with thousands of values makes thousands of bars. Dropped from
    # the pairs, not drawn; and if that leaves nothing, said outright, with
    # the way forward -- ranges -- named, since it is the person who knows
    # which ranges mean something.
    crowded = sorted(x for x in labels if distinct[x] > MAX_MARKS)
    pairs = [(x, y) for x, y in pairs if distinct[x] <= MAX_MARKS]
    if not pairs and crowded:
        x = crowded[0]
        return _flat(
            f"{x} has {distinct[x]:,} distinct values, and a bar for each "
            f"would be {distinct[x]:,} bars — too many to read. Ask for it "
            f"grouped into ranges first (for example \"{x} in bands of 10\") "
            "and I will chart the ranges.", [])
    if not pairs:
        varying_names = ", ".join(f["name"] for f in varying)
        tail = (f", {', '.join(constant)} are the same in {scope}."
                if constant else ".")
        return _flat(
            "A chart needs one column to label the bars and a DIFFERENT one "
            "to size them, and this result does not have both: only "
            f"{varying_names} varies{tail} "
            "Charting it would draw one bar per row, all the same height.",
            [])

    if len(pairs) == 1:
        x, y = pairs[0]
        return {"outcome": "ok", "x": x, "y": y}

    return {
        "outcome": "ambiguous",
        "question": ("Which two columns should the chart use? More than one "
                     "pair would work for these rows, and they say different "
                     "things."),
        "options": [f"Chart {y} by {x}" for x, y in pairs[:MAX_OPTIONS]],
    }


def _flat(question: str, options: list[str]) -> dict:
    """A refusal that still leads somewhere: the rows exist and can be read,
    so the way out is offered rather than left for the person to guess."""
    return {"outcome": "flat", "question": question,
            "options": options + ["Show the rows as a table"]}


def validated_axes(x, y, columns: list[str]) -> tuple[str | None, str | None]:
    """The axes a message named, kept only if they are columns of THIS result.

    Matched case-insensitively, because a person types `symbol_code` about a
    column the database calls `SYMBOL_CODE`. Anything else comes back as None
    and the caller falls through to `pick_axes` -- a named column that does
    not exist is not a reason to fail, and is never a reason to invent one.
    """
    by_fold = {c.casefold(): c for c in columns}
    got_x = by_fold.get(str(x).casefold()) if x else None
    got_y = by_fold.get(str(y).casefold()) if y else None
    if got_x is None or got_y is None or got_x == got_y:
        return None, None
    return got_x, got_y
