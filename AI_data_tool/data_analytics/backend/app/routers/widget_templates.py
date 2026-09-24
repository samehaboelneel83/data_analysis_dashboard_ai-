"""Object templates: a configured widget saved by name for reuse across reports.

Org-scoped like a DataView. Apply is a client-side insert of a new widget carrying
the saved type + config, so a template never binds to a dataset's ids — matching is
by the same column-name convention the builder uses everywhere else.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user
from ..models.models import User, WidgetTemplate
from ..services.audit import record as audit

router = APIRouter(prefix="/widget-templates", tags=["widget-templates"])


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    widget_type: str = Field(min_length=1, max_length=50)
    config: dict = {}


def _out(t: WidgetTemplate) -> dict:
    return {"id": t.id, "name": t.name, "widget_type": t.widget_type,
            "config": t.config or {}, "created_at": t.created_at}


@router.get("")
async def list_templates(db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(WidgetTemplate).where(WidgetTemplate.org_id == current_user.org_id)
        .order_by(WidgetTemplate.name)
    )).scalars().all()
    return [_out(t) for t in rows]


@router.post("", status_code=201)
async def create_template(body: TemplateCreate,
                          db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "A template needs a name")
    # Reserved __keys never travel with a template (export policy, container ids and
    # other placement/governance state belong to the source, not a reusable object).
    config = {k: v for k, v in (body.config or {}).items() if not k.startswith("__")}
    config.pop("container_id", None)
    tpl = WidgetTemplate(org_id=current_user.org_id, name=name,
                         widget_type=body.widget_type, config=config,
                         creator_user_id=current_user.id)
    db.add(tpl)
    await audit(db, current_user, "widget_template.create", "widget_template", None, name)
    await db.commit()
    await db.refresh(tpl)
    return _out(tpl)


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: int,
                          db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    tpl = await db.get(WidgetTemplate, template_id)
    check_org(tpl, current_user, "Template not found")
    await audit(db, current_user, "widget_template.delete", "widget_template", template_id, tpl.name)
    await db.delete(tpl)
    await db.commit()
