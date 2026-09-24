"""Where an uploaded file goes on disk, and what it may be called.

Layer 2. Split out of `routers/datasets.py`, which derived the save path from
the client-supplied filename:

    file_path = upload_dir / (file.filename or "upload")

Two things were wrong with that, both verified rather than assumed.

**Arbitrary file write.** Neither Starlette nor python_multipart sanitises the
filename in a multipart part; it reaches the handler verbatim. A filename of
`../../../../tmp/pwned.csv` walks out of `upload_dir`, and an absolute one is
worse -- `Path("/app/uploads") / "/abs/evil.csv"` is `/abs/evil.csv`, because
pathlib discards the left operand when the right is absolute. That value went
straight into `open(path, "wb")`, so any authenticated user could write a file
anywhere the server process could.

**Cross-org collision.** `upload_dir` was flat and global, so org A's `sales.csv`
and org B's `sales.csv` were the same bytes on disk: two Dataset rows, one file.
Deleting either unlinked the other's data, and the survivor rendered nothing.

Both die the same way: the client filename is used ONLY for its extension, never
as a path component, and the stored name is a UUID under a per-org directory.

The extension has to survive, which is why this isn't just `uuid4().hex`:
`frame_cache._parse` dispatches on the suffix, and the parquet sidecar is written
only for `.csv`.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pandas as pd

from ..core.config import settings

#: Formats that are containers of many tables rather than a single frame, and so
#: are NOT in `ingest.SUPPORTED` -- one .mdb yields N datasets, which that
#: dict's suffix -> reader -> one-DataFrame shape cannot express. They are
#: nonetheless legal to upload; the router routes them to the Access path.
CONTAINER_SUFFIXES = {".mdb", ".accdb"}


def storage_root(org_id: int) -> Path:
    """The directory this org's uploads live in.

    Per-org, so two organisations uploading a file with the same name cannot
    reach each other's bytes even before the UUID naming below.
    """
    return Path(settings.upload_dir) / f"org_{org_id}"


def allowed_suffixes() -> set[str]:
    """Extensions an upload may carry.

    Read from `ingest.SUPPORTED` at CALL time, not import time, so the optional
    dependency idiom there (`.parquet` only when pyarrow imports, `.xml` only
    when lxml does) still decides what is accepted.
    """
    from .ingest import SUPPORTED
    return set(SUPPORTED) | CONTAINER_SUFFIXES


def allowed_suffix(filename: str | None) -> str:
    """The validated, lowercased extension of `filename`.

    Raises ValueError for anything unsupported. The message is deliberately the
    same one `frame_cache._parse` raises -- tests assert on "Unsupported file
    type", and matching it lets the check move earlier (before any bytes are
    written) without rewriting them.
    """
    suffix = Path(filename or "").suffix.lower()
    if suffix not in allowed_suffixes():
        raise ValueError(f"Unsupported file type: {suffix or filename or '(none)'}")
    return suffix


def allocate_path(org_id: int, filename: str | None) -> Path:
    """A fresh, unused path for this org to store `filename`'s bytes at.

    The caller's name contributes ONLY its extension. Traversal sequences,
    absolute paths and directory separators cannot survive `Path(...).suffix`,
    so no input to this function can produce a path outside `storage_root`.

    The UUID stem also means an org uploading `sales.csv` twice gets two
    independent files, where before the second silently overwrote the first.
    """
    ext = allowed_suffix(filename)
    root = storage_root(org_id)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{uuid4().hex}{ext}"


def concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Append several uploads into one frame.

    `sort=False` gives the union of columns in first-seen order, with NaN where
    a file did not carry a column. That is deliberately laxer than requiring
    identical headers: monthly extracts routinely gain a trailing column, and
    refusing those would make the feature useless for its main use case.

    A column whose dtype differs between files becomes `object`, which
    `detect_types` then reports as text. Lossy, but correct -- and far better
    than guessing which file's type was intended.
    """
    return pd.concat(frames, ignore_index=True, sort=False)
