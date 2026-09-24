"""Every route the app serves, flattened, on any FastAPI version.

Up to FastAPI 0.136, ``app.routes`` is a flat list of ``APIRoute``s: every
``include_router`` copies its routes up with the prefix applied. From 0.137 it
holds one ``_IncludedRouter`` wrapper per ``include_router`` call instead, and
the real routes only appear through its ``effective_route_contexts()``.

Tests that walked ``app.routes`` directly (admin endpoints require admin,
router reachability, frontend constant mirrors) then saw a few wrappers and
no paths, so they failed, or worse, checked nothing and passed. This helper
reads both shapes, so those tests mean the same thing on either side of the
change and FastAPI can move past 0.136.
"""
from __future__ import annotations

from typing import Iterator, NamedTuple


class ServedRoute(NamedTuple):
    path: str
    methods: frozenset[str]


def served_routes(app) -> Iterator[ServedRoute]:
    for route in app.routes:
        contexts = getattr(route, "effective_route_contexts", None)
        if contexts is None:
            yield ServedRoute(getattr(route, "path", "") or "",
                              frozenset(getattr(route, "methods", None) or ()))
            continue
        for ctx in contexts():
            yield ServedRoute(ctx.path or "",
                              frozenset(getattr(ctx.original_route, "methods", None) or ()))


def served_paths(app) -> set[str]:
    return {r.path for r in served_routes(app) if r.path}
