"""Several LLM endpoints, one default, a live up/down light for each.

The platform used to know exactly one model endpoint (`settings.llm_base_url`).
When that machine was down, every AI feature was down with it, and nobody could
see why until a request failed. This module keeps a LIST of OpenAI-compatible
endpoints instead:

- A platform admin keeps the list on Admin -> Platform settings -> "LLM
  endpoints" and picks the default: one endpoint, or ``auto``.
- ``auto`` means "any endpoint that is up": the reachable ones in list order,
  so a call fails over to the next endpoint when one does not answer.
- Anyone signed in may pick a different endpoint (or ``auto``) for their own
  requests from the top bar. The choice travels as the ``X-LLM-Endpoint``
  header; `main.py`'s middleware puts it in `_choice` for the request, and
  `llm.get_client()` reads it -- so every call site follows the choice without
  having to know about it.
- A background loop probes every enabled endpoint (``GET /models``) so the UI
  can show a green or red light without anyone having to try a question first.
  Real calls also report back (`mark`), so the light turns red the moment a
  call fails rather than at the next probe.

Storage: one `app_settings` row, key ``llm_endpoints``::

    {"default": "auto" | "<id>",
     "endpoints": [{"id", "name", "base_url", "model", "api_key", "enabled"}]}

``api_key`` is encrypted at rest and is never sent to a browser. With no row
saved, the list comes from the deployment: ``settings.llm_endpoints`` (the
``LLM_ENDPOINTS`` env var, a JSON list) when set, else ONE endpoint built live
from the older single-endpoint settings (``llm_base_url`` / ``llm_model`` /
``llm_api_key``), so an install that never opens the new panel behaves
exactly as before.

SMART AUTO (`route`)
--------------------
Auto does not just take the first endpoint that is up. For each call it
orders the endpoints by what that call needs, cheapest rules first:

1. Fit. The prompt is estimated in tokens; an endpoint whose context
   (``max_model_len``, read from its /models answer, or set by the admin) is
   too small for prompt + answer is skipped -- asking a 16k model a 20k
   prompt only buys a 400 error. When nothing fits, the largest context wins.
2. Health. Endpoints that are up go first, never-checked next, down last.
3. Weight. Heavy work (Ask AI, the copilot, dashboard suggestions: SQL and
   plans where a weak answer is a wrong answer) goes to the STRONGEST model;
   light work (column descriptions, short narratives, classification,
   background batches) goes to the WEAKEST that fits, which is also the
   fastest and keeps the big model free for people waiting on it.
4. Load. Between equals, the one with fewer calls in flight.

Strength is the admin's 1-10 rank per endpoint (vLLM does not report
parameter counts); a blank one is guessed from a size in the model name
("27b" -> 8). No judge model, no learning: every rule is cheap, predictable
and explainable, which is what a picker with a status light needs.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings

logger = logging.getLogger(__name__)

ROW_KEY = "llm_endpoints"
AUTO = "auto"
ENV_ID = "env"
#: How often the background loop probes every endpoint.
PROBE_SECONDS = 30
#: A probe must be quick: it only asks "are you there?".
PROBE_TIMEOUT_S = 5.0
_ID_OK = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class EndpointError(ValueError):
    """A list the admin cannot save; the message says which entry and why."""


@dataclass(frozen=True)
class Endpoint:
    id: str
    name: str
    base_url: str
    model: str
    api_key: str = ""
    enabled: bool = True
    #: 1-10, higher = better answers. 0 = not set: guessed from the name.
    strength: int = 0
    #: Context window in tokens. 0 = not set: read from the endpoint's /models.
    context: int = 0


_SIZE = re.compile(r"(\d+(?:\.\d+)?)\s*b\b", re.IGNORECASE)


def guess_strength(model: str) -> int:
    """A rank from a parameter count in the model name ("qwen3.8_27b" -> 8);
    5 when the name says nothing."""
    m = _SIZE.search((model or "").replace("_", " ").replace("-", " "))
    if not m:
        return 5
    b = float(m.group(1))
    return 10 if b >= 60 else 9 if b >= 30 else 8 if b >= 20 else 6 if b >= 12 else 4 if b >= 7 else 3 if b >= 3 else 2


def strength_of(ep: Endpoint) -> int:
    return ep.strength or guess_strength(ep.model)


def context_of(ep: Endpoint) -> int:
    """Tokens the endpoint accepts; 0 when unknown (then nothing is skipped)."""
    return ep.context or int((_meta.get(ep.id) or {}).get("max_model_len") or 0)


# ---------------------------------------------------------------------------
# State: the saved list (None = nothing saved, use the environment) and health
# ---------------------------------------------------------------------------

_saved: list[Endpoint] | None = None
_saved_default: str = AUTO
#: endpoint id -> {"ok": bool, "latency_ms": int|None, "checked_at": iso, "error": str|None}
_health: dict[str, dict[str, Any]] = {}
#: endpoint id -> what its /models said about the configured model.
_meta: dict[str, dict[str, Any]] = {}
#: endpoint id -> calls in flight in this process (the router's load signal).
_inflight: dict[str, int] = {}
#: The request's own pick (the X-LLM-Endpoint header), if it made one.
_choice: ContextVar[str | None] = ContextVar("llm_endpoint_choice", default=None)
#: The calls answered during the current HTTP request, in order: main.py's
#: middleware opens a fresh list per request and sends it back as the
#: X-LLM-Used header, so the top bar can show which model Auto really used.
_used: ContextVar[list | None] = ContextVar("llm_endpoints_used", default=None)
#: user id -> their most recent answered calls (newest last), for the picker
#: after a reload and for work that outlives the request that started it.
_last_by_user: dict[int, list[dict[str, Any]]] = {}
_LAST_KEEP = 6


def _env_endpoint() -> Endpoint:
    return Endpoint(id=ENV_ID, name="Default", base_url=settings.llm_base_url,
                    model=settings.llm_model, api_key=settings.llm_api_key, enabled=True)


_builtin_cache: tuple[str, list[Endpoint]] | None = None


def _builtin() -> list[Endpoint]:
    """The deployment's list (settings.llm_endpoints, JSON), parsed once per
    value. A malformed value is logged and ignored, never fatal."""
    global _builtin_cache
    raw = (settings.llm_endpoints or "").strip()
    if _builtin_cache is not None and _builtin_cache[0] == raw:
        return _builtin_cache[1]
    eps: list[Endpoint] = []
    if raw:
        try:
            import json
            for n, item in enumerate(json.loads(raw), start=1):
                name = str(item.get("name") or item.get("model") or f"Endpoint {n}")
                eid = str(item.get("id") or re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-").lower()[:40] or f"ep{n}")
                eps.append(Endpoint(
                    id=eid, name=name, base_url=str(item["base_url"]).rstrip("/"),
                    model=str(item.get("model") or ""), api_key=str(item.get("api_key") or ""),
                    enabled=bool(item.get("enabled", True)), strength=int(item.get("strength") or 0),
                    context=int(item.get("context") or 0)))
        except Exception:
            logger.exception("LLM_ENDPOINTS is not a valid JSON list of endpoints; ignoring it")
            eps = []
    _builtin_cache = (raw, eps)
    return eps


def endpoints() -> list[Endpoint]:
    """Every configured endpoint, in the admin's order (enabled or not)."""
    if _saved is not None:
        return list(_saved)
    return list(_builtin()) or [_env_endpoint()]


def default_choice() -> str:
    if _saved is not None:
        return _saved_default
    if _builtin():
        default = (settings.llm_endpoints_default or AUTO).strip()
        return default if default == AUTO or any(e.id == default for e in _builtin()) else AUTO
    return ENV_ID


def source() -> str:
    if _saved is not None:
        return "saved"
    return "deployment" if _builtin() else "environment"


def find(endpoint_id: str | None) -> Endpoint | None:
    return next((e for e in endpoints() if e.id == endpoint_id), None)


# -- the per-request choice ---------------------------------------------------

def use_choice(choice: str | None) -> Token:
    value = (choice or "").strip()[:40] or None
    return _choice.set(value)


def release_choice(token: Token) -> None:
    try:
        _choice.reset(token)
    except ValueError:
        _choice.set(None)


def current_choice() -> str:
    """The request's pick when it names something that exists, else the default."""
    picked = _choice.get()
    if picked and (picked == AUTO or find(picked) is not None):
        return picked
    return default_choice()


# -- health -------------------------------------------------------------------

def health(endpoint_id: str) -> dict[str, Any] | None:
    return _health.get(endpoint_id)


def is_up(endpoint_id: str) -> bool | None:
    """True / False from the last probe or call; None when never checked."""
    h = _health.get(endpoint_id)
    return None if h is None else bool(h["ok"])


def mark(endpoint_id: str | None, ok: bool, error: str | None = None,
         latency_ms: int | None = None) -> None:
    """Record what a probe or a real call just learned about an endpoint."""
    if not endpoint_id:
        return
    _health[endpoint_id] = {
        "ok": ok, "error": None if ok else (error or "did not answer")[:300],
        "latency_ms": latency_ms, "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def candidates(choice: str | None = None) -> list[Endpoint]:
    """The endpoints a call should try, in order.

    A named endpoint is used alone, up or down: the person asked for that one
    (a down one then fails with its own error instead of silently answering
    from somewhere else). ``auto`` is every enabled endpoint, the ones that
    are up first, then the never-checked, then the down ones as a last
    resort -- a stale red light must not stop a call that would now succeed.
    """
    choice = choice or current_choice()
    if choice != AUTO:
        ep = find(choice)
        if ep is not None and ep.enabled:
            return [ep]
    live = [e for e in endpoints() if e.enabled]
    rank = {True: 0, None: 1, False: 2}
    return sorted(live, key=lambda e: rank[is_up(e.id)])   # stable: keeps list order


def auto_pick() -> str | None:
    """Which endpoint ``auto`` would use right now (for the UI)."""
    first = next(iter(candidates(AUTO)), None)
    return first.id if first is not None and is_up(first.id) else None


# ---------------------------------------------------------------------------
# Smart Auto: which endpoint for THIS call
# ---------------------------------------------------------------------------

HEAVY, NORMAL, LIGHT = "heavy", "normal", "light"
#: services/quotas.py feature names -> how much the answer's quality matters.
FEATURE_WEIGHT = {
    "ask": HEAVY, "copilot": HEAVY, "suggest": HEAVY,
    "explain": NORMAL, "insights": NORMAL, "automation": NORMAL,
    "narrate": LIGHT, "metadata": LIGHT,
}
#: Headroom kept free in a context window: the estimate is an estimate.
_CONTEXT_MARGIN = 0.92


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """A deliberately high estimate: ~3 characters a token for English, and
    Arabic runs closer to 2, so 2.5 errs toward "does not fit" rather than
    toward a 400 from the server."""
    chars = sum(len(str(m.get("content") or "")) for m in messages)
    return int(chars / 2.5) + 8 * len(messages) + 16


def fits(ep: Endpoint, prompt_tokens: int, max_tokens: int) -> bool:
    ctx = context_of(ep)
    return not ctx or prompt_tokens + max_tokens <= ctx * _CONTEXT_MARGIN


def route(pool: list[Endpoint], *, prompt_tokens: int, max_tokens: int,
          weight: str = NORMAL) -> list[Endpoint]:
    """Order `pool` for one call (see SMART AUTO in the module docstring).
    Never drops an endpoint: ones that do not fit or are down go last, so a
    call still has somewhere to go when every rule is against it."""
    health_rank = {True: 0, None: 1, False: 2}

    def key(ep: Endpoint):
        fit = fits(ep, prompt_tokens, max_tokens)
        strength = strength_of(ep)
        # Heavy: strongest first. Light: weakest (fastest) first. Normal:
        # strongest first, but a busy strong model yields to an idle one.
        pref = strength if weight == LIGHT else -strength
        load = _inflight.get(ep.id, 0)
        if weight == NORMAL:
            pref += 2 * load
        return (0 if fit else 1,
                -context_of(ep) if not fit else 0,       # nothing fits: the biggest window
                health_rank[is_up(ep.id)], pref, load)
    return sorted(pool, key=key)


def open_usage() -> Token:
    return _used.set([])


def close_usage(token: Token) -> list[dict[str, Any]]:
    got = _used.get() or []
    try:
        _used.reset(token)
    except ValueError:
        _used.set(None)
    return got


def record_use(endpoint_id: str | None, weight: str, *, auto: bool,
               user_id: int | None = None, feature: str | None = None) -> None:
    """One call was answered by `endpoint_id`. Kept for this request's
    X-LLM-Used header and, when the caller is known, the person's history."""
    if not endpoint_id:
        return
    ep = find(endpoint_id)
    entry = {"id": endpoint_id, "name": ep.name if ep else endpoint_id,
             "model": ep.model if ep else "", "weight": weight, "auto": auto,
             "feature": feature, "at": datetime.now(timezone.utc).isoformat()}
    used = _used.get()
    if used is not None:
        used.append(entry)
    if user_id is not None:
        hist = _last_by_user.setdefault(user_id, [])
        hist.append(entry)
        del hist[:-_LAST_KEEP]


def used_header(used: list[dict[str, Any]]) -> str:
    """`id=weight` per answered call, in order, e.g.
    ``qwen3.5-9b=light,qwen3.8-27b=heavy`` -- ASCII-only, as a header must be."""
    return ",".join(f"{u['id']}={u['weight']}" for u in used)[:1000]


def last_used(user_id: int | None) -> list[dict[str, Any]]:
    return list(_last_by_user.get(user_id, [])) if user_id is not None else []


def begin_call(endpoint_id: str | None) -> None:
    if endpoint_id:
        _inflight[endpoint_id] = _inflight.get(endpoint_id, 0) + 1


def end_call(endpoint_id: str | None) -> None:
    if endpoint_id and _inflight.get(endpoint_id):
        _inflight[endpoint_id] -= 1


async def probe(ep: Endpoint, *, transport: httpx.AsyncBaseTransport | None = None) -> dict[str, Any]:
    """Is the endpoint there, and does it serve the model it is set up for?

    ``GET {base}/models`` is what every OpenAI-compatible server (vLLM,
    Ollama, llama.cpp, LM Studio, OpenAI) answers without spending a token.
    A server with no /models route (404) answered, so it counts as up.
    """
    headers = {"Authorization": f"Bearer {ep.api_key}"} if ep.api_key else {}
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_S, transport=transport) as http:
            r = await http.get(ep.base_url.rstrip("/") + "/models", headers=headers)
        ms = round((time.monotonic() - started) * 1000)
        if r.status_code in (401, 403):
            mark(ep.id, False, f"HTTP {r.status_code}: the API key was refused", ms)
        elif r.status_code >= 500:
            mark(ep.id, False, f"HTTP {r.status_code}", ms)
        else:
            served: list[str] = []
            models: list[dict] = []
            if r.status_code < 400:
                try:
                    models = [m for m in (r.json().get("data") or []) if isinstance(m, dict)]
                    served = [str(m.get("id")) for m in models]
                except Exception:
                    served = []
            mine = next((m for m in models if str(m.get("id")) == ep.model), None)
            if mine is not None and mine.get("max_model_len"):
                _meta[ep.id] = {"max_model_len": int(mine["max_model_len"])}
            if served and ep.model and ep.model not in served:
                mark(ep.id, False, f"model '{ep.model}' is not served here (serves: {', '.join(served[:5])})", ms)
            else:
                mark(ep.id, True, None, ms)
    except Exception as exc:
        mark(ep.id, False, f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__)
    return _health[ep.id]


async def probe_all() -> None:
    eps = [e for e in endpoints() if e.enabled]
    await asyncio.gather(*(probe(e) for e in eps), return_exceptions=True)
    known = {e.id for e in endpoints()}
    for stale in set(_health) - known:
        _health.pop(stale, None)
    for stale in set(_meta) - known:
        _meta.pop(stale, None)


async def run_prober() -> None:
    """Background loop, one per process (started in main.py's lifespan)."""
    while True:
        try:
            if settings.llm_enabled:
                await probe_all()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("LLM endpoint probe failed")
        await asyncio.sleep(PROBE_SECONDS)


# ---------------------------------------------------------------------------
# Saving and loading
# ---------------------------------------------------------------------------

def apply_stored(value: Any) -> None:
    """Make a stored row (or None: no row) the live list. Never raises: a row
    that no longer makes sense is logged and the environment endpoint used."""
    global _saved, _saved_default
    if value is None:
        _saved, _saved_default = None, AUTO
        return
    try:
        from .secrets import decrypt_value
        eps = []
        for raw in value.get("endpoints") or []:
            key = raw.get("api_key") or ""
            eps.append(Endpoint(id=str(raw["id"]), name=str(raw.get("name") or raw["id"]),
                                base_url=str(raw["base_url"]), model=str(raw.get("model") or ""),
                                api_key=decrypt_value(key) if key else "",
                                enabled=bool(raw.get("enabled", True)),
                                strength=int(raw.get("strength") or 0),
                                context=int(raw.get("context") or 0)))
        default = str(value.get("default") or AUTO)
        if default != AUTO and not any(e.id == default for e in eps):
            default = AUTO
        _saved, _saved_default = eps, default
    except Exception:
        logger.exception("saved LLM endpoint list ignored; using the environment endpoint")
        _saved, _saved_default = None, AUTO


def _clean(items: list[dict[str, Any]], default: str) -> tuple[list[Endpoint], str]:
    """Validate the list from the form. `api_key` None keeps the stored key of
    the endpoint with that id; "" removes it."""
    if not items:
        raise EndpointError("Add at least one endpoint, or turn AI features off instead")
    out: list[Endpoint] = []
    seen: set[str] = set()
    for n, raw in enumerate(items, start=1):
        name = str(raw.get("name") or "").strip()
        base = str(raw.get("base_url") or "").strip().rstrip("/")
        model = str(raw.get("model") or "").strip()
        label = name or f"Endpoint {n}"
        if not name:
            raise EndpointError(f"Endpoint {n}: give it a name")
        p = urlparse(base)
        if p.scheme not in ("http", "https") or not p.netloc:
            raise EndpointError(f"{label}: the address must be an http(s) URL, e.g. http://host:8000/v1")
        if not model:
            raise EndpointError(f"{label}: enter the model name the endpoint serves")
        eid = str(raw.get("id") or "").strip() or uuid.uuid4().hex[:8]
        if not _ID_OK.match(eid) or eid == AUTO:
            raise EndpointError(f"{label}: invalid id")
        if eid in seen:
            raise EndpointError(f"{label}: two endpoints share the id '{eid}'")
        seen.add(eid)
        key = raw.get("api_key")
        if key is None:
            old = find(eid)
            key = old.api_key if old is not None else ""
        try:
            strength = int(raw.get("strength") or 0)
            context = int(raw.get("context") or 0)
        except (TypeError, ValueError):
            raise EndpointError(f"{label}: strength and context must be whole numbers") from None
        if not 0 <= strength <= 10:
            raise EndpointError(f"{label}: strength must be 1 to 10 (or empty to guess it)")
        if context < 0:
            raise EndpointError(f"{label}: context must be a positive number of tokens (or empty)")
        out.append(Endpoint(id=eid, name=name[:80], base_url=base, model=model[:200],
                            api_key=str(key).strip(), enabled=bool(raw.get("enabled", True)),
                            strength=strength, context=context))
    default = (default or AUTO).strip()
    if default != AUTO:
        target = next((e for e in out if e.id == default), None)
        if target is None:
            raise EndpointError("The default must be one of the endpoints, or Auto")
        if not target.enabled:
            raise EndpointError(f"{target.name}: a disabled endpoint cannot be the default")
    if not any(e.enabled for e in out):
        raise EndpointError("At least one endpoint must be enabled")
    return out, default


async def save(db: AsyncSession, items: list[dict[str, Any]], default: str, by: str) -> None:
    from ..models.models import AppSetting
    from .secrets import encrypt_value
    eps, default = _clean(items, default)
    stored = {"default": default, "endpoints": [
        {"id": e.id, "name": e.name, "base_url": e.base_url, "model": e.model,
         "api_key": encrypt_value(e.api_key) if e.api_key else "", "enabled": e.enabled,
         "strength": e.strength, "context": e.context}
        for e in eps]}
    now = datetime.utcnow()
    row = await db.get(AppSetting, ROW_KEY)
    if row is None:
        db.add(AppSetting(key=ROW_KEY, value=stored, updated_by=by, updated_at=now))
    else:
        row.value, row.updated_by, row.updated_at = stored, by, now
    await db.flush()
    apply_stored(stored)


async def reset(db: AsyncSession) -> None:
    """Forget the saved list: back to the single environment endpoint."""
    from sqlalchemy import delete
    from ..models.models import AppSetting
    await db.execute(delete(AppSetting).where(AppSetting.key == ROW_KEY))
    await db.flush()
    apply_stored(None)


# ---------------------------------------------------------------------------
# What the browser sees
# ---------------------------------------------------------------------------

def describe(*, admin: bool = False, user_id: int | None = None) -> dict[str, Any]:
    """The list with a status light each. Addresses only for admins; an API
    key never, only whether one is set."""
    default = default_choice()
    items = []
    for e in endpoints():
        item: dict[str, Any] = {
            "id": e.id, "name": e.name, "model": e.model, "enabled": e.enabled,
            "is_default": e.id == default, "status": _health.get(e.id),
            "strength": strength_of(e), "context": context_of(e) or None,
        }
        if admin:
            item.update(base_url=e.base_url, has_api_key=bool(e.api_key),
                        strength_set=e.strength or None, context_set=e.context or None,
                        max_model_len=(_meta.get(e.id) or {}).get("max_model_len"))
        items.append(item)
    return {"llm_enabled": settings.llm_enabled, "default": default,
            "auto_pick": auto_pick(), "source": source(), "endpoints": items,
            "last_used": last_used(user_id)}
