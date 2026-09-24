"""The HTTPException that carries a widget error code, and the one way to raise it.

The codes themselves are `services/error_codes.WIDGET_ERROR_CODES` -- pure
data, so a service can name one without importing FastAPI. This module is
the Layer 6 half: it knows about status codes, and lives beside
`capability.py` and `org_scope.py`, which raise HTTPException from core for
the same reason.

The contract the handler in main.py writes, on every widget error:

    {"detail": <the same text as before>, "code": <one of WIDGET_ERROR_CODES>}

`detail` stays a string, so nothing that reads it today changes. `code` is
additive. `widget_error` refuses a code not in the set, so a typo at a raise
site fails where the author is looking rather than becoming an undocumented
code in production.
"""
from __future__ import annotations

from fastapi import HTTPException

from ..services.error_codes import WIDGET_ERROR_CODES


class CodedHTTPException(HTTPException):
    """An HTTPException that also knows what kind of failure it is.

    A subclass rather than a dict in `detail`, so `detail` stays the string
    every existing reader expects; the handler in main.py writes the code
    beside it.
    """

    def __init__(self, status_code: int, code: str, detail: str):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code


def widget_error(status_code: int, code: str, detail: str) -> CodedHTTPException:
    """The one way the widget path raises. `raise widget_error(413, "row_cap", msg)`."""
    if code not in WIDGET_ERROR_CODES:
        raise ValueError(f"{code!r} is not a widget error code; add it to "
                         "WIDGET_ERROR_CODES with a comment saying what it means")
    return CodedHTTPException(status_code, code, detail)
