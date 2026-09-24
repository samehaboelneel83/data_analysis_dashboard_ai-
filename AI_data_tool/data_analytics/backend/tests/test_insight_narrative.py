"""The LLM narrative: phrasing, never evidence.

`insights.py`'s narrative was a join of the top findings' titles -- template
prose, and its docstring was "honest about being template prose rather than an
LLM's". The upgrade keeps that honesty in three ways, each pinned here:

* the model receives ONLY the findings' already-computed sentences, so it can
  phrase evidence but never produce any (the boundary `agent/nodes/explain.py`
  proved);
* any failure -- disabled, unreachable, empty reply -- falls back to the
  template, so a dead model degrades prose quality and never availability
  (llm.py's "failure is normal and must not propagate");
* a reply stating a number the evidence does not contain is DISCARDED. The
  prompt forbids invention, but explain.py's round-5 history shows prompts do
  not hold that line alone -- the guard is on the output.
"""
import pytest

from app.services import insights as ins


@pytest.fixture(autouse=True)
def _reset_breaker():
    """The down-marker is module state; a failure test would otherwise trip it
    and every later test would skip the client without touching the code under
    test -- passing or failing for reasons that have nothing to do with it."""
    ins._narrative_down_until = 0.0
    yield
    ins._narrative_down_until = 0.0


class _FakeClient:
    def __init__(self, reply):
        self._reply = reply
        self.calls = []

    async def complete(self, messages, **kw):
        self.calls.append(messages)
        return self._reply


FINDINGS = [
    {"kind": "standout", "score": 0.8,
     "title": "N carries 91% of revenue",
     "detail": "2 values of region would average 50% each; N holds 88.4k of 97.2k.",
     "columns": ["region", "revenue"]},
    {"kind": "correlation", "score": 0.7,
     "title": "revenue moves with cost (r = 0.99)",
     "detail": "Strongly correlated across 200 rows.",
     "columns": ["revenue", "cost"]},
]


def _patched(monkeypatch, client):
    import app.services.llm as llm
    monkeypatch.setattr(llm, "get_client", lambda: client)


class TestTheBoundary:
    @pytest.mark.asyncio
    async def test_the_model_sees_only_precomputed_sentences(self, monkeypatch):
        """The facts block is titles + details -- numbers already baked in.
        No frame, no columns, nothing to compute over."""
        client = _FakeClient("N carries 91% of revenue, and revenue moves with cost.")
        _patched(monkeypatch, client)
        await ins.narrate_findings(FINDINGS)
        sent = str(client.calls[0])
        assert "91%" in sent
        assert "r = 0.99" in sent

    @pytest.mark.asyncio
    async def test_a_faithful_reply_is_used(self, monkeypatch):
        _patched(monkeypatch, _FakeClient(
            "N carries 91% of revenue; revenue moves with cost (r = 0.99) "
            "across 200 rows."))
        out = await ins.narrate_findings(FINDINGS)
        assert out is not None and "91%" in out


class TestFailureFallsBack:
    @pytest.mark.asyncio
    async def test_a_dead_model_returns_none(self, monkeypatch):
        # llm.complete returns None when disabled/unreachable, by contract.
        _patched(monkeypatch, _FakeClient(None))
        assert await ins.narrate_findings(FINDINGS) is None

    @pytest.mark.asyncio
    async def test_an_empty_reply_returns_none(self, monkeypatch):
        _patched(monkeypatch, _FakeClient("   "))
        assert await ins.narrate_findings(FINDINGS) is None

    @pytest.mark.asyncio
    async def test_a_broken_client_factory_returns_none(self, monkeypatch):
        import app.services.llm as llm

        def boom():
            raise RuntimeError("no loop")
        monkeypatch.setattr(llm, "get_client", boom)
        assert await ins.narrate_findings(FINDINGS) is None

    @pytest.mark.asyncio
    async def test_no_findings_means_no_call_at_all(self, monkeypatch):
        client = _FakeClient("anything")
        _patched(monkeypatch, client)
        assert await ins.narrate_findings([]) is None
        assert client.calls == []


class TestTheDigitGuard:
    @pytest.mark.asyncio
    async def test_an_invented_number_discards_the_reply(self, monkeypatch):
        """THE guard. "About 95% of revenue" states a figure the evidence does
        not contain; the template -- which cannot misstate -- is used instead."""
        _patched(monkeypatch, _FakeClient("N carries about 95% of revenue."))
        assert await ins.narrate_findings(FINDINGS) is None

    @pytest.mark.asyncio
    async def test_a_rounded_number_is_also_discarded(self, monkeypatch):
        # "roughly 90%" reads harmless and is exactly how misstatement starts.
        _patched(monkeypatch, _FakeClient("N carries roughly 90% of revenue."))
        assert await ins.narrate_findings(FINDINGS) is None

    @pytest.mark.asyncio
    async def test_a_reply_with_no_numbers_at_all_is_allowed(self, monkeypatch):
        # Stating fewer numbers than the evidence is honest; stating different
        # ones is not.
        _patched(monkeypatch, _FakeClient(
            "Revenue is heavily concentrated in one region, and it moves "
            "closely with cost."))
        out = await ins.narrate_findings(FINDINGS)
        assert out is not None

    @pytest.mark.asyncio
    async def test_the_row_count_is_part_of_the_evidence(self, monkeypatch):
        _patched(monkeypatch, _FakeClient("Across 5000 rows, N leads with 91%."))
        out = await ins.narrate_findings(FINDINGS, row_count=5000)
        assert out is not None


class TestTheBreaker:
    @pytest.mark.asyncio
    async def test_a_failure_stops_further_attempts(self, monkeypatch):
        """Measured live: without this, a down model cost EVERY insights click
        the full 8s ceiling. One failure buys a quiet period; the template
        serves in the meantime."""
        client = _FakeClient(None)          # llm.py contract: None = down
        _patched(monkeypatch, client)
        await ins.narrate_findings(FINDINGS)
        await ins.narrate_findings(FINDINGS)
        assert len(client.calls) == 1       # second call never reached the model

    @pytest.mark.asyncio
    async def test_a_bad_answer_is_not_downtime(self, monkeypatch):
        # An empty string is a model that answered badly; it stays reachable.
        client = _FakeClient("   ")
        _patched(monkeypatch, client)
        await ins.narrate_findings(FINDINGS)
        await ins.narrate_findings(FINDINGS)
        assert len(client.calls) == 2

