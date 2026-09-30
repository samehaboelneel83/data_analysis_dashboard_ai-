"""Several LLM endpoints, a default, Auto failover and a status light each
(services/llm_endpoints.py, routers/llm.py, platform_settings.py)."""
import httpx
import pytest

from app.core.config import settings
from app.models.models import AppSetting
from app.services import app_settings, llm as llm_service, llm_endpoints as le

ADMIN = "/api/v1/platform/settings/llm-endpoints"
PUBLIC = "/api/v1/llm/endpoints"

TWO = [
    {"id": "a", "name": "Server A", "base_url": "http://a:8000/v1", "model": "qwen", "api_key": "ka"},
    {"id": "b", "name": "Server B", "base_url": "http://b:8000/v1", "model": "llama"},
]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(settings, "super_admin_emails", "admin-a@example.com")
    monkeypatch.setattr(settings, "llm_enabled", True)

    async def no_probe():
        return None
    monkeypatch.setattr(le, "probe_all", no_probe)
    le.apply_stored(None)
    le._health.clear()
    yield
    le.apply_stored(None)
    le._health.clear()
    app_settings._apply({})


class TestWithNothingSaved:
    def test_the_single_environment_endpoint_is_the_list(self):
        [ep] = le.endpoints()
        assert (ep.id, ep.base_url, ep.model) == ("env", settings.llm_base_url, settings.llm_model)
        c = llm_service.get_client()
        assert c.base_url == settings.llm_base_url.rstrip("/") and c.fallbacks == []


class TestSaving:
    async def test_admin_saves_a_list_and_a_default(self, client, db_session, two_orgs, auth_headers):
        r = await client.put(ADMIN, headers=auth_headers["a"], json={"endpoints": TWO, "default": "b"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["default"] == "b" and [e["id"] for e in body["endpoints"]] == ["a", "b"]
        assert "ka" not in r.text and body["endpoints"][0]["has_api_key"] is True
        row = await db_session.get(AppSetting, le.ROW_KEY)
        assert row.value["endpoints"][0]["api_key"] not in ("", "ka")      # encrypted at rest
        c = llm_service.get_client()
        assert (c.endpoint_id, c.model) == ("b", "llama")

    async def test_a_blank_key_keeps_the_stored_one(self, client, two_orgs, auth_headers):
        await client.put(ADMIN, headers=auth_headers["a"], json={"endpoints": TWO, "default": "a"})
        again = [dict(TWO[0], api_key=None), TWO[1]]
        await client.put(ADMIN, headers=auth_headers["a"], json={"endpoints": again, "default": "a"})
        assert le.find("a").api_key == "ka"

    @pytest.mark.parametrize("endpoints, default, words", [
        ([], "auto", "at least one"),
        ([dict(TWO[0], base_url="ftp://x")], "auto", "http(s)"),
        ([dict(TWO[0], model="")], "auto", "model name"),
        ([TWO[0], dict(TWO[1], id="a")], "auto", "share the id"),
        (TWO, "zzz", "default must be"),
        ([dict(TWO[0], enabled=False)], "auto", "must be enabled"),
    ])
    async def test_a_bad_list_is_refused(self, client, two_orgs, auth_headers, endpoints, default, words):
        r = await client.put(ADMIN, headers=auth_headers["a"], json={"endpoints": endpoints, "default": default})
        assert r.status_code == 400 and words in r.json()["detail"], r.text

    async def test_only_platform_admins_edit(self, client, two_orgs, auth_headers):
        assert (await client.get(ADMIN, headers=auth_headers["b"])).status_code == 403
        assert (await client.put(ADMIN, headers=auth_headers["b"],
                                 json={"endpoints": TWO, "default": "a"})).status_code == 403

    async def test_load_applies_the_saved_list_in_another_worker(self, client, db_session, two_orgs, auth_headers):
        await client.put(ADMIN, headers=auth_headers["a"], json={"endpoints": TWO, "default": "b"})
        le.apply_stored(None)
        await app_settings.load(db_session)
        assert le.default_choice() == "b" and le.find("a").api_key == "ka"


class TestPicking:
    async def test_everyone_sees_names_and_lights_but_no_addresses(self, client, two_orgs, auth_headers):
        await client.put(ADMIN, headers=auth_headers["a"], json={"endpoints": TWO, "default": "auto"})
        le.mark("a", False, "refused"); le.mark("b", True)
        r = await client.get(PUBLIC, headers=auth_headers["b"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert "http://a" not in r.text and "has_api_key" not in r.text
        assert body["auto_pick"] == "b"
        assert [e["status"]["ok"] for e in body["endpoints"]] == [False, True]

    def test_auto_puts_reachable_endpoints_first(self):
        le.apply_stored({"default": "auto", "endpoints": [dict(e, api_key="") for e in TWO]})
        le.mark("a", False, "down"); le.mark("b", True)
        assert [e.id for e in le.candidates("auto")] == ["b", "a"]
        c = llm_service.get_client()
        assert c.endpoint_id == "b" and [e.id for e in c.fallbacks] == ["a"]

    def test_a_named_endpoint_is_used_alone_even_when_down(self):
        le.apply_stored({"default": "auto", "endpoints": [dict(e, api_key="") for e in TWO]})
        le.mark("a", False, "down")
        assert [e.id for e in le.candidates("a")] == ["a"]

    def test_the_request_header_choice_wins_over_the_default(self):
        le.apply_stored({"default": "a", "endpoints": [dict(e, api_key="") for e in TWO]})
        tok = le.use_choice("b")
        try:
            assert llm_service.get_client().endpoint_id == "b"
        finally:
            le.release_choice(tok)
        assert llm_service.get_client().endpoint_id == "a"
        tok = le.use_choice("deleted-one")     # unknown: falls back to the default
        try:
            assert llm_service.get_client().endpoint_id == "a"
        finally:
            le.release_choice(tok)


class TestFailover:
    async def test_auto_fails_over_and_turns_the_light_red(self):
        le.apply_stored({"default": "auto", "endpoints": [dict(e, api_key="") for e in TWO]})

        def handler(request):
            if request.url.host == "a":
                raise httpx.ConnectError("All connection attempts failed")
            assert request.read() and b'"llama"' in request.content   # B's own model name
            return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

        c = llm_service.get_client("auto")
        c._transport = httpx.MockTransport(handler)
        assert await c.complete([{"role": "user", "content": "x"}]) == "hi"
        assert c.answered_by == "b"
        assert le.is_up("a") is False and le.is_up("b") is True


class TestProbe:
    async def test_probe_reports_a_model_the_server_does_not_serve(self):
        ep = le.Endpoint(id="p", name="P", base_url="http://p/v1", model="missing")
        t = httpx.MockTransport(lambda r: httpx.Response(200, json={"data": [{"id": "qwen"}]}))
        h = await le.probe(ep, transport=t)
        assert h["ok"] is False and "not served" in h["error"]
        ok = await le.probe(le.Endpoint(id="q", name="Q", base_url="http://p/v1", model="qwen"), transport=t)
        assert ok["ok"] is True

    async def test_probe_of_an_unreachable_server_is_red_not_raised(self):
        def boom(r):
            raise httpx.ConnectError("refused")
        h = await le.probe(le.Endpoint(id="x", name="X", base_url="http://x/v1", model="m"),
                           transport=httpx.MockTransport(boom))
        assert h["ok"] is False and "ConnectError" in h["error"]


BUILTIN = ('[{"id":"big","name":"Qwen 27B","base_url":"http://b:8014/v1","model":"qwen3.8_27b","strength":8},'
           '{"id":"mid","name":"Qwen 3.5","base_url":"http://m:8000/v1","model":"qwen3.5","strength":6},'
           '{"id":"small","name":"Qwen 9B","base_url":"http://s:8015/v1","model":"qwen3.5_9b"}]')


class TestBuiltInList:
    def test_the_deployment_list_is_used_until_one_is_saved(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_endpoints", BUILTIN)
        assert [e.id for e in le.endpoints()] == ["big", "mid", "small"]
        assert le.default_choice() == "auto" and le.source() == "deployment"
        assert le.strength_of(le.find("small")) == 4          # guessed from "9b"
        le.apply_stored({"default": "a", "endpoints": [dict(TWO[0], api_key="")]})
        assert [e.id for e in le.endpoints()] == ["a"]         # a saved list wins

    def test_a_broken_list_is_ignored_not_fatal(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_endpoints", "[{not json")
        assert [e.id for e in le.endpoints()] == ["env"]


class TestSmartAuto:
    @pytest.fixture(autouse=True)
    def _three(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_endpoints", BUILTIN)
        for eid in ("big", "mid", "small"):
            le.mark(eid, True)
        le._meta.update({"big": {"max_model_len": 32768}, "mid": {"max_model_len": 32768},
                         "small": {"max_model_len": 16384}})
        yield
        le._meta.clear()
        le._inflight.clear()

    def order(self, **kw):
        return [e.id for e in le.route(le.endpoints(), **kw)]

    def test_heavy_work_goes_to_the_strongest(self):
        assert self.order(prompt_tokens=2000, max_tokens=600, weight="heavy")[0] == "big"

    def test_light_work_goes_to_the_fastest(self):
        assert self.order(prompt_tokens=500, max_tokens=200, weight="light")[0] == "small"

    def test_a_prompt_too_big_for_a_model_skips_it(self):
        # 20k tokens do not fit the 16k model even for light work.
        assert self.order(prompt_tokens=20000, max_tokens=500, weight="light") == ["mid", "big", "small"]

    def test_a_down_model_is_tried_last(self):
        le.mark("big", False, "down")
        assert self.order(prompt_tokens=100, max_tokens=100, weight="heavy") == ["mid", "small", "big"]

    def test_a_busy_strong_model_yields_normal_work(self):
        le._inflight["big"] = 3
        assert self.order(prompt_tokens=100, max_tokens=100, weight="normal")[0] == "mid"

    def test_the_feature_decides_the_weight(self):
        from app.services.llm import UsageMeter, use_meter, release_meter
        tok = use_meter(UsageMeter(org_id=1, user_id=1, feature="metadata"))
        try:
            assert llm_service.LLMClient._weight(False) == "light"
        finally:
            release_meter(tok)
        tok = use_meter(UsageMeter(org_id=1, user_id=1, feature="ask"))
        try:
            assert llm_service.LLMClient._weight(True) == "heavy"
        finally:
            release_meter(tok)

    async def test_auto_sends_the_call_where_route_says_and_trims_the_answer_budget(self):
        seen = []

        def handler(request):
            import json
            body = json.loads(request.content)
            seen.append((request.url.host, body["model"], body["max_tokens"]))
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        c = llm_service.get_client("auto")
        assert c.auto
        c._transport = httpx.MockTransport(handler)
        assert await c.complete([{"role": "user", "content": "hi"}], weight="light", max_tokens=100) == "ok"
        assert seen[-1][:2] == ("s", "qwen3.5_9b")
        # 14k-token prompt on a light call: the 9B (16k) fits the prompt but
        # not a 4k answer, so it goes to the next fitting model instead.
        long = "x" * 35000
        assert await c.complete([{"role": "user", "content": long}], weight="light", max_tokens=4000) == "ok"
        assert seen[-1][0] == "m"

    async def test_probe_reads_the_context_size(self):
        le._meta.clear()
        ep = le.find("small")
        t = httpx.MockTransport(lambda r: httpx.Response(200, json={"data": [
            {"id": "qwen3.5_9b", "max_model_len": 16384}]}))
        await le.probe(ep, transport=t)
        assert le.context_of(ep) == 16384
