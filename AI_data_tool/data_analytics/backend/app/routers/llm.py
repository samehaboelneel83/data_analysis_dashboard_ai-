"""The LLM endpoints any signed-in person can pick from, each with its status.

Feeds the top bar's light and picker. Addresses and keys stay admin-only
(platform_settings.py); this shows names, models and whether each answers.
"""
from fastapi import APIRouter, Depends

from ..dependencies import get_current_user
from ..models.models import User
from ..services import llm_endpoints

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/endpoints")
async def list_endpoints(refresh: bool = False, user: User = Depends(get_current_user)):
    """`refresh=true` probes every endpoint now instead of returning the
    last background probe (at most PROBE_SECONDS old)."""
    if refresh or any(llm_endpoints.health(e.id) is None
                      for e in llm_endpoints.endpoints() if e.enabled):
        await llm_endpoints.probe_all()
    return llm_endpoints.describe(user_id=user.id)
