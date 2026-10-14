"""May a model be called for this data? One answer, asked in one place.

Until 2026-10-10 the per-connection switch ("Allow AI") was honoured by two
features (the catalog sync and the guided setup) out of some twenty-five that
call a model; Ask AI, the page copilot, the designers and the insights wording
ignored it, and an uploaded file had no switch at all.

The rule now:

* a dataset built from a connection follows the CONNECTION's switch
  (`DataSource.allow_llm_sampling`);
* an uploaded dataset has its own (`Dataset.allow_ai`); unset, it follows the
  installation default (`settings.ai_for_uploads_default`);
* a dataset's own switch set to False wins over everything.

`enter()` is called where a request (or a background run) learns which data it
works on. It records the refusal in the model client's own context
(`llm.deny_ai`), so every model call made afterwards in that request returns
None -- whichever feature makes it -- and that feature's no-model path runs.
"""
from __future__ import annotations

import logging
from typing import Iterable

from . import llm

logger = logging.getLogger(__name__)


def source_allows(source) -> bool:
    return source is None or bool(getattr(source, "allow_llm_sampling", False))


async def dataset_allows(db, dataset) -> bool:
    """Whether a model may be called about this dataset. Fails CLOSED: a
    lookup that errors is a refusal, never a silent yes."""
    if dataset is None:
        return True
    own = getattr(dataset, "allow_ai", None)
    if own is False:
        return False
    source_id = getattr(dataset, "data_source_id", None)
    if source_id:
        try:
            from ..models.models import DataSource
            source = await db.get(DataSource, source_id)
        except Exception:                                       # noqa: BLE001
            logger.exception("ai policy: could not read the connection of dataset %s",
                             getattr(dataset, "id", None))
            return False
        # A connection that was deleted leaves an imported copy behind: the
        # copy is then judged like an upload.
        if source is not None:
            return source_allows(source)
    if own is True:
        return True
    from ..core.config import settings
    return bool(settings.ai_for_uploads_default)


async def allowed(db, *, datasets: Iterable = (), source=None) -> bool:
    """True when every dataset named, and the connection named, allow it."""
    if not source_allows(source):
        return False
    for ds in datasets or ():
        if not await dataset_allows(db, ds):
            return False
    return True


async def enter(db, *, datasets: Iterable = (), source=None) -> bool:
    """Apply the answer to the rest of this request: returns whether AI is
    allowed, and when it is not, no model call can be made from here on."""
    ok = await allowed(db, datasets=datasets, source=source)
    if ok:
        llm.allow_ai()
    else:
        llm.deny_ai()
    return ok
