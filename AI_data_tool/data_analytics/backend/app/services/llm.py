"""Client for the self-hosted model endpoint.

Speaks the OpenAI-compatible `/v1/chat/completions` API that vLLM serves, which
is what the existing `prompt.py` prototype talks to. What it deliberately does
NOT carry over from that prototype is the Wren AI dependency: ARCHITECTURE.md
lists WrenAI under "Avoided entirely" because it is AGPL, and a commercial
product should not have it in the query path. The endpoint is just vLLM over
HTTP and is fine; the semantic model Wren's MDL supplies is built natively in
Layer 3.

FAILURE IS NORMAL AND MUST NOT PROPAGATE
-----------------------------------------
The model runs on a separate machine. It will be rebooted, reimaged, saturated,
and occasionally unplugged. Layer 1 uses it for column descriptions — a genuine
improvement, never a requirement — so every method here returns None on failure
instead of raising.

That is a deliberate API choice rather than laziness about error handling.
Returning None makes graceful degradation the behaviour a caller gets by
default; an exception would make it something each call site has to remember to
catch, and the one that forgets takes down a nightly sync at 3am over a missing
sentence of prose. The error is still recorded on `last_error` for callers that
want to surface it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import weakref
from typing import Any

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)

#: Matches a ```json ... ``` or ``` ... ``` fence. Instruction-tuned models wrap
#: JSON in fences regardless of how firmly the prompt forbids it, so stripping
#: them is part of parsing rather than a workaround.
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)

#: Per-event-loop gates, weakly keyed — the widget_data.py pattern, for the
#: same reason: the test suite creates a fresh loop per test, and a semaphore
#: is bound to the loop it was created on.
_GATES: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _gates() -> tuple[asyncio.Semaphore, asyncio.Semaphore]:
    """(total, background) for the current loop.

    Reserved headroom (spec F5): background callers hold BOTH, so they can
    never occupy the last `llm_reserved_interactive` slots. Interactive
    callers hold only the total. The reservation is a promise to the person
    waiting on an answer, enforced by construction rather than by priority.
    """
    from ..core.config import settings

    loop = asyncio.get_running_loop()
    made = _GATES.get(loop)
    total_n = settings.llm_max_concurrency
    back_n = max(1, total_n - settings.llm_reserved_interactive)
    if made is None or made[2] != (total_n, back_n):
        made = (asyncio.Semaphore(total_n), asyncio.Semaphore(back_n),
                (total_n, back_n))
        _GATES[loop] = made
    return made[0], made[1]


class LLMClient:
    """One configured connection to the model endpoint.

    Not a singleton — construct one per unit of work when you want isolated
    token accounting, or use `get_client()` for the app-wide default.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        enabled: bool = True,
        timeout: float = 180.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.enabled = enabled
        self.timeout = timeout
        self._transport = transport

        # Accounting. Layer 8's quota work reads these; keeping them here means
        # every call site is measured without having to opt in.
        self.tokens_in = 0
        self.tokens_out = 0
        self.call_count = 0
        self.last_error: str | None = None

    @property
    def _url(self) -> str:
        return f"{self.base_url}/chat/completions"

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        background: bool = False,
        response_format: dict | None = None,
    ) -> str | None:
        """One chat completion. Returns the assistant's text, or None if the
        endpoint is disabled, unreachable, or answered with something unusable.

        `background=True` marks this call as sync/batch work (spec F5): it is
        bounded by both the total gate and the background gate, so it can
        never occupy the reserved-interactive headroom. Acquire order is
        background-then-total, so a background caller blocked on its own cap
        holds nothing else while it waits.
        """
        if not self.enabled:
            # Not an error worth recording — the operator turned it off.
            return None

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": 0.95,
            "stream": False,
            # Qwen emits chain-of-thought into the message body unless this is
            # off, which would land inside any value we then try to parse.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if response_format is not None:
            payload["response_format"] = response_format

        total, back = _gates()
        if background:
            async with back, total:
                return await self._post(payload)
        async with total:
            return await self._post(payload)

    async def _post(self, payload: dict[str, Any]) -> str | None:
        self.call_count += 1
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, transport=self._transport
            ) as http:
                response = await http.post(
                    self._url, json=payload, headers={"Content-Type": "application/json"}
                )
                if response.status_code >= 400:
                    self.last_error = f"HTTP {response.status_code}: {response.text[:300]}"
                    logger.warning("LLM endpoint error: %s", self.last_error)
                    return None
                data = response.json()
        except Exception as exc:
            # Deliberately broad: connect errors, timeouts, TLS failures, invalid
            # JSON bodies and DNS problems are all the same event to a caller —
            # "no description this run" — and none of them may escape.
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("LLM endpoint unreachable: %s", self.last_error)
            return None

        usage = data.get("usage") or {}
        self.tokens_in += int(usage.get("prompt_tokens") or 0)
        self.tokens_out += int(usage.get("completion_tokens") or 0)

        try:
            choice = data["choices"][0]
            content = choice.get("message", {}).get("content") or choice.get("text")
        except (KeyError, IndexError, TypeError):
            content = None

        if not content:
            self.last_error = "response contained no message content"
            logger.warning("LLM returned an unusable payload: %s", str(data)[:300])
            return None

        self.last_error = None
        return content.strip()

    async def complete_json(
        self,
        messages: list[dict[str, str]],
        schema: dict,
        *,
        retries: int = 2,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        background: bool = False,
        enforce: bool = False,
    ) -> dict | None:
        """A completion constrained to a JSON object matching `schema`.

        ARCHITECTURE.md D4.2 wants token-level grammar constraints (XGrammar or
        Outlines) rather than "please respond only in JSON". Without
        `enforce=True` this is the honest stand-in: parse, validate against the
        schema, and retry with the failure fed back — the metadata pipeline's
        contract, kept for callers that want the retry-and-feedback loop.
        `enforce=True` is the real thing (spec F2): it sends
        `response_format: {type: "json_schema", ...}` so the endpoint itself
        constrains decoding, for callers (the agent) that need the contract
        enforced rather than merely retried into.

        Returns None once the attempts are exhausted, or immediately if the
        endpoint is unreachable (a network failure will not become valid JSON on
        the third try; only a bad generation is worth retrying).
        """
        attempt_messages = list(messages)

        for attempt in range(retries + 1):
            raw = await self.complete(
                attempt_messages, max_tokens=max_tokens, temperature=temperature,
                background=background,
                response_format=(
                    {"type": "json_schema",
                     "json_schema": {"name": "reply", "schema": schema}}
                    if enforce else None),
            )
            if raw is None:
                # Transport-level failure. Retrying cannot help.
                return None

            try:
                parsed, problem = _parse_json_object(raw, schema)
            except Exception as exc:
                # The documented contract is "never raises, even on the NEXT
                # schema shape nobody anticipated" -- a union-typed
                # `ambiguity_reason` was that shape once (unhashable `type`
                # list broke a dict lookup) and is fixed above, but this net
                # exists so the class of bug can't come back as a 500. An
                # unexpected exception here becomes an ordinary contract
                # failure: logged with the schema for diagnosis, treated the
                # same as "the model returned junk" for retry purposes.
                problem = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "complete_json: schema validation raised for schema keys "
                    "%s: %s", list(schema.get("properties") or {}), problem)
                parsed = None

            if parsed is not None:
                return parsed

            if attempt < retries:
                # Feed the specific failure back. A model told exactly what was
                # wrong corrects far more often than one told to "try again".
                attempt_messages = list(messages) + [
                    {"role": "assistant", "content": raw},
                    {
                        "role": "user",
                        "content": (
                            f"That response was rejected: {problem}. "
                            "Reply with ONLY a JSON object matching the requested "
                            "schema. No prose, no code fence."
                        ),
                    },
                ]

        self.last_error = f"no schema-valid JSON after {retries + 1} attempts"
        logger.warning("LLM JSON contract not met: %s", self.last_error)
        return None


def _parse_json_object(raw: str, schema: dict) -> tuple[dict | None, str]:
    """Extract and shape-check a JSON object. Returns (object, "") on success,
    (None, reason) on failure — the reason is fed back to the model on retry.

    Validation is intentionally shallow: required keys and top-level types. A
    full JSON Schema validator would add a dependency for a check that catches
    almost nothing extra at this layer, where the schemas are a handful of
    string fields.
    """
    text = raw.strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()

    # A model that adds a sentence before the object is common enough to handle.
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            return None, "no JSON object found in the response"
        text = text[start : end + 1]

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON ({exc.msg})"

    if not isinstance(obj, dict):
        return None, f"expected a JSON object, got {type(obj).__name__}"

    for key in schema.get("required", []):
        if key not in obj:
            return None, f"missing required key {key!r}"

    for key, spec in (schema.get("properties") or {}).items():
        if key not in obj:
            continue
        expected = spec.get("type")
        # JSON-Schema unions (`"type": ["string", "null"]`) are how an
        # optional field is spelled -- the classify schema's
        # `ambiguity_reason` is exactly this. `expected` is then a list,
        # which is unhashable, so a naive `_TYPE_CHECKS.get(expected)` raises
        # TypeError instead of returning a validation failure. Accept the
        # value if it satisfies ANY member of the union; "null" means None.
        candidates = expected if isinstance(expected, list) else [expected]
        ok = True
        for candidate in candidates:
            if candidate == "null":
                if obj[key] is None:
                    ok = True
                    break
                ok = False
                continue
            checker = _TYPE_CHECKS.get(candidate)
            if checker is None:
                # Unknown/unsupported type keyword -- nothing to check against,
                # so do not reject a value over a schema shape we don't model.
                ok = True
                break
            if checker(obj[key]):
                ok = True
                break
            ok = False
        if not ok:
            return None, f"key {key!r} should be a {expected}"

    return obj, ""


#: bool is checked before int deliberately — in Python `isinstance(True, int)`
#: is True, so an unguarded integer check would silently accept a boolean.
_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


def get_client() -> LLMClient:
    """The app-wide client, built from configuration.

    A fresh instance per call so token counters stay scoped to one unit of work;
    httpx opens its connection per request anyway, so there is no pool to share.
    """
    return LLMClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        enabled=settings.llm_enabled,
        timeout=settings.llm_timeout_s,
    )
