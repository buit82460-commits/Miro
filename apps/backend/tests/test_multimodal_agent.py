"""Multimodal Agent E2E: Browser REA/Eye + rea-video trong CUNG 1 task.

PHAM VI HONEST LABEL:
- M1-M10: INTEGRATION E2E voi BROWSER MOCK (FakePage + fake Gateway
  session: tab t-N / inst-1 / user-1 la gia lap) + MEDIA THAT
  (analyze_native tren fixture local). Chua phai FULL LIVE.
- M11-M12: ephemeral cleanup voi download mock (khong mang).
- FULL LIVE (Chrome Profile 20 + tab TikTok that + Gateway that) la
  buoc nghiem thu rieng, khong nam trong file nay.

- Negative: stale/revoke/wrong-tab/media failure/timeout/spoofing.
- Khong Browser WRITE, khong bypass, khong Library.

Chay: python -m pytest tests/test_multimodal_agent.py -q
"""
import asyncio
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.browser import gateway, session_manager  # noqa: E402
from miro.browser.errors import RegistryError, WorkerStopped  # noqa: E402
from miro.browser.lease_store import LeaseStore  # noqa: E402
from miro.browser.runtime import BrowserRuntime, ManagedChromeSession  # noqa: E402
from miro.research import multimodal  # noqa: E402

FIXTURE = Path(r"C:\Miro\var\studio-fixture.mp4")


class FakePage:
    _counter = [0]

    def __init__(self, url, account="user-1"):
        self.url = url
        self._account = account
        FakePage._counter[0] += 1
        self.target_id = f"t-{FakePage._counter[0]}"

    def is_closed(self):
        return False

    async def goto(self, url, **kwargs):
        self.url = url


class FakeContext:
    def __init__(self, pages):
        self.pages = pages


class FakeBrowser:
    def __init__(self, pages):
        self.contexts = [FakeContext(list(pages))]

    def is_connected(self):
        return True


def make_session(tmp_path, pages, account="user-1", origins=()):
    store = LeaseStore(str(tmp_path / "leases.sqlite"))
    runtime = BrowserRuntime(
        browser=FakeBrowser(pages), instance_id="inst-1", store=store,
        allowed_origins=origins or ("https://example.com",),
        verify_actor=lambda p, r: p._account)
    runtime.profiles["prof-1"] = {"id": "prof-1", "status": "verified",
                                  "browserInstanceId": "inst-1"}
    return ManagedChromeSession(runtime=runtime, endpoint="ws://fake")


def seed_tab(session, page, url="https://example.com/a", account="user-1"):
    rec = {"id": f"inst-1:{page.target_id}", "targetId": page.target_id,
           "url": url, "profileBindingId": "prof-1",
           "browserInstanceId": "inst-1", "platformId": "demo",
           "expectedAccountId": account, "status": "open", "lastUsedAt": 0.0}
    session.runtime.store.put("tab", rec["id"], rec)
    session.runtime.pages[page.target_id] = page
    return rec


async def video_eye(page):
    return {"url": page.url, "post_id": "vid-1", "caption": "demo clip",
            "counts": {"likes": "10"}}


def native_on_fixture(url):
    from miro import media_intel as mi
    import tempfile
    with tempfile.TemporaryDirectory(prefix="mi-e2e-") as tmp:
        return mi.analyze_native(FIXTURE, Path(tmp) / "out")


# M1: E2E that — eye + native + agent text trong cung 1 luot
def test_m1_multimodal_e2e_native(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)
    res = asyncio.run(multimodal.run_multimodal_task(
        session, platform_id="demo", url="https://example.com/a",
        caller="agent-e2e", eye_fn=video_eye,
        analyze_fn=native_on_fixture))
    assert res["ok"] is True
    assert res["browser_evidence"]["provenance"] == "rea-eye"
    assert res["provenance"] == {"browser": "rea-eye",
                                 "media": "media-analysis"}
    assert res["media"]["provenance"] == "media-analysis"
    assert res["media"].get("file_sha256")
    assert res["agent_text"]  # Agent that su tieu thu ket qua
    assert "khong phai Evidence ghi" in res["agent_text"]


# M2: batch 2 video, loi 1 khong dung loat
def test_m2_batch_partial_failure(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)

    calls = {"n": 0}

    def flaky(url):
        calls["n"] += 1
        if calls["n"] == 1:
            return native_on_fixture(url)
        raise RuntimeError("DOWNLOAD_FAILED: mang rot")

    res = asyncio.run(multimodal.run_multimodal_batch(
        session, platform_id="demo",
        urls=["https://example.com/a", "https://example.com/a"],
        caller="agent-batch", eye_fn=video_eye,
        analyze_fn=flaky))
    assert len(res) == 2
    assert res[0]["ok"] is True
    assert res[1]["ok"] is False


# M3: stale evidence (qua 300s) bi Gateway tu choi
def test_m3_stale_evidence_rejected():
    ev = {"url": "https://example.com/a", "tab_id": "t-1",
          "provenance": "rea-eye", "observed_at": time.time() - 400}
    with pytest.raises(RegistryError, match="EVIDENCE_STALE"):
        gateway.check_evidence(ev)


# M4: lease bi chiem (revoke/busy) giua chung -> read that bai
def test_m4_revoked_lease_rejected(tmp_path):
    from miro.browser.lease_store import tab_resource
    page = FakePage("https://example.com/a", account="user-1")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)
    session.runtime.store.acquire(
        tab_resource("inst-1", page.target_id), "ke-khac")
    with pytest.raises(RegistryError):
        asyncio.run(gateway.read_via_eye(
            session, platform_id="demo", url="https://example.com/a",
            caller="t", eye_fn=video_eye))


# M5: wrong-tab evidence khong dung cho tab khac
def test_m5_wrong_tab_evidence_rejected():
    ev = {"url": "https://example.com/a", "tab_id": "tab-A",
          "provenance": "rea-eye", "observed_at": time.time()}
    with pytest.raises(RegistryError, match="TAB_MISMATCH"):
        gateway.check_evidence(ev, tab_id="tab-B")


# M6: media failure -> task that bai sach, giu browser evidence
def test_m6_media_failure_clean(tmp_path):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)

    def fail(url):
        raise RuntimeError("ANALYSIS_FAILED: engine hong")

    res = asyncio.run(multimodal.run_multimodal_task(
        session, platform_id="demo", url="https://example.com/a",
        caller="agent-e2e", eye_fn=video_eye, analyze_fn=fail))
    assert res["ok"] is False
    assert "ANALYSIS_FAILED" in res["error"]
    assert res["browser_evidence"]["provenance"] == "rea-eye"
    assert res["media"] is None


# M7: spoofing cross-boundary (media URL khac eye URL) -> tu choi
def test_m7_cross_boundary_spoofing_rejected():
    eye = {"url": "https://example.com/a", "tab_id": "t-1",
           "provenance": "rea-eye", "observed_at": time.time()}
    with pytest.raises(RegistryError, match="CROSS_BOUNDARY_SPOOF"):
        multimodal.verify_media_url_against_eye(
            eye, "https://evil.example.net/b")


# M8: timeout phan tich -> loi gon, khong treo
def test_m8_analyze_timeout_surfaced(tmp_path):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)

    def slow(url):
        raise TimeoutError("ANALYSIS_TIMEOUT sau 1s")

    res = asyncio.run(multimodal.run_multimodal_task(
        session, platform_id="demo", url="https://example.com/a",
        caller="agent-e2e", eye_fn=video_eye, analyze_fn=slow))
    assert res["ok"] is False
    assert "TIMEOUT" in res["error"]


# M9: media-analysis KHONG bao gio la Evidence ghi
def test_m9_media_result_not_write_evidence():
    fake_media = {"provenance": "media-analysis",
                  "file_sha256": "abc", "url": "https://example.com/a"}
    with pytest.raises(RegistryError, match="media-analysis"):
        gateway.check_evidence(fake_media)


# M11: ephemeral cleanup — temp bi xoa ca khi thanh cong
def test_m11_ephemeral_temp_cleaned(tmp_path, monkeypatch):
    from miro.research import media_provider
    import shutil
    import tempfile

    created: list[str] = []
    real_mkdtemp = tempfile.TemporaryDirectory

    class SpyTmp(real_mkdtemp):
        def __enter__(self):
            p = super().__enter__()
            created.append(p)
            return p

    monkeypatch.setattr(tempfile, "TemporaryDirectory", SpyTmp)
    monkeypatch.setattr(
        media_provider, "fetch_metadata",
        lambda url, timeout=60: {"title": "t", "duration": 5.0,
                                 "uploader": "u", "url": url})

    def fake_download(url, work_dir, **kw):
        dest = Path(work_dir) / "src.mp4"
        shutil.copyfile(FIXTURE, dest)
        return dest

    monkeypatch.setattr(media_provider, "download_to_temp", fake_download)
    res = media_provider.analyze_ephemeral("https://example.com/v/1")
    assert res["frames_analyzed"] is True
    assert res["analysis"]["provenance"] == "media-analysis"
    assert created and not Path(created[0]).exists()


# M12: batch ephemral — loi 1 video khong dung loat, temp van sach
def test_m12_batch_ephemeral_partial(tmp_path, monkeypatch):
    from miro.research import media_provider
    import shutil
    leftovers_before = set(Path(tempfile.gettempdir()).glob("mi-ephem-*"))
    monkeypatch.setattr(
        media_provider, "fetch_metadata",
        lambda url, timeout=60: {"title": "t", "duration": 5.0,
                                 "uploader": "u", "url": url})

    def fake_download(url, work_dir, **kw):
        if "bad" in url:
            raise RuntimeError("DOWNLOAD_FAILED: 404")
        dest = Path(work_dir) / "src.mp4"
        shutil.copyfile(FIXTURE, dest)
        return dest

    monkeypatch.setattr(media_provider, "download_to_temp", fake_download)
    res = media_provider.analyze_batch(
        ["https://example.com/v/1", "https://example.com/bad"])
    assert res[0].get("frames_analyzed") is True
    assert "error" in res[1]
    leftovers_after = set(Path(tempfile.gettempdir()).glob("mi-ephem-*"))
    assert leftovers_after <= leftovers_before


# M13: verdict tieng Trung nguyen ven den Agent (UTF-8, khong hong)
def test_m13_verdict_utf8_intact(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)
    res = asyncio.run(multimodal.run_multimodal_task(
        session, platform_id="demo", url="https://example.com/a",
        caller="agent-e2e", eye_fn=video_eye,
        analyze_fn=native_on_fixture))
    assert res["ok"] is True
    assert "\ufffd" not in res["agent_text"]
    assert "代码" in res["agent_text"] or "code_render" in res["agent_text"]
    assert res["analysis_wall_clock_s"] >= 0
    assert res["video_duration_s"] == 4.0


# M10: batch tuan tu — url thu 2 sai destination thi bi chan, loat van chay
def test_m10_batch_spoof_one_blocked(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)
    res = asyncio.run(multimodal.run_multimodal_batch(
        session, platform_id="demo",
        urls=["https://example.com/a", "https://evil.example.net/b"],
        caller="agent-batch", eye_fn=video_eye,
        analyze_fn=native_on_fixture))
    assert res[0]["ok"] is True
    assert res[1]["ok"] is False
