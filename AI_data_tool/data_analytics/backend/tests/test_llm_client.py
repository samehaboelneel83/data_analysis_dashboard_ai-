"""The offline model client.

The contract that matters most here is NEGATIVE: this client must never take
the application down with it. Layer 1's LLM pass writes nice-to-have column
descriptions. The GPU box is a separate machine on the network; it will be
rebooted, reimaged, and occasionally unplugged. When that happens a metadata
sync must still complete all six stages, minus the descriptions.

So `complete` and `complete_json` return None on every failure rather than
raising. That is a deliberate API choice: returning None makes degradation the
default behaviour a caller gets for free, whereas an exception makes it
something each of the (eventually many) call sites must remember to catch. The
error is still recorded on `last_error` for anyone who wants to report it.
"""
import json

import httpx
import pytest

from app.services import llm as llm_module
from app.services.llm import LLMClient


def _client(handler, **kw) -> LLMClient:
    """An LLMClient whose HTTP layer is a mock transport."""
    return LLMClient(
        base_url="http://model.test/v1",
        model="qwen3.5",
        enabled=True,
        transport=httpx.MockTransport(handler),
        **kw,
    )


def _reply(content: str, *, prompt_tokens: int = 10, completion_tokens: int = 5) -> httpx.Response:
    return httpx.Response(200, json={
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    })


class TestDegradation:
    """Every failure mode returns None. None of them raise."""

    async def test_connection_error_returns_none(self):
        def handler(request):
            raise httpx.ConnectError("no route to host")

        client = _client(handler)
        assert await client.complete([{"role": "user", "content": "hi"}]) is None
        assert client.last_error is not None

    async def test_timeout_returns_none(self):
        def handler(request):
            raise httpx.ReadTimeout("too slow")

        client = _client(handler)
        assert await client.complete([{"role": "user", "content": "hi"}]) is None

    async def test_http_500_returns_none(self):
        client = _client(lambda request: httpx.Response(500, text="boom"))
        assert await client.complete([{"role": "user", "content": "hi"}]) is None

    async def test_malformed_payload_returns_none(self):
        """A 200 whose body is not the shape we expect is a failure, not a crash."""
        client = _client(lambda request: httpx.Response(200, json={"unexpected": True}))
        assert await client.complete([{"role": "user", "content": "hi"}]) is None

    async def test_disabled_client_never_makes_a_request(self):
        calls = []

        def handler(request):
            calls.append(request)
            return _reply("should not happen")

        client = LLMClient(base_url="http://model.test/v1", model="qwen3.5",
                           enabled=False, transport=httpx.MockTransport(handler))
        assert await client.complete([{"role": "user", "content": "hi"}]) is None
        assert calls == [], "a disabled client must not touch the network at all"


class TestCompletion:
    async def test_returns_the_message_content(self):
        client = _client(lambda request: _reply("  the answer  "))
        assert await client.complete([{"role": "user", "content": "q"}]) == "the answer"

    async def test_sends_the_configured_model_and_disables_thinking(self):
        """prompt.py sets enable_thinking=false; Qwen otherwise emits reasoning
        text that would end up inside the value we parse."""
        seen = {}

        def handler(request):
            seen.update(json.loads(request.content))
            return _reply("ok")

        await _client(handler).complete([{"role": "user", "content": "q"}])
        assert seen["model"] == "qwen3.5"
        assert seen["stream"] is False
        assert seen["chat_template_kwargs"] == {"enable_thinking": False}

    async def test_posts_to_the_chat_completions_path(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            return _reply("ok")

        await _client(handler).complete([{"role": "user", "content": "q"}])
        assert seen["url"] == "http://model.test/v1/chat/completions"

    async def test_base_url_trailing_slash_does_not_double(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            return _reply("ok")

        client = LLMClient(base_url="http://model.test/v1/", model="qwen3.5",
                           enabled=True, transport=httpx.MockTransport(handler))
        await client.complete([{"role": "user", "content": "q"}])
        assert seen["url"] == "http://model.test/v1/chat/completions"


class TestTokenAccounting:
    async def test_usage_accumulates_across_calls(self):
        client = _client(lambda request: _reply("ok", prompt_tokens=10, completion_tokens=5))
        await client.complete([{"role": "user", "content": "q"}])
        await client.complete([{"role": "user", "content": "q"}])
        assert client.tokens_in == 20
        assert client.tokens_out == 10
        assert client.call_count == 2

    async def test_failed_calls_are_counted_but_add_no_tokens(self):
        client = _client(lambda request: httpx.Response(500))
        await client.complete([{"role": "user", "content": "q"}])
        assert client.call_count == 1
        assert client.tokens_in == 0


class TestCompleteJson:
    """Validate-and-retry, the honest stand-in for token-level grammar
    constraints against a plain OpenAI-compatible endpoint."""

    SCHEMA = {
        "type": "object",
        "properties": {"description": {"type": "string"}},
        "required": ["description"],
    }

    async def test_parses_a_clean_json_object(self):
        client = _client(lambda request: _reply('{"description": "the order total"}'))
        got = await client.complete_json([{"role": "user", "content": "q"}], self.SCHEMA)
        assert got == {"description": "the order total"}

    async def test_strips_a_fenced_code_block(self):
        """Instruction-tuned models wrap JSON in ```json fences no matter how
        firmly the prompt says not to."""
        client = _client(lambda request: _reply('```json\n{"description": "x"}\n```'))
        got = await client.complete_json([{"role": "user", "content": "q"}], self.SCHEMA)
        assert got == {"description": "x"}

    async def test_retries_on_invalid_json_then_succeeds(self):
        replies = iter(["not json at all", '{"description": "second try"}'])
        client = _client(lambda request: _reply(next(replies)))
        got = await client.complete_json([{"role": "user", "content": "q"}], self.SCHEMA, retries=1)
        assert got == {"description": "second try"}
        assert client.call_count == 2

    async def test_retries_when_the_schema_does_not_match(self):
        """Valid JSON of the wrong shape is still a failure — the caller asked
        for a contract, not merely for parseable text."""
        replies = iter(['{"wrong_key": 1}', '{"description": "right"}'])
        client = _client(lambda request: _reply(next(replies)))
        got = await client.complete_json([{"role": "user", "content": "q"}], self.SCHEMA, retries=1)
        assert got == {"description": "right"}

    async def test_gives_up_and_returns_none_after_retries(self):
        client = _client(lambda request: _reply("never valid"))
        got = await client.complete_json([{"role": "user", "content": "q"}], self.SCHEMA, retries=2)
        assert got is None
        assert client.call_count == 3, "initial attempt plus two retries"

    async def test_unreachable_endpoint_returns_none_without_retrying_forever(self):
        def handler(request):
            raise httpx.ConnectError("down")

        client = _client(handler)
        assert await client.complete_json([{"role": "user", "content": "q"}], self.SCHEMA, retries=2) is None


class TestFactory:
    async def test_get_client_reads_settings(self):
        """The app builds its client from config, so a deployment can point at a
        different endpoint or switch the model off without a code change."""
        client = llm_module.get_client()
        assert client.model
        assert client.base_url
