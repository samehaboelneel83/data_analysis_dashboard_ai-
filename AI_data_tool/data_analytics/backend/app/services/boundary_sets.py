"""Validate a customer-supplied set of map boundaries.

The bundled atlas is countries and only countries. A dataset keyed by Egyptian
governorates, US states or UK counties drew a bare world map with nothing on
it — found the hard way, by a hospital dashboard whose choropleth of 27
governorates matched none of them.

Admin-1 boundaries for every country are tens of megabytes, so they cannot be
bundled. What can be built is the thing SAS calls "custom boundaries from a
geographic data provider": the customer supplies the file, once, and every map
in the org can draw against it.

Three decisions worth stating, because each closes off a worse alternative:

  * **GeoJSON only.** `topojson-client` is already a frontend dependency, so a
    TopoJSON file is converted in the browser before it is sent. Python gains no
    new dependency and there is exactly one validator to keep honest.

  * **Key properties are DETECTED, not configured.** Real boundary files call
    their naming property `name`, `NAME_1`, `shapeName`, `ADM1_EN`, `GID_1`...
    Asking the uploader which one to use is asking them to open a 4 MB file in a
    text editor first. Every string property present and non-blank on EVERY
    feature becomes a matching key, so a file carrying both `name` and `name_ar`
    matches data in either language — several exact lookups, which is not the
    same thing as fuzzy matching.

  * **Refuse at upload, not at render.** A file with no usable key, or with
    point geometry, can only ever produce a blank map. A blank map reads as
    "there is no data", which sends the reader to the wrong problem.

This module raises `BoundarySetError` and imports no HTTP framework: layer 6
owns status codes (see tests/test_layer_conformance.py), and a service that
raised `HTTPException` would be unusable from a script or the scheduler.
"""
from __future__ import annotations

from typing import Any

#: Every viewer's browser downloads this geometry to draw the map. A file of
#: every postcode in a country is not a boundary set, it is an outage.
MAX_FEATURES = 20_000

#: Enough for the picker to show "27 regions: Cairo, Giza, Qalyubia…" so an
#: author can see whether their column will match BEFORE building a widget.
SAMPLE_NAMES = 12

_AREA_GEOMETRIES = {"Polygon", "MultiPolygon"}


class BoundarySetError(ValueError):
    """A file that cannot be drawn, with a reason the uploader can act on."""


def _string_keys(properties: Any) -> set[str]:
    """The properties of one feature that could name a region."""
    if not isinstance(properties, dict):
        return set()
    return {k for k, v in properties.items()
            if isinstance(v, str) and v.strip()}


def validate_boundaries(payload: Any, prefer: list[str] | None = None) -> dict[str, Any]:
    """Check a parsed GeoJSON FeatureCollection and describe what it can match.

    Returns the geometry unchanged alongside `key_properties`, `feature_count`
    and `sample_names`. Unchanged deliberately: simplifying somebody's
    boundaries for them changes their map without telling them, and this is
    reference data they may already have simplified to a tolerance they chose.
    """
    if not isinstance(payload, dict):
        raise BoundarySetError("The file must contain a GeoJSON FeatureCollection")

    kind = payload.get("type")
    if kind == "Topology":
        # By far the likeliest wrong file, and "invalid GeoJSON" would send
        # someone hunting for a typo that is not there.
        raise BoundarySetError(
            "That is a TopoJSON file. Convert it to GeoJSON first — the map "
            "editor does this automatically when you choose the file.")
    if kind != "FeatureCollection":
        raise BoundarySetError(
            f"Expected a GeoJSON FeatureCollection, found {kind or 'no type'}")

    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise BoundarySetError("The file contains no regions")
    if len(features) > MAX_FEATURES:
        raise BoundarySetError(
            f"Too many regions: {len(features):,}. The limit is "
            f"{MAX_FEATURES:,} — every viewer downloads this geometry to draw "
            f"the map.")

    shared: set[str] | None = None
    for i, f in enumerate(features):
        if not isinstance(f, dict):
            raise BoundarySetError(f"Region {i + 1} is not a GeoJSON feature")
        geometry = f.get("geometry")
        if not isinstance(geometry, dict):
            raise BoundarySetError(f"Region {i + 1} has no geometry")
        gtype = geometry.get("type")
        if gtype not in _AREA_GEOMETRIES:
            raise BoundarySetError(
                f"Region {i + 1} is a {gtype}, not an area. Boundaries must be "
                f"Polygon or MultiPolygon — a choropleth fills shapes.")
        keys = _string_keys(f.get("properties"))
        shared = keys if shared is None else (shared & keys)

    if not shared:
        raise BoundarySetError(
            "No property is present on every region, so there is nothing to "
            "match your data against. Boundary files usually name their "
            "regions in a property such as `name`, `NAME_1` or `shapeName`.")

    # Sorted, so the order is stable -- except that a property the caller
    # names as the DISPLAY name goes first: the first key is what a tooltip
    # and the sample show, and "alias_3" is no name for Cairo.
    lead = [k for k in (prefer or []) if k in shared]
    key_properties = lead + sorted(shared - set(lead))
    first = key_properties[0]
    sample = [str(f["properties"][first]) for f in features[:SAMPLE_NAMES]]

    return {
        "geometry": payload,
        "key_properties": key_properties,
        "feature_count": len(features),
        "sample_names": sample,
    }


# ── Starter packs ────────────────────────────────────────────────────────────

def packs_dir() -> "Path":
    from pathlib import Path
    from ..core.config import settings
    if settings.boundary_packs_dir:
        return Path(settings.boundary_packs_dir)
    return Path(__file__).resolve().parents[2] / "boundary_packs"


def list_packs() -> list[dict[str, Any]]:
    """The packs this deployment ships, from `manifest.json`. A missing folder
    or manifest lists none: packs are optional, uploads stay the primary path."""
    import json
    manifest = packs_dir() / "manifest.json"
    try:
        doc = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for p in doc.get("packs") or []:
        # A pack without a stated licence is not offered: installing it would
        # put geometry of unknown terms into every viewer's browser.
        if isinstance(p, dict) and p.get("id") and p.get("file") and p.get("license"):
            if (packs_dir() / str(p["file"])).is_file():
                out.append({k: p.get(k) for k in ("id", "name", "country", "level", "feature_count",
                                                  "description", "source", "license", "license_url",
                                                  "label_property", "attribution", "terms",
                                                  "requires_acceptance")})
    return out


def load_pack(pack_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """(manifest entry, validated boundaries) for one pack."""
    import json
    entry = next((p for p in list_packs() if p["id"] == pack_id), None)
    if entry is None:
        raise BoundarySetError(f"No boundary pack called '{pack_id}'")
    manifest = json.loads((packs_dir() / "manifest.json").read_text(encoding="utf-8"))
    file = next(p["file"] for p in manifest["packs"] if p.get("id") == pack_id)
    # The file name comes from our own manifest, but is still confined to the
    # packs folder: a manifest edited to "../../etc/passwd" reads nothing.
    path = (packs_dir() / file).resolve()
    if packs_dir().resolve() not in path.parents:
        raise BoundarySetError("That pack's file is outside the packs folder")
    geometry = json.loads(path.read_text(encoding="utf-8"))
    label = entry.get("label_property")
    return entry, validate_boundaries(geometry, prefer=[label] if label else None)
