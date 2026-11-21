"""Research endpoints with a mock provider — no network."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from miro.main import app  # noqa: E402
from miro.permissions.store import PermissionStore  # noqa: E402
from miro.storage.db import TaskStore  # noqa: E402
from miro.tasks.service import FakeRemote, TaskService  # noqa: E402


class FakeProvider:
    def search(self, query, limit):
        return [{"title": f"Kết quả {i} cho {query}",
                 "url": f"https://example.com/v{i}",
                 "snippet": "snippet"} for i in range(1, limit + 1)]

    def read_url(self, url):
        return {"title": "Trang mẫu", "text": "Nội dung mẫu" * 10, "url": url}

    def channel_videos(self, channel_url, max_videos):
        videos = [{"url": f"https://example.com/v{i}", "title": f"Video {i}",
                   "play_count": i * 100, "frames_analyzed": i == 1}
                  for i in range(1, max_videos + 1)]
        return {"profile": {"unique_id": "demo"}, "videos": videos}

    def video_detail(self, url, include_frames):
        return {"url": url, "metadata": {"title": "Video mẫu", "play_count": 123,
                                         "digg_count": 10, "comment_count": 2,
                                         "duration": 60},
                "frames_analyzed": include_frames}


def _client(tmp_path=None):
    app.state.research_provider = FakeProvider()
    if tmp_path is not None:
        app.state.task_service = TaskService(
            TaskStore(tmp_path / "tasks.db"), PermissionStore(), FakeRemote())
        app.state.run_task = lambda coro: coro.close()
    return TestClient(app)


def test_search_returns_sources_and_timestamp():
    r = _client().post("/research/search", json={"query": "maoziqi", "limit": 3})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 3
    assert body["sources"] and body["fetched_at"]


def test_read_channel_video_compare_evidence_levels():
    c = _client()
    assert c.post("/research/read", json={"url": "https://example.com/a"}).json()["sources"] == [
        "https://example.com/a"]
    ch = c.post("/research/channel",
                json={"channel_url": "https://tiktok.com/@demo", "max_videos": 2}).json()
    assert ch["evidence"] == "metadata_only"  # 1/2 video có frame
    v_meta = c.post("/research/video",
                    json={"url": "https://example.com/a"}).json()
    assert v_meta["evidence"] == "metadata_only"
    v_frames = c.post("/research/video",
                      json={"url": "https://example.com/a", "include_frames": True}).json()
    assert v_frames["evidence"] == "frames_analyzed"
    cmp = c.post("/research/compare",
                 json={"url_a": "https://example.com/a",
                       "url_b": "https://example.com/b",
                       "include_frames": True}).json()
    assert cmp["sources"] == ["https://example.com/a", "https://example.com/b"]
    assert cmp["evidence"] == "frames_analyzed"
    assert cmp["items"][0]["delta"]["play_count"] == [123, 123]


def test_to_project_creates_task(tmp_path):
    r = _client(tmp_path).post("/research/to-project", json={
        "request_id": "rs-1", "title": "Dựng thử",
        "source_url": "https://example.com/v1"})
    assert r.status_code == 202, r.text
    assert r.json()["request_id"] == "rs-1"
