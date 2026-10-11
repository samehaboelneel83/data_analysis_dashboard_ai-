"""Refuse to load what this machine cannot hold.

With the import limit at 200,000,000 rows the limit no longer protects the
host: a file well under it can still be several times the machine's memory.
Loading it used to end the server process -- for everyone, with nothing said.
This looks BEFORE a whole dataset is read into memory: how much it would take
(from the file's own footer, no row read) against what is free, and refuses
with a sentence when it does not fit.

Charts that are computed without loading the rows (the DuckDB aggregate path,
a live connection) never come here, so they keep working at any size. What
this stops is the paths that need every row in memory at once.
"""
from __future__ import annotations

import contextlib
import os
import threading
from pathlib import Path

#: A CSV in memory, per byte on disk (measured: about 4.5x, PLAN.md §AG).
CSV_FACTOR = 4.5
#: Bytes one value takes in a pandas frame, by the parquet column's physical
#: type. Text is a pointer per row plus the text itself, which pandas shares
#: between equal values -- so a column of a few repeated names costs little
#: more than its pointers, and a column of distinct text costs its text
#: several times over (a Python string carries about 49 bytes of its own).
_FIXED = {"BOOLEAN": 1, "INT32": 4, "INT64": 8, "INT96": 8, "FLOAT": 4, "DOUBLE": 8}
_POINTER = 8
_TEXT_OVERHEAD = 3.0
READ_PEAK = 2.3
#: The frame cache keeps one parsed copy and hands each caller a private one.
COPIES = 2


class TooLargeToLoad(Exception):
    """The dataset does not fit in this machine's free memory."""

    def __init__(self, needed: int, free: int, rows: int | None = None):
        self.needed, self.free, self.rows = needed, free, rows
        size = f"about {needed / 1e9:.1f} GB are needed and {free / 1e9:.1f} GB are free"
        many = f" ({rows:,} rows)" if rows else ""
        super().__init__(
            f"This dataset is too large to load into memory on this server{many}: {size}. "
            "Charts that total, count or average by a column are computed without loading it and still work. "
            "For this one, filter or aggregate the dataset first, or use a live connection.")


def _cgroup_free() -> int | None:
    """Free memory inside this container's own limit, when it has one."""
    try:
        limit = Path("/sys/fs/cgroup/memory.max").read_text().strip()
        if limit == "max":
            return None
        used = int(Path("/sys/fs/cgroup/memory.current").read_text().strip())
        return max(int(limit) - used, 0)
    except (OSError, ValueError):
        return None


def free_bytes() -> int | None:
    """Memory this process could still take: the smaller of what the machine
    has available and what the container's limit leaves. None when unknown."""
    found = []
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                found.append(int(line.split()[1]) * 1024)
                break
    except (OSError, ValueError, IndexError):
        pass
    limited = _cgroup_free()
    if limited is not None:
        found.append(limited)
    return min(found) if found else None


def estimate(path: str) -> tuple[int, int | None]:
    """(bytes a full load would take, rows when the file says) -- from the
    file's size and footer; no row is read."""
    p = Path(path)
    if p.suffix.lower() == ".parquet":
        import pyarrow.parquet as pq
        meta = pq.ParquetFile(p).metadata
        total = 0.0
        for g in range(meta.num_row_groups):
            group = meta.row_group(g)
            for c in range(group.num_columns):
                col = group.column(c)
                fixed = _FIXED.get(col.physical_type)
                if fixed is not None:
                    total += fixed * group.num_rows
                else:
                    # Stored text is already one copy per distinct value where the
                    # writer used a dictionary, which is what pandas ends up holding.
                    total += _POINTER * group.num_rows + col.total_uncompressed_size * _TEXT_OVERHEAD
        # While it is read, the file's own buffers and the frame exist together:
        # measured at 20,000,000 rows, the process peaked at 2.3x the frame.
        return int(total * (READ_PEAK + COPIES - 1)), int(meta.num_rows)
    return int(os.path.getsize(p) * CSV_FACTOR) * COPIES, None


def share() -> float:
    from ..core.config import settings
    return float(getattr(settings, "load_memory_share", 0.6) or 0.0)


#: Loads that have been let through and are still being read, in bytes. Four
#: people opening four large datasets at once each saw the same free memory
#: and each passed alone; together they did not fit. What is promised to a
#: load in progress is no longer free for the next one.
_LOCK = threading.Lock()
_RESERVED = 0


@contextlib.contextmanager
def reserved(path: str):
    """`check`, and the room kept for this load until it has finished:

        with memory_guard.reserved(path):
            frame = read(path)
    """
    global _RESERVED
    allowed = share()
    free = free_bytes() if allowed > 0 else None
    needed, rows = 0, None
    if free is not None:
        try:
            needed, rows = estimate(path)
        except Exception:                                   # noqa: BLE001 -- unreadable: the load reports it
            needed = 0
    with _LOCK:
        if free is not None and needed and needed + _RESERVED > free * allowed:
            raise TooLargeToLoad(needed, max(free - _RESERVED, 0), rows)
        _RESERVED += needed
    try:
        yield
    finally:
        with _LOCK:
            _RESERVED -= needed


def check(path: str) -> None:
    """Raise TooLargeToLoad when loading `path` whole would take more than the
    allowed share of the free memory (settings.load_memory_share; 0 = never
    refuse). A file that cannot be measured is let through: the load itself
    will say what is wrong with it."""
    allowed = share()
    if allowed <= 0:
        return
    free = free_bytes()
    if free is None:
        return
    try:
        needed, rows = estimate(path)
    except Exception:                                       # noqa: BLE001 -- unreadable: the load reports it
        return
    if needed > free * allowed:
        raise TooLargeToLoad(needed, free, rows)
