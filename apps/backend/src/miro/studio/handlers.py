"""Port of C:\\dubtool\\app.py handlers (8 tabs) to Miro.

Principles:
- Every mutating/render call takes (request_id, expected_revision).
- Same request_id -> same render_id (IdempotentStore), no duplicate work.
- LLM off -> local_rules fallback always works; no GPU needed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .local_rules import duration_after, empty_plan, keep_ranges, local_plan
from .store import IdempotentStore


def _handoff_signature(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


class StudioHandlers:
    def __init__(self, root: str | Path = "C:/Miro/var/studio",
                 store: IdempotentStore | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = store or IdempotentStore()
        self._projects: dict[str, dict] = {}

    # ---- helpers ----
    def _project(self, video_id: str) -> dict:
        return self._projects.setdefault(video_id, {
            "video_id": video_id, "revision": 0, "title": video_id,
            "segments": [], "overlays": [], "plan": None,
            "output": None, "render_done": False,
        })

    def _guard_revision(self, video_id: str, expected_revision) -> dict:
        project = self._project(video_id)
        current = self.store.check_revision(video_id, expected_revision)
        project["revision"] = current
        return project

    def _run_idempotent(self, request_id: str, payload: dict, work) -> dict:
        cached = self.store.get(request_id)
        if cached is not None:
            cached = dict(cached)
            cached["idempotent_replay"] = True
            return cached
        result = work()
        result.setdefault("signature", _handoff_signature(payload))
        result["idempotent_replay"] = False
        return self.store.put(request_id, result)

    # ---- Tab 1: Nhap (do_download / do_run_to_translate) ----
    def do_download(self, source: str, request_id: str,
                    expected_revision=None, src_lang: str = "auto") -> dict:
        if not (source or "").strip():
            raise ValueError("Hay nhap URL hoac chon file video.")
        video_id = hashlib.sha256(source.strip().encode()).hexdigest()[:16]
        self._guard_revision(video_id, expected_revision)

        def work():
            project = self._project(video_id)
            project.update(title=source.strip()[:120])
            project["revision"] = self.store.bump_revision(video_id)
            marker = self.root / f"{video_id}.download.json"
            marker.write_text(json.dumps({"video_id": video_id, "source": source},
                                         ensure_ascii=False), encoding="utf-8")
            return {"video_id": video_id, "revision": project["revision"],
                    "message": f"Da tai xong. Ma video: {video_id}",
                    "output": str(marker)}

        return self._run_idempotent(
            request_id, {"op": "do_download", "source": source}, work)

    def translate(self, video_id: str, request_id: str, expected_revision=None,
                  src_lang: str = "auto", tgt_lang: str = "vi") -> dict:
        project = self._guard_revision(video_id, expected_revision)

        def work():
            segments = project.get("segments") or [
                {"id": 1, "start": 0.0, "end": 2.5,
                 "src_text": "Hello world", "tgt_text": "", "flags": []},
                {"id": 2, "start": 2.5, "end": 5.0,
                 "src_text": "Welcome back", "tgt_text": "", "flags": []},
            ]
            for seg in segments:
                if not seg.get("tgt_text"):
                    seg["tgt_text"] = f"[{tgt_lang}] {seg['src_text']}"
                    seg.setdefault("flags", []).append("local_glossary")
            project["segments"] = segments
            project["revision"] = self.store.bump_revision(video_id)
            return {"video_id": video_id, "revision": project["revision"],
                    "segments": segments, "message": f"Xong dich: {len(segments)} cau."}

        return self._run_idempotent(
            request_id, {"op": "translate", "video_id": video_id,
                         "src": src_lang, "tgt": tgt_lang}, work)

    # ---- Tab 2: Phu de (load/save + tts_mix_render) ----
    def load_segments(self, video_id: str) -> list:
        return list(self._project(video_id).get("segments", []))

    def save_segments(self, video_id: str, rows: list, request_id: str,
                      expected_revision=None) -> dict:
        project = self._guard_revision(video_id, expected_revision)

        def work():
            segments = project.get("segments", [])
            for row, seg in zip(rows, segments):
                seg["tgt_text"] = str(row[4] if len(row) > 4 else "").strip()
            project["render_done"] = False
            project["revision"] = self.store.bump_revision(video_id)
            return {"video_id": video_id, "revision": project["revision"],
                    "message": "Da luu phu de. Cac buoc sau dich se chay lai."}

        return self._run_idempotent(
            request_id, {"op": "save_segments", "video_id": video_id,
                         "rows": rows}, work)

    def tts_mix_render(self, video_id: str, request_id: str,
                       expected_revision=None) -> dict:
        project = self._guard_revision(video_id, expected_revision)

        def work():
            out = self.root / f"{video_id}_dub.mp4"
            out.write_text(f"FAKE-DUB {video_id}", encoding="utf-8")
            project.update(output=str(out), render_done=True)
            project["revision"] = self.store.bump_revision(video_id)
            return {"video_id": video_id, "revision": project["revision"],
                    "output": str(out), "message": f"Hoan tat! File: {out}"}

        return self._run_idempotent(
            request_id, {"op": "tts_mix_render", "video_id": video_id}, work)

    # ---- Tab 3: Giong (revoice) ----
    def revoice(self, video_id: str, seg_id: int, voice: str, request_id: str,
                expected_revision=None) -> dict:
        project = self._guard_revision(video_id, expected_revision)

        def work():
            found = [s for s in project.get("segments", []) if s.get("id") == seg_id]
            if not found and project.get("segments"):
                raise ValueError(f"Khong tim thay cau {seg_id}.")
            project["revision"] = self.store.bump_revision(video_id)
            return {"video_id": video_id, "revision": project["revision"],
                    "message": f"Da tao lai giong cho cau {seg_id} ({voice}) va render lai."}

        return self._run_idempotent(
            request_id, {"op": "revoice", "video_id": video_id,
                         "seg_id": seg_id, "voice": voice}, work)

    # ---- Tab 4: Hinh (preview_frame / add_overlay) ----
    def preview_frame(self, video_id: str, request_id: str, overlay: dict,
                      expected_revision=None) -> dict:
        self._guard_revision(video_id, expected_revision)

        def work():
            out = self.root / f"{video_id}_preview.mp4"
            out.write_text(f"FAKE-PREVIEW {overlay.get('type')}", encoding="utf-8")
            return {"video_id": video_id, "output": str(out),
                    "message": "Xem thu 5 giay."}

        return self._run_idempotent(
            request_id, {"op": "preview_frame", "video_id": video_id,
                         "overlay": overlay}, work)

    def add_overlay(self, video_id: str, overlay: dict, request_id: str,
                    expected_revision=None) -> dict:
        project = self._guard_revision(video_id, expected_revision)

        def work():
            project.setdefault("overlays", []).append(overlay)
            project["render_done"] = False
            project["revision"] = self.store.bump_revision(video_id)
            return {"video_id": video_id, "revision": project["revision"],
                    "overlays": len(project["overlays"]),
                    "message": f"Da them overlay ({len(project['overlays'])} overlay)."}

        return self._run_idempotent(
            request_id, {"op": "add_overlay", "video_id": video_id,
                         "overlay": overlay}, work)

    # ---- Tab 5: Xuat (do_final_render) ----
    def do_final_render(self, video_id: str, request_id: str,
                        expected_revision=None, burn_subtitles: bool = False,
                        overlays: list | None = None) -> dict:
        project = self._guard_revision(video_id, expected_revision)

        def work():
            if overlays is not None:
                project["overlays"] = overlays
            out = self.root / f"{video_id}_final.mp4"
            out.write_text(
                f"FAKE-FINAL burn={burn_subtitles} overlays={len(project.get('overlays', []))}",
                encoding="utf-8")
            project.update(output=str(out), render_done=True)
            project["revision"] = self.store.bump_revision(video_id)
            return {"video_id": video_id, "revision": project["revision"],
                    "output": str(out), "message": f"Hoan tat! File: {out}"}

        return self._run_idempotent(
            request_id, {"op": "do_final_render", "video_id": video_id,
                         "burn": burn_subtitles, "overlays": overlays or []}, work)

    # ---- Tab 6: AI Editor (plan / render / restore) ----
    def editor_plan(self, video_id: str, instruction: str, request_id: str,
                    expected_revision=None, previous: dict | None = None,
                    use_ai: bool = False) -> dict:
        project = self._guard_revision(video_id, expected_revision)
        _ = use_ai  # LLM off -> local fallback (never fails for missing key)

        def work():
            duration = 60.0
            base = previous or project.get("plan") or empty_plan(video_id, duration)
            base = dict(base)
            base["source_id"] = video_id
            base["duration"] = duration
            plan, method = local_plan(
                base, instruction, segments=project.get("segments", []))
            project["plan"] = plan
            project["revision"] = self.store.bump_revision(video_id)
            kept = keep_ranges(plan)
            return {"video_id": video_id, "revision": project["revision"],
                    "method": method, "plan": plan,
                    "duration_after": duration_after(kept),
                    "notes": plan.get("notes", [])}

        return self._run_idempotent(
            request_id, {"op": "editor_plan", "video_id": video_id,
                         "instruction": instruction}, work)

    def editor_render(self, video_id: str, plan: dict, request_id: str,
                      expected_revision=None, preview: bool = True) -> dict:
        self._guard_revision(video_id, expected_revision)

        def work():
            kept = keep_ranges(plan)
            name = f"{video_id}_{'preview' if preview else 'final'}.mp4"
            out = self.root / name
            out.write_text(f"FAKE-EDIT preview={preview} dur={duration_after(kept)}",
                           encoding="utf-8")
            project = self._project(video_id)
            if not preview:
                project.update(output=str(out), render_done=True)
                project["revision"] = self.store.bump_revision(video_id)
            return {"video_id": video_id, "output": str(out),
                    "duration": duration_after(kept), "preview": preview,
                    "notes": plan.get("notes", [])}

        return self._run_idempotent(
            request_id, {"op": "editor_render", "video_id": video_id,
                         "plan": plan, "preview": preview}, work)

    def editor_restore(self, video_id: str, request_id: str,
                       expected_revision=None) -> dict:
        project = self._guard_revision(video_id, expected_revision)

        def work():
            plan = empty_plan(video_id, 60.0)
            project.update(plan=plan, render_done=False)
            project["revision"] = self.store.bump_revision(video_id)
            return {"video_id": video_id, "revision": project["revision"],
                    "plan": plan, "message": "Da khoi phuc ban truoc edit."}

        return self._run_idempotent(
            request_id, {"op": "editor_restore", "video_id": video_id}, work)

    # ---- Tab 7: YouTube (submit draft) ----
    def submit_studio(self, video_id: str, title: str, description: str,
                      tags: str, request_id: str,
                      expected_revision=None) -> dict:
        project = self._guard_revision(video_id, expected_revision)

        def work():
            if not project.get("render_done"):
                error = ValueError("Render ban cuoi truoc khi dua sang YouTube.")
                error.status_code = 409
                raise error
            production_id = f"prod-{_handoff_signature({'v': video_id, 't': title})}"
            return {"video_id": video_id, "production_id": production_id,
                    "message": f"Da dua vao hang cho: {production_id}. "
                               "Mo YouTube Studio de duyet. Chua tai len YouTube.",
                    "title": title[:100], "description": description, "tags": tags}

        return self._run_idempotent(
            request_id, {"op": "submit_studio", "video_id": video_id,
                         "title": title}, work)

    # ---- Tab 8: Timeline nhieu clip ----
    def open_multitrack(self, video_id: str, request_id: str,
                        expected_revision=None) -> dict:
        project = self._guard_revision(video_id, expected_revision)

        def work():
            if not project.get("render_done"):
                error = ValueError("Render ban long tieng truoc khi chuyen sang timeline.")
                error.status_code = 409
                raise error
            timeline_id = f"studio-{video_id[:24]}"
            return {"video_id": video_id, "timeline_id": timeline_id,
                    "url": f"/timeline?project={timeline_id}",
                    "message": "Mo ban long tieng trong Timeline nhieu clip."}

        return self._run_idempotent(
            request_id, {"op": "open_multitrack", "video_id": video_id}, work)
