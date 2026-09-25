import pytest
from fastapi import HTTPException
from app.core.org_scope import check_org


class _FakeObj:
    def __init__(self, org_id):
        self.org_id = org_id


class _FakeUser:
    def __init__(self, org_id):
        self.org_id = org_id


def test_raises_404_when_obj_is_none():
    with pytest.raises(HTTPException) as exc_info:
        check_org(None, _FakeUser(1), "Thing not found")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Thing not found"


def test_raises_404_when_org_ids_do_not_match():
    with pytest.raises(HTTPException) as exc_info:
        check_org(_FakeObj(org_id=2), _FakeUser(org_id=1), "Thing not found")
    assert exc_info.value.status_code == 404


def test_does_not_raise_when_org_ids_match():
    check_org(_FakeObj(org_id=1), _FakeUser(org_id=1), "Thing not found")  # no exception


def test_default_message_is_not_found():
    with pytest.raises(HTTPException) as exc_info:
        check_org(None, _FakeUser(1))
    assert exc_info.value.detail == "Not found"
