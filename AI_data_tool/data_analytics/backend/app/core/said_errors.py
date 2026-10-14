"""A refusal that reaches the browser in the reader's language.

The analysis services refuse with a ValueError whose message is a keyed
sentence (`services/readback.Said`): English as text, plus the key and pieces
the browser's catalogue renders (`rb.<key>`). `refused()` keeps both on the way
out, so the response is `{"detail": <English>, "detail_i18n": {key, vars}}`.
An error with an ordinary message comes out exactly as before.
"""
from __future__ import annotations

from fastapi import HTTPException

from ..services.readback import Said


class SaidHTTPException(HTTPException):
    def __init__(self, status_code: int, said: Said):
        super().__init__(status_code=status_code, detail=str(said))
        self.detail_i18n = said.as_i18n()


def refused(status_code: int, error: BaseException) -> HTTPException:
    """The HTTP form of a service's refusal -- `raise refused(400, e)`."""
    said = error.args[0] if error.args else None
    if isinstance(said, Said):
        return SaidHTTPException(status_code, said)
    return HTTPException(status_code, str(error))
