"""The seven-layer architecture, enforced.

ARCHITECTURE.md describes the backend as seven layers in data-flow order, and
states that dependencies point downward only. Prose cannot enforce that; this
test does.

How it works
------------
Every module in `app/services/` and `app/core/` is assigned a layer. Imports
are parsed with `ast` (not regex -- a regex matches the word "import" inside a
docstring, and this codebase has long ones). An import from a HIGHER layer to a
LOWER one is fine; the reverse is a violation.

The ratchet
-----------
`KNOWN_VIOLATIONS` is an allowlist of the upward imports that existed when this
test was written. It may only shrink:

  * a violation NOT in the list      -> fail (new coupling introduced)
  * a listed violation that is GONE  -> fail (delete the entry; keeps the list
                                        honest instead of accumulating fiction)

A plain "zero violations" assertion would have to be skipped today, and a
skipped test enforces nothing. The ratchet lets the codebase converge while
still failing the moment someone adds a new upward dependency.

Layer assignments live in `LAYER_MAP` below and must match ARCHITECTURE.md.
When you move a module between layers, update both.
"""
from __future__ import annotations

import ast
import os

import pytest

# ---------------------------------------------------------------------------
# Layer map. Mirrors the "seven layers at a glance" table in ARCHITECTURE.md.
# ---------------------------------------------------------------------------

L1_SOURCES = 1        # reaching external systems; dialect capability
L2_INGESTION = 2      # raw source -> described, profiled dataset
L3_STORAGE = 3        # durable and cached state
L4_QUERY = 4          # widget intent -> safe, governed SQL
L5_ANALYTICS = 5      # statistics, forecasting, NL->SQL
L6_API = 6            # HTTP surface, authn/authz, delivery
L7_PRESENTATION = 7   # frontend; no Python modules

LAYER_MAP: dict[str, int] = {
    # -- Layer 1: sources & connectivity -----------------------------------
    "services/connectors": L1_SOURCES,
    "services/connections": L1_SOURCES,
    "services/mdb": L1_SOURCES,
    # Pooled SQLAlchemy engines keyed by connection identity. Extracted from
    # direct_query.py in conformance task 2.5: opening a connection is
    # acquisition (layer 1), not query building (layer 4).
    "services/engines": L1_SOURCES,
    "services/secrets": L1_SOURCES,
    "services/net_guard": L1_SOURCES,

    # -- Layer 2: ingestion & metadata -------------------------------------
    # pii masking runs during sampling, before anything reaches the sample
    # cache or the model -- an ingestion concern, not an API one.
    "services/pii": L2_INGESTION,
    "services/dataset_refresh": L2_INGESTION,
    # The ingestion half of the old analytics.py: reading a file, typing its
    # columns. Split out in conformance task 2.4.
    "services/ingest": L2_INGESTION,
    "services/upload_store": L2_INGESTION,
    "services/metadata/introspect": L2_INGESTION,
    "services/metadata/sample": L2_INGESTION,
    "services/metadata/profile": L2_INGESTION,
    "services/metadata/infer_keys": L2_INGESTION,
    "services/metadata/infer_semantic": L2_INGESTION,
    "services/metadata/catalog_sync": L2_INGESTION,
    "services/metadata/sync": L2_INGESTION,
    "services/metadata/drift": L2_INGESTION,
    "services/metadata/store": L2_INGESTION,
    "services/metadata/cache": L2_INGESTION,

    # -- Layer 3: storage & persistence ------------------------------------
    "services/cache_backend": L3_STORAGE,
    "services/frame_cache": L3_STORAGE,
    "core/database": L3_STORAGE,

    # -- Layer 4: query & semantic -----------------------------------------
    # direct_query sits here, NOT layer 1: it takes a widget config, builds
    # SQL, and hands the result to widget_data's shaper. Reaching a source is
    # layer 1; building and running the query is layer 4.
    "services/direct_query": L4_QUERY,
    "services/widget_data": L4_QUERY,
    # The shaping + result-cache surface both engines share. Imports only
    # cache_backend (L3) and config, so it is a clean layer-4 leaf.
    "services/widget_shaping": L4_QUERY,
    # DuckDB pre-aggregation for the import path. Same layer as the engines it
    # sits beside; imports direct_query only for the grain-safety rules.
    "services/duck_agg": L4_QUERY,
    # prep applies RLS filters and filter expressions to the frame it builds
    # (resolve_rls_expr, resolve_denied_columns, apply_rls_filter): governed
    # query work, not raw ingestion.
    "services/prep": L4_QUERY,
    # Relative date windows resolve inside the widget pipeline (Phase 6.4).
    "services/relative_dates": L4_QUERY,
    # Tokenising, stop lists and lexicon sentiment: pure text functions the
    # calc-column SENTIMENT() (layer 4) and the text analyses (layer 5) share.
    "services/text_lang": L4_QUERY,
    # Sensitivity labels: lineage + enforcement decisions, read by the
    # widget/export/delivery paths and the routers.
    "services/sensitivity": L4_QUERY,
    # A script tile runs author code over the already-secured frame and hands
    # rows back to the shaper: the same job direct_query does with SQL, so the
    # same layer. `script_runner` is the child process it spawns -- mapped so
    # that an import of app code into it (which would defeat the scrubbed
    # environment) shows up here as an upward violation.
    "services/script_tile": L4_QUERY,
    "services/script_runner": L4_QUERY,
    "services/query_builder": L4_QUERY,
    "services/sql_expr": L4_QUERY,
    "services/measure_eval": L4_QUERY,
    "services/parameters": L4_QUERY,
    "services/display_rules": L4_QUERY,
    "services/data_views": L4_QUERY,
    "services/query_log": L4_QUERY,
    "core/rls": L4_QUERY,

    # -- Layer 5: analytics & AI -------------------------------------------
    # analytics.py is dual-layer: load_file/detect_types are ingestion (L2),
    # analyze_*/run_full_analysis are statistics (L5). Recorded at L5 with the
    # L2 callers allowlisted below; conformance plan task 2.4 splits it.
    "services/analytics": L5_ANALYTICS,
    "services/insights": L5_ANALYTICS,
    "services/report_composer": L5_ANALYTICS,
    "services/explain": L5_ANALYTICS,
    "services/llm": L5_ANALYTICS,
    "services/retrieval": L5_ANALYTICS,
    "services/analysis/anomaly": L5_ANALYTICS,
    "services/analysis/segment": L5_ANALYTICS,
    "services/analysis/patterns": L5_ANALYTICS,
    "services/analysis/registry": L5_ANALYTICS,
    "services/analysis/influencers": L5_ANALYTICS,
    "services/analysis/inferential": L5_ANALYTICS,
    "services/analysis/restricted": L5_ANALYTICS,
    "services/analysis/goal_seek": L5_ANALYTICS,
    "services/analysis/forecast_goal": L5_ANALYTICS,
    "services/analysis/decision_tree": L5_ANALYTICS,
    "services/analysis/automated_prediction": L5_ANALYTICS,
    "services/analysis/text_topics": L5_ANALYTICS,
    "services/analysis/text_sentiment": L5_ANALYTICS,
    "services/analysis/forecast_scenario": L5_ANALYTICS,
    # The pure crossing logic sits with the forecaster that uses it:
    # shape_forecast answers a target inline so the caption cannot
    # disagree with the chart, and layer 4 may not import layer 5.
    "services/forecast_goal": L4_QUERY,
    "services/boundary_sets": L5_ANALYTICS,
    "services/analysis_contract": L5_ANALYTICS,
    "services/agent/graph": L5_ANALYTICS,
    "services/agent/context": L5_ANALYTICS,
    "services/agent/plan": L5_ANALYTICS,
    "services/agent/dag": L5_ANALYTICS,
    "services/agent/executor": L5_ANALYTICS,
    "services/agent/policy": L5_ANALYTICS,
    "services/agent/validate": L5_ANALYTICS,
    "services/agent/memory": L5_ANALYTICS,
    "services/agent/state": L5_ANALYTICS,
    "services/agent/nodes/classify": L5_ANALYTICS,
    "services/agent/nodes/clarify": L5_ANALYTICS,
    "services/agent/nodes/generate": L5_ANALYTICS,
    "services/agent/nodes/explain": L5_ANALYTICS,

    # -- Layer 6: API & services -------------------------------------------
    # refresh_scheduler orchestrates refresh THEN alerts/delivery: that is
    # operational orchestration composing downward, not ingestion.
    "services/refresh_scheduler": L6_API,
    # Power Pi's automation runner sits beside it for the same reason and
    # shares its tick: sequencing profile -> scan -> propose -> compose is
    # orchestration over layers 2-5, not a member of any of them.
    "services/automation_runner": L6_API,
    "services/pdf_export": L6_API,
    "services/delivery": L6_API,
    "services/alerts": L6_API,
    "services/notifications": L6_API,
    "services/eval_schedule": L6_API,
    "services/sso": L6_API,
    "services/saml": L6_API,
    "services/auth_provisioning": L6_API,
    "services/org_access": L6_API,
    "services/audit": L6_API,
    "services/admin_audit": L6_API,
    "services/quotas": L6_API,
    "services/demo_content": L6_API,
    "services/page_templates": L6_API,
    "core/security": L6_API,
    "core/api_keys": L6_API,
    "core/capability": L6_API,
    "core/org_scope": L6_API,
    "core/rate_limit": L6_API,
}

#: Modules deliberately exempt: config and telemetry are read by every layer,
#: and treating them as layered would make every module a violator.
CROSS_CUTTING = {"core/config", "core/telemetry"}

#: Upward imports present when this test was written. MAY ONLY SHRINK.
#: Each entry is (importing_module, imported_module). See the conformance plan
#: (docs/superpowers/plans/2026-08-28-architecture-conformance.md) for the
#: verdict on each.
KNOWN_VIOLATIONS: set[tuple[str, str]] = {
    # -- accepted by design ------------------------------------------------
    # Invalidation flows from whoever changed the data: layer 2 clearing
    # layer 3's cache after a refresh is correct, not a leak.
    ("services/dataset_refresh", "services/frame_cache"),
    ("services/metadata/sync", "services/frame_cache"),

    # `ingest.load_file` reads THROUGH the process-local frame memo rather than
    # parsing directly, so the same bytes are parsed once per process instead of
    # once per widget. Layer 2 calling layer 3 to read cached state is the same
    # shape as the invalidation entries above, and it is the surviving half of
    # the old analytics <-> frame_cache cycle -- now one-directional, and a
    # normal function call instead of a function-local import workaround.
    ("services/ingest", "services/frame_cache"),
}

_APP_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")


def _parse(path: str) -> ast.Module:
    """Parse a source file to an AST.

    Read as utf-8-sig: 12 modules in this tree begin with a UTF-8 BOM, and
    `ast.parse` rejects U+FEFF as an invalid non-printable character even
    though Python's own import machinery strips it silently. Plain "utf-8"
    here would make this whole test fail on files that import fine.
    """
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        return ast.parse(fh.read(), filename=path)


def _module_key(path: str) -> str:
    """'…/app/services/metadata/sync.py' -> 'services/metadata/sync'."""
    rel = os.path.relpath(path, _APP_ROOT).replace(os.sep, "/")
    return rel[:-3] if rel.endswith(".py") else rel


def _resolve(node: ast.ImportFrom, importer: str) -> list[str]:
    """Resolve a relative `from … import …` to module keys under app/.

    Only relative imports are considered: an absolute import of a third-party
    package cannot be an intra-app layer violation.
    """
    if node.level == 0:
        return []

    parts = importer.split("/")
    # level 1 = current package, 2 = parent, and so on.
    base = parts[: len(parts) - node.level] if node.level <= len(parts) else []
    prefix = base + ([node.module.replace(".", "/")] if node.module else [])
    stem = "/".join(p for p in prefix if p)

    # `from .foo import bar` -- bar may be a submodule or just a name. Emit
    # both candidates; unknown keys are filtered out by the caller.
    return [stem] + [f"{stem}/{a.name}" for a in node.names]


def _collect_imports() -> list[tuple[str, str]]:
    """Every (importer, imported) edge between mapped modules."""
    edges: list[tuple[str, str]] = []
    for root, _dirs, files in os.walk(_APP_ROOT):
        if "__pycache__" in root:
            continue
        for fname in sorted(files):
            if not fname.endswith(".py"):
                continue
            path = os.path.join(root, fname)
            key = _module_key(path)
            if key not in LAYER_MAP:
                continue
            try:
                tree = _parse(path)
            except SyntaxError:  # pragma: no cover - would fail elsewhere
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    for target in _resolve(node, key):
                        if target in LAYER_MAP and target != key:
                            edges.append((key, target))
    return edges


def _upward_violations() -> set[tuple[str, str]]:
    return {
        (a, b)
        for a, b in _collect_imports()
        if a not in CROSS_CUTTING
        and b not in CROSS_CUTTING
        and LAYER_MAP[b] > LAYER_MAP[a]
    }


class TestTheMapItself:
    """Guard the map before trusting anything derived from it."""

    def test_every_mapped_module_exists(self):
        missing = [
            key for key in LAYER_MAP
            if not os.path.exists(os.path.join(_APP_ROOT, key + ".py"))
        ]
        assert not missing, (
            "LAYER_MAP names modules that no longer exist -- rename or delete "
            f"these entries: {sorted(missing)}"
        )

    def test_layers_are_in_range(self):
        assert all(1 <= v <= 7 for v in LAYER_MAP.values())

    def test_imports_were_actually_parsed(self):
        """A resolver bug that silently found nothing would make every other
        assertion here vacuously true."""
        assert len(_collect_imports()) > 50


class TestLayerBoundaries:
    def test_no_new_upward_imports(self):
        unexpected = _upward_violations() - KNOWN_VIOLATIONS
        assert not unexpected, (
            "New upward import(s) -- a module imported something from a layer "
            "above it, which ARCHITECTURE.md says cannot happen:\n"
            + "\n".join(
                f"  L{LAYER_MAP[a]} {a}  ->  L{LAYER_MAP[b]} {b}"
                for a, b in sorted(unexpected)
            )
            + "\n\nEither invert the dependency, or -- if the layer assignment "
              "is what is wrong -- update LAYER_MAP here AND the layer tables "
              "in ARCHITECTURE.md/.html together."
        )

    def test_allowlist_has_no_stale_entries(self):
        """The ratchet: a fixed violation must be removed from the list."""
        stale = KNOWN_VIOLATIONS - _upward_violations()
        assert not stale, (
            "These allowlisted violations no longer exist -- delete them from "
            "KNOWN_VIOLATIONS so the list keeps meaning something:\n"
            + "\n".join(f"  {a} -> {b}" for a, b in sorted(stale))
        )


class TestDocumentedInvariants:
    """Boundaries ARCHITECTURE.md calls out by name."""

    def test_no_service_imports_fastapi(self):
        """Layer 6 owns the HTTP surface. A service picking status codes is
        unusable from the scheduler or a CLI without a fake request context.

        `quotas` was the last exception; task 2.3 replaced its `HTTPException`
        raises with a `QuotaExceeded` domain exception translated by a handler
        in `main.py`. There are now no exemptions -- keep it that way."""
        offenders = []
        services = os.path.join(_APP_ROOT, "services")
        for root, _dirs, files in os.walk(services):
            if "__pycache__" in root:
                continue
            for fname in sorted(files):
                if not fname.endswith(".py"):
                    continue
                path = os.path.join(root, fname)
                tree = _parse(path)
                for node in ast.walk(tree):
                    hit = (
                        isinstance(node, ast.ImportFrom)
                        and (node.module or "").split(".")[0] == "fastapi"
                    ) or (
                        isinstance(node, ast.Import)
                        and any(a.name.split(".")[0] == "fastapi" for a in node.names)
                    )
                    if hit:
                        offenders.append(_module_key(path))
        assert not offenders, (
            f"Service module(s) importing FastAPI: {sorted(set(offenders))}. "
            "Raise a domain exception and translate it at the router boundary "
            "or in an exception handler, as services/quotas.py does with "
            "QuotaExceeded."
        )

    def test_routers_do_not_execute_raw_sql(self):
        """Layer 6 goes through layer 4, never straight to the database."""
        offenders = []
        routers = os.path.join(_APP_ROOT, "routers")
        for fname in sorted(os.listdir(routers)):
            if not fname.endswith(".py"):
                continue
            path = os.path.join(routers, fname)
            tree = _parse(path)
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "text"
                    and node.args
                    and isinstance(node.args[0], (ast.Constant, ast.JoinedStr))
                ):
                    offenders.append(f"{fname}:{node.lineno}")
        assert not offenders, (
            f"Router(s) building raw SQL with text(): {offenders}. Route the "
            "query through services/ (layer 4) so RLS and query logging apply."
        )
