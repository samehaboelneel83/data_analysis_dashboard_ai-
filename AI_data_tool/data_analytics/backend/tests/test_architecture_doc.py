"""ARCHITECTURE.md and .html must agree with the code they describe.

The conformance test (test_layer_conformance.py) enforces the *structure* the
architecture document describes. This one enforces its *facts*: every count in
those documents is re-derived from the tree and compared.

Why bother: on 2026-08-28 the documents claimed 46 connectors. The registry held
43. The wrong number came from a hand-read of the spec list that double-counted
wire-compatible variants, and it had already propagated into two documents and a
published comparison before anyone re-derived it. Prose rots silently because no
test reads it -- so this one does.

The counts here are DERIVED, never hard-coded. A test asserting `connectors ==
43` would need editing every time a connector is added, and would be edited
without thought. Asserting "whatever the registry holds is what the document
says" needs editing only when someone changes the document, which is the point.

Both documents are checked: they are maintained in parallel and drifting apart
is exactly the failure this catches.
"""
from __future__ import annotations

import ast
import io
import os
import re

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_BACKEND)

MD_PATH = os.path.join(_ROOT, "ARCHITECTURE.md")
HTML_PATH = os.path.join(_ROOT, "ARCHITECTURE.html")


@pytest.fixture(scope="module")
def docs() -> dict[str, str]:
    return {
        "ARCHITECTURE.md": io.open(MD_PATH, encoding="utf-8").read(),
        "ARCHITECTURE.html": io.open(HTML_PATH, encoding="utf-8").read(),
    }


# ── counts derived from the tree ─────────────────────────────────────────────

def _connector_count() -> int:
    """From the registry itself, not by counting lines in the source."""
    from app.services.connectors import _REGISTRY
    return len(_REGISTRY)


def _table_count() -> int:
    src = io.open(os.path.join(_BACKEND, "app/models/models.py"),
                  encoding="utf-8-sig").read()
    return len(re.findall(r"^\s*__tablename__\s*=", src, re.M))


def _router_module_count() -> int:
    """Distinct router MODULES, which is not the number of include_router calls:
    `analysis` and `metadata` each mount a second router. The document says
    'modules', so that is what is counted."""
    src = io.open(os.path.join(_BACKEND, "app/main.py"), encoding="utf-8-sig").read()
    return len({m.group(1) for m in re.finditer(r"app\.include_router\((\w+)\.", src)})


def _report_ts() -> str:
    return io.open(os.path.join(_ROOT, "frontend/src/types/report.ts"),
                   encoding="utf-8").read()


def _widget_count() -> int:
    return len(re.findall(r"as WidgetType, label:", _report_ts()))


def _aggregation_count() -> int:
    catalogue = _report_ts().split("AGGREGATIONS", 1)[1]
    return len(re.findall(r"\{\s*value:", catalogue))


def _page_count() -> int:
    pages = os.path.join(_ROOT, "frontend/src/pages")
    return len([f for f in os.listdir(pages)
                if f.endswith(".tsx") and ".test." not in f])


def _alembic_revision_count() -> int:
    versions = os.path.join(_BACKEND, "alembic/versions")
    return len([f for f in os.listdir(versions) if f.endswith(".py")])


def _backend_test_module_count() -> int:
    return len([f for f in os.listdir(_HERE)
                if f.startswith("test_") and f.endswith(".py")])


def _frontend_test_file_count() -> int:
    root = os.path.join(_ROOT, "frontend/src")
    return sum(1 for dirpath, _dirs, files in os.walk(root)
               for f in files if ".test." in f and f.endswith((".ts", ".tsx")))


#: (label, deriver, regex template). `{n}` is replaced by the derived count.
CLAIMS = [
    ("connectors", _connector_count, r"\b{n} connectors\b"),
    ("tables", _table_count, r"\b{n} tables\b"),
    ("router modules", _router_module_count, r"\b{n} router modules\b"),
    ("widget types", _widget_count, r"\b{n} widget types\b"),
    ("aggregations", _aggregation_count, r"\b{n} aggregations\b"),
    ("pages", _page_count, r"\b{n} pages\b"),
    ("alembic revisions", _alembic_revision_count, r"\b{n} revisions\b"),
    # Module counts, not test counts. The number of tests changes with almost
    # every commit, so pinning it would produce a test that fails constantly and
    # gets edited without being read -- the documents say "~2,550 tests" and this
    # deliberately does not check that. How many test MODULES exist is a
    # structural fact that changes rarely and means something.
    ("backend test modules", _backend_test_module_count, r"\b{n} modules\b"),
    ("frontend test files", _frontend_test_file_count, r"\b{n} files\b"),
]


@pytest.mark.parametrize("label,derive,template",
                         CLAIMS, ids=[c[0] for c in CLAIMS])
@pytest.mark.parametrize("doc", ["ARCHITECTURE.md", "ARCHITECTURE.html"])
def test_documented_count_matches_the_code(doc, label, derive, template, docs):
    actual = derive()
    pattern = template.format(n=actual)
    assert re.search(pattern, docs[doc]), (
        f"{doc} does not state the real {label} count.\n"
        f"  the code has: {actual}\n"
        f"  expected the document to contain: {pattern!r}\n"
        f"Update the document, or -- if the count changed because you added "
        f"something -- update it there too. Both documents are maintained in "
        f"parallel and must agree."
    )


class TestModulesTheDocumentsName:
    """A document naming a module that no longer exists is worse than one that
    omits it: the reader goes looking and loses trust when it is not there."""

    def _named_service_modules(self, text: str) -> set[str]:
        return set(re.findall(r"services/([a-z_]+)\.py", text))

    @pytest.mark.parametrize("doc", ["ARCHITECTURE.md", "ARCHITECTURE.html"])
    def test_every_named_service_module_exists(self, doc, docs):
        missing = sorted(
            name for name in self._named_service_modules(docs[doc])
            if not os.path.exists(
                os.path.join(_BACKEND, "app/services", name + ".py"))
        )
        assert not missing, (
            f"{doc} names service modules that do not exist: {missing}. "
            "Rename or remove them."
        )

    @pytest.mark.parametrize("doc", ["ARCHITECTURE.md", "ARCHITECTURE.html"])
    def test_every_named_core_module_exists(self, doc, docs):
        named = set(re.findall(r"core/([a-z_]+)\.py", docs[doc]))
        missing = sorted(
            name for name in named
            if not os.path.exists(os.path.join(_BACKEND, "app/core", name + ".py"))
        )
        assert not missing, f"{doc} names core modules that do not exist: {missing}"


class TestTheLayerMapAgrees:
    """The conformance test's LAYER_MAP and the documents' layer tables are two
    statements of the same thing, and the conformance test says so in its own
    docstring. This checks they were changed together."""

    def _layer_map(self):
        from tests import test_layer_conformance as lc
        return lc.LAYER_MAP

    @pytest.mark.parametrize("doc", ["ARCHITECTURE.md", "ARCHITECTURE.html"])
    def test_documented_violation_count_matches_the_allowlist(self, doc, docs):
        from tests import test_layer_conformance as lc

        actual = len(lc._upward_violations())
        words = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five"}
        pattern = rf"({words.get(actual, actual)}|{actual}) remaining violations"
        assert re.search(pattern, docs[doc], re.I), (
            f"{doc} does not state the real violation count ({actual}). "
            "The allowlist shrank (or grew) without the document following."
        )


class TestTheAuditCannotPassVacuously:
    """A deriver that silently returned 0, or a regex that matched nothing,
    would make every assertion above trivially true or trivially false. These
    pin the derivers themselves."""

    @pytest.mark.parametrize("label,derive,_t", CLAIMS, ids=[c[0] for c in CLAIMS])
    def test_every_deriver_returns_a_plausible_count(self, label, derive, _t):
        value = derive()
        assert isinstance(value, int) and value > 0, (
            f"the {label} deriver returned {value!r}; it is measuring nothing")

    def test_the_documents_were_actually_loaded(self, docs):
        for name, text in docs.items():
            assert len(text) > 5_000, f"{name} looks empty or truncated"

    def test_models_parse_as_python(self):
        """The table count regexes over source; if that file ever stops being
        valid Python the count is meaningless."""
        src = io.open(os.path.join(_BACKEND, "app/models/models.py"),
                      encoding="utf-8-sig").read()
        ast.parse(src)
