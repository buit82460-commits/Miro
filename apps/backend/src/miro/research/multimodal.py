"""Multimodal Agent orchestration — noi Browser REA/Eye voi rea-video.

Luu do that trong CUNG 1 task (khong ghep log 2 lan chay rieng):
  Agent -> Browser Gateway (read_via_eye + eye collector)
      -> doi chieu URL (chong spoofing cross-boundary)
      -> Media Acquisition (tai ve temp, co quota/admission check)
      -> native rea-video (analyze_ephemeral / analyze_native)
      -> Research (summarize_for_agent) -> Agent Answer.

Bien phan tach giu nguyen:
- Browser Evidence (provenance "rea-eye"): url/tab/actor/timestamps.
- Media result (provenance "media-analysis"): chi de hieu noi dung,
  KHONG bao gio la Evidence ghi (Gateway tu choi tai runtime).

Khong Browser WRITE, khong sua Gateway/Eye/Bridge (Phien A).
Khong tao browser tool moi, khong bypass.
"""
from __future__ import annotations

import asyncio
import inspect
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from miro.browser import gateway
from miro.browser.errors import RegistryError


def verify_media_url_against_eye(eye_evidence: dict, media_url: str) -> dict:
    """Chong spoofing cross-boundary: URL dem phan tich phai cung
    destination voi URL mat vua doc. Lech -> tu choi, khong phan tich."""
    from miro.browser.runtime import _urls_same_destination

    eye_url = str((eye_evidence or {}).get("url") or "")
    media_url = str(media_url or "")
    if not eye_url or not media_url:
        raise RegistryError(
            "CROSS_BOUNDARY_SPOOF: thieu url eye hoac media de doi chieu")
    if not _urls_same_destination(eye_url, media_url):
        raise RegistryError(
            "CROSS_BOUNDARY_SPOOF: url media khac destination voi "
            f"Browser Evidence (eye={eye_url} media={media_url}); "
            "tu choi phan tich")
    return eye_evidence


def build_agent_text(analysis: dict) -> str:
    """Agent that su tieu thu ket qua phan tich.

    Uu tien summarize_for_agent (contract hien tai) khi co breakdown day du;
    neu chi co ephemeral nhe thi render tu verdict/shots/sha.
    """
    from miro import media_intel as mi

    if isinstance(analysis, dict) and isinstance(
            analysis.get("breakdown"), dict):
        try:
            return mi.summarize_for_agent(analysis)
        except Exception:
            pass
    inner = analysis.get("analysis") if isinstance(analysis, dict) else None
    if isinstance(inner, dict):
        lines = [
            f"video {analysis.get('url')}: "
            f"{inner.get('shot_count', 0)} shots, "
            f"evidence={analysis.get('evidence')}.",
            f"verdict rea-video: {inner.get('verdict')}",
            f"production_mix: {inner.get('production_mix')}",
            f"sha256: {str(inner.get('file_sha256') or '')[:16]}...",
        ]
        for shot in (inner.get("shots") or [])[:20]:
            det = shot.get("deterministic") or {}
            probs = det.get("probs") or {}
            if probs:
                top = max(probs.items(), key=lambda kv: kv[1])
                label, conf = f"{top[0]}", float(top[1])
            else:
                label, conf = str(shot.get("label", "?")), None
            c = f" {conf:.2f}" if isinstance(conf, (int, float)) else ""
            lines.append(
                f"- shot {shot.get('index')}: "
                f"{float(shot.get('start', 0) or 0):.1f}-"
                f"{float(shot.get('end', 0) or 0):.1f}s {label}{c}")
        lines.append("luu y: du lieu chi de hieu noi dung, "
                     "khong phai Evidence ghi.")
        return "\n".join(lines)
    return str(analysis)[:4000]


async def _maybe_await(fn: Callable, *args: Any) -> Any:
    res = fn(*args)
    if inspect.isawaitable(res):
        return await res
    return res


def _video_duration_s(media: Any) -> float | None:
    """Thoi luong VIDEO (giay), khac wall-clock phan tich.

    Tim theo thu tu: metadata.duration (ephemeral) -> breakdown tong
    shot end -> None (khong doan). Khong bao gio tra wall-clock.
    """
    if not isinstance(media, dict):
        return None
    meta = media.get("metadata") or {}
    try:
        dur = float(meta.get("duration") or 0)
        if dur > 0:
            return round(dur, 3)
    except (TypeError, ValueError):
        pass
    bd = media.get("breakdown") if isinstance(
        media.get("breakdown"), dict) else None
    inner = media.get("analysis") if isinstance(
        media.get("analysis"), dict) else None
    shots = None
    if isinstance(bd, dict):
        shots = bd.get("shots")
    if shots is None and isinstance(inner, dict):
        shots = inner.get("shots")
    try:
        ends = [float(s.get("end", s.get("end_time", 0)) or 0)
                for s in (shots or []) if isinstance(s, dict)]
        if ends and max(ends) > 0:
            return round(max(ends), 3)
    except (TypeError, ValueError):
        pass
    return None


async def run_multimodal_task(
    session,
    *,
    platform_id: str,
    url: str,
    caller: str,
    eye_fn: Callable,
    expected_account: str = "",
    analyze_fn: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Chay 1 nhiem vu multimodal E2E trong cung 1 luot.

    1. READ qua Gateway (read_via_eye): actor/lease/tab duoc verify.
    2. Doi chieu media URL voi eye URL (chong spoofing).
    3. Phan tich media (mac dinh analyze_ephemeral that; test co the
       inject analyze_fn chay native tren fixture).
    4. Agent tieu thu qua summarize_for_agent / build_agent_text.
    """
    from miro.research import media_provider

    t0 = time.time()
    eye_evidence = await gateway.read_via_eye(
        session, platform_id=platform_id, url=url, caller=caller,
        eye_fn=eye_fn, expected_account=expected_account)
    verify_media_url_against_eye(eye_evidence, url)
    analyze = analyze_fn or media_provider.analyze_ephemeral
    try:
        media = await _maybe_await(analyze, url)
    except Exception as exc:
        return {"ok": False,
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "browser_evidence": {
                    "url": eye_evidence.get("url"),
                    "tab_id": eye_evidence.get("tab_id"),
                    "instance_id": eye_evidence.get("instance_id"),
                    "actor": eye_evidence.get("actor"),
                    "observed_at": eye_evidence.get("observed_at"),
                    "provenance": eye_evidence.get("provenance")},
                "media": None,
                "agent_text": "",
                "elapsed_s": round(time.time() - t0, 2)}
    agent_text = build_agent_text(media if isinstance(media, dict) else {})
    elapsed = round(time.time() - t0, 2)
    return {
        "ok": True,
        "agent_text": agent_text,
        "browser_evidence": {
            "url": eye_evidence.get("url"),
            "tab_id": eye_evidence.get("tab_id"),
            "instance_id": eye_evidence.get("instance_id"),
            "actor": eye_evidence.get("actor"),
            "observed_at": eye_evidence.get("observed_at"),
            "provenance": eye_evidence.get("provenance"),
            "platform": eye_evidence.get("platform")},
        "media": media,
        "provenance": {"browser": "rea-eye", "media": "media-analysis"},
        "elapsed_s": elapsed,
        "analysis_wall_clock_s": elapsed,
        "video_duration_s": _video_duration_s(media),
    }


async def run_multimodal_batch(
    session,
    *,
    platform_id: str,
    urls: list[str],
    caller: str,
    eye_fn: Callable,
    max_batch: int = 10,
    analyze_fn: Callable[[str], Any] | None = None,
) -> list[dict[str, Any]]:
    """Batch TUAN TU (khong song song): moi video 1 luot E2E rieng,
    loi 1 video khong dung ca loat. Temp do analyze_ephemeral tu xoa."""
    out: list[dict[str, Any]] = []
    for url in list(urls or [])[:max_batch]:
        try:
            out.append(await run_multimodal_task(
                session, platform_id=platform_id, url=url, caller=caller,
                eye_fn=eye_fn, analyze_fn=analyze_fn))
        except Exception as exc:  # noqa: BLE001 - giu loat chay tiep
            out.append({"ok": False, "url": url,
                        "error": f"{type(exc).__name__}: {exc}"[:300],
                        "browser_evidence": None, "media": None,
                        "agent_text": ""})
    return out


def run_multimodal_task_sync(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Wrapper sync cho caller khong async."""
    return asyncio.run(run_multimodal_task(*args, **kwargs))
