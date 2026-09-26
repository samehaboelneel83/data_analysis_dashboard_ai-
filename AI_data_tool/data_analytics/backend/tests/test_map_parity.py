"""E15: a map says what a table says, to whom it may, and exports what it shows.

The plan's acceptance for geographic analytics includes "same values in
map/table", "data-derived tooltips respect policy" and "map exports tested".
The map widgets are drawn from the same widget-data route as every chart, so
these pin that they stay on it:

* **Parity.** A choropleth or a bubble map by region carries exactly the
  values a bar or a table grouped by that region computes; a point map's
  markers are exactly the dataset's rows with valid coordinates; a line map's
  arcs are its origin/destination rows. On the pandas path and on DuckDB.
* **Filters and row rules** reach the map: a filter or a restricted role's
  row rule leaves exactly the rows a table over the same scope shows.
* **Policy.** A column denied to a role is not on the map in any role --
  region, coordinates, measure, size, label -- so a tooltip, which shows what
  the widget returned, cannot show it either.
* **Export.** A map's CSV is the rows it draws.
"""
import io

import pandas as pd
import pytest

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.models import ColumnSecurityRule, Dataset, DatasetColumn, Role, RowSecurityRule, User
from app.services import widget_data as wd

GOVS = [("Cairo", 30.04, 31.24), ("Giza", 30.01, 31.21), ("Alexandria", 31.20, 29.92),
        ("Aswan", 24.09, 32.90), ("Luxor", 25.69, 32.64)]
ROWS = []
for i in range(30):
    g, lat, lon = GOVS[i % 5]
    d, dlat, dlon = GOVS[(i + 2) % 5]
    ROWS.append({"governorate": g, "zone": "North" if lat > 29 else "South",
                 "lat": round(lat + (i % 3) * 0.01, 4), "lon": round(lon - (i % 4) * 0.01, 4),
                 "dest_lat": dlat, "dest_lon": dlon, "dest": d,
                 "revenue": float(10 + (i * 37) % 90),
                 # Values no other column has, so a leak is findable in any response.
                 "margin": 7000.25 + i * 3.5,
                 "units": 1 + (i * 7) % 9})
# One row a map must drop and say so: coordinates out of range.
ROWS.append({"governorate": "Cairo", "zone": "North", "lat": 999.0, "lon": 31.0, "dest_lat": 30.0,
             "dest_lon": 31.0, "dest": "Giza", "revenue": 5.0, "margin": 7999.75, "units": 1})
TYPES = {"governorate": "categorical", "zone": "categorical", "dest": "categorical",
         "lat": "numeric", "lon": "numeric", "dest_lat": "numeric", "dest_lon": "numeric",
         "revenue": "numeric", "margin": "numeric", "units": "numeric"}
_VOLATILE = {"cached", "cache", "elapsed_ms", "query_ms", "duration_ms", "engine", "sql", "timing"}


@pytest.fixture(autouse=True)
def _no_cache():
    wd.clear_widget_data_cache()
    yield
    wd.clear_widget_data_cache()


@pytest.fixture(params=["pandas", "duckdb"])
def engine(request, monkeypatch):
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", request.param == "duckdb")
    return request.param


@pytest.fixture
async def world(client, db_session, two_orgs, auth_headers, tmp_path):
    org = two_orgs["a"]["org"]
    path = tmp_path / "sales_by_governorate.csv"
    pd.DataFrame(ROWS).to_csv(path, index=False)
    ds = Dataset(name="Governorate sales", filename=str(path), org_id=org.id, mode="import")
    db_session.add(ds)
    await db_session.flush()
    for col, dtype in TYPES.items():
        db_session.add(DatasetColumn(dataset_id=ds.id, name=col, dtype=dtype))
    # A role that may not see margin, and sees only the North zone.
    role = Role(org_id=org.id, name="north, no margin", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(ColumnSecurityRule(role_id=role.id, dataset_id=ds.id, denied_columns=["margin"]))
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="zone == 'North'"))
    user = User(org_id=org.id, role_id=role.id, email="north@example.com",
                password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    return {"client": client, "ds": ds.id, "admin": auth_headers["a"],
            "north": {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}}


async def _data(world, widget_type, config, who="admin", ok=True):
    r = await world["client"].post(f"/api/v1/datasets/{world['ds']}/widget-data",
                                   json={"widget_type": widget_type, "config": config},
                                   headers=world[who])
    if ok:
        assert r.status_code == 200, f"{widget_type}: {r.text}"
    return r


def _by_name(body):
    return {r["name"]: r["value"] for r in body["rows"]}


def _frame(rows=ROWS):
    return pd.DataFrame(rows)


VALID = _frame()[_frame()["lat"].between(-90, 90)]


class TestParity:
    @pytest.mark.parametrize("widget_type", ["map_choropleth", "map_bubbles"])
    @pytest.mark.parametrize("agg", ["sum", "avg", "count"])
    async def test_a_region_map_carries_the_bar_charts_values(self, world, engine, widget_type, agg):
        cfg = {"dimension": "governorate", "measure": "revenue", "aggregation": agg}
        on_map = _by_name((await _data(world, widget_type, cfg)).json())
        on_bar = _by_name((await _data(world, "bar", cfg)).json())
        assert on_map == on_bar
        expected = getattr(_frame().groupby("governorate")["revenue"],
                           {"sum": "sum", "avg": "mean", "count": "count"}[agg])()
        assert on_map == pytest.approx(expected.to_dict())

    async def test_a_region_map_carries_the_tables_values(self, world, engine):
        cfg = {"dimension": "governorate", "measure": "units", "aggregation": "sum"}
        on_map = _by_name((await _data(world, "map_choropleth", cfg)).json())
        table = (await _data(world, "table", cfg)).json()
        assert on_map == {r["name"]: r["value"] for r in table["rows"] if r["name"] != "__total__"}

    async def test_a_point_map_draws_every_row_with_valid_coordinates_and_says_what_it_dropped(self, world, engine):
        body = (await _data(world, "map_points", {"lat": "lat", "lon": "lon", "dimension": "governorate",
                                                   "measure": "revenue"})).json()
        assert body["dropped"] == 1 and body["total"] == len(ROWS)
        got = sorted((r["name"], r["lat"], r["lon"], r["value"]) for r in body["rows"])
        want = sorted(zip(VALID["governorate"], VALID["lat"], VALID["lon"], VALID["revenue"]))
        assert got == want

    async def test_a_line_map_draws_the_origin_destination_rows(self, world, engine):
        body = (await _data(world, "map_lines", {"lat": "lat", "lon": "lon", "lat2": "dest_lat",
                                                  "lon2": "dest_lon", "measure": "units"})).json()
        assert body["dropped"] == 1
        got = sorted((r["lat"], r["lon"], r["lat2"], r["lon2"]) for r in body["rows"])
        want = sorted(zip(VALID["lat"], VALID["lon"], VALID["dest_lat"], VALID["dest_lon"]))
        assert got == want

    async def test_a_filter_reaches_the_map_as_it_reaches_the_table(self, world, engine):
        south = [{"column": "zone", "op": "eq", "value": "South"}]
        cfg = {"dimension": "governorate", "measure": "revenue", "aggregation": "sum", "filters": south}
        on_map = _by_name((await _data(world, "map_choropleth", cfg)).json())
        assert set(on_map) == {"Aswan", "Luxor"}
        assert on_map == _by_name((await _data(world, "bar", cfg)).json())
        points = (await _data(world, "map_points", {"lat": "lat", "lon": "lon", "filters": south})).json()
        assert len(points["rows"]) == int((VALID["zone"] == "South").sum())


class TestPolicy:
    async def test_a_row_rule_reaches_every_map(self, world, engine):
        cfg = {"dimension": "governorate", "measure": "revenue", "aggregation": "sum"}
        seen = _by_name((await _data(world, "map_choropleth", cfg, who="north")).json())
        assert set(seen) == {"Cairo", "Giza", "Alexandria"}
        assert seen == _by_name((await _data(world, "bar", cfg, who="north")).json())
        points = (await _data(world, "map_points", {"lat": "lat", "lon": "lon", "dimension": "governorate"},
                              who="north")).json()
        assert {r["name"] for r in points["rows"]} == {"Cairo", "Giza", "Alexandria"}
        assert points["total"] == int((_frame()["zone"] == "North").sum())

    @pytest.mark.parametrize("widget_type,config", [
        ("map_choropleth", {"dimension": "governorate", "measure": "margin", "aggregation": "sum"}),
        ("map_bubbles", {"dimension": "governorate", "measure": "margin", "aggregation": "avg"}),
        ("map_points", {"lat": "lat", "lon": "lon", "dimension": "governorate", "measure": "margin"}),
        ("map_points", {"lat": "margin", "lon": "lon"}),
        ("map_lines", {"lat": "lat", "lon": "lon", "lat2": "dest_lat", "lon2": "dest_lon", "measure": "margin"}),
        ("map_clusters", {"lat": "lat", "lon": "margin"}),
        ("map_pie", {"dimension": "governorate", "dimension2": "zone", "measure": "margin", "aggregation": "sum"}),
    ])
    async def test_a_denied_column_is_on_no_map_in_any_role(self, world, engine, widget_type, config):
        r = await _data(world, widget_type, config, who="north", ok=False)
        # Refused, or answered without it -- never one of its values, in a
        # measure, a size, a coordinate or a label a tooltip would show.
        assert r.status_code in (200, 403, 422), r.text
        leaked = [v for v in _frame()["margin"] if f"{v:g}" in r.text or repr(v) in r.text]
        assert leaked == [], f"{widget_type} showed denied values {leaked[:3]}"
        # The same config is a sound request for someone who may see margin.
        await _data(world, widget_type, config)


class TestExport:
    async def _csv(self, world, widget_type, config, who="admin"):
        r = await world["client"].post(f"/api/v1/datasets/{world['ds']}/widget-data/export?format=csv",
                                       json={"widget_type": widget_type, "config": config},
                                       headers=world[who])
        assert r.status_code == 200, r.text
        return pd.read_csv(io.BytesIO(r.content), encoding="utf-8-sig")

    async def test_a_region_maps_csv_is_the_rows_it_draws(self, world, engine):
        cfg = {"dimension": "governorate", "measure": "revenue", "aggregation": "sum"}
        drawn = _by_name((await _data(world, "map_choropleth", cfg)).json())
        exported = await self._csv(world, "map_choropleth", cfg)
        assert dict(zip(exported.iloc[:, 0], exported.iloc[:, 1])) == pytest.approx(drawn)

    async def test_a_point_maps_csv_has_one_line_per_marker(self, world, engine):
        cfg = {"lat": "lat", "lon": "lon", "dimension": "governorate", "measure": "revenue"}
        body = (await _data(world, "map_points", cfg)).json()
        exported = await self._csv(world, "map_points", cfg)
        assert len(exported) == len(body["rows"]) == len(VALID)
        assert {"lat", "lon"} <= {str(c).lower() for c in exported.columns}

    async def test_a_restricted_roles_map_export_is_their_map(self, world, engine):
        cfg = {"lat": "lat", "lon": "lon", "dimension": "governorate", "measure": "revenue"}
        exported = await self._csv(world, "map_points", cfg, who="north")
        names = exported[[c for c in exported.columns if str(c).lower() == "name"][0]]
        assert set(names) == {"Cairo", "Giza", "Alexandria"}
        assert len(exported) == int((VALID["zone"] == "North").sum())

    async def test_a_map_on_a_denied_column_exports_none_of_it(self, world, engine):
        cfg = {"lat": "lat", "lon": "lon", "dimension": "governorate", "measure": "margin"}
        r = await world["client"].post(f"/api/v1/datasets/{world['ds']}/widget-data/export?format=csv",
                                       json={"widget_type": "map_points", "config": cfg},
                                       headers=world["north"])
        assert r.status_code in (200, 400, 403), r.text
        text = r.content.decode("utf-8-sig", errors="replace")
        assert not any(f"{v:g}" in text for v in _frame()["margin"])
