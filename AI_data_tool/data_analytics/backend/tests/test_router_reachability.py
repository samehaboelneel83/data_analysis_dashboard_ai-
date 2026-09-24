"""Every route the frontend calls must be a route the server serves.

This exists because the entire Layer 4 agent surface -- natural-language
querying, the product's flagship feature -- was unreachable from the UI for its
whole life, and nothing noticed.

`main.py` mounted `agent_router` with no prefix, on the reasoning that the
router owned its own `/agent` namespace. But `frontend/src/services/api.ts`
builds ONE axios instance whose `baseURL` already ends in `/api/v1`, so every
`agentApi` call requested `/api/v1/agent/conversations` while the server served
`/agent/conversations`. Verified against the running stack: 404 and 200
respectively.

The reason it survived is the interesting part, and it is why this file is
written the way it is. `test_agent_api.py` passed the whole time -- it called
the bare path, exactly as mounted. Both halves were correct about themselves
and wrong about each other, so no amount of testing either side in isolation
could ever have caught it. Only a test that reads BOTH sides can.

So this derives the paths from the two real artifacts -- the mounted FastAPI
app, and the TypeScript the browser actually ships -- and asserts they meet.
"""
import os
import re

import pytest

from app.main import app
from tests._routes import served_paths

_HERE = os.path.dirname(os.path.abspath(__file__))
_API_TS = os.path.join(os.path.dirname(os.path.dirname(_HERE)),
                       "frontend", "src", "services", "api.ts")

#: The prefix `api.ts` bakes into its axios instance:
#:     const BASE = (import.meta.env.VITE_API_URL ?? '...') + '/api/v1'
_CLIENT_PREFIX = "/api/v1"

#: Paths reached by a full-page navigation rather than the axios instance, so
#: the client prefix does not apply to them. `api.ts` builds these by hand
#: against the bare origin (see the `window.location` redirect for SSO login).
_NOT_VIA_AXIOS = {
    "/health", "/health/live", "/health/ready",
    "/", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc",
}


#: Paths whose final segment is chosen at runtime from a lookup table, so the
#: literal in api.ts is a template the server never serves verbatim.
#:
#: Empty now: the statistics slug table it existed for is gone. The panel posts
#: every analysis to one literal route (`/datasets/{}/analysis/run`), which this
#: file checks like any other, and test_frontend_constant_mirrors.py pins the
#: typed statistics endpoints on the backend side. Kept rather than deleted
#: because the NEXT runtime-assembled path needs somewhere to be declared, with
#: the rule attached: exclude it here only if it is covered better elsewhere.
_RESOLVED_AT_RUNTIME: set[str] = set()


def _served_paths() -> set[str]:
    return served_paths(app)


@pytest.fixture(scope="module")
def api_ts() -> str:
    if not os.path.exists(_API_TS):
        pytest.skip("frontend/src/services/api.ts not reachable")
    with open(_API_TS, encoding="utf-8") as fh:
        return fh.read()


def _client_paths(text: str) -> set[str]:
    """Every path passed to `api.get/post/put/patch/delete` in api.ts.

    Template holes become `{}` so `/agent/conversations/${id}/ask` compares
    against the server's `/agent/conversations/{conversation_id}/ask`: the
    parameter NAMES are free to differ, the shape is not.
    """
    out: set[str] = set()
    for raw in re.findall(
            r"""api\.(?:get|post|put|patch|delete)\s*(?:<[^>]*>)?\s*\(\s*([`'"])(/[^`'"]*)\1""",
            text):
        path = raw[1]
        path = re.sub(r"\$\{[^}]*\}", "{}", path)   # template hole
        path = path.split("?", 1)[0].rstrip("/")     # drop query string
        if path:
            out.add(path)
    return out


def _normalise(path: str) -> str:
    """Server path with parameter names erased, for shape comparison."""
    return re.sub(r"\{[^}]*\}", "{}", path).rstrip("/")


class TestEveryClientCallIsServed:
    """The check that would have caught the agent outage."""

    def test_api_ts_actually_yields_paths(self, api_ts):
        """Guard the guard.

        If the regex stops matching -- api.ts switches to a helper, or to
        another quoting style -- every assertion below would pass vacuously by
        comparing an empty set. This is the tripwire for that.
        """
        found = _client_paths(api_ts)
        assert len(found) > 50, (
            f"only {len(found)} client paths parsed out of api.ts; the "
            f"extraction regex has probably gone stale, which would make the "
            f"reachability assertions below pass without checking anything")

    def test_every_path_the_client_requests_exists_on_the_server(self, api_ts):
        served = {_normalise(p) for p in _served_paths()}
        missing = sorted(
            p for p in _client_paths(api_ts)
            if _normalise(_CLIENT_PREFIX + p) not in served
            and p not in _RESOLVED_AT_RUNTIME
        )
        assert not missing, (
            "frontend calls these, the server does not serve them at "
            f"{_CLIENT_PREFIX}: {missing}\n"
            "Either the router is mounted without the prefix (the agent bug) "
            "or the path is misspelled. Both are 404s no test would otherwise "
            "see.")


class TestRoutersAreMountedConsistently:
    """A router mounted off-prefix is invisible to the client, whatever its
    own tests say."""

    def test_the_agent_surface_is_reachable_at_the_client_prefix(self):
        """Pinned by name because this is the one that actually broke, and it
        is the product's flagship feature rather than an incidental endpoint."""
        served = _served_paths()
        assert f"{_CLIENT_PREFIX}/agent/conversations" in served, (
            "the agent chat surface is not mounted under the prefix the "
            "frontend uses; natural-language querying is dark")

    def test_no_router_is_mounted_outside_the_versioned_prefix(self):
        """Everything the browser reaches through axios lives under /api/v1.

        The exceptions are enumerated rather than pattern-matched, so adding a
        route outside the prefix is a decision someone has to write down here.
        """
        stray = sorted(
            p for p in _served_paths()
            if not p.startswith(_CLIENT_PREFIX)
            and p not in _NOT_VIA_AXIOS
            and not p.startswith("/static")
        )
        assert not stray, (
            f"routes served outside {_CLIENT_PREFIX}: {stray}\n"
            "The frontend's axios instance cannot reach these. If one is "
            "genuinely meant to be reached another way, add it to "
            "_NOT_VIA_AXIOS with a reason.")
