"""Research service — pure orchestration over an injected provider.

Patterns ported from D:/JARVIS-Assistant (page_extract → social_video →
channel_report → tiktok_discover) and C:/dubtool download/listing adapters:

- search: candidate listing (like PageExtractAgent phase 2 — links only).
- read_url: page text extraction (like page_extract load phase, read-only).
- analyze_channel: profile + N newest videos, each video flagged
  metadata_only unless frames were analyzed.
- analyze_video: single video; evidence level reflects include_frames AND
  whether the provider actually analyzed frames.
- compare: two videos side by side with a code-computed delta
  (no LLM counting — cf. social_video.comment_stats).
- to_project: handoff a researched URL into a Miro task (TaskVideo.source).

Every SourcedResult carries `sources` + `fetched_at`.
"""
from __future__ import annotations

from typing import Any

from .models import EvidenceLevel, SourcedResult, utc_now_iso
from .providers import ResearchProvider


class NullProvider:
    """Default provider: no network, honest empty results."""

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        return []

    def read_url(self, url: str) -> dict[str, Any]:
        return {"title": "", "text": "", "url": url, "note": "no provider configured"}

    def channel_videos(self, channel_url: str, max_videos: int) -> dict[str, Any]:
        return {"profile": {}, "videos": []}

    def video_detail(self, url: str, include_frames: bool) -> dict[str, Any]:
        return {"url": url, "metadata": {}, "frames_analyzed": False}


def _evidence(frames_analyzed: bool) -> EvidenceLevel:
    return "frames_analyzed" if frames_analyzed else "metadata_only"


def search(provider: ResearchProvider, query: str, limit: int) -> SourcedResult:
    items = provider.search(query, limit)[:limit]
    sources = [str(i.get("url", "")) for i in items if i.get("url")]
    return SourcedResult(
        kind="search", summary=f"{len(items)} kết quả cho '{query}'.",
        items=items, sources=sources, fetched_at=utc_now_iso(),
    )


def read_url(provider: ResearchProvider, url: str) -> SourcedResult:
    page = provider.read_url(url)
    return SourcedResult(
        kind="read", summary=str(page.get("title") or url),
        items=[page], sources=[url], fetched_at=utc_now_iso(),
    )


def analyze_channel(provider: ResearchProvider, channel_url: str,
                    max_videos: int) -> SourcedResult:
    data = provider.channel_videos(channel_url, max_videos)
    videos = (data.get("videos") or [])[:max_videos]
    analyzed = sum(1 for v in videos if v.get("frames_analyzed"))
    level = _evidence(analyzed == len(videos) and bool(videos))
    return SourcedResult(
        kind="channel",
        summary=(f"Kênh {channel_url}: {len(videos)} video "
                 f"({analyzed} có frame, {len(videos) - analyzed} chỉ metadata)."),
        items=[{"profile": data.get("profile", {}), "videos": videos}],
        sources=[channel_url] + [str(v.get("url", "")) for v in videos if v.get("url")],
        fetched_at=utc_now_iso(), evidence=level,
    )


def analyze_video(provider: ResearchProvider, url: str,
                  include_frames: bool) -> SourcedResult:
    detail = provider.video_detail(url, include_frames)
    level = _evidence(bool(detail.get("frames_analyzed")))
    return SourcedResult(
        kind="video",
        summary=str((detail.get("metadata") or {}).get("title") or url),
        items=[detail], sources=[url],
        fetched_at=utc_now_iso(), evidence=level,
    )


def compare(provider: ResearchProvider, url_a: str, url_b: str,
            include_frames: bool) -> SourcedResult:
    a = provider.video_detail(url_a, include_frames)
    b = provider.video_detail(url_b, include_frames)
    ma, mb = a.get("metadata") or {}, b.get("metadata") or {}
    delta = {
        "play_count": [(ma.get("play_count")), (mb.get("play_count"))],
        "digg_count": [(ma.get("digg_count")), (mb.get("digg_count"))],
        "comment_count": [(ma.get("comment_count")), (mb.get("comment_count"))],
        "duration": [(ma.get("duration")), (mb.get("duration"))],
    }
    frames = bool(a.get("frames_analyzed")) and bool(b.get("frames_analyzed"))
    return SourcedResult(
        kind="compare",
        summary=f"So sánh {url_a} vs {url_b} (code-computed, 0 LLM).",
        items=[{"a": a, "b": b, "delta": delta}],
        sources=[url_a, url_b],
        fetched_at=utc_now_iso(), evidence=_evidence(frames),
    )
