"""Turn an uploaded CSV into the one dialect every reader here assumes.

Layer 2 (ingestion). Every reader of a stored CSV -- pandas in the frame cache,
DuckDB pushdown, the refresh path -- reads UTF-8 with commas and a dot for the
decimal. A file in any other dialect was not refused: a semicolon file became
ONE column called "a;b;c" that looked like a dataset, and an Arabic export
from Excel (Windows-1256) failed with a UnicodeDecodeError naming a byte.

Rather than teach every reader to sniff (and hope they agree), the upload is
rewritten once, at ingest, into the canonical dialect. A file already in it
is left byte-for-byte alone.
"""
from __future__ import annotations

import codecs
import os
import re
from pathlib import Path

import pandas as pd

_CANDIDATE_SEPS = (",", ";", "\t", "|")
_SAMPLE_BYTES = 64 * 1024
_BOM = codecs.BOM_UTF8
_ARABIC = re.compile(r"[؀-ۿ]")
_DECIMAL_COMMA = re.compile(r"^\s*-?\d+,\d+\s*$")


def _is_utf8(path: Path) -> bool:
    """Validated over the WHOLE file, streamed: one Windows-1256 letter on the
    last line is enough to break every later read."""
    dec = codecs.getincrementaldecoder("utf-8")()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                dec.decode(chunk)
        dec.decode(b"", final=True)
        return True
    except UnicodeDecodeError:
        return False


def _high_bytes(path: Path, limit: int = 20_000) -> bytes:
    """The non-ASCII bytes of the whole file (up to `limit`): only they tell
    code pages apart, and the head of a file often has none."""
    out = bytearray()
    with open(path, "rb") as f:
        while (chunk := f.read(1024 * 1024)) and len(out) < limit:
            out.extend(b for b in chunk if b > 127)
    return bytes(out[:limit])


def _legacy_encoding(path: Path) -> str:
    """Not UTF-8: which single-byte code page? Windows-1256 when its non-ASCII
    bytes decode mostly to Arabic letters (this product's first users), else
    Windows-1252, the Western default; latin-1 as the never-failing floor."""
    high = _high_bytes(path)
    text = high.decode("cp1256", errors="replace")
    if text and sum(bool(_ARABIC.match(c)) for c in text) / len(text) > 0.5:
        return "cp1256"
    try:
        high.decode("cp1252")
        return "cp1252"
    except UnicodeDecodeError:
        return "latin-1"


def _separator(text: str) -> str:
    """The delimiter that splits the leading lines into the same number of
    fields, most fields winning; a comma on any tie. Quoted fields are
    stripped first so a comma inside "Cairo, Egypt" is not counted."""
    lines = [ln for ln in text.splitlines()[:20] if ln.strip()]
    if len(lines) > 1 and not text.endswith(("\n", "\r")):
        lines = lines[:-1]          # the sample may cut the last line short
    lines = [re.sub(r'"[^"]*"', '""', ln) for ln in lines]
    best, best_n = ",", 0
    for sep in _CANDIDATE_SEPS:
        counts = {ln.count(sep) for ln in lines}
        if len(counts) == 1 and (n := counts.pop()) > best_n:
            best, best_n = sep, n
    return best


def _decimal_comma_columns(df: pd.DataFrame) -> list[str]:
    out = []
    for c in df.columns:
        s = df[c].dropna()
        if s.dtype == object and len(s) and s.astype(str).str.match(_DECIMAL_COMMA).all():
            out.append(c)
    return out


def canonicalize_csv(path) -> dict | None:
    """Rewrite `path` as UTF-8, comma-separated, dot-decimal, if it is not.

    Returns what was found ({"encoding", "separator", "decimal_comma"}) when the
    file was rewritten, None when it was already canonical and untouched. The
    rewrite is atomic (temp file + rename), so a failure leaves the original.
    """
    path = Path(path)
    with open(path, "rb") as f:
        sample = f.read(_SAMPLE_BYTES)
    has_bom = sample.startswith(_BOM)
    encoding = "utf-8-sig" if _is_utf8(path) else _legacy_encoding(path)
    text = sample.decode(encoding, errors="replace")
    sep = _separator(text)
    if encoding == "utf-8-sig" and not has_bom and sep == ",":
        return None

    df = pd.read_csv(path, sep=sep, encoding=encoding)
    # A semicolon file is the European convention, where the decimal is a
    # comma: "1,5" left as text would make a measure a category. Converted
    # only where EVERY value in the column has that shape.
    decimal_cols = _decimal_comma_columns(df) if sep != "," else []
    for c in decimal_cols:
        df[c] = pd.to_numeric(df[c].str.replace(",", ".", regex=False).str.strip(), errors="coerce")
    tmp = path.with_name(path.name + ".tmp")
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)
    return {"encoding": encoding.replace("utf-8-sig", "utf-8"), "separator": sep,
            "decimal_comma": decimal_cols}
