"""Bring-your-own map boundaries.

The bundled atlas is countries and only countries. A dataset keyed by Egyptian
governorates, US states or UK counties drew a bare world map with nothing on it
-- found the hard way, by a hospital dashboard whose choropleth of 27
governorates matched none of them.

Admin-1 boundaries for every country are tens of megabytes, so they cannot be
bundled, and nothing offline has them. The answer is therefore the one SAS calls
"custom boundaries from a geographic data provider": the customer supplies the
file. This validates it.

Two decisions worth stating:

  * **GeoJSON only.** `topojson-client` is already a frontend dependency, so a
    TopoJSON file is converted in the browser before it is sent. Python gains no
    new dependency and there is exactly one validator to keep honest.
  * **Key properties are DETECTED, not configured.** A boundary file's naming
    property is called `name`, `NAME_1`, `shapeName`, `ADM1_EN`... asking the
    uploader to name it is asking them to open the file in a text editor first.
    Every string property present on every feature becomes a matching key, so
    the hospital file's `name` AND `name_ar` both work -- several exact lookups,
    which is not the same thing as fuzzy matching.
"""
import pytest

from app.services.boundary_sets import BoundarySetError, validate_boundaries


def poly(x=0.0, y=0.0):
    """A unit square. Shape does not matter to validation, only its type."""
    return {"type": "Polygon",
            "coordinates": [[[x, y], [x + 1, y], [x + 1, y + 1], [x, y + 1], [x, y]]]}


def feature(props, geometry=None):
    return {"type": "Feature", "properties": props, "geometry": geometry or poly()}


def collection(*features):
    return {"type": "FeatureCollection", "features": list(features)}


class TestItAcceptsARealFile:
    def test_a_minimal_collection_is_accepted(self):
        got = validate_boundaries(collection(feature({"name": "Cairo"})))
        assert got["feature_count"] == 1

    def test_it_reports_the_properties_it_can_match_on(self):
        got = validate_boundaries(collection(
            feature({"name": "Cairo", "name_ar": "القاهرة"}),
            feature({"name": "Giza", "name_ar": "الجيزة"})))
        assert set(got["key_properties"]) == {"name", "name_ar"}

    def test_a_property_missing_from_one_feature_is_not_a_key(self):
        """Matching on it would silently fail for whichever regions lack it,
        and a partly-painted map reads as missing data rather than a bad key."""
        got = validate_boundaries(collection(
            feature({"name": "Cairo", "nickname": "The Capital"}),
            feature({"name": "Giza"})))
        assert got["key_properties"] == ["name"]

    def test_numeric_properties_are_not_matching_keys(self):
        # An area or a population is not something a data column joins on.
        got = validate_boundaries(collection(
            feature({"name": "Cairo", "area_km2": 3085}),
            feature({"name": "Giza", "area_km2": 13184})))
        assert got["key_properties"] == ["name"]

    def test_multipolygons_are_fine(self):
        # Most real admin boundaries are: islands, exclaves, river deltas.
        got = validate_boundaries(collection(feature({"name": "Alexandria"}, {
            "type": "MultiPolygon",
            "coordinates": [poly()["coordinates"], poly(5, 5)["coordinates"]]})))
        assert got["feature_count"] == 1

    def test_the_geometry_comes_back_unchanged(self):
        """Stored as given. Simplifying somebody's boundaries for them changes
        their map without telling them."""
        source = collection(feature({"name": "Cairo"}))
        got = validate_boundaries(source)
        assert got["geometry"] == source


class TestItRefusesWhatCannotBeDrawn:
    """Every refusal is a `BoundarySetError` -- a ValueError, raised by a
    service that imports no HTTP framework, translated by the router."""

    def test_something_that_is_not_a_feature_collection(self):
        with pytest.raises(BoundarySetError):
            validate_boundaries({"type": "Polygon", "coordinates": []})

    def test_a_topojson_file_is_refused_by_name(self):
        """The likeliest wrong file. The message has to say what to do about
        it, because "invalid GeoJSON" sends someone hunting for a typo."""
        with pytest.raises(BoundarySetError) as e:
            validate_boundaries({"type": "Topology", "objects": {}, "arcs": []})
        assert "topojson" in str(e.value).lower()

    def test_an_empty_collection(self):
        with pytest.raises(BoundarySetError):
            validate_boundaries(collection())

    def test_a_feature_with_no_geometry(self):
        with pytest.raises(BoundarySetError):
            validate_boundaries(collection(
                {"type": "Feature", "properties": {"name": "x"}, "geometry": None}))

    def test_points_and_lines_are_not_boundaries(self):
        # A choropleth fills shapes. A point layer is a different widget.
        with pytest.raises(BoundarySetError) as e:
            validate_boundaries(collection(feature(
                {"name": "x"}, {"type": "Point", "coordinates": [0, 0]})))
        assert "polygon" in str(e.value).lower()

    def test_no_property_shared_by_every_feature(self):
        """Nothing to match a data column against, so the map could only ever
        be blank. Refusing at upload beats a silent blank later."""
        with pytest.raises(BoundarySetError) as e:
            validate_boundaries(collection(
                feature({"name": "Cairo"}), feature({"governorate": "Giza"})))
        assert "match" in str(e.value).lower()

    def test_features_that_are_not_objects(self):
        with pytest.raises(BoundarySetError):
            validate_boundaries({"type": "FeatureCollection", "features": ["Cairo"]})

    def test_too_many_features(self):
        """Every viewer's browser downloads this. A file of every postcode in a
        country is not a boundary set, it is an outage."""
        many = collection(*[feature({"name": f"r{i}"}) for i in range(20001)])
        with pytest.raises(BoundarySetError) as e:
            validate_boundaries(many)
        assert "too many" in str(e.value).lower()


class TestTheValuesAreUsableAsKeys:
    def test_it_lists_the_region_names_for_the_first_key(self):
        """So the picker can say "27 regions: Cairo, Giza, Qalyubia..." and a
        user can see at a glance whether their column will match, before they
        build a widget and find out it does not."""
        got = validate_boundaries(collection(
            feature({"name": "Cairo"}), feature({"name": "Giza"})))
        assert got["sample_names"] == ["Cairo", "Giza"]

    def test_the_sample_is_capped(self):
        got = validate_boundaries(collection(
            *[feature({"name": f"r{i}"}) for i in range(50)]))
        assert len(got["sample_names"]) <= 12

    def test_a_blank_name_does_not_qualify_a_key(self):
        # An empty string matches nothing and would make a useless key look fine.
        with pytest.raises(BoundarySetError):
            validate_boundaries(collection(
                feature({"name": "Cairo"}), feature({"name": "  "})))


@pytest.mark.asyncio
async def test_deleting_a_set_clears_the_columns_classified_with_it(
        client, auth_headers, db_session, two_orgs, tmp_path):
    """A classification pointing at a deleted set is a silent no-op.

    `column_meta[col].boundary_set_id` is how a column says which shapes it
    draws with. Delete the set and the id survives, pointing at nothing: the
    map falls back to countries with no error anywhere, and the column still
    claims to be geography. Same shape as an action edge left pointing at a
    deleted widget, and the same fix -- prune where the deletion happens,
    because that is the only place that knows it happened."""
    import pandas as pd
    from app.models.models import Dataset

    org = two_orgs["a"]["org"]
    path = tmp_path / "g.csv"
    pd.DataFrame({"governorate": ["Cairo"], "amount": [1]}).to_csv(path, index=False)
    ds = Dataset(name="G", filename=str(path), org_id=org.id, mode="import")
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)

    made = await client.post("/api/v1/boundary-sets", headers=auth_headers["a"], json={
        "name": "Governorates",
        "geometry": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"name": "Cairo"},
             "geometry": {"type": "Polygon", "coordinates": [[[31, 30], [32, 30], [32, 31], [31, 30]]]}}]},
    })
    assert made.status_code in (200, 201), made.text
    set_id = made.json()["id"]

    ds.column_meta = {"governorate": {"role": "geography", "boundary_set_id": set_id},
                      "amount": {"role": "measure"}}
    await db_session.commit()

    gone = await client.delete(f"/api/v1/boundary-sets/{set_id}", headers=auth_headers["a"])
    assert gone.status_code == 204, gone.text

    await db_session.refresh(ds)
    meta = ds.column_meta or {}
    # The dead pointer is gone, and so is the role that depended on it -- a
    # column calling itself geography with nothing to draw is the same lie.
    assert "boundary_set_id" not in meta.get("governorate", {})
    assert meta.get("governorate", {}).get("role") != "geography"
    # Everything else is left exactly as it was.
    assert meta.get("amount") == {"role": "measure"}
