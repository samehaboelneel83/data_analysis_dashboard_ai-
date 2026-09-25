"""Reading Microsoft Access databases (.mdb / .accdb) through mdbtools.

Layer 1 -- the same layer as `connections.py`, for the same reason: this reaches
an external system through a driver. It happens to shell out to a CLI instead of
opening a SQLAlchemy engine, which changes the mechanism, not the layer. It must
not import `ingest`, `frame_cache`, or anything above.

**Why a subprocess and not a driver.** Microsoft's ACE/Jet OLEDB provider is
Windows-only, and the backend is a Linux container, so the ODBC route
(pyodbc + sqlalchemy-access) cannot work in the shipped deployment at all.
mdbtools is the only option that reads Access on Linux without a JVM; Debian
bookworm -- what `python:3.12-slim` is built on -- ships 1.0.0, the release that
added real .accdb support.

**What that buys, honestly:**

  works       .mdb  (Access 97 / 2000 / 2002 / 2003 -- Jet 3 and Jet 4)
              .accdb (Access 2007 through 2021/365)
  refuses     password-protected or encrypted files. Access 2007+ uses real
              AES; no open-source tool decrypts it, and pretending otherwise
              would turn a clear error into a confusing one.
  read-only   nothing here writes back to an .mdb.
  no SQL      mdbtools has no usable query engine (`mdb-sql` is an interactive
              shell), so Access is import-only: DirectQuery is impossible and
              the connector declares sql_family=None to say so.

`pandas_access` was considered and rejected: it is an unmaintained wrapper over
these same binaries, adds a wheel to an air-gapped image, and would hide the one
seam that makes this module testable without the binary installed.
"""
from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path

import pandas as pd

#: Access keeps its own catalogue in tables named MSysObjects, MSysQueries and
#: friends. They are implementation detail, never what someone uploading a
#: database wants as a dataset.
_SYSTEM_PREFIXES = ("msys", "~")

#: A corrupt or pathological file must not hold a worker forever.
_TIMEOUT_SECONDS = 120

_SUFFIXES = {".mdb", ".accdb"}


class MdbUnavailable(RuntimeError):
    """mdbtools is not installed on this host."""


class MdbReadError(RuntimeError):
    """The file could not be read: wrong format, encrypted, or corrupt."""


def mdbtools_available() -> bool:
    """Whether the binaries this module drives are on PATH.

    Checked at call time, never at import: the module must import cleanly on a
    Windows dev box so that the only symptom is a clear 400 on an Access
    request, not a crash at startup for everyone.
    """
    return (shutil.which("mdb-tables") is not None
            and shutil.which("mdb-export") is not None)


def _validated_path(path: str) -> str:
    """Resolve `path` and confirm it is an Access file we can try to read.

    NOT a sandbox, and must not be mistaken for one. A `filepath` connector can
    already reach any file the server process can read -- that is true of the
    existing `sqlite` connector too, and is a property of file-path data sources
    generally. This check exists so that a typo or a wrong-format file produces
    a clear error instead of mdbtools' output being parsed as CSV.
    """
    p = Path(path).resolve()
    if p.suffix.lower() not in _SUFFIXES:
        raise MdbReadError(
            f"Not a Microsoft Access file: {p.name} "
            f"(expected {' or '.join(sorted(_SUFFIXES))})")
    if not p.is_file():
        raise MdbReadError(f"File not found: {p}")
    return str(p)


def _run_cli(args: list[str]) -> bytes:
    """Run one mdbtools command and return its stdout.

    The single seam in this module: tests monkeypatch THIS, not
    `subprocess.run`, so they exercise the parsing and filtering above without
    needing mdbtools installed.

    `args` is passed as a list and `shell` is left at its default of False, so a
    path containing `;`, `&&` or `$(...)` is one argv element and cannot be
    interpreted as anything else.
    """
    if not mdbtools_available():
        raise MdbUnavailable(
            "Microsoft Access support requires mdbtools, which is not installed "
            "on this server.")
    try:
        proc = subprocess.run(args, capture_output=True,
                              timeout=_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        raise MdbReadError(
            f"Reading the Access file timed out after {_TIMEOUT_SECONDS}s; "
            f"it may be corrupt.")
    if proc.returncode != 0:
        raise MdbReadError(_explain(proc.stderr))
    return proc.stdout


def _explain(stderr: bytes) -> str:
    """Turn mdbtools' stderr into something a user can act on."""
    msg = stderr.decode("utf-8", "replace").strip()
    low = msg.lower()
    if "password" in low or "encrypt" in low or "crypt" in low:
        return ("This Access file is password-protected. Open it in Access and "
                "save an unencrypted copy, then upload that -- encrypted "
                "databases cannot be read on the server.")
    return msg[:500] or "mdbtools could not read this file"


def _decode(raw: bytes) -> str:
    """Text out of mdbtools.

    Jet 4 and ACE files are UTF-8, but legacy Jet 3 databases carry a Windows
    codepage. cp1252 is the overwhelmingly common one and decodes every byte, so
    it is a safe last resort rather than a guess that can fail. Deliberately not
    doing codepage sniffing.
    """
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", "replace")


def list_tables(path: str) -> list[str]:
    """The user tables in an Access database, in file order."""
    out = _run_cli(["mdb-tables", "-1", _validated_path(path)])
    return [t for t in (line.strip() for line in _decode(out).splitlines())
            if t and not t.lower().startswith(_SYSTEM_PREFIXES)]


def read_table(path: str, table: str) -> pd.DataFrame:
    """One Access table as a DataFrame.

    `-D` pins the datetime format: without it mdbtools emits the host locale's
    rendering, so the same database would parse differently on two machines.
    """
    out = _run_cli(["mdb-export", "-D", "%Y-%m-%d %H:%M:%S",
                    _validated_path(path), table])
    try:
        return pd.read_csv(io.StringIO(_decode(out)))
    except pd.errors.EmptyDataError:
        return pd.DataFrame()      # a table with no rows is not an error
    except Exception as e:
        raise MdbReadError(f"Could not parse table {table!r}: {e}")
