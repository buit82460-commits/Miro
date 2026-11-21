"""Mock tests cho miro.integrations — không gọi mạng/process/browser thật."""
from __future__ import annotations

import asyncio
import json

import pytest

from miro.integrations.agent_reach import AgentReachAdapter, ReadUrlRequest, SearchRequest
from miro.integrations.base import READS_LOG, IntegrationError
from miro.integrations.browser_use import AutomateRequest, BindRequest, BrowserUseAdapter, ReadTabRequest
from miro.integrations.captcha import CaptchaJob, CaptchaSolver, OhmCaptchaStandby
from miro.integrations.llm_provider import LlmProvider, LlmRequest
from miro.integrations.reader import LocalReader, ReaderRouter, ReadRequest, ReaReader
from miro.integrations.vision_provider import VisionProvider, VisionRequest


# ── fakes ────────────────────────────────────────────────────────────────

class _FakeResp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeHttp:
    def __init__(self, resp):
        self._resp = resp
        self.posts = []

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        self.posts.append({"url": url, "json": json})
        return self._resp

    async def get(self, url):
        self.posts.append({"url": url})
        return self._resp


def _chat_payload(text="xin chao", pt=10, ct=5):
    return {"choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": pt, "completion_tokens": ct}}


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ── llm ──────────────────────────────────────────────────────────────────

def test_llm_ok():
    p = LlmProvider(model="m", api_key="k", base_url="https://x",
                    http_client=lambda: _FakeHttp(_FakeResp(200, _chat_payload())))
    out = run(p.complete(LlmRequest(prompt="hello")))
    assert out["text"] == "xin chao" and out["prompt_tokens"] == 10


def test_llm_missing_key():
    with pytest.raises(IntegrationError) as e:
        LlmProvider(model="m", api_key="", base_url="https://x")
    assert e.value.code == "LLM_AUTH_MISSING"


def test_llm_rate_limited():
    p = LlmProvider(model="m", api_key="k", base_url="https://x",
                    http_client=lambda: _FakeHttp(_FakeResp(429, {})))
    with pytest.raises(IntegrationError) as e:
        run(p.complete(LlmRequest(prompt="hi")))
    assert e.value.code == "LLM_RATE_LIMITED"


def test_llm_empty_output():
    p = LlmProvider(model="m", api_key="k", base_url="https://x",
                    http_client=lambda: _FakeHttp(_FakeResp(200, _chat_payload(text="  "))))
    with pytest.raises(IntegrationError) as e:
        run(p.complete(LlmRequest(prompt="hi")))
    assert e.value.code == "LLM_EMPTY_OUTPUT"


# ── vision ───────────────────────────────────────────────────────────────

def test_vision_ok_and_image_dropped(tmp_path):
    f = tmp_path / "frame.jpg"
    f.write_bytes(b"\xff\xd8fake")
    ok_resp = _FakeResp(200, {"choices": [{"message": {"content": "co xe"}}],
                              "usage": {"prompt_tokens": 626, "completion_tokens": 12}})
    v = VisionProvider(model="qwen", api_key="k", base_url="https://x",
                       http_client=lambda: _FakeHttp(ok_resp))
    out = run(v.describe_frame(VisionRequest(image_path=str(f), prompt="mo ta")))
    assert out["text"] == "co xe"

    drop_resp = _FakeResp(200, _chat_payload(pt=104))
    v2 = VisionProvider(model="m", api_key="k", base_url="https://x",
                        http_client=lambda: _FakeHttp(drop_resp))
    with pytest.raises(IntegrationError) as e:
        run(v2.describe_frame(VisionRequest(image_path=str(f), prompt="mo ta")))
    assert e.value.code == "VISION_IMAGE_DROPPED"


def test_vision_unreadable_frame(tmp_path):
    v = VisionProvider(model="m", api_key="k", base_url="https://x",
                       http_client=lambda: _FakeHttp(_FakeResp(200, _chat_payload())))
    with pytest.raises(IntegrationError) as e:
        run(v.describe_frame(VisionRequest(image_path=str(tmp_path / "no.jpg"), prompt="x")))
    assert e.value.code == "VISION_FRAME_UNREADABLE"


# ── reader: REA vs local, log phân biệt ──────────────────────────────────

class _FakeRea:
    async def read_text(self, target, max_chars):
        return "REA-CONTENT " + target


def test_reader_router_rea_vs_local(tmp_path):
    READS_LOG.clear()
    rea = ReaReader(_FakeRea())
    f = tmp_path / "doc.txt"
    f.write_text("local hello", encoding="utf-8")
    local = LocalReader(allowed_dirs=[str(tmp_path)])
    router = ReaderRouter(rea=rea, local=local)

    r1 = run(router.read(ReadRequest(target="0x401000")))
    r2 = run(router.read(ReadRequest(target=str(f))))
    assert r1["via"] == "rea" and "REA-CONTENT" in r1["text"]
    assert r2["via"] == "local" and r2["text"] == "local hello"
    tools = [e["tool"] for e in READS_LOG[-2:]]
    assert tools == ["rea", "local"]  # lần đọc nào dùng cái nào: ghi rõ ở log


def test_local_policy_denies_private_ip():
    READS_LOG.clear()
    local = LocalReader()
    with pytest.raises(IntegrationError) as e:
        run(local.read(ReadRequest(target="http://127.0.0.1/secret")))
    assert e.value.code == "READER_POLICY_DENIED"


def test_rea_unavailable():
    with pytest.raises(IntegrationError) as e:
        run(ReaReader(None).read(ReadRequest(target="0x10")))
    assert e.value.code == "READER_REA_UNAVAILABLE"


# ── captcha ──────────────────────────────────────────────────────────────

def test_captcha_ok_and_policy():
    calls = []

    def fake_solve(kind, page, **kw):
        calls.append(kind)

    s = CaptchaSolver(solve_fn=fake_solve)
    with pytest.raises(IntegrationError) as e:
        s.solve(CaptchaJob(kind="recaptcha-v2", confirmed=False), page=None)
    assert e.value.code == "CAPTCHA_POLICY_DENIED"
    out = s.solve(CaptchaJob(kind="recaptcha-v2", confirmed=True), page=None)
    assert out == {"ok": True, "kind": "recaptcha-v2",
                   "elapsed_s": out["elapsed_s"], "via": "pypasser"}
    assert calls == ["recaptcha-v2"]


def test_captcha_unsupported_kind():
    s = CaptchaSolver(solve_fn=lambda *a, **k: None)
    with pytest.raises(IntegrationError) as e:
        s.solve(CaptchaJob(kind="shopee-crawler", confirmed=True))
    assert e.value.code == "CAPTCHA_UNSUPPORTED_KIND"


def test_ohmycaptcha_standby_by_default():
    o = OhmCaptchaStandby()
    assert o.status() == {"standby": True, "enabled": False,
                          "url_set": False, "url": "OHMYCAPTCHA_URL unset"}
    with pytest.raises(IntegrationError) as e:
        run(o.submit("abc", confirmed=True))
    assert e.value.code == "CAPTCHA_SOLVER_MISSING"


# ── agent-reach ──────────────────────────────────────────────────────────

def _envelope(items, action="search", backend="exa"):
    return json.dumps({"ok": True, "channel": "web", "action": action,
                       "backend": backend, "items": items})


def test_agent_reach_search_ok():
    async def fake_cli(argv, timeout):
        assert "--backend" in argv and "exa" in argv  # ghim backend, không fallback
        return 0, _envelope([{"title": "T", "url": "https://a.vn", "text": "x" * 5000}]), ""
    a = AgentReachAdapter(repo_dir="/tmp", home_dir="/tmp", cli_runner=fake_cli)
    out = run(a.search(SearchRequest(query="q")))
    assert out["backend"] == "exa" and out["items"][0]["truncated"] is True


def test_agent_reach_unexpected_backend():
    async def fake_cli(argv, timeout):
        return 0, _envelope([{"title": "T", "url": "https://a.vn", "text": "t"}],
                            backend="jina"), ""
    a = AgentReachAdapter(repo_dir="/tmp", home_dir="/tmp", cli_runner=fake_cli)
    with pytest.raises(IntegrationError) as e:
        run(a.search(SearchRequest(query="q")))
    assert e.value.code == "AGENT_REACH_UNEXPECTED_BACKEND"


def test_agent_reach_read_and_stop():
    async def fake_cli(argv, timeout):
        assert "jina" in argv
        return 0, _envelope([{"title": "P", "url": "https://a.vn/p", "text": "noidung"}],
                            action="read", backend="jina"), ""
    a = AgentReachAdapter(repo_dir="/tmp", home_dir="/tmp", cli_runner=fake_cli)
    out = run(a.read(ReadUrlRequest(url="https://a.vn/p")))
    assert out["content"] == "noidung" and out["backend"] == "jina"
    run(a.request_stop())
    with pytest.raises(IntegrationError) as e:
        run(a.search(SearchRequest(query="q")))
    assert e.value.code == "AGENT_REACH_STOPPED"


# ── browser-use ──────────────────────────────────────────────────────────

class _FakeDriver:
    async def tabs(self):
        return [{"id": "t1"}]

    async def bind(self, payload):
        return {"bound": True}

    async def read(self, binding, max_chars):
        return {"text": "page text here"}

    async def act(self, action, lease):
        return f"did:{action}"

    async def extract(self, goal, lease):
        return {"goal": goal}


_BIND = {"browser_id": "a" * 64, "target_id": "t1",
         "profile_target_id": "p1", "profile_directory": "Profile 20",
         "account_id": "123"}


def test_browser_live_flow():
    b = BrowserUseAdapter(driver=_FakeDriver())
    tabs = run(b.tabs())
    assert tabs["mode"] == "existing_cdp"
    bound = run(b.bind(BindRequest(**_BIND)))
    assert bound["capability"] == "READ"
    page = run(b.read(ReadTabRequest(binding_id=bound["binding_id"])))
    assert page["content"] == "page text here"


def test_browser_automate_needs_lease():
    b = BrowserUseAdapter(driver=_FakeDriver())
    with pytest.raises(IntegrationError) as e:
        run(b.automate(AutomateRequest(goal="click")))
    assert e.value.code == "BROWSER_LEASE_LOST"
    out = run(b.automate(AutomateRequest(goal="extract:price",
                                         actions=["click #buy"]), lease={"token": "t"}))
    assert out["adapter"] == "browser_use" and out["extracted"] == {"goal": "price"}


def test_browser_no_driver():
    with pytest.raises(IntegrationError) as e:
        run(BrowserUseAdapter().tabs())
    assert e.value.code == "BROWSER_RUNTIME_MISSING"
