"""Platform settings that can be changed from the app (Admin -> Settings).

Layer 6. Every install-wide setting lived only in environment variables: the
LLM endpoint, the mail server, upload limits, timeouts. Changing one meant
editing the deployment and restarting. This module lets a platform admin
change them from the app:

- `SPECS` lists EVERY field of `core.config.Settings`, grouped for the page.
  A field with no spec fails `test_app_settings.py`, so a new setting cannot
  be added without deciding how the page treats it.
- An override is one `app_settings` row. It is validated with the field's own
  type and bounds, stored (a secret encrypted), and applied onto the live
  `settings` object. Callers read `settings.<field>` when they use it, so most
  changes apply at once; the few read only at startup say `restart`.
- Deleting the row puts the environment value back.
- Deploy-time settings (database, secret keys, CORS, admin emails, paths) are
  shown read-only: changing them from a web page is unsafe or meaningless
  without a restart.
- Other processes pick changes up within `RELOAD_SECONDS` (`run_reloader`).
"""
from __future__ import annotations

import asyncio
import logging
import zoneinfo
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError, create_model
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import Settings, settings
from ..models.models import AppSetting

logger = logging.getLogger(__name__)

RELOAD_SECONDS = 30


@dataclass(frozen=True)
class Spec:
    key: str
    category: str
    label: str
    help: str = ""
    editable: bool = True
    secret: bool = False
    #: Read once at startup: a saved change applies after the next restart.
    restart: bool = False
    options: tuple[str, ...] = ()
    #: Bounds for fields whose declaration has none (Settings predates this page).
    minimum: float | None = None
    maximum: float | None = None


CATEGORIES: list[tuple[str, str]] = [
    ("ai", "AI model (LLM)"),
    ("embeddings", "Semantic search (embeddings)"),
    ("email", "Email and links"),
    ("data", "Data import and limits"),
    ("maps", "Maps"),
    ("metadata", "Metadata sync"),
    ("performance", "Performance and caching"),
    ("security", "Sessions and security"),
    ("rate_limits", "Rate limits"),
    ("quality", "Answer-quality gate"),
    ("observability", "Monitoring (OpenTelemetry)"),
    ("deployment", "Deployment (read-only)"),
]

_S = Spec
SPECS: list[Spec] = [
    # -- AI model ---------------------------------------------------------
    _S("llm_enabled", "ai", "AI features on", "Off: Ask AI, the copilot and AI suggestions are unavailable."),
    _S("llm_base_url", "ai", "LLM endpoint (single)",
       "An OpenAI-compatible base URL, ending in /v1. Used only while no list is saved under LLM endpoints."),
    _S("llm_model", "ai", "Model name (single)", "The model id that endpoint serves."),
    _S("llm_api_key", "ai", "API key (single)", "Only if that endpoint requires one; sent as a Bearer token.", secret=True),
    _S("llm_endpoints", "ai", "Built-in endpoint list (LLM_ENDPOINTS)",
       "From the deployment; used until a list is saved under LLM endpoints above.", editable=False),
    _S("llm_endpoints_default", "ai", "Built-in default (LLM_ENDPOINTS_DEFAULT)",
       "An endpoint id from the built-in list, or auto.", editable=False),
    _S("llm_timeout_s", "ai", "Request timeout (seconds)"),
    _S("llm_max_concurrency", "ai", "Concurrent LLM calls", "Across the whole install."),
    _S("llm_reserved_interactive", "ai", "Calls reserved for people",
       "Of the concurrent calls, how many background work may never take."),
    _S("agent_statement_timeout_s", "ai", "AI query timeout (seconds)", "The longest one AI-generated query may run."),
    _S("agent_row_cap", "ai", "AI result row limit"),
    # -- Embeddings ---------------------------------------------------------
    _S("embedding_base_url", "embeddings", "Embeddings endpoint", "Empty turns semantic search off."),
    _S("embedding_model", "embeddings", "Embeddings model"),
    _S("embedding_dim", "embeddings", "Vector dimension", "Must match the model.", restart=True, minimum=1),
    # -- Email ----------------------------------------------------------------
    _S("smtp_host", "email", "Mail server", "Empty: scheduled reports and alerts are not emailed."),
    _S("smtp_port", "email", "Port", minimum=1, maximum=65535),
    _S("smtp_user", "email", "User name"),
    _S("smtp_password", "email", "Password", secret=True),
    _S("smtp_from", "email", "From address"),
    _S("smtp_starttls", "email", "Use STARTTLS"),
    _S("public_base_url", "email", "Public address of the app",
       "Used in links inside emails and single sign-on redirects."),
    # -- Data -----------------------------------------------------------------
    _S("max_upload_mb", "data", "Largest upload (MB)", minimum=1),
    _S("max_upload_files", "data", "Files per upload", minimum=1),
    _S("max_batch_upload_mb", "data", "Largest multi-file upload (MB)", minimum=1),
    _S("import_row_cap", "data", "Import row limit", "A larger file or query is refused, never cut short. 0 = no limit."),
    _S("analysis_row_cap", "data", "Analysis row limit"),
    _S("source_connect_timeout_s", "data", "Database connect timeout (seconds)",
       "How long to wait for a connected database to answer before giving up."),
    _S("source_statement_timeout_s", "data", "Database query timeout (seconds)",
       "Any one query against a connected database. 0 = no limit."),
    _S("data_timezone", "data", "Data time zone",
       "Timestamps with a UTC offset are stored as local time in this zone, e.g. Africa/Cairo."),
    _S("automation_frame_max_mb", "data", "Automation data limit (MB)"),
    _S("connector_allow_private_hosts", "data", "Allow connections to private network addresses"),
    _S("job_worker_enabled", "data", "Background job worker", "Runs queued imports and refreshes.", restart=True),
    # -- Maps -----------------------------------------------------------------
    _S("map_tile_hosts", "maps", "Allowed tile servers",
       "Comma-separated host names. Empty: an organization may use any tile server."),
    _S("boundary_packs_dir", "maps", "Boundary packs folder", editable=False),
    # -- Metadata -------------------------------------------------------------
    _S("metadata_sample_rows", "metadata", "Rows sampled per table"),
    _S("metadata_statement_timeout_s", "metadata", "Per-table timeout (seconds)"),
    _S("metadata_sample_concurrency", "metadata", "Tables sampled at once"),
    _S("metadata_describe_concurrency", "metadata", "Tables described at once"),
    _S("metadata_cache_max_mb", "metadata", "Sample cache size (MB)"),
    _S("fk_overlap_high", "metadata", "Relationship confidence: accept", "0 to 1."),
    _S("fk_overlap_review", "metadata", "Relationship confidence: review", "0 to 1."),
    # -- Performance ----------------------------------------------------------
    _S("widget_duckdb_pushdown", "performance", "Compute charts in DuckDB"),
    _S("widget_duckdb_threads", "performance", "DuckDB threads per chart"),
    _S("widget_work_max_concurrency", "performance", "Charts computed at once", restart=True),
    _S("widget_data_cache_maxsize", "performance", "Chart result cache (entries)"),
    _S("widget_data_cache_max_entry_bytes", "performance", "Largest cached chart result (bytes)"),
    _S("frame_cache_enabled", "performance", "Keep parsed files in memory"),
    _S("frame_cache_max_frames", "performance", "Files kept in memory"),
    _S("frame_cache_max_total_bytes", "performance", "Memory for kept files (bytes)"),
    _S("directquery_engine_pool_maxsize", "performance", "Open database connections kept"),
    _S("valkey_cache_ttl_s", "performance", "Shared cache lifetime (seconds)"),
    # -- Security -------------------------------------------------------------
    _S("access_token_expire_hours", "security", "Sign-in lasts (hours)", "Applies to new sign-ins."),
    # -- Rate limits ----------------------------------------------------------
    _S("rate_limit_enabled", "rate_limits", "Rate limiting on"),
    _S("rate_limit_window_seconds", "rate_limits", "Window (seconds)"),
    _S("rate_limit_requests_per_window", "rate_limits", "Requests per window, signed in"),
    _S("rate_limit_guest_requests_per_window", "rate_limits", "Requests per window, shared links"),
    _S("rate_limit_bucket_cap", "rate_limits", "Clients tracked"),
    # -- Quality gate ---------------------------------------------------------
    _S("eval_gate_enabled", "quality", "Nightly answer-quality check", restart=True),
    _S("eval_gate_source_id", "quality", "Connection with the test questions", restart=True, minimum=0),
    _S("eval_gate_min_accuracy", "quality", "Lowest acceptable accuracy", "0 to 1."),
    # -- Observability (read at startup) --------------------------------------
    _S("otel_enabled", "observability", "Tracing on", editable=False),
    _S("otel_endpoint", "observability", "Trace collector", editable=False),
    _S("otel_service_name", "observability", "Service name", editable=False),
    _S("otel_metrics_enabled", "observability", "Metrics on", editable=False),
    _S("otel_metrics_endpoint", "observability", "Metrics collector", editable=False),
    _S("otel_metric_interval_ms", "observability", "Metrics interval (ms)", editable=False),
    # -- Deployment (read-only) -----------------------------------------------
    _S("env", "deployment", "Environment", editable=False),
    _S("database_url", "deployment", "Database", editable=False, secret=True),
    _S("secret_key", "deployment", "Session signing key", editable=False, secret=True),
    _S("connector_secret_key", "deployment", "Connection encryption key", editable=False, secret=True),
    _S("allowed_origins", "deployment", "Allowed browser origins (CORS)", editable=False),
    _S("super_admin_emails", "deployment", "Platform admins", editable=False),
    _S("upload_dir", "deployment", "Upload folder", editable=False),
    _S("duckdb_cache_path", "deployment", "Metadata cache file", editable=False),
    _S("valkey_url", "deployment", "Shared cache (Valkey)", editable=False, secret=True),
]
BY_KEY = {s.key: s for s in SPECS}

#: Each field's value from the environment (or default), captured before the
#: first override is applied: what "Reset" puts back.
_BASELINE: dict[str, Any] = {}
#: The overrides this process has applied, and the newest row it has seen.
_APPLIED: dict[str, Any] = {}
_SEEN_STAMP: Any = None


class SettingError(ValueError):
    """A value the setting cannot take; the message names the setting."""


def _baseline() -> dict[str, Any]:
    if not _BASELINE:
        _BASELINE.update(settings.model_dump())
    return _BASELINE


def _validate(key: str, value: Any) -> Any:
    spec = BY_KEY.get(key)
    if spec is None:
        raise SettingError(f"'{key}' is not a setting")
    if not spec.editable:
        raise SettingError(f"{spec.label} is set by the deployment and cannot be changed here")
    field = Settings.model_fields[key]
    probe = create_model("One", **{key: (field.annotation, field)})
    try:
        clean = getattr(probe.model_validate({key: value}), key)
    except ValidationError as e:
        msg = e.errors()[0].get("msg", "invalid value")
        raise SettingError(f"{spec.label}: {msg}") from None
    if isinstance(clean, str):
        clean = clean.strip()
    if isinstance(clean, (int, float)) and not isinstance(clean, bool):
        declared = any(getattr(m, a, None) is not None for m in field.metadata for a in ("ge", "gt", "le", "lt"))
        low = spec.minimum if spec.minimum is not None else (None if declared else 0)
        if low is not None and clean < low:
            raise SettingError(f"{spec.label}: must be at least {low:g}")
        if spec.maximum is not None and clean > spec.maximum:
            raise SettingError(f"{spec.label}: must be at most {spec.maximum:g}")
    if key == "data_timezone":
        try:
            zoneinfo.ZoneInfo(clean or "UTC")
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            raise SettingError(f"{spec.label}: '{clean}' is not a time zone name (e.g. Africa/Cairo)") from None
    if key in ("llm_base_url", "embedding_base_url", "public_base_url") and clean:
        p = urlparse(clean)
        if p.scheme not in ("http", "https") or not p.netloc:
            raise SettingError(f"{spec.label}: must be an http(s) address")
    if key == "llm_base_url" and not clean:
        raise SettingError(f"{spec.label}: cannot be empty; turn AI features off instead")
    return clean


def _apply(values: dict[str, Any]) -> None:
    """Make `values` (already validated, secrets decrypted) the live overrides."""
    base = _baseline()
    for key in set(_APPLIED) - set(values):
        setattr(settings, key, base[key])
    for key, value in values.items():
        setattr(settings, key, value)
    _APPLIED.clear()
    _APPLIED.update(values)


def _decode(key: str, stored: Any) -> Any:
    if BY_KEY[key].secret and isinstance(stored, str):
        from .secrets import decrypt_value
        return decrypt_value(stored)
    return stored


async def load(db: AsyncSession) -> None:
    """Apply every stored override. A row that no longer validates (a setting
    removed, a bound tightened) is skipped and logged, never fatal: a bad row
    must not stop the app starting."""
    global _SEEN_STAMP
    rows = (await db.execute(select(AppSetting))).scalars().all()
    values: dict[str, Any] = {}
    from . import llm_endpoints
    endpoint_list = None
    for row in rows:
        if row.key == llm_endpoints.ROW_KEY:
            # The LLM endpoint list is one structured row with its own
            # validation (services/llm_endpoints.py), not a Settings field.
            endpoint_list = row.value
            continue
        spec = BY_KEY.get(row.key)
        if spec is None or not spec.editable:
            logger.warning("app setting %r ignored: not an editable setting", row.key)
            continue
        try:
            values[row.key] = _validate(row.key, _decode(row.key, row.value))
        except (SettingError, ValueError) as e:
            logger.warning("app setting %r ignored: %s", row.key, e)
    _apply(values)
    llm_endpoints.apply_stored(endpoint_list)
    _SEEN_STAMP = await _stamp(db)


async def _stamp(db: AsyncSession):
    return (await db.execute(select(func.count(), func.max(AppSetting.updated_at)))).one()


async def save(db: AsyncSession, changes: dict[str, Any], by: str) -> list[str]:
    """Validate every change first, then store and apply them together. A value
    of None removes the override. Returns the keys that need a restart."""
    from .secrets import encrypt_value
    clean: dict[str, Any] = {}
    for key, value in changes.items():
        clean[key] = None if value is None else _validate(key, value)
    now = datetime.utcnow()
    for key, value in clean.items():
        if value is None:
            await db.execute(delete(AppSetting).where(AppSetting.key == key))
            continue
        stored = encrypt_value(value) if BY_KEY[key].secret and value else value
        row = await db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=stored, updated_by=by, updated_at=now))
        else:
            row.value, row.updated_by, row.updated_at = stored, by, now
    await db.flush()
    await load(db)
    return [k for k in clean if BY_KEY[k].restart]


def _present(spec: Spec, value: Any) -> Any:
    if spec.secret:
        return None
    return value


async def describe(db: AsyncSession) -> dict:
    """Everything the settings page shows. A secret's value is never included,
    only whether it is set."""
    rows = {r.key: r for r in (await db.execute(select(AppSetting))).scalars().all()}
    base = _baseline()
    out = []
    for cid, clabel in CATEGORIES:
        items = []
        for spec in (s for s in SPECS if s.category == cid):
            field = Settings.model_fields[spec.key]
            ann = field.annotation
            kind = ("bool" if ann is bool else "int" if ann in (int, int | None) else
                    "float" if ann in (float, float | None) else "str")
            bounds = {}
            for m in field.metadata:
                for attr in ("ge", "gt", "le", "lt"):
                    if getattr(m, attr, None) is not None:
                        bounds[attr] = getattr(m, attr)
            if kind in ("int", "float") and not bounds:
                bounds["ge"] = spec.minimum if spec.minimum is not None else 0
            if spec.maximum is not None:
                bounds["le"] = spec.maximum
            current = getattr(settings, spec.key)
            row = rows.get(spec.key)
            items.append({
                "key": spec.key, "label": spec.label, "help": spec.help, "type": kind,
                "bounds": bounds, "editable": spec.editable, "secret": spec.secret,
                "restart": spec.restart, "options": list(spec.options),
                "value": _present(spec, current),
                "is_set": current not in (None, ""),
                "default": _present(spec, base.get(spec.key)),
                "source": "saved" if row is not None else "environment",
                "updated_by": row.updated_by if row is not None else None,
                "updated_at": row.updated_at.isoformat() if row is not None and row.updated_at else None,
            })
        out.append({"id": cid, "label": clabel, "settings": items})
    return {"categories": out}


async def run_reloader(session_factory) -> None:
    """Pick up changes saved by another process (another worker, or a
    replica). Cheap: one count/max query per interval, a full load only when
    it moved."""
    global _SEEN_STAMP
    while True:
        await asyncio.sleep(RELOAD_SECONDS)
        try:
            async with session_factory() as db:
                if await _stamp(db) != _SEEN_STAMP:
                    await load(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("app settings reload failed; keeping the current values")
