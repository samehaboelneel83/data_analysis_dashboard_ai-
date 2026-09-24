"""Rootdir conftest: a floor on how many tests must be collected.

This file deliberately lives at the rootdir, NOT in tests/. tests/conftest.py
imports pytest_asyncio, httpx, and the app itself; if any of those is missing
from the environment, that file fails to import and pytest collects ZERO tests
-- and then exits 0. A green exit code with nothing run is worse than a red
one, because CI, hooks, and humans all read the exit code and believe it.

That is not hypothetical: it is exactly what a stock environment did here
before `backend/requirements.txt` was installed (pytest 7.4.4, no
pytest_asyncio), and the suite "passed" while running nothing.

This module imports only pytest, so it survives whatever breaks tests/.
"""
from __future__ import annotations

import os

import pytest

# The suite is ~2450 tests. The floor is deliberately far below that: it is a
# tripwire for catastrophic collection failure, not a count to keep in sync
# with reality. Raise it only if it ever stops catching a real breakage.
MINIMUM_EXPECTED_TESTS = 500

_SKIP_ENV = "DATALYTICS_ALLOW_PARTIAL_COLLECTION"


def pytest_collection_modifyitems(session, config, items):
    """Fail loudly when collection returns implausibly few tests.

    Skipped when the caller selected a subset on purpose -- a nodeid, -k, -m,
    --last-failed, or an explicit opt-out for bisecting.
    """
    if os.environ.get(_SKIP_ENV):
        return

    # A subset was requested deliberately: file/nodeid args, -k, -m, or any of
    # the cache-driven selectors. `config.args` holds the positional targets;
    # when it is just the testpaths default, nothing narrowed the run.
    narrowed = (
        config.option.keyword
        or config.option.markexpr
        or getattr(config.option, "lf", False)
        or getattr(config.option, "ff", False)
        or getattr(config.option, "last_failed", False)
        or [a for a in config.args if a not in ("tests",)]
    )
    if narrowed:
        return

    if len(items) < MINIMUM_EXPECTED_TESTS:
        raise pytest.UsageError(
            f"Collected only {len(items)} tests, expected at least "
            f"{MINIMUM_EXPECTED_TESTS}.\n"
            "This almost always means tests/conftest.py failed to import and "
            "pytest silently collected nothing -- check that the environment "
            "matches backend/requirements.txt (pytest_asyncio, httpx, fastapi).\n"
            f"Set {_SKIP_ENV}=1 to bypass this check deliberately."
        )
