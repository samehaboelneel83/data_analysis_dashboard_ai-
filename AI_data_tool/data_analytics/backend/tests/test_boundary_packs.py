"""Starter boundary packs (MASTER_PLAN Phase 4 item 2): Egypt governorates
first, because the hospital dashboard whose 27 governorates drew a blank world
map is where the geography gap was found."""
import json

import pytest

from app.core.config import settings
from app.services.boundary_sets import list_packs, load_pack

URL = "/api/v1/boundary-sets"


def test_the_shipped_packs_are_listed_with_a_licence():
    packs = {p["id"]: p for p in list_packs()}
    assert {"egypt-governorates", "us-states"} <= set(packs)
    for p in packs.values():
        assert p["license"] and p["source"]
    assert packs["egypt-governorates"]["feature_count"] == 27


def test_egypt_matches_the_spellings_people_type():
    _, checked = load_pack("egypt-governorates")
    assert checked["key_properties"][0] == "name"  # the display name leads
    assert checked["sample_names"][0]  # an English name, not an alias
    index = {}
    for f in checked["geometry"]["features"]:
        for k in checked["key_properties"]:
            index.setdefault(str(f["properties"][k]).strip().lower(), f["properties"]["name"])
    for spelling, gov in [("Cairo", "Cairo"), ("القاهرة", "Cairo"), ("Al Qahirah", "Cairo"),
                          ("EG-C", "Cairo"), ("Sharkia", "Al Sharqia"), ("Fayoum", "Faiyum"),
                          ("الاسكندرية", "Alexandria"), ("Giza", "Giza"), ("Menoufia", "Monufia")]:
        assert index.get(spelling.lower()) == gov, spelling


def test_a_missing_folder_lists_no_packs(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "boundary_packs_dir", str(tmp_path / "nothing-here"))
    assert list_packs() == []


def test_a_pack_without_a_licence_is_not_offered(monkeypatch, tmp_path):
    (tmp_path / "x.geojson").write_text("{}")
    (tmp_path / "manifest.json").write_text(json.dumps({"packs": [{"id": "x", "file": "x.geojson"}]}))
    monkeypatch.setattr(settings, "boundary_packs_dir", str(tmp_path))
    assert list_packs() == []


@pytest.mark.asyncio
async def test_installing_a_pack_creates_an_ordinary_boundary_set(client, two_orgs, auth_headers):
    listed = await client.get(f"{URL}/packs", headers=auth_headers["a"])
    assert listed.status_code == 200 and any(p["id"] == "egypt-governorates" for p in listed.json())
    r = await client.post(f"{URL}/packs/egypt-governorates/install", headers=auth_headers["a"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Egypt governorates" and body["feature_count"] == 27
    assert body["key_properties"][0] == "name"
    # It is now just a set of the org's, drawable by id...
    got = await client.get(f"{URL}/{body['id']}", headers=auth_headers["a"])
    assert len(got.json()["geometry"]["features"]) == 27
    # ...and installing it again is refused by name, as a second upload is.
    again = await client.post(f"{URL}/packs/egypt-governorates/install", headers=auth_headers["a"])
    assert again.status_code == 409
    # Another org installs its own copy; nothing is shared across tenants.
    other = await client.post(f"{URL}/packs/egypt-governorates/install", headers=auth_headers["b"])
    assert other.status_code == 201


@pytest.mark.asyncio
async def test_an_unknown_pack_is_a_404(client, two_orgs, auth_headers):
    r = await client.post(f"{URL}/packs/atlantis/install", headers=auth_headers["a"])
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_values_can_be_pinned_to_regions_and_travel_with_the_set(client, two_orgs, auth_headers):
    made = (await client.post(f"{URL}/packs/egypt-governorates/install", headers=auth_headers["a"])).json()
    geo = (await client.get(f"{URL}/{made['id']}", headers=auth_headers["a"])).json()["geometry"]
    cairo = next(i for i, f in enumerate(geo["features"]) if f["properties"]["name"] == "Cairo")
    r = await client.put(f"{URL}/{made['id']}/pins", headers=auth_headers["a"],
                         json={"pins": {"Greater Cairo": cairo, " ": 0}})
    assert r.status_code == 200, r.text
    assert r.json()["pins"] == {"Greater Cairo": cairo}
    geo = (await client.get(f"{URL}/{made['id']}", headers=auth_headers["a"])).json()["geometry"]
    assert geo["x_pins"] == {"Greater Cairo": cairo}
    bad = await client.put(f"{URL}/{made['id']}/pins", headers=auth_headers["a"], json={"pins": {"X": 999}})
    assert bad.status_code == 400 and "999" in bad.text
    cleared = await client.put(f"{URL}/{made['id']}/pins", headers=auth_headers["a"], json={"pins": {}})
    assert cleared.status_code == 200
    geo = (await client.get(f"{URL}/{made['id']}", headers=auth_headers["a"])).json()["geometry"]
    assert "x_pins" not in geo
    # Another org cannot even see it.
    other = await client.put(f"{URL}/{made['id']}/pins", headers=auth_headers["b"], json={"pins": {}})
    assert other.status_code == 404


@pytest.mark.asyncio
async def test_the_eu_nuts1_pack_needs_its_terms_accepted_and_carries_its_credit(client, two_orgs, auth_headers):
    listed = {p["id"]: p for p in (await client.get(f"{URL}/packs", headers=auth_headers["a"])).json()}
    eu = listed["eu-nuts1"]
    assert eu["requires_acceptance"] is True and "EuroGeographics" in eu["attribution"]
    refused = await client.post(f"{URL}/packs/eu-nuts1/install", headers=auth_headers["a"])
    assert refused.status_code == 400 and "commercial" in refused.json()["detail"]
    ok = await client.post(f"{URL}/packs/eu-nuts1/install", json={"accept_terms": True}, headers=auth_headers["a"])
    assert ok.status_code == 201 and ok.json()["feature_count"] == 123
    geo = (await client.get(f"{URL}/{ok.json()['id']}", headers=auth_headers["a"])).json()["geometry"]
    assert geo["x_attribution"] == "© EuroGeographics for the administrative boundaries"
    names = {f["properties"]["nuts_id"]: f["properties"]["name"] for f in geo["features"]}
    assert names["DE2"] == "Bayern" and names["ES3"] == "Comunidad de Madrid"
