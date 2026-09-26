"""E17: what an old SAS program uses, and where each piece goes in Datalytics.

`FEATURES` is the feature mapping: each SAS construct a migration meets, the
Datalytics feature that replaces it, and how well: "native" (the same job,
done by a built-in feature), "partial" (the common cases are covered and
the note says what is not) or "manual" (no equivalent; someone decides what
happens to it). It is written from what this codebase actually has -- the
recipe steps in services/prep.py, the statistics in routers/analysis.py,
parameters, deliveries, models -- not from a brochure, and it is served to
the inventory page as it is.

`scan_sas` reads a program's text and says which of those constructs it
uses and how often. It is a scanner, not a parser: comments are removed
first (a commented-out PROC is not a use), then PROC names, DATA steps,
macros, ODS destinations, LIBNAMEs and OS commands are found by their
statement shape. A PROC it does not know is reported by name as "manual"
rather than dropped, so an inventory never looks more complete than it is.

`read_inventory` reads the inventory spreadsheet an estate usually already
has (one row per report or program) from CSV text.
"""
from __future__ import annotations

import csv
import io
import re

#: key -> (SAS construct, Datalytics replacement, fit, note)
FEATURES: dict[str, tuple[str, str, str, str]] = {
    "data_step": ("DATA step", "Dataflow recipe steps or calculated columns", "partial",
                  "Filters, derived columns, joins, appends, dedupes and aggregates are recipe steps. Row-by-row "
                  "logic (RETAIN, arrays, FIRST./LAST., DO loops over rows) needs a rewrite as SQL or a calculated column."),
    "proc_sql": ("PROC SQL", "A SQL dataset on a connection, or a Dataflow", "native",
                 "SELECT queries run as-is on the source connection; CREATE TABLE becomes a Dataflow output."),
    "proc_means": ("PROC MEANS / SUMMARY", "KPI cards and aggregated tables", "native",
                   "Sum, mean, min, max, count, median and percentiles are widget aggregations."),
    "proc_freq": ("PROC FREQ", "Tables and bar charts of counts; pivot tables for cross-tabs", "native",
                  "Chi-square and other tests of independence are under Analyze → Statistics."),
    "proc_tabulate": ("PROC TABULATE", "Pivot table with subtotals and grand totals", "native", ""),
    "proc_report": ("PROC REPORT", "Table widget with totals, conditional formatting and page breaks", "native",
                    "COMPUTE blocks become calculated columns or display rules."),
    "proc_print": ("PROC PRINT", "Table widget", "native", ""),
    "proc_sort": ("PROC SORT", "Sorting in the widget, or a sort / dedupe recipe step", "native",
                  "NODUPKEY is the dedupe step."),
    "proc_transpose": ("PROC TRANSPOSE", "Pivot table for display; SQL for reshaping stored data", "partial",
                       "There is no unpivot recipe step: reshaping the stored rows needs SQL on the source."),
    "proc_import": ("PROC IMPORT", "File upload or a data connection", "native", ""),
    "proc_export": ("PROC EXPORT", "Widget and report export; scheduled deliveries", "native", ""),
    "proc_format": ("PROC FORMAT", "Column labels, value mappings (replace step) and bins", "partial",
                    "Ranged formats become calculated columns (CASE WHEN)."),
    "proc_append": ("PROC APPEND / DATASETS", "Append recipe step; Dataflow outputs", "partial",
                    "Library housekeeping (DELETE, RENAME, MODIFY) has no equivalent; datasets are managed in the app."),
    "graphs": ("SAS/GRAPH and ODS Graphics (SGPLOT, GCHART, GPLOT…)", "Chart widgets", "native",
               "Bar, line, area, scatter, box, histogram, heat map, waterfall and more."),
    "maps": ("PROC GMAP / SGMAP", "Map widgets (choropleth, points, bubbles) on the self-hosted basemap", "native", ""),
    "regression": ("PROC REG / GLM / LOGISTIC / GENMOD", "Analyze → Statistics (regression, GLM, logistic, mixed models); "
                   "prediction models to score new rows", "partial",
                   "Model output tables differ in layout; compare coefficients, not the printout."),
    "forecast": ("PROC FORECAST / ARIMA / ESM / TIMESERIES", "Forecast on line charts; forecast goals", "partial",
                 "Model families and options differ; reconcile the forecast values, not the method."),
    "descriptive": ("PROC UNIVARIATE / CORR / TTEST / NPAR1WAY", "Dataset profile; Analyze → Statistics "
                    "(correlation, group comparison, pairwise tests)", "partial", ""),
    "survival": ("PROC LIFETEST / PHREG", "Analyze → Statistics → survival", "partial", ""),
    "cluster": ("PROC FASTCLUS / CLUSTER / PRINCOMP", "Segmentation; PCA recipe step", "partial", ""),
    "macro": ("Macros (%MACRO, %LET, &variables)", "Report parameters", "partial",
              "Prompts and values substituted into a query are parameters. Macros that generate code need a rewrite."),
    "stored_process": ("Stored process (%STPBEGIN / prompts)", "A report with parameters, shared by link", "partial", ""),
    "ods": ("ODS output (PDF, Excel, HTML, RTF)", "Export and scheduled deliveries (PDF, Excel, CSV, image)", "native",
            "RTF has no equivalent; PDF replaces it."),
    "libname": ("LIBNAME", "Data connections", "native", "Each engine needs a connector; the inventory lists the librefs used."),
    "os_command": ("X / CALL SYSTEM / %SYSEXEC", "No equivalent", "manual",
                   "Datalytics does not run operating-system commands. Decide what the command did and who does it now."),
    "iml": ("PROC IML / OPTMODEL", "No equivalent", "manual", "Matrix programming and optimisation are out of scope."),
}

_PROC_KEY = {
    "sql": "proc_sql", "fedsql": "proc_sql", "means": "proc_means", "summary": "proc_means",
    "freq": "proc_freq", "surveyfreq": "proc_freq", "tabulate": "proc_tabulate", "report": "proc_report",
    "print": "proc_print", "sort": "proc_sort", "transpose": "proc_transpose", "import": "proc_import",
    "export": "proc_export", "format": "proc_format", "append": "proc_append", "datasets": "proc_append",
    "delete": "proc_append", "copy": "proc_append",
    "sgplot": "graphs", "sgpanel": "graphs", "sgscatter": "graphs", "sgrender": "graphs", "gchart": "graphs",
    "gplot": "graphs", "gbarline": "graphs", "boxplot": "graphs", "gcontour": "graphs",
    "gmap": "maps", "sgmap": "maps", "mapimport": "maps", "geocode": "maps",
    "reg": "regression", "glm": "regression", "logistic": "regression", "genmod": "regression",
    "glmselect": "regression", "mixed": "regression", "hpreg": "regression", "hplogistic": "regression",
    "forecast": "forecast", "arima": "forecast", "esm": "forecast", "timeseries": "forecast",
    "ucm": "forecast", "autoreg": "forecast", "hpf": "forecast",
    "univariate": "descriptive", "corr": "descriptive", "ttest": "descriptive", "npar1way": "descriptive",
    "rank": "descriptive", "stdize": "descriptive",
    "lifetest": "survival", "phreg": "survival",
    "fastclus": "cluster", "cluster": "cluster", "princomp": "cluster", "factor": "cluster",
    "iml": "iml", "optmodel": "iml",
}

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
# A comment statement: `* anything ;` at the start of a statement.
_STAR_COMMENT = re.compile(r"(^|;)\s*\*[^;]*;", re.M)
_MACRO_COMMENT = re.compile(r"%\*[^;]*;")
_PROC = re.compile(r"(?:^|;)\s*proc\s+([a-z_][a-z0-9_]*)", re.I | re.M)
# `data out;` / `data a.b (keep=x);` / `data _null_;` -- not `data=` (an option).
_DATA = re.compile(r"(?:^|;)\s*data\s+(?!=)[&a-z_]", re.I | re.M)
_MACRO = re.compile(r"%macro\b|%let\b|&[a-z_][a-z0-9_]*", re.I)
# A destination opened, not `ods pdf close;`.
_ODS = re.compile(r"(?:^|;)\s*ods\s+(pdf|excel|html5?|rtf|tagsets\.[a-z0-9_]+|powerpoint|csv)\b(?!\s*close\b)",
                  re.I | re.M)
_LIBNAME = re.compile(r"(?:^|;)\s*libname\s+([a-z_][a-z0-9_]{0,7})\s+(?!clear\b)", re.I | re.M)
_OS = re.compile(r"(?:^|;)\s*x\s+['\"]|\bcall\s+system\s*\(|%sysexec\b|\bpipe\s+['\"]", re.I | re.M)
_STP = re.compile(r"%stpbegin\b|%stpend\b", re.I)


def strip_comments(text: str) -> str:
    text = _BLOCK_COMMENT.sub(" ", text)
    text = _MACRO_COMMENT.sub(" ", text)
    return _STAR_COMMENT.sub(lambda m: m.group(1), text)


def feature_row(key: str, count: int = 1) -> dict:
    label, target, fit, note = FEATURES[key]
    return {"key": key, "label": label, "target": target, "fit": fit, "note": note, "count": count}


def scan_sas(text: str) -> dict:
    """What a SAS program uses: `features` (mapped, most used first),
    `unknown_procs` (PROCs the map does not cover, each a manual item),
    `libnames` (the librefs it opens) and its line count."""
    code = strip_comments(text or "")
    counts: dict[str, int] = {}
    unknown: dict[str, int] = {}

    def add(key: str, n: int = 1) -> None:
        if n:
            counts[key] = counts.get(key, 0) + n

    for m in _PROC.finditer(code):
        name = m.group(1).lower()
        key = _PROC_KEY.get(name)
        if key:
            add(key)
        else:
            unknown[name] = unknown.get(name, 0) + 1
    add("data_step", len(_DATA.findall(code)))
    add("macro", len(_MACRO.findall(code)))
    add("ods", len(_ODS.findall(code)))
    librefs = sorted({m.group(1).upper() for m in _LIBNAME.finditer(code)})
    add("libname", len(librefs))
    add("os_command", len(_OS.findall(code)))
    add("stored_process", len(_STP.findall(code)))

    features = [feature_row(k, n) for k, n in counts.items()]
    features.sort(key=lambda f: (-f["count"], f["key"]))
    features += [{"key": f"proc:{name}", "label": f"PROC {name.upper()}", "target": "Not in the feature map",
                  "fit": "manual", "note": "Decide by hand what replaces it.", "count": n}
                 for name, n in sorted(unknown.items())]
    return {"features": features, "unknown_procs": sorted(unknown), "libnames": librefs,
            "lines": (text or "").count("\n") + (1 if text else 0)}


def fit_summary(features: list[dict] | None) -> str | None:
    """The weakest fit among an item's features: what the whole item needs."""
    fits = {f.get("fit") for f in features or []}
    for fit in ("manual", "partial", "native"):
        if fit in fits:
            return fit
    return None


# ── the inventory spreadsheet ───────────────────────────────────────────────

KINDS = ("report", "program", "stored_process", "job", "dataset", "other")

#: Column headings an estate's own inventory tends to use, lower-cased.
_HEADINGS = {
    "name": ("name", "report", "report name", "program", "title", "item"),
    "kind": ("kind", "type", "object type"),
    "source_path": ("path", "location", "source path", "metadata path", "folder"),
    "owner": ("owner", "owner email", "business owner", "email"),
    "report": ("datalytics report", "target", "target report", "replacement", "new report"),
    "notes": ("notes", "note", "comments", "comment"),
    "source_system": ("system", "source system", "source"),
}

MAX_INVENTORY_ROWS = 5000


def _kind(value: str) -> str:
    v = (value or "").strip().lower().replace(" ", "_")
    aliases = {"stp": "stored_process", "stored": "stored_process", "code": "program", "sas": "program",
               "va_report": "report", "table": "dataset", "flow": "job", "schedule": "job"}
    v = aliases.get(v, v)
    return v if v in KINDS else ("report" if not v else "other")


def read_inventory(text: str) -> list[dict]:
    """Rows of an inventory CSV as {name, kind, source_path, owner, report,
    notes, source_system}; the separator is sniffed (comma, semicolon, tab).
    Raises ValueError when no column can be read as the item's name."""
    text = (text or "").lstrip("﻿")
    if not text.strip():
        raise ValueError("The file is empty")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    header = [h.strip().lower() for h in next(reader, [])]
    where: dict[str, int] = {}
    for field, names in _HEADINGS.items():
        for i, h in enumerate(header):
            if h in names and i not in where.values():
                where[field] = i
                break
    if "name" not in where:
        raise ValueError("No column says what the item is called: head one column Name (or Report, Program)")
    rows = []
    for raw in reader:
        if len(rows) >= MAX_INVENTORY_ROWS:
            raise ValueError(f"The inventory has more than {MAX_INVENTORY_ROWS} rows; split it")

        def cell(field: str) -> str:
            i = where.get(field)
            return raw[i].strip() if i is not None and i < len(raw) else ""
        name = cell("name")
        if not name:
            continue
        rows.append({"name": name[:300], "kind": _kind(cell("kind")),
                     "source_path": cell("source_path")[:1000] or None, "owner": cell("owner") or None,
                     "report": cell("report") or None, "notes": cell("notes") or None,
                     "source_system": (cell("source_system") or "SAS")[:40]})
    return rows
