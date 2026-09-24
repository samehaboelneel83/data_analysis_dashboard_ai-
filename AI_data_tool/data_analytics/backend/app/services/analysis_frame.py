"""One bounded, secured frame for analysis — whichever mode the dataset is in.

WHY THIS EXISTS
---------------
Six endpoints carried the same refusal: "these run over import-mode datasets".
It read like a statement about analysis and was really a statement about
plumbing. Every detector in `insights.py` and every one of the 24 analyses in
`analysis/registry.py` takes a pandas DataFrame; none of them cares where the
rows came from. The only thing missing was a way to GET a frame out of a live
source, and `direct_query` has had the parts since it shipped.

So the guard was on the wrong axis. It refused by MODE, when what decides
feasibility is SIZE: a 112,650-row DirectQuery table is trivially analysable and
was refused, while a 60-million-row import dataset sails through and is not.
This module asks the question that actually matters -- how many rows are there
-- and answers it before deciding.

WHAT IT REFUSES TO PRETEND
--------------------------
Below the cap, the frame is every matching row and any figure computed from it
is exact. Above it, `direct_query` fetches a RANDOM sample (ordered by the
dialect's random function, never an arbitrary prefix) and the figures become
estimates.

`insights.py` promises "every number is computed here, never guessed". A sampled
share presented without that word would break the promise quietly, which is
worse than the refusal this replaces. So provenance travels WITH the frame and
callers are expected to show it.

NO FastAPI HERE
---------------
`tests/test_layer_conformance.py` forbids it. Failures raise plain exceptions and
the routers decide what status they deserve.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..core.config import settings
from ..models.models import DataSource, Dataset


class FrameUnavailable(Exception):
    """The rows could not be obtained, with a reason worth showing a person.

    Distinct from a bug: every raise here is a condition the reader can act on
    -- an unsupported engine, a source that is gone, a table too large to pull.
    """


@dataclass
class AnalysisFrame:
    """Rows to analyse, and an honest account of what they represent."""
    frame: pd.DataFrame
    #: "import" | "directquery" -- where the rows came from.
    origin: str
    #: Rows the analysis actually saw.
    rows_analysed: int
    #: Rows that exist. Equal to `rows_analysed` unless sampled.
    total_rows: int
    #: True when `frame` is a random subset. The one field a caller must not
    #: drop on the floor.
    sampled: bool = False

    @property
    def exact(self) -> bool:
        return not self.sampled

    def describe(self) -> str:
        """One sentence a UI can print without further interpretation."""
        if self.origin == "import":
            return f"Measured over all {self.rows_analysed:,} rows."
        if self.sampled:
            return (f"Measured live over a random sample of "
                    f"{self.rows_analysed:,} of {self.total_rows:,} rows.")
        return f"Measured live over all {self.total_rows:,} rows."


def analysis_row_cap() -> int:
    """How many rows an analysis will pull from a live source.

    Separate from the widget row cap (10,000), which sizes a scatter plot, and
    from the import cap (2,000,000), which sizes a file on disk. Analysis sits
    between the two: statistics over 10,000 rows of a 112,650-row table would be
    a needless estimate, and pulling millions across the wire to compute a mean
    is not analysis, it is a download.
    """
    return int(getattr(settings, "analysis_row_cap", 250_000) or 250_000)


async def load_directquery_frame(
    db, dataset: Dataset, *, rls_filter_expr: str | None = None,
    denied: set[str] | None = None, row_cap: int | None = None,
) -> AnalysisFrame:
    """Pull a DirectQuery dataset's rows into a frame, bounded and secured.

    Row-level security is pushed down with the query rather than applied to the
    frame afterwards, which is why this adds no `apply_rls_filter` call site --
    `tests/test_rls_base_frame_choke_point.py` allowlists those, and the right
    number of new ones is zero.

    Denied columns are dropped from the frame on arrival. They are not excluded
    from the SELECT because the fetch is `SELECT *` by design (shapers ignore
    what they do not need); dropping here is the same thing the import path does
    and keeps one rule in one shape.
    """
    import asyncio

    from .direct_query import (DirectQueryUnsupported, SourceUnavailable,
                               fetch_analysis_frame)

    if dataset.data_source_id is None:
        raise FrameUnavailable(
            "This dataset has no connection behind it, so there is nothing to query.")

    source = await db.get(DataSource, dataset.data_source_id)
    if source is None:
        raise FrameUnavailable("The connection behind this dataset no longer exists.")

    cfg = dict(source.config or {})
    cfg["type"] = source.type

    try:
        got = await asyncio.to_thread(
            fetch_analysis_frame, cfg, dataset,
            rls_filter_expr=rls_filter_expr,
            row_cap=row_cap or analysis_row_cap())
    except DirectQueryUnsupported as exc:
        raise FrameUnavailable(str(exc)) from exc
    except SourceUnavailable as exc:
        raise FrameUnavailable(
            "Could not reach the data source to read its rows.") from exc

    frame = got.frame
    if denied:
        frame = frame.drop(columns=[c for c in denied if c in frame.columns])

    return AnalysisFrame(frame=frame, origin="directquery",
                         rows_analysed=len(frame), total_rows=got.total_rows,
                         sampled=got.sampled)


def imported_frame(frame: pd.DataFrame) -> AnalysisFrame:
    """Wrap an already-loaded import frame, so both modes hand callers one type.

    Import frames are never sampled: `load_file` reads the whole file, which is
    itself bounded by the import row cap at the moment it was created.
    """
    return AnalysisFrame(frame=frame, origin="import", rows_analysed=len(frame),
                         total_rows=len(frame), sampled=False)
