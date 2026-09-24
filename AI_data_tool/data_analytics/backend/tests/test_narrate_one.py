"""One guarded sentence for one finding -- the Dynamic Pin card's prose.

Same boundary as narrate_findings, pinned separately because the card is a
separate consumer: the model only ever rephrases a finding's own computed
sentence and figures, a reply stating a number the evidence lacks is
discarded, and the breaker state is SHARED -- a model that just failed a scan
narration must not be asked again for a card.
"""
import pytest

from app.services import insights as ins


@pytest.fixture(autouse=True)
def _reset_breaker():
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


FINDING = {
    "kind": "trend", "score": 0.6,
    "title": "revenue in 2026-08 ran 26% above its monthly average",
    "detail": "12.4M against an average of 9.8M over the prior 5 months.",
    "columns": ["revenue", "date"],
    "figures": {"delta_pct": 26.5, "value": 12400000.0, "direction": "up"},
}


def _patched(monkeypatch, client):
    import app.services.llm as llm
    monkeypatch.setattr(llm, "get_client", lambda: client)


class TestTheCardSentence:
    @pytest.mark.asyncio
    async def test_the_model_sees_title_detail_and_figures(self, monkeypatch):
        client = _FakeClient("Revenue rose 26% to 12.4M.")
        _patched(monkeypatch, client)
        await ins.narrate_one(FINDING)
        sent = str(client.calls[0])
        assert "26% above" in sent
        assert "26.5" in sent            # figures travel as evidence too

    @pytest.mark.asyncio
    async def test_a_faithful_sentence_is_used(self, monkeypatch):
        _patched(monkeypatch, _FakeClient("Revenue ran 26% above its average, at 12.4M."))
        out = await ins.narrate_one(FINDING)
        assert out is not None and "26%" in out

    @pytest.mark.asyncio
    async def test_an_invented_number_is_discarded(self, monkeypatch):
        # "about 30%" is a figure the evidence does not contain; the template
        # -- which cannot misstate -- stays on the card.
        _patched(monkeypatch, _FakeClient("Revenue rose about 30% this month."))
        assert await ins.narrate_one(FINDING) is None

    @pytest.mark.asyncio
    async def test_a_dead_model_returns_none_and_arms_the_breaker(self, monkeypatch):
        client = _FakeClient(None)
        _patched(monkeypatch, client)
        assert await ins.narrate_one(FINDING) is None
        assert await ins.narrate_one(FINDING) is None
        assert len(client.calls) == 1     # second call skipped the model

    @pytest.mark.asyncio
    async def test_the_breaker_is_shared_with_scan_narration(self, monkeypatch):
        """One model, one health state. A card must not retry a model the scan
        narrator just watched fail."""
        client = _FakeClient(None)
        _patched(monkeypatch, client)
        await ins.narrate_findings([FINDING])     # fails, arms the breaker
        await ins.narrate_one(FINDING)            # must not call again
        assert len(client.calls) == 1

    @pytest.mark.asyncio
    async def test_an_empty_finding_is_never_sent(self, monkeypatch):
        client = _FakeClient("anything")
        _patched(monkeypatch, client)
        assert await ins.narrate_one({}) is None
        assert client.calls == []


class TestTheEndpoint:
    """Both answers, and neither depending on whether the GPU box happens to be up.

    This used to assume "LLM disabled in the test env" and read the ambient
    configuration. On a machine where the model endpoint IS reachable -- a
    developer's, and this one -- it failed, which made a real regression run look
    like it had found something and cost a bisect to rule out. A test whose result
    depends on a service being down is not testing the code.
    """

    @pytest.mark.asyncio
    async def test_null_sentence_is_a_normal_answer(self, client, auth_headers,
                                                    monkeypatch):
        """No model, or nothing usable back: {sentence: null} means "keep the
        template", and is never an error."""
        _patched(monkeypatch, _FakeClient(None))

        r = await client.post("/api/v1/analysis/narrate",
                              json={"finding": FINDING},
                              headers=auth_headers["a"])

        assert r.status_code == 200
        assert r.json() == {"sentence": None}

    @pytest.mark.asyncio
    async def test_a_usable_sentence_is_returned(self, client, auth_headers,
                                                 monkeypatch):
        """The other half, which nothing covered: when the model answers within
        the digit guard, the endpoint passes the sentence through."""
        _patched(monkeypatch, _FakeClient(
            "Revenue in 2026-08 ran 26.5% above its average, at 12.4M."))

        r = await client.post("/api/v1/analysis/narrate",
                              json={"finding": FINDING},
                              headers=auth_headers["a"])

        assert r.status_code == 200
        assert "26.5" in (r.json()["sentence"] or "")

    @pytest.mark.asyncio
    async def test_a_sentence_stating_an_invented_number_is_refused(
            self, client, auth_headers, monkeypatch):
        """The digit guard, at the endpoint rather than only in the service. A
        model that rounds 26.5% to "about 30%" must reach the caller as null."""
        _patched(monkeypatch, _FakeClient("Revenue jumped about 99% last month."))

        r = await client.post("/api/v1/analysis/narrate",
                              json={"finding": FINDING},
                              headers=auth_headers["a"])

        assert r.status_code == 200
        assert r.json() == {"sentence": None}

    @pytest.mark.asyncio
    async def test_it_requires_auth(self, client):
        r = await client.post("/api/v1/analysis/narrate", json={"finding": FINDING})
        assert r.status_code in (401, 403)
