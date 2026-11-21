"""Research providers — injectable backends for search/read/analysis.

Production providers (yt-dlp, browser read, metadata mirrors) plug in here.
Tests inject fakes implementing the same protocol, so no network is needed.
"""
from __future__ import annotations

from typing import Any, Protocol


class ResearchProvider(Protocol):
    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        """Return candidate items: {title, url, snippet}."""
        ...

    def read_url(self, url: str) -> dict[str, Any]:
        """Return page content: {title, text, url}."""
        ...

    def channel_videos(self, channel_url: str, max_videos: int) -> dict[str, Any]:
        """Return {profile, videos: [{url, title, ...}]}."""
        ...

    def video_detail(self, url: str, include_frames: bool) -> dict[str, Any]:
        """Return {metadata, frames_analyzed: bool, ...}."""
        ...
