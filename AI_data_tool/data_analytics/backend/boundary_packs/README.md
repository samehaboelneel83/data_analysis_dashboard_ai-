# Boundary packs

Starter map boundaries an org admin can install with one click from any region
map's **Boundaries** picker ("Starter packs"). Installing a pack creates an
ordinary boundary set in the org, exactly as uploading the same file would —
after that it is the org's reference data, not something this folder controls.

## Format

- `manifest.json` — `{"format": 1, "packs": [...]}`. Each pack names its `file`,
  `label_property` (the property shown as the region's name), `feature_count`,
  `source`, `license` and `license_url`. A pack without a license is not shipped.
- `<id>.geojson` — a GeoJSON `FeatureCollection` of `Polygon`/`MultiPolygon`
  features. **Every string property present on every feature is a matching
  key**, so extra spellings are carried as `alias_1 … alias_N` (padded with the
  English name so each feature has all of them). Matching stays exact —
  several exact lookups, never fuzzy.

TopoJSON is accepted for *uploads* (the browser converts it); packs are stored
as GeoJSON so the server has one validator.

## Offline / air-gapped installs

The folder is optional. Deployments that must stay lean can leave it out
(`BOUNDARY_PACKS_DIR` pointing at an empty or missing folder simply lists no
packs); customer-supplied boundary files remain the primary path.

## Sources

Egypt, US, Saudi and UAE packs are cut from Natural Earth 1:10m Admin-1
(public domain).

`eu-nuts1` is Eurostat GISCO NUTS 2021 (1:20M), fetched from Eurostat's own
`eurostat/Nuts2json` repository. It is NOT public domain: the credit
"© EuroGeographics for the administrative boundaries" must be shown with the
map, and commercial use needs Eurostat's permission. Its manifest entry carries
`requires_acceptance`, `terms` and `attribution`: the install endpoint refuses
until the admin accepts the terms, and the credit is stored on the installed set
so every map drawn with it shows it.
Natural Earth draws de facto boundaries; an organisation with an official
boundary file should upload that instead.
