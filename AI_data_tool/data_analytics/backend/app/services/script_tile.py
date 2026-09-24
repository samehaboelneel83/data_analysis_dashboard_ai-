"""A tile that runs server-side Python and shows what it returns.

SAS's Job content object runs code on the server and embeds its output on a
report. This is that feature, and it is exactly as dangerous as it sounds, so
the design says out loud what it does and does not protect:

**It is not a sandbox.** The script runs as the server user. It can read any
file the server can read and open any socket the server can open. Nothing here
changes that, and nothing here pretends to. What it DOES do is keep the blast
radius away from the two things that are cheap to protect and catastrophic to
lose:

  * **A subprocess, never `exec()` inside the API worker.** The worker holds the
    database session, the cached frames and every credential in `os.environ`.
    Running author code there is not a weak sandbox; it is handing over the
    secrets in the first line of the script.

  * **A scrubbed environment.** The child inherits PATH and the OS essentials
    and nothing else -- no DATABASE_URL, no model API keys. Pinned by a test,
    because this is the property most likely to rot without anyone noticing.

  * **A timeout and a row cap.** A tile that never returns would otherwise take
    a worker with it, and one that returns ten million rows would take the
    browser.

Because it is not a sandbox, **authoring is admin-only** -- gated in the router,
tested there. Offering a script tile is offering a shell, and the only honest
way to ship it is to say so and restrict who may write one. Viewers run what an
admin already wrote, which is the same trust model as a saved SQL view.

The frame arrives already secured: RLS, column rules and dataset filters are
applied by the caller before this is reached, so a script sees exactly the rows
the requesting user may see, not the table.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time

import pandas as pd

#: A tile is a query with a bit of logic, not an ETL job. Past this the answer
#: is a prep pipeline or a materialised dataset.
MAX_CODE_CHARS = 20_000
#: Rows sent INTO the script. A bigger frame means a slower pickle and a longer
#: hold on the worker, and no tile reads a million rows.
MAX_INPUT_ROWS = 200_000
#: Rows the tile will draw. Anything past this is truncated and SAID to be.
MAX_OUTPUT_ROWS = 5_000
#: Long enough for real work, short enough that a runaway script is noticed by
#: whoever wrote it rather than by the on-call engineer.
TIMEOUT_SECONDS = 20
MAX_TIMEOUT_SECONDS = 120

#: The only variables the child keeps. Everything else -- DATABASE_URL, the
#: model keys, the object-store credentials -- is dropped on the floor.
_KEEP_ENV = ("PATH", "SYSTEMROOT", "SystemRoot", "COMSPEC", "ComSpec",
             "WINDIR", "windir", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL",
             "HOME", "USERPROFILE")

_RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "script_runner.py")


class ScriptError(ValueError):
    """The script would not run, or would not produce something drawable."""


def _child_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in _KEEP_ENV}
    env["PYTHONIOENCODING"] = "utf-8"
    # No user site-packages and no PYTHONPATH: a writable directory on the
    # parent's path must not become a way to run code in every script tile.
    env["PYTHONNOUSERSITE"] = "1"
    return env


def run_script(df: pd.DataFrame, code: str,
               timeout: int = TIMEOUT_SECONDS) -> dict:
    """Run `code` over `df` in a separate process and return what it produced."""
    body = (code or "").strip()
    if not body:
        raise ScriptError("There is no code to run.")
    if len(body) > MAX_CODE_CHARS:
        raise ScriptError(
            f"At most {MAX_CODE_CHARS:,} characters of code. A tile is a query "
            f"with some logic in it; anything larger belongs in a prep pipeline "
            f"or a materialised dataset.")
    seconds = max(1, min(int(timeout or TIMEOUT_SECONDS), MAX_TIMEOUT_SECONDS))

    # Declared, not silent: a script summing a column over the first 200,000 of
    # 900,000 rows returns a number that is simply wrong, and the tile has to
    # say so rather than let it read as the total.
    input_truncated = len(df) > MAX_INPUT_ROWS
    frame = df.head(MAX_INPUT_ROWS) if input_truncated else df
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="script-tile-") as work:
        in_path = os.path.join(work, "input.pkl")
        code_path = os.path.join(work, "code.py")
        out_path = os.path.join(work, "output.json")
        # A copy, not the caller's frame: the child gets its own pickle anyway,
        # and copying makes that explicit rather than incidental.
        frame.copy().to_pickle(in_path)
        with open(code_path, "w", encoding="utf-8") as fh:
            fh.write(body)

        try:
            completed = subprocess.run(
                [sys.executable, "-I", _RUNNER, in_path, code_path, out_path],
                env=_child_env(), cwd=work, capture_output=True, text=True,
                timeout=seconds,
            )
        except subprocess.TimeoutExpired:
            raise ScriptError(
                f"The script was still running after {seconds} seconds and was "
                f"stopped. A tile has to answer while someone is looking at it.")

        if not os.path.exists(out_path):
            # The child died before it could write anything: a segfault, a
            # MemoryError, an os._exit(). Its stderr is the only evidence.
            stderr = (completed.stderr or "").strip()[-1000:]
            raise ScriptError(
                "The script stopped without returning anything"
                + (f": {stderr}" if stderr else "."))
        with open(out_path, encoding="utf-8") as fh:
            payload = json.load(fh)

    if not payload.get("ok"):
        raise ScriptError(payload.get("error") or "The script failed.")

    rows = payload.get("rows") or []
    truncated = len(rows) > MAX_OUTPUT_ROWS
    return {
        "kind": "script",
        "columns": payload.get("columns") or [],
        "rows": rows[:MAX_OUTPUT_ROWS],
        "stdout": payload.get("stdout") or "",
        "truncated": truncated,
        "row_count": len(rows),
        "rows_in": int(len(frame)),
        "input_truncated": input_truncated,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }
