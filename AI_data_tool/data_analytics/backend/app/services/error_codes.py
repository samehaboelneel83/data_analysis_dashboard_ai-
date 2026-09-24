"""The codes a widget-data error can carry, and the one way to raise one.

Before this the widget endpoint answered errors as ad hoc HTTPExceptions -- six
different things were a 400 -- and a SECOND channel carried a measure failure
as a 200 with `{"type": "error", "message": ...}` that nothing on the frontend
read. A widget cannot decide whether to offer "try again" from a status code
and a sentence. It can from a code.

This module is the SET only, pure data: a service may not import FastAPI
(test_layer_conformance), and the scheduler or a CLI must be able to name a
code without a request context. The exception that carries one lives in
`core/widget_errors.py`.

The contract, both channels:

    {"detail": <the same text as before>, "code": <one of WIDGET_ERROR_CODES>}

`detail` is unchanged and still a string, so nothing that reads it today
changes. `code` is additive. The set is closed: `widget_error` refuses a code
that is not in it, so a typo at a raise site is a failure where the author is
looking rather than a new undocumented code in production.
"""
from __future__ import annotations

#: Retryable: `source_unavailable` and `quota` (after Retry-After). Everything
#: else is a fact about the request or the data that will be the same fact a
#: second later.
WIDGET_ERROR_CODES = frozenset({
    "parameter",           # a report parameter is missing, unknown or the wrong type
    "unsupported",         # the feature does not exist here: a DirectQuery engine, an export format
    "forbidden_column",    # the widget references a column this role cannot see
    "forbidden",           # this role may not read the dataset at all
    "not_found",           # the dataset, or its file on disk
    "row_cap",             # the import row cap; names the size and the limit
    "source_unavailable",  # the customer's database could not be reached
    "export_disabled",     # exports are switched off for this dataset
    "export_no_data",      # this widget has nothing tabular to export
    "measure_error",       # a measure expression could not be evaluated (200 channel)
    "internal",            # ours; the generic 500
    "quota",               # the org's query quota for the day; Retry-After says when
    "semantic_veto",       # arithmetic on a year, coordinate or identifier (constitution rule 3)
})
