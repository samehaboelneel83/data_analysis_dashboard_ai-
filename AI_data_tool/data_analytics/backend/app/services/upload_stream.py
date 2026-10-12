"""A CSV upload too large to parse in memory is turned into the dataset's
file a chunk at a time -- the same writer a large database import uses
(connections._stream_to_parquet), so memory stays at about one chunk and the
dataset is kept as a parquet file.

What differs from a small upload, and is said in the plan: the dialect
(separator, encoding, decimal commas) is decided on the start of the file and
the first chunk, not on every row."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def wanted(path, size: int) -> bool:
    """Whether this upload is streamed: a CSV at or past the configured size,
    or one that would not fit in memory parsed whole."""
    from ..core.config import settings
    if Path(path).suffix.lower() != ".csv":
        return False
    from_mb = int(getattr(settings, "upload_stream_mb", 0) or 0)
    if from_mb <= 0:
        return False
    if size >= from_mb * 1024 * 1024:
        return True
    from . import memory_guard
    try:
        memory_guard.check(str(path))
    except memory_guard.TooLargeToLoad:
        return True
    return False


def csv_to_parquet(path, stream_dir: str):
    """`connections.Streamed` for the CSV at `path`. Blocking."""
    from . import connections, csv_dialect as cd
    from .ingest import detect_types
    from .timezones import normalize_instants
    path = Path(path)
    with open(path, "rb") as f:
        head = f.read(cd._SAMPLE_BYTES)
    encoding = "utf-8-sig" if cd._is_utf8(path) else cd._legacy_encoding(path)
    sep = cd._separator(head.decode(encoding, errors="replace"))
    decimal: list[str] | None = None

    def prepare(chunk: pd.DataFrame) -> pd.DataFrame:
        nonlocal decimal
        if decimal is None:
            decimal = cd._decimal_comma_columns(chunk) if sep != "," else []
        for c in decimal:
            if c in chunk.columns and chunk[c].dtype == object:
                chunk[c] = pd.to_numeric(chunk[c].astype(str).str.replace(",", ".", regex=False).str.strip(),
                                         errors="coerce")
        normalize_instants(chunk)
        detect_types(chunk)
        return chunk

    with pd.read_csv(path, sep=sep, encoding=encoding, chunksize=connections.CHUNK_ROWS) as reader:
        return connections._stream_to_parquet([], reader, 0, stream_dir, prepare, 0)
