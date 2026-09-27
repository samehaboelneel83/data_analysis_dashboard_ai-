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
    """Values to try before saving; anything left out uses the current setting."""
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None


@router.post("/test-llm")
async def test_llm(body: LlmTest | None = None, _: User = Depends(require_super_admin)):
    """One tiny completion against the endpoint, with the values on the form.
    Says what went wrong in words a person can act on."""
    from ..services.llm import LLMClient
    body = body or LlmTest()
    try:
        base = app_settings._validate("llm_base_url", body.llm_base_url) if body.llm_base_url else settings.llm_base_url
    except app_settings.SettingError as e:
        raise HTTPException(400, str(e))
    model = (body.llm_model or settings.llm_model).strip()
    key = settings.llm_api_key if body.llm_api_key is None else body.llm_api_key
    client = LLMClient(base_url=base, model=model, enabled=True, api_key=key,
                       timeout=min(settings.llm_timeout_s, 30.0))
    started = time.monotonic()
    reply = await client.complete([{"role": "user", "content": "Reply with the word ok."}],
                                  max_tokens=5, temperature=0)
    ms = round((time.monotonic() - started) * 1000)
    if reply is None:
        return {"ok": False, "latency_ms": ms, "model": model,
                "detail": client.last_error or "The endpoint did not answer."}
    return {"ok": True, "latency_ms": ms, "model": model, "detail": f"Answered: {reply.strip()[:60]}"}
