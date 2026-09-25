"""F1: .xml joins csv/xlsx/xls/json/parquet as a supported upload extension.

pd.read_xml (via lxml, already in requirements.txt) is registered in
analytics.SUPPORTED the same way every other reader is, so it flows through
the existing load_file -> frame_cache._parse dispatch with no special-casing.
The only NEW behaviour is that upload_dataset now converts a reader failure
(unsupported extension, or a file the reader can't parse) into a clean 400
instead of letting it propagate to a 500.
"""
from app.services.analytics import SUPPORTED


VALID_XML = b"""<?xml version="1.0"?>
<rows>
  <row><a>1</a><b>x</b></row>
  <row><a>2</a><b>y</b></row>
</rows>
"""

MALFORMED_XML = b"<rows><row><a>1</a></row>"  # unclosed tag -- not well-formed


def test_xml_is_registered_as_a_supported_extension():
    assert ".xml" in SUPPORTED


async def test_xml_fixture_uploads_and_parses(client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path):
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))

    resp = await client.post(
        "/api/v1/datasets",
        files={"file": ("rows.xml", VALID_XML, "application/xml")},
        data={"name": "XML Dataset", "description": ""},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["row_count"] == 2
    assert body["col_count"] == 2
    col_names = {c["name"] for c in body["columns"]}
    assert col_names == {"a", "b"}


async def test_malformed_xml_upload_is_a_clean_400_not_a_500(client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path):
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))

    resp = await client.post(
        "/api/v1/datasets",
        files={"file": ("bad.xml", MALFORMED_XML, "application/xml")},
        data={"name": "Bad XML", "description": ""},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 400
    assert "detail" in resp.json()


async def test_unsupported_extension_message_unchanged(client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path):
    """Existing behaviour, now surfaced as a 400 instead of a 500: an
    extension outside SUPPORTED still names itself in frame_cache's error."""
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))

    resp = await client.post(
        "/api/v1/datasets",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
        data={"name": "Unsupported", "description": ""},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]
