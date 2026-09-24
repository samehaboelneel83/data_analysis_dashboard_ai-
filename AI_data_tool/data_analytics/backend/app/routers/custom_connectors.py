from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..core.database import get_db
from ..dependencies import require_org_admin
from ..models.models import CustomConnector, DataSource, User
from ..schemas.schemas import CustomConnectorCreate, CustomConnectorOut, CustomConnectorUpdate
from ..services import connectors, secrets
from ..services.custom_connectors import CustomConnectorError, validate_custom_connector_def

router = APIRouter(prefix="/custom-connectors", tags=["custom-connectors"])


def _redacted(cc: CustomConnector) -> CustomConnectorOut:
    out = CustomConnectorOut.model_validate(cc)
    out.base_config = secrets.redact_config(cc.base_config or {}, connectors.secret_field_names(cc.base_type))
    return out


async def _owned_or_404(db: AsyncSession, cc_id: int, org_id: int) -> CustomConnector:
    cc = (await db.execute(
        select(CustomConnector).where(CustomConnector.id == cc_id, CustomConnector.org_id == org_id)
    )).scalar_one_or_none()
    if cc is None:
        raise HTTPException(404, "Custom connector not found")
    return cc


@router.get("", response_model=list[CustomConnectorOut])
async def list_custom_connectors(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    result = await db.execute(
        select(CustomConnector).where(CustomConnector.org_id == current_user.org_id).order_by(CustomConnector.created_at.desc())
    )
    return [_redacted(cc) for cc in result.scalars().all()]


@router.post("", response_model=CustomConnectorOut)
async def create_custom_connector(body: CustomConnectorCreate, db: AsyncSession = Depends(get_db),
                                   current_user: User = Depends(require_org_admin)):
    try:
        validate_custom_connector_def(body.base_type, body.base_config, body.locked_fields)
    except CustomConnectorError as e:
        raise HTTPException(400, str(e))

    dupe = (await db.execute(
        select(CustomConnector).where(CustomConnector.org_id == current_user.org_id, CustomConnector.key == body.key)
    )).scalar_one_or_none()
    if dupe is not None:
        raise HTTPException(409, f"A custom connector with key '{body.key}' already exists")

    encrypted = secrets.encrypt_config(body.base_config or {}, connectors.secret_field_names(body.base_type))
    cc = CustomConnector(org_id=current_user.org_id, key=body.key, label=body.label, base_type=body.base_type,
                          base_config=encrypted, locked_fields=body.locked_fields or [], created_by=current_user.id)
    db.add(cc)
    await db.commit()
    await db.refresh(cc)
    return _redacted(cc)


@router.put("/{cc_id}", response_model=CustomConnectorOut)
async def update_custom_connector(cc_id: int, body: CustomConnectorUpdate, db: AsyncSession = Depends(get_db),
                                   current_user: User = Depends(require_org_admin)):
    cc = await _owned_or_404(db, cc_id, current_user.org_id)

    if body.base_type is not None and body.base_type != cc.base_type:
        count = (await db.execute(
            select(func.count()).select_from(DataSource).where(DataSource.custom_connector_id == cc.id)
        )).scalar_one()
        if count:
            raise HTTPException(
                409, f"{count} connection(s) still use this preset; reassign them to a different preset or delete them first"
            )

    new_base_type = body.base_type if body.base_type is not None else cc.base_type
    new_base_config = (body.base_config if body.base_config is not None
                        else secrets.decrypt_config(cc.base_config or {}, connectors.secret_field_names(cc.base_type)))
    new_locked = body.locked_fields if body.locked_fields is not None else (cc.locked_fields or [])
    if body.base_config is not None:
        # A secret field sent back as the redaction sentinel means "unchanged" — keep the
        # stored (encrypted) value; anything else is a new secret to encrypt. Use cc.base_type
        # (the pre-update type) since that's what cc.base_config was encrypted against.
        secret_names = connectors.secret_field_names(cc.base_type)
        stored = secrets.decrypt_config(cc.base_config or {}, secret_names)
        new_base_config = dict(new_base_config)
        for name in secret_names:
            if new_base_config.get(name) == secrets.REDACTED:
                new_base_config[name] = stored.get(name)
    try:
        validate_custom_connector_def(new_base_type, new_base_config, new_locked)
    except CustomConnectorError as e:
        raise HTTPException(400, str(e))

    if body.key is not None and body.key != cc.key:
        dupe = (await db.execute(
            select(CustomConnector).where(CustomConnector.org_id == current_user.org_id,
                                           CustomConnector.key == body.key, CustomConnector.id != cc.id)
        )).scalar_one_or_none()
        if dupe is not None:
            raise HTTPException(409, f"A custom connector with key '{body.key}' already exists")
        cc.key = body.key
    if body.label is not None:
        cc.label = body.label
    cc.base_type = new_base_type
    cc.base_config = secrets.encrypt_config(new_base_config, connectors.secret_field_names(new_base_type))
    cc.locked_fields = new_locked
    flag_modified(cc, "base_config")
    await db.commit()
    await db.refresh(cc)
    return _redacted(cc)


@router.delete("/{cc_id}", status_code=204)
async def delete_custom_connector(cc_id: int, db: AsyncSession = Depends(get_db),
                                   current_user: User = Depends(require_org_admin)):
    cc = await _owned_or_404(db, cc_id, current_user.org_id)
    count = (await db.execute(
        select(func.count()).select_from(DataSource).where(DataSource.custom_connector_id == cc.id)
    )).scalar_one()
    if count:
        raise HTTPException(
            409, f"{count} connection(s) still use this preset; reassign them to a different preset or delete them first"
        )
    await db.delete(cc)
    await db.commit()
