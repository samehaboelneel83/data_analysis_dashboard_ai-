"""Platform settings: read and change install-wide settings (services/app_settings.py).

Platform super-admins only: these settings apply to every organization on the
install. Each change is audited by key, never by value, so a secret never
reaches the audit log.
"""
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.database import get_db
from ..dependencies import require_super_admin
from ..models.models import User
from ..services import app_settings
from ..services.audit import record as audit

router = APIRouter(prefix="/platform/settings", tags=["platform"])


class SettingsChange(BaseModel):
    #: key -> new value; null removes the override (back to the environment).
    values: dict[str, object | None]


@router.get("")
async def get_settings(db: AsyncSession = Depends(get_db),
                       _: User = Depends(require_super_admin)):
    return await app_settings.describe(db)


@router.put("")
async def put_settings(body: SettingsChange, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_super_admin)):
    if not body.values:
        raise HTTPException(400, "Nothing to change")
    try:
        restart = await app_settings.save(db, body.values, current_user.email)
    except app_settings.SettingError as e:
        await db.rollback()
        raise HTTPException(400, str(e))
    changed = ", ".join(f"{k}{' (reset)' if v is None else ''}" for k, v in body.values.items())
    await audit(db, current_user, "platform.settings", None, None, changed)
    await db.commit()
    out = await app_settings.describe(db)
    out["restart_required"] = restart
    return out


class LlmTest(BaseModel):
    """Values to try before saving; anything left out uses the current setting
    -- or, with `endpoint_id`, that saved endpoint's value (its stored API key
    included, which the browser never has)."""
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    endpoint_id: str | None = None


@router.post("/test-llm")
async def test_llm(body: LlmTest | None = None, _: User = Depends(require_super_admin)):
    """One tiny completion against the endpoint, with the values on the form.
    Says what went wrong in words a person can act on."""
    from ..services.llm import LLMClient
    from ..services import llm_endpoints
    body = body or LlmTest()
    saved = llm_endpoints.find(body.endpoint_id) if body.endpoint_id else None
    d_base = saved.base_url if saved else settings.llm_base_url
    d_model = saved.model if saved else settings.llm_model
    d_key = saved.api_key if saved else settings.llm_api_key
    try:
        base = app_settings._validate("llm_base_url", body.llm_base_url) if body.llm_base_url else d_base
    except app_settings.SettingError as e:
        raise HTTPException(400, str(e))
    model = (body.llm_model or d_model).strip()
    key = d_key if body.llm_api_key is None else body.llm_api_key
    client = LLMClient(base_url=base, model=model, enabled=True, api_key=key,
                       timeout=min(settings.llm_timeout_s, 30.0),
                       endpoint_id=saved.id if saved and not (body.llm_base_url or body.llm_model) else None)
    started = time.monotonic()
    reply = await client.complete([{"role": "user", "content": "Reply with the word ok."}],
                                  max_tokens=5, temperature=0)
    ms = round((time.monotonic() - started) * 1000)
    if reply is None:
        return {"ok": False, "latency_ms": ms, "model": model,
                "detail": client.last_error or "The endpoint did not answer."}
    return {"ok": True, "latency_ms": ms, "model": model, "detail": f"Answered: {reply.strip()[:60]}"}


# ── Several LLM endpoints (services/llm_endpoints.py) ──────────────────────

class EndpointIn(BaseModel):
    id: str | None = None
    name: str
    base_url: str
    model: str
    #: None keeps the stored key of the endpoint with this id; "" removes it.
    api_key: str | None = None
    enabled: bool = True


class EndpointList(BaseModel):
    endpoints: list[EndpointIn]
    default: str = "auto"


@router.get("/llm-endpoints")
async def get_llm_endpoints(_: User = Depends(require_super_admin)):
    from ..services import llm_endpoints
    return llm_endpoints.describe(admin=True)


@router.put("/llm-endpoints")
async def put_llm_endpoints(body: EndpointList, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(require_super_admin)):
    from ..services import llm_endpoints
    try:
        await llm_endpoints.save(db, [e.model_dump() for e in body.endpoints], body.default,
                                 current_user.email)
    except llm_endpoints.EndpointError as e:
        await db.rollback()
        raise HTTPException(400, str(e))
    await audit(db, current_user, "platform.settings", None, None,
                f"llm_endpoints ({len(body.endpoints)}, default {body.default})")
    await db.commit()
    await llm_endpoints.probe_all()
    return llm_endpoints.describe(admin=True)


@router.delete("/llm-endpoints")
async def reset_llm_endpoints(db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(require_super_admin)):
    """Back to the single endpoint from the environment settings."""
    from ..services import llm_endpoints
    await llm_endpoints.reset(db)
    await audit(db, current_user, "platform.settings", None, None, "llm_endpoints (reset)")
    await db.commit()
    await llm_endpoints.probe_all()
    return llm_endpoints.describe(admin=True)
