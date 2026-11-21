# -*- coding: utf-8 -*-
"""Studio handlers chay pipeline THAT (port A: C:\\dubtool\\app.py vao kien truc C).

Moi method chay pipeline that hoac service that (download/transcribe/
translate/tts/mix/render + cache/invalidation), giu invariant:
- A app.py: 7 diem goi (do_download, do_run_to_translate, save_segments,
  do_tts_mix_render, revoice, add_overlay, do_final_render) + submit_studio
  chi queue duyet (CAM dang luon) + create_from_dubtool/handoff.
- A invalidation: sua text -> tu tts; them overlay -> chi render.
- B (reader-jarvis §7): fingerprint + slot don/contamination lock +
  retry TRANSIENT co ngan sach (trong pipeline._guarded) + persist atomic +
  synthesize guard nguon (transcript that, khong bia) + revision moi bien.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import threading
from pathlib import Path

from .local_rules import duration_after, empty_plan, keep_ranges, local_plan
from .pipeline import LocalEngine, Pipeline, PipelineConflict, PipelineError
from .store import IdempotentStore, SlotContaminated, StudioConflict

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_MAX_RENDERS = 4  # A: studio_service._start_render hang doi toi da 4


def _handoff_signature(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def _conflict(message: str) -> ValueError:
    error = ValueError(message)
    error.status_code = 409
    return error


class StudioHandlers:
    def __init__(self, root: str | Path = "C:/Miro/var/studio",
                 store: IdempotentStore | None = None,
                 engine: LocalEngine | None = None,
                 max_renders: int = _MAX_RENDERS):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = store or IdempotentStore(persist_dir=self.root / "store")
        self.pipeline = Pipeline(root=self.root / "work", engine=engine)
        self._render_guard = threading.BoundedSemaphore(max(max_renders, 1))
        self._projects: dict[str, dict] = {}  # C-side view (plan/editor state)

    # ---- helpers ----
    def _project(self, video_id: str) -> dict:
        return self._projects.setdefault(video_id, {"video_id": video_id, "plan": None})

    def _run_idempotent(self, request_id: str, payload: dict, video_id: str,
                        expected_revision, work, render_slot: bool = False,
                        bump: bool = True) -> dict:
        """Fingerprint-first replay + slot don + revision guard + terminal persist.

        B §7.2: cung id + cung noi dung -> tra cu; cung id + khac noi dung ->
        REQUEST_ID_CONFLICT; exception la -> persist needs_attention + danh dau
        contamination (khoa pipeline moi den khi kiem tra thu cong).
        """
        if not isinstance(request_id, str) or not _REQUEST_ID_RE.match(request_id):
            raise ValueError("request_id khong hop le (1-80 ky tu [A-Za-z0-9_-]).")
        cached = self.store.check_fingerprint(request_id, payload)
        if cached is not None:
            return cached
        self.store.acquire_slot(video_id, request_id)
        render_held = False
        if render_slot:
            if not self._render_guard.acquire(blocking=False):
                self.store.release_slot(video_id, request_id)
                raise _conflict("Hang render dang day (toi da 4). Cho roi thu lai.")
            render_held = True
        try:
            self.store.check_revision(video_id, expected_revision)
            try:
                result = work()
            except ValueError:
                raise
            except PipelineError as exc:
                result = {"video_id": video_id, "status": "needs_attention",
                          "error": {"code": "PIPELINE_FAILED", "message": str(exc)},
                          "message": f"Pipeline that bai: {exc}"}
                result["revision"] = self.store.check_revision(video_id, None)
                return self.store.put(request_id, payload, result)
            except Exception as exc:  # noqa: BLE001 — la: persist + khoa
                self.store.mark_contaminated(video_id)
                result = {"video_id": video_id, "status": "needs_attention",
                          "error": {"code": type(exc).__name__, "message": str(exc)},
                          "message": "Loi chua ro; da khoa pipeline de kiem tra thu cong."}
                result["revision"] = self.store.check_revision(video_id, None)
                return self.store.put(request_id, payload, result)
            result.setdefault("signature", _handoff_signature(payload))
            result["idempotent_replay"] = False
            result["revision"] = (self.store.bump_revision(video_id) if bump
                                  else self.store.check_revision(video_id, None))
            return self.store.put(request_id, payload, result)
        finally:
            self.store.release_slot(video_id, request_id)
            if render_held:
                self._render_guard.release()

    def _source_of(self, video_id: str) -> str:
        source = self.pipeline.load_project(video_id).get("source")
        if not source:
            raise PipelineError("Chua co du lieu download cho video nay.")
        return source

    def _require_render_done(self, video_id: str) -> dict:
        proj = self.pipeline.load_project(video_id)
        output = proj.get("output")
        if not output or not Path(output).is_file():
            raise _conflict("Render ban cuoi truoc khi dua sang YouTube.")
        return proj

    # ---- Tab 1: Nhap (A app.py:42-82) ----
    def do_download(self, source: str, request_id: str,
                    expected_revision=None, src_lang: str = "auto") -> dict:
        if not (source or "").strip():
            raise ValueError("Hay nhap URL hoac chon file video.")
        source = source.strip()
        video_id = self.pipeline.resolve_video_id(source)

        def work():
            res = self.pipeline.run(source, src_lang=src_lang, steps=["download"])
            duration = self.pipeline.engine.probe_duration(res.get("output") or "") \
                if res.get("output") else self.pipeline.engine.probe_duration(
                    self.pipeline._find_video_file(res["video_id"]) or source)
            return {"video_id": res["video_id"],
                    "message": f"Da tai xong. Ma video: {res['video_id']}",
                    "duration": round(duration, 1), "steps_run": res["steps_run"]}

        return self._run_idempotent(
            request_id, {"op": "do_download", "source": source, "src": src_lang},
            video_id, expected_revision, work)

    def translate(self, video_id: str, request_id: str, expected_revision=None,
                  src_lang: str = "auto", tgt_lang: str = "vi",
                  default_voice: str | None = None) -> dict:
        def work():
            source = self._source_of(video_id)
            res = self.pipeline.run(
                source, src_lang=src_lang, tgt_lang=tgt_lang,
                default_voice=default_voice,
                steps=["download", "audio", "stt", "translate"])
            segments = res.get("segments") or []
            return {"video_id": res["video_id"], "segments": segments,
                    "message": f"Xong dich: {len(segments)} cau.",
                    "steps_run": res["steps_run"]}

        return self._run_idempotent(
            request_id, {"op": "translate", "video_id": video_id,
                         "src": src_lang, "tgt": tgt_lang,
                         "voice": default_voice},
            video_id, expected_revision, work)

    # ---- Tab 2: Phu de (A app.py:106-142; invalidate tu tts) ----
    def load_segments(self, video_id: str) -> list:
        try:
            return self.pipeline._load_segments(video_id)
        except (OSError, ValueError) as exc:
            raise _conflict(f"Chua co segments: {exc}")

    def save_segments(self, video_id: str, rows: list, request_id: str,
                      expected_revision=None) -> dict:
        def work():
            segments = self.pipeline.edit_subtitles(video_id, rows)
            return {"video_id": video_id,
                    "message": "Da luu phu de. Cac buoc sau dich se chay lai.",
                    "segments": len(segments)}

        return self._run_idempotent(
            request_id, {"op": "save_segments", "video_id": video_id, "rows": rows},
            video_id, expected_revision, work)

    def tts_mix_render(self, video_id: str, request_id: str,
                       expected_revision=None, default_voice: str | None = None) -> dict:
        def work():
            source = self._source_of(video_id)
            proj = self.pipeline.load_project(video_id)
            res = self.pipeline.run(
                source, src_lang=proj.get("src_lang", "auto"),
                tgt_lang=proj.get("tgt_lang", "vi"),
                default_voice=default_voice or proj.get("default_voice"),
                steps=["tts", "sync", "mix", "render"])
            return {"video_id": res["video_id"], "output": res.get("output"),
                    "message": f"Hoan tat! File: {res.get('output')}",
                    "steps_run": res["steps_run"]}

        return self._run_idempotent(
            request_id, {"op": "tts_mix_render", "video_id": video_id,
                         "voice": default_voice},
            video_id, expected_revision, work, render_slot=True)

    # ---- Tab 3: Giong (A app.py:154-167; revoice_segment xoa tts->render) ----
    def revoice(self, video_id: str, seg_id: int, voice: str, request_id: str,
                expected_revision=None) -> dict:
        try:
            seg_id = int(str(seg_id).strip())
        except (TypeError, ValueError):
            raise ValueError("So cau phai la so nguyen.")

        def work():
            res = self.pipeline.revoice_segment(video_id, seg_id, new_voice=voice)
            return {"video_id": res["video_id"], "output": res.get("output"),
                    "message": f"Da tao lai giong cho cau {seg_id} ({voice}) va render lai.",
                    "steps_run": res["steps_run"]}

        return self._run_idempotent(
            request_id, {"op": "revoice", "video_id": video_id,
                         "seg_id": seg_id, "voice": voice},
            video_id, expected_revision, work, render_slot=True)

    # ---- Tab 4: Hinh (A app.py:171-209; overlay chi invalidate render) ----
    def preview_frame(self, video_id: str, request_id: str, overlay: dict,
                      expected_revision=None, t: float = 5.0) -> dict:
        def work():
            proj = self._require_render_done(video_id)
            src = proj["output"]
            out = self.root / "work" / "temp" / f"{video_id}_preview.mp4"
            out.parent.mkdir(parents=True, exist_ok=True)
            vf = "scale=480:-1"
            if isinstance(overlay, dict) and overlay.get("type") == "box":
                x, y, w, h = (float(overlay.get(k, 0)) for k in ("x", "y", "w", "h"))
                vf += (f",drawbox=x='iw*{x}':y='ih*{y}':w='iw*{w}':h='ih*{h}'"
                       ":color=black@0.6:t=fill")
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise PipelineError("FFMPEG_MISSING: khong preview duoc.")
            result = subprocess.run(
                [ffmpeg, "-y", "-v", "error", "-ss", str(max(0.0, t)),
                 "-i", str(src), "-t", "5", "-vf", vf,
                 "-c:v", "libx264", "-preset", "veryfast", "-an", str(out)],
                capture_output=True, text=True, timeout=300)
            if result.returncode or not out.is_file():
                raise PipelineError(f"PREVIEW_FAILED: {result.stderr[-300:]}")
            return {"video_id": video_id, "output": str(out),
                    "message": "Xem thu 5 giay."}

        return self._run_idempotent(
            request_id, {"op": "preview_frame", "video_id": video_id,
                         "overlay": overlay, "t": t},
            video_id, expected_revision, work, bump=False)

    def add_overlay(self, video_id: str, overlay: dict, request_id: str,
                    expected_revision=None) -> dict:
        if not isinstance(overlay, dict) or overlay.get("type") not in (
                "blur", "box", "text", "logo"):
            raise ValueError("overlay can type blur/box/text/logo.")

        def work():
            count = self.pipeline.add_overlay(video_id, overlay)
            return {"video_id": video_id, "overlays": count,
                    "message": f"Da them overlay ({count} overlay)."}

        return self._run_idempotent(
            request_id, {"op": "add_overlay", "video_id": video_id,
                         "overlay": overlay},
            video_id, expected_revision, work)

    # ---- Tab 5: Xuat (A app.py:212-229) ----
    def do_final_render(self, video_id: str, request_id: str,
                        expected_revision=None, burn_subtitles: bool = False,
                        overlays: list | None = None,
                        default_voice: str | None = None) -> dict:
        def work():
            source = self._source_of(video_id)
            proj = self.pipeline.load_project(video_id)
            if overlays is not None:
                proj = self.pipeline.save_project(video_id, overlays=overlays)
                marker = self.pipeline._work_dir(video_id) / "render.done"
                if marker.exists():
                    marker.unlink()
            res = self.pipeline.run(
                source, src_lang=proj.get("src_lang", "auto"),
                tgt_lang=proj.get("tgt_lang", "vi"),
                default_voice=default_voice or proj.get("default_voice"),
                steps=["tts", "sync", "mix", "render"],
                overlays=proj.get("overlays"), burn_subtitles=burn_subtitles)
            return {"video_id": res["video_id"], "output": res.get("output"),
                    "message": f"Hoan tat! File: {res.get('output')}",
                    "steps_run": res["steps_run"]}

        return self._run_idempotent(
            request_id, {"op": "do_final_render", "video_id": video_id,
                         "burn": burn_subtitles, "overlays": overlays or [],
                         "voice": default_voice},
            video_id, expected_revision, work, render_slot=True)

    # ---- Tab 6: AI Editor (local rules that; render that bang ffmpeg) ----
    def _editor_state(self, video_id: str) -> tuple[dict, Path]:
        work = self.pipeline._work_dir(video_id)
        return self._project(video_id), work / "edit_plan.json"

    def editor_plan(self, video_id: str, instruction: str, request_id: str,
                    expected_revision=None, previous: dict | None = None,
                    use_ai: bool = False) -> dict:
        if not isinstance(instruction, str) or not 1 <= len(instruction.strip()) <= 4000:
            raise ValueError("Yeu cau can 1-4000 ky tu.")

        def work():
            project, plan_file = self._editor_state(video_id)
            try:
                segments = self.pipeline._load_segments(video_id)
            except (OSError, ValueError):
                segments = []
            video_file = (self.pipeline.load_project(video_id).get("output")
                          or self.pipeline._find_video_file(video_id))
            duration = 60.0
            if video_file:
                duration = self.pipeline.engine.probe_duration(video_file) or 60.0
            base = previous or project.get("plan") or empty_plan(video_id, duration)
            base = dict(base)
            base["source_id"] = video_id
            base["duration"] = duration
            if use_ai:
                raise PipelineError(
                    "LLM chua cau hinh trong C; tat AI de dung quy tac local.")
            plan, method = local_plan(base, instruction, segments=segments)
            project["plan"] = plan
            from .pipeline import atomic_write_json
            atomic_write_json(plan_file, plan)
            kept = keep_ranges(plan)
            return {"video_id": video_id, "method": method, "plan": plan,
                    "duration_after": duration_after(kept),
                    "notes": plan.get("notes", [])}

        return self._run_idempotent(
            request_id, {"op": "editor_plan", "video_id": video_id,
                         "instruction": instruction, "use_ai": use_ai},
            video_id, expected_revision, work)

    def editor_render(self, video_id: str, plan: dict, request_id: str,
                      expected_revision=None, preview: bool = True) -> dict:
        def work():
            kept = keep_ranges(plan)
            if not kept:
                raise PipelineError("Ke hoach cat bo toan bo video.")
            proj = self.pipeline.load_project(video_id)
            video_file = proj.get("output") or self.pipeline._find_video_file(video_id)
            if not video_file or not Path(video_file).is_file():
                raise PipelineError("Chua co video nguon de dung ban edit.")
            total = 0.0
            ranges = []
            for start, end in kept:
                if preview and total >= 20.0:
                    break
                end = min(end, start + max(0.0, 20.0 - total)) if preview else end
                if end > start:
                    ranges.append((start, end))
                    total += end - start
            out_dir = self.root / "work" / ("temp" if preview else "output")
            out_dir.mkdir(parents=True, exist_ok=True)
            name = f"{video_id}_{'preview' if preview else 'final'}.mp4"
            out = out_dir / name
            self._concat_ranges(str(video_file), ranges, out)
            if not preview:
                self.pipeline.save_project(video_id, output=str(out))
            return {"video_id": video_id, "output": str(out),
                    "duration": duration_after(kept), "preview": preview,
                    "notes": plan.get("notes", [])}

        return self._run_idempotent(
            request_id, {"op": "editor_render", "video_id": video_id,
                         "plan": plan, "preview": preview},
            video_id, expected_revision, work,
            render_slot=True, bump=not preview)

    def _concat_ranges(self, source: str, ranges: list, out: Path) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise PipelineError("FFMPEG_MISSING: khong dung duoc ban edit.")
        tmpdir = out.parent / f".{out.stem}.parts"
        tmpdir.mkdir(parents=True, exist_ok=True)
        parts = []
        try:
            for i, (start, end) in enumerate(ranges):
                part = tmpdir / f"p{i:03d}.mp4"
                result = subprocess.run(
                    [ffmpeg, "-y", "-v", "error", "-ss", f"{start:.3f}",
                     "-i", source, "-t", f"{end - start:.3f}",
                     "-c:v", "libx264", "-preset", "veryfast",
                     "-c:a", "aac", str(part)],
                    capture_output=True, text=True, timeout=600)
                if result.returncode or not part.is_file():
                    raise PipelineError(f"EDIT_FAILED: {result.stderr[-300:]}")
                parts.append(part)
            lst = tmpdir / "list.txt"
            lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts),
                           encoding="utf-8")
            result = subprocess.run(
                [ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0",
                 "-i", str(lst), "-c", "copy", str(out)],
                capture_output=True, text=True, timeout=300)
            if result.returncode or not out.is_file():
                raise PipelineError(f"EDIT_CONCAT_FAILED: {result.stderr[-300:]}")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def editor_restore(self, video_id: str, request_id: str,
                       expected_revision=None) -> dict:
        def work():
            project, plan_file = self._editor_state(video_id)
            plan = empty_plan(video_id, 60.0)
            project["plan"] = plan
            from .pipeline import atomic_write_json
            atomic_write_json(plan_file, plan)
            return {"video_id": video_id, "plan": plan,
                    "message": "Da khoi phuc ban truoc edit."}

        return self._run_idempotent(
            request_id, {"op": "editor_restore", "video_id": video_id},
            video_id, expected_revision, work)

    # ---- Tab 7: YouTube (A app.py:257-266 — CHI QUEUE DUYET, CAM DANG) ----
    def submit_studio(self, video_id: str, title: str, description: str,
                      tags: str, request_id: str,
                      expected_revision=None) -> dict:
        def work():
            proj = self._require_render_done(video_id)
            production_id = f"prod-{_handoff_signature({'v': video_id, 't': title})}"
            return {"video_id": video_id, "production_id": production_id,
                    "status": "awaiting_review",
                    "message": f"Da dua vao hang cho: {production_id}. "
                               "Mo YouTube Studio de duyet. Chua tai len YouTube.",
                    "title": (title or "")[:100], "description": description,
                    "tags": tags, "output": proj.get("output")}

        return self._run_idempotent(
            request_id, {"op": "submit_studio", "video_id": video_id,
                         "title": title, "description": description,
                         "tags": tags},
            video_id, expected_revision, work, bump=False)

    # ---- Tab 8: Timeline (A studio_service.create_from_dubtool + handoff) ----
    def create_from_dubtool(self, video_id: str) -> dict:
        """Cau dub->timeline (A studio_service.py:411-447): guard + sidecar."""
        self.pipeline._check_video_id(video_id)
        proj = self.pipeline.load_project(video_id)
        output = proj.get("output")
        if proj.get("editor_pending") or not output or not Path(output).is_file():
            raise _conflict("Video dubtool co thay doi chua dung. "
                            "Render ban cuoi truoc khi chuyen sang timeline.")
        marker = self.pipeline._work_dir(video_id) / "render.done"
        if not marker.is_file():
            raise _conflict("Chua co ban render cuoi (thieu render.done).")
        try:
            segments = self.pipeline._load_segments(video_id)
        except (OSError, ValueError):
            segments = []
        timeline_id = f"studio-{video_id[:24]}"
        timeline_dir = self.root / "timelines" / timeline_id
        timeline_dir.mkdir(parents=True, exist_ok=True)
        cues = [{"id": i + 1, "start": s["start"], "end": s["end"],
                 "src_text": s.get("src_text") or "",
                 "tgt_text": s.get("tgt_text") or "",
                 "flags": s.get("flags", [])}
                for i, s in enumerate(segments)
                if s.get("end", 0) > s.get("start", 0)]
        from .pipeline import atomic_write_json
        atomic_write_json(timeline_dir / "project.json",
                          {"id": timeline_id, "title": proj.get("title") or video_id,
                           "source_video_id": video_id, "assets": {"output": output},
                           "cues": cues})
        return {"video_id": video_id, "timeline_id": timeline_id,
                "url": f"/timeline?project={timeline_id}",
                "message": "Mo ban long tieng trong Timeline nhieu clip."}

    def open_multitrack(self, video_id: str, request_id: str,
                        expected_revision=None) -> dict:
        def work():
            return self.create_from_dubtool(video_id)

        return self._run_idempotent(
            request_id, {"op": "open_multitrack", "video_id": video_id},
            video_id, expected_revision, work, bump=False)

    def handoff(self, video_id: str, title: str, description: str,
                tags, request_id: str, expected_revision=None,
                transcript: str = "", language: str = "vi") -> dict:
        """Cau timeline->duyet (A studio_service.py:449-497): verify + queue."""
        if language not in ("vi", "en", "zh"):
            raise ValueError("Ngon ngu loi thoai phai la vi, en hoac zh.")

        def work():
            proj = self._require_render_done(video_id)
            if transcript.strip():
                if len(transcript) > 50000:
                    raise ValueError("Ban loi thoai toi da 50.000 ky tu.")
            else:
                try:
                    check = self.pipeline._load_segments(video_id)
                except (OSError, ValueError):
                    check = []
                script = " ".join((s.get("tgt_text") or s.get("src_text") or "")
                                  for s in check).strip()
                if not script:
                    raise PipelineError(
                        "Chua co transcript. Nhap loi thoai that de duyet; "
                        "he thong khong tu bia kich ban.")
            try:
                segments = self.pipeline._load_segments(video_id)
            except (OSError, ValueError):
                segments = []
            work_dir = self.pipeline._work_dir(video_id)
            handoff_dir = self.root / "handoff" / video_id
            handoff_dir.mkdir(parents=True, exist_ok=True)
            from .pipeline import atomic_write_json
            seg_copy = handoff_dir / "segments.json"
            shutil.copy2(work_dir / "segments.json", seg_copy)
            manifest = {"video_id": video_id, "output": proj["output"],
                        "output_sha": Pipeline.hash_file_static(proj["output"]),
                        "segments_sha": Pipeline.hash_file_static(seg_copy),
                        "title": (title or "")[:100], "language": language,
                        "status": "awaiting_review"}
            atomic_write_json(handoff_dir / "manifest.json", manifest)
            production_id = f"prod-{_handoff_signature({'v': video_id, 't': title})}"
            return {"video_id": video_id, "production_id": production_id,
                    "status": "awaiting_review",
                    "message": f"Da dua vao hang cho: {production_id}. "
                               "Chua tai len YouTube.",
                    "manifest": str(handoff_dir / "manifest.json")}

        tag_text = ",".join(tags) if isinstance(tags, list) else (tags or "")
        return self._run_idempotent(
            request_id, {"op": "handoff", "video_id": video_id, "title": title,
                         "description": description, "tags": tag_text,
                         "language": language},
            video_id, expected_revision, work, bump=False)

    # ---- van hanh slot (B: contamination phai mo khoa thu cong) ----
    def clear_pipeline_block(self, video_id: str) -> dict:
        self.store.clear_contamination(video_id)
        return {"video_id": video_id, "contaminated": False,
                "message": "Da mo khoa pipeline sau kiem tra thu cong."}
