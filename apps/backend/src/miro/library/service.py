"""LibraryService — nhap asset, dedupe sha256, tag/collection, relink, xoa an toan, truy 2 chieu."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .store import LibraryStore

CHUNK = 1024 * 1024


def sha256_file(path: str | Path, fs=(open, os.path.getsize)) -> tuple[str, int]:
    opener, sizer = fs
    h = hashlib.sha256()
    size = 0
    with opener(str(path), "rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)
    try:
        disk_size = sizer(str(path))
        size = max(size, disk_size) if isinstance(disk_size, int) else size
    except OSError:
        pass
    return h.hexdigest(), size


class LibraryService:
    """Nghiep vu thu vien asset. `fs_root` gioi han relink quet trong thu muc cho phep."""

    def __init__(self, store: LibraryStore, fs_root: str | Path | None = None):
        self.store = store
        self.fs_root = Path(fs_root) if fs_root else None

    @staticmethod
    def _asset_id(sha: str) -> str:
        return f"asset-{sha[:16]}"

    @staticmethod
    def _kind_for(suffix: str) -> str:
        s = suffix.lower()
        if s in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
            return "video"
        if s in {".mp3", ".wav", ".ogg", ".m4a", ".flac"}:
            return "audio"
        if s in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            return "image"
        if s in {".srt", ".vtt", ".ass"}:
            return "subtitle"
        return "file"

    # ---- nhap + dedupe ----
    def import_asset(self, path: str | Path, name: str = "", kind: str = "",
                     tags: list[str] | None = None) -> dict:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"khong tim thay file nguon: {path}")
        sha, size = sha256_file(p)
        existing = self.store.get_by_sha(sha)
        if existing is not None:
            merged = sorted(set(existing["tags"]) | set(tags or []))
            if merged != existing["tags"] or existing.get("missing"):
                existing["tags"] = merged
                existing["missing"] = False
                self.store.upsert_asset(existing)
            return {**existing, "duplicate": True}
        asset = {
            "id": self._asset_id(sha), "sha256": sha, "path": str(p),
            "name": name or p.name, "kind": kind or self._kind_for(p.suffix),
            "size": size, "tags": list(tags or []), "collections": [],
            "archived": False, "missing": False,
        }
        self.store.upsert_asset(asset)
        return {**asset, "duplicate": False}

    # ---- tag / bo suu tap ----
    def tag(self, asset_id: str, tags: list[str]) -> dict:
        asset = self._require(asset_id)
        asset["tags"] = sorted(set(asset["tags"]) | set(tags))
        self.store.upsert_asset(asset)
        return asset

    def untag(self, asset_id: str, tags: list[str]) -> dict:
        asset = self._require(asset_id)
        drop = set(tags)
        asset["tags"] = [t for t in asset["tags"] if t not in drop]
        self.store.upsert_asset(asset)
        return asset

    def create_collection(self, col_id: str, name: str) -> dict:
        existing = self.store.get_collection(col_id)
        asset_ids = existing["asset_ids"] if existing else []
        self.store.save_collection(col_id, name, asset_ids)
        return {"id": col_id, "name": name, "asset_ids": asset_ids}

    def add_to_collection(self, col_id: str, asset_id: str) -> dict:
        self._require(asset_id)
        col = self.store.get_collection(col_id) or {"id": col_id, "name": col_id, "asset_ids": []}
        if asset_id not in col["asset_ids"]:
            col["asset_ids"].append(asset_id)
            self.store.save_collection(col["id"], col["name"], col["asset_ids"])
        asset = self._require(asset_id)
        if col_id not in asset["collections"]:
            asset["collections"].append(col_id)
            self.store.upsert_asset(asset)
        return col

    # ---- relink file di chuyen ----
    def mark_missing(self) -> list[dict]:
        missing = []
        for asset in self.store.list_assets(include_archived=True):
            if not Path(asset["path"]).is_file():
                asset["missing"] = True
                self.store.upsert_asset(asset)
                missing.append(asset)
        return missing

    def relink(self, asset_id: str, new_path: str | Path) -> dict:
        asset = self._require(asset_id)
        sha, size = sha256_file(new_path)
        if sha != asset["sha256"]:
            raise ValueError(f"hash khong khop khi relink {asset_id}: file khac noi dung goc")
        asset.update(path=str(Path(new_path)), size=size, missing=False)
        self.store.upsert_asset(asset)
        return asset

    def relink_scan(self, search_dirs: list[str | Path] | None = None) -> list[dict]:
        roots = [Path(d) for d in (search_dirs or ([self.fs_root] if self.fs_root else []))]
        index: dict[str, Path] = {}
        for root in roots:
            if not root.is_dir():
                continue
            for file in root.rglob("*"):
                if file.is_file():
                    index.setdefault(file.name.lower(), file)
        relinked = []
        for asset in self.store.list_assets(include_archived=True):
            if not asset.get("missing") and Path(asset["path"]).is_file():
                continue
            candidate = index.get(Path(asset["path"]).name.lower())
            if candidate is None and self.fs_root:
                guess = self.fs_root / Path(asset["path"]).name
                candidate = guess if guess.is_file() else None
            if candidate is None:
                continue
            try:
                relinked.append(self.relink(asset["id"], candidate))
            except ValueError:
                continue
        return relinked

    # ---- luu tru / xoa an toan ----
    def archive(self, asset_id: str) -> dict:
        asset = self._require(asset_id)
        asset["archived"] = True
        self.store.upsert_asset(asset)
        return asset

    def delete_safety_report(self, asset_id: str) -> dict:
        asset = self._require(asset_id)
        renders = self.store.renders_for_asset(asset_id)
        posts = self.store.posts_for_asset(asset_id)
        projects = sorted({r["project_id"] for r in renders if r.get("project_id")})
        return {"asset_id": asset_id, "projects": projects, "renders": renders,
                "posts": posts, "blocked": bool(renders or posts)}

    def delete(self, asset_id: str, force: bool = False) -> dict:
        report = self.delete_safety_report(asset_id)
        if report["blocked"] and not force:
            raise ValueError(
                f"{asset_id} dang duoc dung boi {len(report['renders'])} render / "
                f"{len(report['posts'])} bai dang (project: {', '.join(report['projects']) or '?'}). "
                "Can force=True de xoa."
            )
        self.store.delete_asset(asset_id)
        return {"deleted": asset_id, **report}

    # ---- quan he su dung ----
    def link_usage(self, asset_id: str, render_id: str, project_id: str = "") -> None:
        self._require(asset_id)
        self.store.link_render(asset_id, render_id, project_id)

    def link_publication(self, render_id: str, publication_id: str,
                         platform: str = "", url: str = "") -> None:
        self.store.link_post(render_id, publication_id, platform, url)

    # ---- truy 2 chieu asset <-> render <-> bai dang ----
    def trace_asset(self, asset_id: str) -> dict:
        self._require(asset_id)
        renders = self.store.renders_for_asset(asset_id)
        posts = self.store.posts_for_asset(asset_id)
        return {"asset_id": asset_id, "renders": renders, "posts": posts}

    def trace_render(self, render_id: str) -> dict:
        asset_ids = self.store.assets_for_render(render_id)
        posts = self.store.posts_for_render(render_id)
        return {"render_id": render_id, "asset_ids": asset_ids, "posts": posts}

    def trace_post(self, publication_id: str) -> dict:
        asset_ids: list[str] = []
        render_ids: list[str] = []
        for asset in self.store.list_assets(include_archived=True):
            for post in self.store.posts_for_asset(asset["id"]):
                if post["publication_id"] == publication_id:
                    if asset["id"] not in asset_ids:
                        asset_ids.append(asset["id"])
        return {"publication_id": publication_id, "asset_ids": asset_ids, "render_ids": render_ids}

    def _require(self, asset_id: str) -> dict:
        asset = self.store.get_by_id(asset_id)
        if asset is None:
            raise KeyError(f"khong tim thay asset: {asset_id}")
        return asset

    # ---- W0: auto-tag tu ket qua media_intel ----
    def auto_tag_from_analysis(self, asset_id: str, analysis: dict) -> dict:
        """Gan tag `mi:*` tu ket qua media_intel (label/provenance/tempo).

        Khong doan: label nao uncertain van tag kem `:uncertain`.
        Khong xoa tag tay co san.
        """
        asset = self._require(asset_id)
        tags: set[str] = set()
        data = analysis or {}
        bd = data.get("breakdown") if isinstance(
            data.get("breakdown"), dict) else {}
        bd_shots = bd.get("shots") if isinstance(
            bd.get("shots"), list) else []
        shots = data.get("shots") or bd_shots or []
        for shot in shots:
            det = shot.get("deterministic") or {}
            probs = det.get("probs") or {}
            if probs:
                top_label = max(probs.items(), key=lambda kv: kv[1])[0]
                label = str(top_label).strip()
            else:
                label = str(shot.get("label") or "").strip()
            if label:
                tags.add(f"mi:{label}")
                if shot.get("uncertain"):
                    tags.add(f"mi:{label}:uncertain")
        summary = bd.get("summary") if isinstance(
            bd.get("summary"), dict) else {}
        for mix in summary.get("production_mix") or []:
            mix_label = str(mix.get("label") or "").strip()
            if mix_label:
                tags.add(f"mi:{mix_label}")
        audio = data.get("audio") or {}
        if audio.get("has_audio") or data.get("evidence") in (
                "audio_analyzed", "multimodal_analyzed"):
            tags.add("mi:has-audio")
            if audio.get("tempo_bpm"):
                tags.add(f"mi:tempo-{int(round(float(audio['tempo_bpm'])))}")
        if data.get("subtitles"):
            tags.add("mi:has-subtitles")
        if data.get("provider") == "rea-video":
            tags.add("mi:rea-video")
        tags.add("mi:analyzed")
        return self.tag(asset_id, sorted(tags))
