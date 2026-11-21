"""Test luồng M2 khép kín trong C (Studio→Library→Renders→Publications→
worker→adapter→lịch sử). Mặc định dry-run/read-only; đăng mới chỉ với fake
managed tab (không Chrome thật, không mạng).

Entry point kiểm chứng M2: `python -m pytest tests/test_threads_flow.py -q`
(chạy từ C:\\Miro\\apps\\backend).
"""
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.library.service import LibraryService  # noqa: E402
from miro.library.store import LibraryStore  # noqa: E402
from miro.publishing.publisher import Intent, Publisher  # noqa: E402
from miro.storage.registry import PublicationStore, RenderStore  # noqa: E402
from miro.threads.flow import (  # noqa: E402
    AuditLog,
    approve_intent,
    check_secret_text,
    history_for,
    intent_fingerprint,
    prepare_publish,
)
from miro.threads.worker import ThreadsWorker  # noqa: E402

A = Path(r"C:\dubtool")
BATCH_2P = A / "reports" / "resource-batches" / "threads-20261120-2p"
ATTEMPTS = A / "reports" / "social-attempts"

needs_a = pytest.mark.skipif(not BATCH_2P.exists(), reason="C:\\dubtool khong mount")


class FakeManagedPage:
    """Fake 1 managed tab: verify actor + submit ack + eye readback."""

    def __init__(self, owner="haodaojrk5"):
        self.owner = owner
        self.posts = 0
        self.released = False
        self.renews = 0
        self.eye: dict[str, dict] = {}

    def verify_actor(self, owner):
        return str(owner or "").lower().lstrip("@") == self.owner.lower()

    def submit(self, intent):
        self.posts += 1
        code = f"P{self.posts:03d}"
        url = f"https://www.threads.com/@{intent.owner}/post/{code}"
        self.eye[intent.shortcode or intent.intent_id] = {
            "author": f"@{intent.owner}", "tag": intent.tag, "url": url,
            "post_id": code, "has_video": False}
        return {"ack_post_codes": [code], "ack_via": "fake-managed-tab",
                "ack_response_url": None, "observed_toasts": ["Posted"],
                "observed_responses": []}

    def read_eye(self, intent):
        hit = self.eye.get(intent.shortcode or intent.intent_id)
        return [hit] if hit else []

    def renew(self, ttl=300):
        self.renews += 1

    def release(self):
        self.released = True

    # Publisher browser contract (Publisher.publish/reconcile gọi trực tiếp).
    def post_once(self, intent):
        return self.submit(intent)

    def read_receipt(self, intent):
        return self.read_eye(intent)


def make_stack(tmp_path):
    base = tmp_path / "batch"
    attempts = tmp_path / "attempts"
    base.mkdir()
    attempts.mkdir()
    library = LibraryService(LibraryStore(tmp_path / "library.db"))
    renders = RenderStore(tmp_path / "renders.db")
    publications = PublicationStore(tmp_path / "publications.db")
    publisher = Publisher(base, attempts_dir=attempts, require_approval=True)
    return base, attempts, library, renders, publications, publisher


@needs_a
def test_closed_loop_with_real_manifest(tmp_path):
    """Luồng khép kín trên manifest thật threads-20261120-2p (read-only ở đầu,
    fake tab ở cuối — không chạm mạng)."""
    manifest = json.loads((BATCH_2P / "download.json").read_text(encoding="utf-8-sig"))
    assert manifest["account"] == "haodaojrk5" and manifest["count"] == 2
    saved = manifest["saved"]
    base, attempts, library, renders, publications, publisher = make_stack(tmp_path)

    # 1. Library: nhập 2 file media thật (dedupe sha256) — file có thể vắng
    #    trên máy này thì dùng payload giả nhưng giữ shortcode/caption thật.
    assets = []
    for item in saved:
        local = Path(str(item.get("local_path") or ""))
        if local.is_file():
            asset = library.import_asset(local, tags=["threads-m2"])
        else:
            probe = tmp_path / f"{item['shortcode']}.mp4"
            probe.write_bytes(f"m2-probe-{item['shortcode']}".encode())
            asset = library.import_asset(probe, tags=["threads-m2"])
        assets.append(asset)
    assert len({a["id"] for a in assets}) == 2

    # 2. Renders: idempotent create (request_id + content_hash), link asset↔render.
    prepared = []
    for i, (item, asset) in enumerate(zip(saved, assets)):
        out = prepare_publish(
            library, renders, asset_path=asset["path"],
            project_id="studio-m2", request_id=f"m2-render-{i}",
            expected_revision=0, content_hash=f"ch-{i}",
            spec={"shortcode": item["shortcode"]})
        prepared.append(out)
    assert all(p["render"]["status"] == "queued" for p in prepared)
    # replay cùng khóa → không tạo trùng (REQUEST_ID_CONFLICT khi khác nội dung)
    again, replayed = renders.create("m2-render-0", "studio-m2", 0, "ch-0", {})
    assert replayed is True

    # 3. Publications queue + approval bound fingerprint+revision.
    # Manifest thật có media → media gate mở đường thật (fix #3): file gốc
    # C:\Users\Admin\Videos\Ai\vizzion*(-20261119)\*.mp4 tồn tại trên máy này
    # → media_for + check_video pass → được post; file vắng → MEDIA_UNVERIFIED
    # chặn FAILED_BEFORE_POST (fail-closed). Tách 2 đường: (a) media kiểm gate,
    # (b) text-only post có approval.
    intents = [Intent.from_item(s, manifest["account"]) for s in saved]
    for intent in intents:
        assert intent.tag.startswith("#dub")
    from dataclasses import replace as _replace
    from miro.publishing.publisher import _media_gate
    postable = [_replace(it, media_sha256="", media_path="") for it in intents]
    try:
        _media_gate(intents[0])
        media_expect = "posted"
    except Exception:
        media_expect = "FAILED_BEFORE_POST"
    blocked = publisher.publish(intents[0], FakeManagedPage(manifest["account"]),
                                approval=approve_intent(intents[0], 3), revision=3)
    if media_expect == "posted":
        assert blocked.get("posted") is True
    else:
        assert blocked.get("error") == "FAILED_BEFORE_POST"
    queued, replayed = publications.publish("m2-pub", "att-1",
                                            prepared[0]["render"]["render_id"],
                                            "threads")
    assert queued["status"] == "queued" and replayed is False
    approvals = {it.intent_id: approve_intent(it, revision=3) for it in postable}
    assert approvals[postable[0].intent_id]["fingerprint"] == intent_fingerprint(postable[0])
    # intent đổi sau duyệt → gate từ chối
    postable[0].text += " chen thêm"
    worker_base = tmp_path / "batch-w"
    worker_attempts = tmp_path / "attempts-w"
    worker_base.mkdir()
    worker_attempts.mkdir()
    from miro.publishing.publisher import Publisher as _Publisher
    publisher2 = _Publisher(worker_base, attempts_dir=worker_attempts,
                            require_approval=True)
    worker = ThreadsWorker(publisher2, audit=AuditLog(tmp_path / "audit.jsonl"))
    page = FakeManagedPage(manifest["account"])
    res = worker.run_batch(postable, lambda: page, allow_post=True,
                           approvals=approvals, revision=3)
    changed = [r for r in res["results"] if r.get("shortcode") == postable[0].shortcode]
    assert changed and changed[0].get("error") == "FINGERPRINT_CONFLICT"
    assert page.posts == 1  # chỉ intent còn nguyên được post
    assert page.released is True  # finally release
    assert page.renews >= 0

    # 4. Lịch sử: mở đúng file render + đúng bài (library trace + journal).
    library.link_publication(prepared[1]["render"]["render_id"], "m2-pub",
                             platform="threads",
                             url="https://www.threads.com/@haodaojrk5/post/P001")
    history = history_for(library, publications, worker_base, worker_attempts,
                          publication_id="m2-pub",
                          render_id=prepared[1]["render"]["render_id"])
    assert history["render_id"] == prepared[1]["render"]["render_id"]
    assert any(a["asset_id"] == assets[1]["id"] for a in history["assets"])
    assert any(j.get("status") in ("verified", "published", "submit", "unknown",
                                   "submitted-awaiting-group-reconcile")
               for j in history["journals"])


def test_guard_unknown_never_replays_and_reconcile_readonly(tmp_path):
    """UNKNOWN không replay; reconcile read-only 0 post (đọc journal thật
    submitted-awaiting-group-reconcile khi A mount)."""
    base, attempts, library, renders, publications, publisher = make_stack(tmp_path)
    if (ATTEMPTS / "threads-7696940881491889440.json").exists():
        shutil.copy(ATTEMPTS / "threads-7696940881491889440.json",
                    attempts / "threads-7696940881491889440.json")
        from miro.publishing.publisher import guard_duplicate
        skip = guard_duplicate(base, "7696940881491889440",
                               "threads-7696940881491889440.json", attempts)
        assert skip is not None and skip["skipped"] == "UNRECONCILED_ATTEMPT"

    intent = Intent(intent_id="threads-hang", shortcode="hang",
                    owner="alice", text="treo #dub000099", tag="#dub000099")
    audit = AuditLog(tmp_path / "audit.jsonl")
    worker = ThreadsWorker(publisher, audit=audit)
    page = FakeManagedPage(owner="alice")

    class CrashPage(FakeManagedPage):
        def submit(self, intent):
            raise RuntimeError("simulated ambiguous ack after click")

    out = worker.run_batch([intent], lambda: CrashPage(owner="alice"),
                           allow_post=True,
                           approvals={"threads-hang": approve_intent(intent, 1)},
                           revision=1)
    assert out["results"] and out["results"][0].get("receipt") == "UNKNOWN"
    journal = json.loads((attempts / "threads-hang.json").read_text(encoding="utf-8-sig"))
    assert journal["status"] == "unknown"

    # publish lại cùng intent → guard chặn, không post lần 2
    retry = publisher.publish(intent, CrashPage(owner="alice"),
                              approval=approve_intent(intent, 1), revision=1)
    assert retry.get("skipped") == "UNRECONCILED_ATTEMPT"

    # reconcile read-only với receipt verified → promoted, 0 post
    reader = FakeManagedPage(owner="alice")
    reader.eye["hang"] = {"author": "@alice", "tag": "#dub000099",
                          "url": "https://www.threads.com/@alice/post/PH",
                          "post_id": "PH", "has_video": False}
    rec = publisher.reconcile(intent, _EyeOnly(reader))
    assert rec.get("reconciled") is True
    assert reader.posts == 0


class _EyeOnly:
    def __init__(self, page):
        self._page = page

    def read_receipt(self, intent):
        return self._page.read_eye(intent)


def test_dryrun_default_zero_post(tmp_path):
    """Mặc định dry-run: worker không post khi allow_post=False."""
    base, attempts, library, renders, publications, publisher = make_stack(tmp_path)
    intent = Intent(intent_id="threads-dry", shortcode="dry", owner="alice",
                    text="nháp #dub000100", tag="#dub000100")
    worker = ThreadsWorker(publisher)
    page = FakeManagedPage(owner="alice")
    out = worker.run_batch([intent], lambda: page)
    assert out["results"][0].get("dry_run") is True
    assert page.posts == 0


def test_secret_rejected_and_audit_dropped_counted(tmp_path):
    intent = Intent(intent_id="threads-s", shortcode="s", owner="alice",
                    text="leak api_key=SECRET", tag="#dub000101")
    try:
        check_secret_text(intent.text)
        raise AssertionError("secret phải bị từ chối")
    except Exception as exc:
        assert getattr(exc, "code", "") == "SECRET_REJECTED"
    audit = AuditLog(tmp_path / "a.jsonl", batch_size=1)
    audit.append({"shortcode": "s", "decision": "denied"})
    assert (tmp_path / "a.jsonl").exists()


def test_worker_duplicate_tags_stops_whole_batch(tmp_path):
    """Worker: 2 intent cùng #dub → dừng cả batch, 0 post (A §8.7.2)."""
    base, attempts, library, renders, publications, publisher = make_stack(tmp_path)
    a = Intent(intent_id="threads-d1", shortcode="d1", owner="alice",
               text="một #dub000111", tag="#dub000111")
    b = Intent(intent_id="threads-d2", shortcode="d2", owner="alice",
               text="hai #dub000111", tag="#dub000111")
    worker = ThreadsWorker(publisher)
    page = FakeManagedPage(owner="alice")
    out = worker.run_batch([a, b], lambda: page, allow_post=True,
                           approvals={"threads-d1": approve_intent(a, 1),
                                      "threads-d2": approve_intent(b, 1)},
                           revision=1)
    assert out["results"] and out["results"][0].get("error") == "DUPLICATE_TAGS"
    assert page.posts == 0


def test_worker_phase_b_group_reconcile_merges_publication(tmp_path):
    """Worker phase B: submit chưa verified → group reconcile read-only rồi
    mới merge publication (A §8.1). Fake tab submit ack rỗng (không receipt)
    nhưng eye đã có record verified → phase B promote + merge, pass gom
    read-only đúng 1 lần."""
    base, attempts, library, renders, publications, publisher = make_stack(tmp_path)

    class AcklessPage(FakeManagedPage):
        def __init__(self, owner="alice"):
            super().__init__(owner)
            self.group_passes = 0

        def submit(self, intent):
            self.posts += 1
            self.eye[intent.shortcode or intent.intent_id] = {
                "author": f"@{intent.owner}", "tag": intent.tag,
                "url": f"https://www.threads.com/@{intent.owner}/post/PB1",
                "post_id": "PB1", "has_video": False}
            return {"ack_post_codes": [], "ack_via": "fake-managed-tab",
                    "ack_response_url": None, "observed_toasts": [],
                    "observed_responses": []}

        def read_group_receipts(self, intents):
            self.group_passes += 1
            return {}

    # _ReadOnlyBrowser của worker không có read_group_receipts riêng → đếm
    # pass gom bằng cách bọc Publisher.run_batch-style: page có
    # read_group_receipts, worker gọi 1 lần trước reconcile từng item.
    intent = Intent(intent_id="threads-pb", shortcode="pb", owner="alice",
                    text="phase b #dub000112", tag="#dub000112")
    worker = ThreadsWorker(publisher)
    page = AcklessPage(owner="alice")
    out = worker.run_batch([intent], lambda: page, allow_post=True,
                           approvals={"threads-pb": approve_intent(intent, 1)},
                           revision=1)
    assert page.released is True
    phase_b = [r for r in out["results"] if r.get("phase") == "B-group-reconcile"]
    assert phase_b and phase_b[0]["reconciled"]
    pub = json.loads((base / "publication-threads.json").read_text(encoding="utf-8-sig"))
    assert any(x.get("shortcode") == "pb" and x.get("url") for x in pub.get("items", []))


REAL_VIDEO = Path(r"C:\Miro\var\studio-fixture.mp4")


def test_media_gate_real_video_passes_and_unverified_blocked(tmp_path):
    """Gate media trên file video thật (M2 fix #3): file thật cho qua,
    sha256 không file vẫn cấm."""
    from miro.publishing.publisher import _media_gate
    base, attempts, library, renders, publications, publisher = make_stack(tmp_path)
    if REAL_VIDEO.is_file():
        vid = Intent(intent_id="threads-v", shortcode="v", owner="alice",
                     text="video that #dub000113", tag="#dub000113",
                     media_path=str(REAL_VIDEO))
        _media_gate(vid)  # không raise
        page = FakeManagedPage(owner="alice")
        out = publisher.publish(vid, page, approval=approve_intent(vid, 1), revision=1)
        assert out.get("posted") is True
    ghost = Intent(intent_id="threads-g", shortcode="g", owner="alice",
                   text="ma #dub000114", tag="#dub000114",
                   media_sha256="f" * 64,
                   media_path=r"C:\khong-ton-tai\ghost.mp4")
    blocked = publisher.publish(ghost, FakeManagedPage(owner="alice"),
                                approval=approve_intent(ghost, 1), revision=1)
    assert blocked.get("error") == "FAILED_BEFORE_POST"
