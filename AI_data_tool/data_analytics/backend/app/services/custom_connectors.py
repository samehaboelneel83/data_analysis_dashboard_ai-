"""Custom connector presets: save-time validation and config merging.

A preset wraps one existing `connectors.py` base type (see that module) with
fixed field values, some of which are locked. This module never touches the
database and never talks to `connectors.py`'s registry beyond the read-only
lookups it already exposes -- see
docs/superpowers/specs/2026-09-09-custom-connector-framework-design.md.
"""
from __future__ import annotations

from . import connectors
from . import secrets
from ..models.models import CustomConnector


class CustomConnectorError(ValueError):
    """Raised when a custom connector preset definition fails validation."""


def validate_custom_connector_def(base_type: str, base_config: dict, locked_fields: list[str]) -> None:
    if not connectors.is_known(base_type):
        raise CustomConnectorError(f"Unknown connector type '{base_type}'")
    field_names = {f.name for f in connectors.resolve(base_type).config_fields}

    unknown_base = set(base_config or {}) - field_names
    if unknown_base:
        raise CustomConnectorError(
            f"Unknown config field(s) for '{base_type}': {', '.join(sorted(unknown_base))}")

    unknown_locked = set(locked_fields or []) - field_names
    if unknown_locked:
        raise CustomConnectorError(
            f"Unknown locked field(s) for '{base_type}': {', '.join(sorted(unknown_locked))}")

    not_in_base = set(locked_fields or []) - set(base_config or {})
    if not_in_base:
        raise CustomConnectorError(
            f"Locked field(s) have no value to lock: {', '.join(sorted(not_in_base))}")


def apply_preset_locks(config: dict, preset: CustomConnector) -> dict:
    """`config` with the preset's locked fields forced to the preset's values,
    and its non-locked fields used only as defaults for keys `config` omits.
    `preset.base_config` is stored encrypted (same convention as
    DataSource.config), so it is decrypted here before merging."""
    base = secrets.decrypt_config(preset.base_config or {}, connectors.secret_field_names(preset.base_type))
    locked = set(preset.locked_fields or [])
    merged = dict(config or {})
    for key, value in base.items():
        if key in locked or key not in merged:
            merged[key] = value
    return merged
