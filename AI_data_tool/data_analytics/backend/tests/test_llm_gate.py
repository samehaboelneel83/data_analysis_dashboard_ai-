"""One Qwen box serves the sync AND the agent (spec F5).

Two independent semaphores against one endpoint is a queue nobody manages: a
sync during an agent run doubles the load and the person's question waits
behind 82 table descriptions. The gate lives in the CLIENT, so every caller
is bounded by construction — and background work is capped below the total,
leaving reserved headroom so an interactive question never starves.
"""
import asyncio

import httpx
import pytest

from app.core.config import settings
from app.services.llm import LLMClient


def make_client(inflight, peak, delay=0.05):
    """A client whose transport records concurrency instead of calling out."""
    async def handler(request):
        inflight.append(1)
        peak[0] = max(peak[0], len(inflight))
        await asyncio.sleep(delay)
        inflight.pop()
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })
    return LLMClient(base_url="http://test/v1", model="m",
                     transport=httpx.MockTransport(handler))


MSGS = [{"role": "user", "content": "hi"}]


class TestTheGateBounds:
    async def test_total_concurrency_never_exceeds_the_setting(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_max_concurrency", 3)
        monkeypatch.setattr(settings, "llm_reserved_interactive", 1)
        inflight, peak = [], [0]
        client = make_client(inflight, peak)
        await asyncio.gather(*(client.complete(MSGS) for _ in range(10)))
        assert peak[0] <= 3

    async def test_background_work_cannot_take_the_reserved_slots(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_max_concurrency", 4)
        monkeypatch.setattr(settings, "llm_reserved_interactive", 2)
        inflight, peak = [], [0]
        client = make_client(inflight, peak)
        await asyncio.gather(*(client.complete(MSGS, background=True)
                               for _ in range(10)))
        assert peak[0] <= 2, (
            "background callers filled the whole gate; an interactive "
            "question would queue behind a sync"
        )

    async def test_interactive_work_may_use_every_slot(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_max_concurrency", 4)
        monkeypatch.setattr(settings, "llm_reserved_interactive", 2)
        inflight, peak = [], [0]
        client = make_client(inflight, peak)
        await asyncio.gather(*(client.complete(MSGS) for _ in range(10)))
        assert peak[0] > 2, "the reservation throttled interactive work too"


class TestEnforcedJson:
    async def test_enforce_sends_response_format_json_schema(self):
        seen = {}

        async def handler(request):
            import json
            seen.update(json.loads(request.content))
            return httpx.Response(200, json={
                "choices": [{"message": {"content": '{"x": 1}'}}], "usage": {}})

        client = LLMClient(base_url="http://test/v1", model="m",
                           transport=httpx.MockTransport(handler))
        schema = {"type": "object", "properties": {"x": {"type": "integer"}},
                  "required": ["x"]}
        got = await client.complete_json(MSGS, schema, enforce=True)
        assert got == {"x": 1}
        # F2: json_schema is the ONE enforced mechanism on this endpoint.
        # guided_json is silently ignored — asserting it is absent guards
        # against someone "upgrading" to the documented-but-dead parameter.
        assert seen["response_format"]["type"] == "json_schema"
        assert "guided_json" not in seen


class TestUnionTypedSchema:
    """A JSON-Schema union (`"type": ["string", "null"]`) is how the agent's
    classify schema spells an optional field (ambiguity_reason). `expected`
    being a list broke a naive `_TYPE_CHECKS.get(expected)` dict lookup —
    lists are unhashable — which escaped as a TypeError instead of the
    documented "returns None, never raises" contract. These pin the fix and
    the contract, not just the happy path.
    """

    SCHEMA = {
        "type": "object",
        "properties": {"note": {"type": ["string", "null"]}},
        "required": ["note"],
    }

    def _client(self, content: str) -> LLMClient:
        async def handler(request):
            return httpx.Response(200, json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            })
        return LLMClient(base_url="http://test/v1", model="m",
                         transport=httpx.MockTransport(handler))

    async def test_a_union_typed_field_accepts_a_matching_type(self):
        client = self._client('{"note": "why it is ambiguous"}')
        got = await client.complete_json(MSGS, self.SCHEMA)
        assert got == {"note": "why it is ambiguous"}

    async def test_a_union_typed_field_accepts_explicit_null(self):
        client = self._client('{"note": null}')
        got = await client.complete_json(MSGS, self.SCHEMA)
        assert got == {"note": None}

    async def test_a_union_typed_field_rejects_a_value_of_neither_type(self):
        # 1 is neither a string nor null -- every retry gets the same wrong
        # shape, so the contract is never satisfied and complete_json must
        # give up cleanly rather than loop forever or raise.
        client = self._client('{"note": 1}')
        got = await client.complete_json(MSGS, self.SCHEMA, retries=1)
        assert got is None

    async def test_a_pathological_type_keyword_never_raises(self):
        """`type` as a dict is not a schema this codebase is meant to author,
        but the contract is "never raises even for the NEXT unanticipated
        shape" -- so a schema this malformed must degrade to None, the same
        as any other validation failure, not blow up the caller."""
        client = self._client('{"note": "x"}')
        schema = {
            "type": "object",
            "properties": {"note": {"type": {"weird": "shape"}}},
            "required": ["note"],
        }
        got = await client.complete_json(MSGS, schema, retries=0)
        assert got is None
