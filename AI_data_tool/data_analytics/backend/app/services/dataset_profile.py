"""A description of a dataset thorough enough to choose charts from.

The suggestion engines that came before this one worked from either a table
catalog (names and types) or from statistical findings. Neither is what a person
looks at when deciding what to put on a dashboard. They look at how many
distinct departments there are, whether the dates cover a month or three years,
whether anything here is a coordinate, and which columns are identifiers they
should leave alone.

That is what this builds, and it exists because the alternative is a model
guessing. A model told only `department: text` will cheerfully propose a pie
chart of 40,000 patient names; told `department: text, 3 distinct, mostly
Cardiology / ENT / Oncology` it will not.

Nothing here is specific to hospitals, courses, or any other domain: every
signal is derived from the frame.
"""
from __future__ import annotations

import pandas as pd

from .ingest import missing_pct
from .insights import effective_roles
from .pii import detect_semantic_type, is_pii
from .widget_data import _is_id_like_column

#: Enough labels to show what a column contains without pasting the column in.
TOP_VALUES = 5
#: A prompt has to stay affordable. Columns beyond this are named but not
#: profiled -- the model can still bind to them, it simply gets less detail.
MAX_PROFILED_COLUMNS = 60
#: Above this many distinct values a column is a poor axis: the chart becomes a
#: list. Recorded so the prompt can say so rather than the model finding out.
HIGH_CARDINALITY = 50


def _sample_values(series: pd.Series) -> list[dict]:
    try:
        counts = series.dropna().astype(str).value_counts().head(TOP_VALUES)
    except Exception:                                        # noqa: BLE001
        return []
    return [{"value": str(k), "count": int(v)} for k, v in counts.items()]


def _numeric_bounds(series: pd.Series):
    try:
        clean = pd.to_numeric(series, errors="coerce").dropna()
        if clean.empty:
            return None, None
        return float(clean.min()), float(clean.max())
    except Exception:                                        # noqa: BLE001
        return None, None


def _granularity_for(days: float) -> str:
    """A bucket size that yields a readable number of points.

    Not a matter of taste: a daily axis over three years is 1,095 columns, which
    is not a chart. Somewhere between 12 and 60 points is what a person reads.
    """
    if days <= 45:
        return "day"
    if days <= 120:
        return "week"
    if days <= 2200:
        return "month"
    return "quarter"


def _looks_like(name: str, words) -> bool:
    low = str(name).lower()
    return any(low == w or low.endswith("_" + w) or low.startswith(w + "_")
               or ("_" + w + "_") in low for w in words)


def _coordinate_pairs(columns, roles) -> list:
    """Latitude/longitude columns that belong together.

    Paired by NAME rather than by value: that is how they are actually named,
    and two unrelated numeric columns that happen to fall in range would pair by
    value alone. Nine widget types are unusable without a pair, and offering one
    of them when no pair exists is how a proposal becomes a blank tile.
    """
    pairs: list = []
    lows = {c.lower(): c for c in columns}
    for col in columns:
        low = col.lower()
        for lat_word in ("latitude", "lat"):
            if lat_word not in low:
                continue
            for lon_word in ("longitude", "long", "lon", "lng"):
                cand = low.replace(lat_word, lon_word)
                match = lows.get(cand)
                if (match and match != col
                        and roles.get(col) == "numeric"
                        and roles.get(match) == "numeric"
                        and [col, match] not in pairs):
                    pairs.append([col, match])
            break
    return pairs


def _parent_child(df: pd.DataFrame, columns) -> list:
    """Self-referencing pairs: an identifier column, and a column holding values
    drawn from it. That is what an org chart is, and nothing else in the profile
    would reveal it."""
    ids = [c for c in columns if _is_id_like_column(c)]
    parent_words = ("parent", "manager", "reports_to", "supervisor", "reports")
    out: list = []
    for cand in columns:
        if not _looks_like(cand, parent_words):
            continue
        for id_col in ids:
            if id_col == cand:
                continue
            try:
                child = set(pd.Series(df[cand]).dropna().unique())
                parent_of = set(pd.Series(df[id_col]).dropna().unique())
            except Exception:                                # noqa: BLE001
                continue
            if child and child <= parent_of:
                out.append([id_col, cand])
                break
    return out


def _hierarchies(profiled) -> list:
    """Categorical columns ordered coarse to fine, which is what the five
    hierarchy widgets consume as `levels`. Cardinality is the ordering signal: a
    division contains departments contains units, and has fewer of them."""
    cats = [c for c in profiled
            if c["role"] == "categorical" and not c["is_identifier"]
            and not c["is_personal"] and 1 < (c["distinct"] or 0) <= HIGH_CARDINALITY]
    if len(cats) < 2:
        return []
    ordered = sorted(cats, key=lambda c: c["distinct"])
    return [[c["name"] for c in ordered[:3]]]


def _detect_role(series: pd.Series) -> str:
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_bool_dtype(series):
        return "categorical"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    return "categorical"


def _date_bounds(series: pd.Series):
    try:
        clean = pd.to_datetime(series, errors="coerce").dropna()
        if clean.empty:
            return None, None
        return str(clean.min()), str(clean.max())
    except Exception:                                        # noqa: BLE001
        return None, None


def _date_range(profiled) -> dict | None:
    """The widest date column, with a granularity that suits its span."""
    best = None
    for entry in profiled:
        if entry["role"] != "datetime" or not entry["min"]:
            continue
        try:
            lo, hi = pd.Timestamp(entry["min"]), pd.Timestamp(entry["max"])
        except Exception:                                    # noqa: BLE001
            continue
        days = int((hi - lo).days)
        if best is None or days > best["days"]:
            best = {"column": entry["name"], "from": str(lo), "to": str(hi),
                    "days": days, "granularity": _granularity_for(days)}
    return best


def build_profile(df: pd.DataFrame, type_map: dict | None = None,
                  column_meta: dict | None = None) -> dict:
    """Everything a chart-choosing model should know about `df`."""
    empty = {"row_count": 0, "columns": [], "other_columns": [],
             "structure": {"coordinate_pairs": [], "parent_child": [],
                           "hierarchies": [], "date_range": None}}
    if df is None or not len(df.columns):
        return empty

    columns = list(df.columns)
    if type_map is None:
        type_map = {c: _detect_role(df[c]) for c in columns}
    roles = effective_roles(type_map, column_meta)

    profiled: list = []
    for name in columns[:MAX_PROFILED_COLUMNS]:
        series = df[name]
        role = roles.get(name) or _detect_role(series)
        try:
            semantic = detect_semantic_type(series.dropna().head(200).tolist())
        except Exception:                                    # noqa: BLE001
            semantic = None
        entry = {
            "name": name,
            "role": role,
            "distinct": int(series.nunique(dropna=True)) if len(series) else 0,
            "missing_pct": missing_pct(series),
            "is_identifier": bool(_is_id_like_column(name)),
            "is_personal": bool(is_pii(semantic)),
            # A 0/1 column. The number people want from one is the SHARE that are
            # 1 -- a mortality rate, an abnormal rate -- which is its average.
            # Counting it counts every row instead, flagged or not.
            "is_flag": False,
            "top_values": [],
            "min": None,
            "max": None,
        }
        if role == "numeric":
            entry["min"], entry["max"] = _numeric_bounds(series)
            entry["is_flag"] = (entry["distinct"] <= 2
                                and entry["min"] in (0, 0.0, None)
                                and entry["max"] in (1, 1.0, None)
                                and not entry["is_identifier"])
        elif role == "datetime":
            entry["min"], entry["max"] = _date_bounds(series)
        # A personal column is never sampled: this profile is sent to a model.
        if role == "categorical" and not entry["is_personal"]:
            entry["top_values"] = _sample_values(series)
        profiled.append(entry)

    # Columns past the cap stay nameable, so a proposal may still use them.
    overflow = [{"name": c, "role": roles.get(c) or "unknown"}
                for c in columns[MAX_PROFILED_COLUMNS:]]

    return {
        "row_count": int(len(df)),
        "columns": profiled,
        "other_columns": overflow,
        "structure": {
            "coordinate_pairs": _coordinate_pairs(columns, roles),
            "parent_child": _parent_child(df, columns),
            "hierarchies": _hierarchies(profiled),
            "date_range": _date_range(profiled),
        },
    }


#: How many enum labels are spelled out per column. A status column with six
#: codes is worth listing; a product-code column with four hundred is a
#: dictionary, and pasting it would crowd out every other column's meaning.
MAX_LABELS_IN_PROMPT = 12


def _meaning_lines(entry, indent: str = "    ") -> list[str]:
    """The sentences one column's knowledge contributes, or nothing at all.

    Deliberately silent when there is nothing to say: an empty "description:"
    line teaches the model that descriptions are noise, and the next column that
    HAS one then gets read with the same weight.
    """
    out = []
    if entry.description:
        out.append(indent + entry.description.strip())
    labels = entry.enum_labels or {}
    if labels:
        shown = list(labels.items())[:MAX_LABELS_IN_PROMPT]
        rendered = ", ".join("{} = {}".format(k, v) for k, v in shown)
        if len(labels) > len(shown):
            rendered += ", ... ({} in total)".format(len(labels))
        # The most useful line on this list: it turns an axis of 1/2/3 into
        # words, for the model now and for the person reading the chart later.
        out.append(indent + "values mean: " + rendered)
    return out


def describe_for_prompt(profile: dict, knowledge=None) -> str:
    """The profile as compact prose, which is what the model actually reads.

    `knowledge` is a `services.knowledge.DatasetKnowledge` and is optional: with
    none this returns exactly what it always did, byte for byte. With one, the
    model stops seeing a table of shapes and starts seeing a described thing --
    what one row IS, what each column MEANS, what a coded value stands for, and
    the terms the business uses for them.

    That difference is the entire point of the knowledge layer. A designer handed
    `status (categorical, 3 distinct)` picks a chart that is valid and
    meaningless; one handed "where the order is in fulfilment; 2 = paid" picks
    the chart somebody actually wanted.
    """
    lines = []
    if knowledge is not None:
        obj = knowledge.object
        headline = obj.business_name or obj.name
        # The grain goes on the headline: "one row per completed order" is the
        # single fact that most often stops a model double-counting.
        if obj.grain:
            headline += " -- {}".format(obj.grain.strip().rstrip("."))
        markers = []
        if obj.is_canonical:
            markers.append("the source of truth for this; prefer it over "
                           "recomputing the same fact from raw tables")
        if obj.is_deprecated:
            markers.append("deprecated -- prefer another table if one says the same thing")
        if markers:
            headline += "  [{}]".format("; ".join(markers))
        lines += ["WHAT THESE ROWS ARE", headline]
        if obj.description:
            lines.append(obj.description.strip())
        lines.append("")

    lines += ["{:,} rows.".format(profile["row_count"]), "", "COLUMNS"]
    for c in profile["columns"]:
        head = "- {} ({}".format(c["name"], c["role"])
        if c["distinct"]:
            head += ", {:,} distinct".format(c["distinct"])
        if c["missing_pct"]:
            head += ", {:.0f}% missing".format(c["missing_pct"])
        head += ")"
        if c["is_identifier"]:
            head += "  [identifier - count or group by it, never sum or average it]"
        if c["is_personal"]:
            head += "  [personal data - do not use as a dimension]"
        if c.get("is_flag"):
            head += ("  [0/1 flag - its share is `avg`; `count` of it counts "
                     "every row and is never a rate]")
        if c["role"] == "numeric" and c["min"] is not None:
            head += "  range {:g} to {:g}".format(c["min"], c["max"])
        if c["role"] == "datetime" and c["min"]:
            head += "  {} to {}".format(c["min"][:10], c["max"][:10])
        if c["top_values"]:
            head += "\n    commonest: " + ", ".join(v["value"][:24] for v in c["top_values"])
        if c["role"] == "categorical" and (c["distinct"] or 0) > HIGH_CARDINALITY:
            head += "\n    (high cardinality - needs a limit, or works better as a filter)"
        entry = knowledge.column(c["name"]) if knowledge is not None else None
        if entry is not None:
            # MARKED, not removed. An ineligible column is still a perfectly
            # good filter, join key or sort -- what the author withheld is the
            # platform putting a chart of it in front of someone unprompted.
            # Removing it from the prompt would also remove the model's ability
            # to narrow a chart by it, which nobody asked for.
            if not entry.eligible_for_suggestion:
                head += "  [do not chart this column - usable as a filter only]"
            if entry.target_priority is not None:
                head += ("  [an OUTCOME worth explaining - a dashboard about "
                         "this column answers a question somebody has]")
            for line in _meaning_lines(entry):
                head += "\n" + line
        lines.append(head)

    if profile.get("other_columns"):
        lines.append("- also available, not profiled: "
                     + ", ".join(c["name"] for c in profile["other_columns"]))

    st = profile["structure"]
    lines += ["", "STRUCTURE"]
    if st["date_range"]:
        d = st["date_range"]
        lines.append("- time: {} spans {} to {} ({} days) - bucket it by {}".format(
            d["column"], d["from"][:10], d["to"][:10], d["days"], d["granularity"]))
    else:
        lines.append("- no date column: time-series widgets are not possible here")
    if st["coordinate_pairs"]:
        for lat, lon in st["coordinate_pairs"]:
            lines.append("- coordinates: {} / {} - map widgets are possible".format(lat, lon))
    else:
        lines.append("- no latitude/longitude pair: do not propose map widgets")
    for id_col, parent in st["parent_child"]:
        lines.append("- reference hierarchy: {} <- {} - an org chart is possible".format(
            id_col, parent))
    if st["hierarchies"]:
        lines.append("- nesting, coarse to fine: " + " > ".join(st["hierarchies"][0])
                     + " - usable as `levels` for tree/sunburst/icicle/dendrogram")

    if knowledge is not None and knowledge.glossary:
        # What the business calls things. Without this, a model proposing a
        # "GMV" tile has to guess which column that is, and guesses quietly.
        lines += ["", "BUSINESS TERMS"]
        for g in knowledge.glossary:
            term = g.term
            if g.synonyms:
                term += " (also {})".format(", ".join(g.synonyms))
            maps = ""
            if g.maps_to_column:
                maps = "  -> column {}".format(g.maps_to_column)
            elif g.maps_to_object:
                maps = "  -> {}".format(g.maps_to_object)
            lines.append("- {}: {}{}".format(term, (g.definition or "").strip(), maps))

    return "\n".join(lines)
