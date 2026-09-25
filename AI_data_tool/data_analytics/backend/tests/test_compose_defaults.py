"""Shipped deployment defaults, pinned where they are a real claim.

The capability audit's sharpest finding was not a missing feature: six
capabilities were built, tested, and left switched off in the shipping
configuration. `widget_duckdb_pushdown` and `import_row_cap` were corrected in
code; `VALKEY_URL` lived in docker-compose.yml instead, where no test could see
it -- so the compose file shipped a 256MB Valkey container, with a healthcheck,
wired to nothing, while every worker repeated identical widget renders in its own
in-process cache.

These tests read the compose file directly because that is where the claim lives.
They are deliberately few: pinning every line of a deployment file would make it
unmaintainable. Only defaults whose silent reversion would cost something real
are here.
"""
import os
import re

import pytest

_COMPOSE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docker-compose.yml")


@pytest.fixture(scope="module")
def compose() -> str:
    """The compose file, or a skip.

    It sits one level above the backend package and is deliberately NOT copied
    into the runtime image, so this same suite run inside the container cannot
    see it. Skipping there is the correct behaviour, not a gap: these assert a
    DEPLOYMENT claim, and the container is the thing being deployed rather than
    the thing that defines the deployment. On a developer checkout and in CI the
    file is present and every assertion below runs.
    """
    if not os.path.exists(_COMPOSE):
        pytest.skip("docker-compose.yml not reachable (running inside the image)")
    with open(_COMPOSE, encoding="utf-8") as fh:
        return fh.read()


def _default_for(compose: str, var: str) -> str | None:
    """The `${VAR:-default}` fallback for one environment entry, or None when the
    variable is passed through with no default."""
    m = re.search(r"^\s*%s:\s*\$\{%s:-(.*?)\}\s*$" % (re.escape(var), re.escape(var)),
                  compose, re.M)
    return m.group(1) if m else None


class TestTheSharedCacheIsWiredUp:
    def test_valkey_url_defaults_to_the_service_compose_already_runs(self, compose):
        """Unset, this shipped a running Valkey container connected to nothing."""
        assert _default_for(compose, "VALKEY_URL") == "redis://valkey:6379/0"

    def test_the_valkey_service_actually_exists(self, compose):
        """A URL pointing at a service that is not defined would be worse than
        leaving it unset: every request would pay a connection timeout to learn
        what the compose file already knows."""
        assert re.search(r"^\s{2}valkey:\s*$", compose, re.M)

    def test_it_stays_overridable(self, compose):
        """A deployment with no Valkey sets VALKEY_URL= to get the old
        in-process behaviour. Hardcoding the URL would take that away."""
        assert "${VALKEY_URL:-" in compose

    def test_the_backend_does_not_depend_on_valkey(self, compose):
        """The backend must start and keep running whether or not this optional
        service exists -- the same rule already applied to `embeddings`. A
        `depends_on: valkey` would turn a cache outage into a boot failure,
        which is exactly the fragility the circuit breaker exists to avoid."""
        backend = compose[compose.index("\n  backend:"):compose.index("\n  frontend:")]
        depends = re.search(r"depends_on:\n(?:\s+.*\n)+?(?=\s{4}\w|\s{2}\w)", backend)
        assert depends is None or "valkey" not in depends.group(0)
