"""The child process that executes a script tile's code. Never imported.

Deliberately standalone: it imports pandas and the standard library and NOTHING
from this application. That is the point -- it is spawned with a scrubbed
environment by `script_tile.run_script`, so nothing in this process has ever
held a database URL, an API key, or a session. Importing app code here would
undo that by loading settings into the same interpreter as the author's script.

    python -I script_runner.py <input.pkl> <code.py> <output.pkl>

`-I` keeps the parent's PYTHONPATH and user site directory out of it, so an
attacker who can write a `sitecustomize.py` somewhere on the parent's path does
not get to run it here.

Contract: the code is executed with `df` in scope and must bind `result`.
Anything printed is captured and returned to the tile, because print() is how
anyone debugs one of these.
"""
import io
import json
import sys
import traceback
from contextlib import redirect_stdout


def main() -> int:
    in_path, code_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    import pandas as pd

    df = pd.read_pickle(in_path)
    with open(code_path, encoding="utf-8") as fh:
        code = fh.read()

    printed = io.StringIO()
    namespace: dict = {"df": df, "pd": pd}
    try:
        with redirect_stdout(printed):
            exec(compile(code, "<script tile>", "exec"), namespace)  # noqa: S102
    except SyntaxError as e:
        return _fail(out_path, f"Syntax error on line {e.lineno}: {e.msg}", printed)
    except Exception as e:
        # The traceback's last frame is the author's line; the frames above it
        # are this runner and would only be noise in a tile.
        return _fail(out_path, f"{type(e).__name__}: {e}", printed,
                     detail=traceback.format_exc(limit=1))

    if "result" not in namespace:
        return _fail(out_path,
                     "The script finished without setting `result`. Assign the "
                     "table, series or number you want the tile to show to a "
                     "variable called `result`.", printed)

    try:
        payload = _tabulate(namespace["result"], pd)
    except Exception as e:
        return _fail(out_path,
                     f"`result` is not something a tile can draw ({type(e).__name__}: {e}). "
                     f"Return a DataFrame, a Series or a single number.", printed)

    payload["stdout"] = printed.getvalue()[-4000:]
    payload["ok"] = True
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, default=str)
    return 0


#: What a tile can draw as a single cell. Anything else that is not a frame,
#: a series or something a frame can be built from is refused by name rather
#: than rendered as "<object object at 0x...>", which is the kind of
#: half-answer that looks like a bug in the product rather than in the script.
_SCALARS = (str, int, float, bool, bytes, type(None))


def _tabulate(result, pd) -> dict:
    if isinstance(result, pd.DataFrame):
        frame = result.reset_index() if result.index.name else result
    elif isinstance(result, pd.Series):
        frame = result.reset_index()
        frame.columns = [str(c) for c in frame.columns]
    elif isinstance(result, _SCALARS) or hasattr(result, "item") \
            or isinstance(result, pd.Timestamp):
        # A scalar answer is a legitimate tile: "how many orders breached SLA".
        # `hasattr(item)` catches numpy scalars without importing numpy here.
        frame = pd.DataFrame({"result": [result]})
    elif isinstance(result, (list, tuple, dict)):
        # Records or a column map: pandas decides whether it is tabular, and
        # says so in its own words when it is not.
        frame = pd.DataFrame(result)
    else:
        raise TypeError(f"a {type(result).__name__} is not a table, a series or "
                        f"a single value")
    columns = [str(c) for c in frame.columns]
    rows = json.loads(frame.to_json(orient="values", date_format="iso"))
    return {"columns": columns, "rows": rows}


def _fail(out_path: str, message: str, printed: io.StringIO,
          detail: str | None = None) -> int:
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"ok": False, "error": message, "detail": detail,
                   "stdout": printed.getvalue()[-4000:]}, fh)
    return 1


if __name__ == "__main__":
    sys.exit(main())
