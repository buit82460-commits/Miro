"""Library tests with mock filesystem (tmp_path). No real media, no network."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.library.service import LibraryService
from miro.library.store import LibraryStore


def make_service(tmp_path: Path) -> LibraryService:
    store = LibraryStore(tmp_path / "library.db")
    return LibraryService(store, fs_root=tmp_path / "media")


def write_clip(path: Path, payload: bytes = b"fake-video-bytes") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_import_dedupe_by_hash(tmp_path):
    svc = make_service(tmp_path)
    first = svc.import_asset(write_clip(tmp_path / "a.mp4"), tags=["intro"])
    dup = svc.import_asset(write_clip(tmp_path / "copy" / "a-copy.mp4"), tags=["reuse"])
    assert first["duplicate"] is False
    assert dup["duplicate"] is True
    assert dup["id"] == first["id"]
    assert set(dup["tags"]) == {"intro", "reuse"}


def test_tag_and_collection(tmp_path):
    svc = make_service(tmp_path)
    asset = svc.import_asset(write_clip(tmp_path / "b.mp4"))
    svc.tag(asset["id"], ["vlog", "cat"])
    svc.create_collection("col-cat", "Meo")
    col = svc.add_to_collection("col-cat", asset["id"])
    assert asset["id"] in col["asset_ids"]
    stored = svc.store.get_by_id(asset["id"])
    assert "col-cat" in stored["collections"]


def test_relink_moved_file(tmp_path):
    svc = make_service(tmp_path)
    src = write_clip(tmp_path / "media" / "c.mp4", b"clip-c")
    asset = svc.import_asset(src)
    src.unlink()  # gia lap file bi di chuyen / xoa
    missing = svc.mark_missing()
    assert [m["id"] for m in missing] == [asset["id"]]
    moved = write_clip(tmp_path / "media" / "restored" / "c.mp4", b"clip-c")
    relinked = svc.relink_scan()
    assert [r["id"] for r in relinked] == [asset["id"]]
    assert svc.store.get_by_id(asset["id"])["path"] == str(moved)


def test_relink_rejects_different_content(tmp_path):
    svc = make_service(tmp_path)
    asset = svc.import_asset(write_clip(tmp_path / "d.mp4", b"original"))
    other = write_clip(tmp_path / "other.mp4", b"khac-hoan-toan")
    try:
        svc.relink(asset["id"], other)
        raise AssertionError("relink sai noi dung phai bi chan")
    except ValueError:
        pass


def test_delete_blocked_when_shared_then_forced(tmp_path):
    svc = make_service(tmp_path)
    asset = svc.import_asset(write_clip(tmp_path / "e.mp4"))
    svc.link_usage(asset["id"], "render-1", project_id="studio-abc")
    svc.link_publication("render-1", "pub-1", platform="threads", url="https://x/1")
    report = svc.delete_safety_report(asset["id"])
    assert report["blocked"] is True
    assert report["projects"] == ["studio-abc"]
    try:
        svc.delete(asset["id"])
        raise AssertionError("xoa khi dang dung chung phai bi chan")
    except ValueError:
        pass
    done = svc.delete(asset["id"], force=True)
    assert done["deleted"] == asset["id"]
    assert svc.store.get_by_id(asset["id"]) is None


def test_trace_asset_render_post_both_directions(tmp_path):
    svc = make_service(tmp_path)
    asset = svc.import_asset(write_clip(tmp_path / "f.mp4"))
    svc.link_usage(asset["id"], "render-9", project_id="studio-xyz")
    svc.link_publication("render-9", "pub-9", platform="youtube", url="https://yt/9")
    by_asset = svc.trace_asset(asset["id"])
    assert [r["render_id"] for r in by_asset["renders"]] == ["render-9"]
    assert [p["publication_id"] for p in by_asset["posts"]] == ["pub-9"]
    by_render = svc.trace_render("render-9")
    assert asset["id"] in by_render["asset_ids"]
    assert [p["publication_id"] for p in by_render["posts"]] == ["pub-9"]
    by_post = svc.trace_post("pub-9")
    assert asset["id"] in by_post["asset_ids"]
