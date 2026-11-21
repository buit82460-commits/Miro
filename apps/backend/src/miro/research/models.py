"""Research domain models.

Every result carries its source URLs and a fetch timestamp, so callers
can tell metadata-only evidence apart from frame-level evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EvidenceLevel = Literal["metadata_only", "frames_analyzed"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SourcedResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    summary: str = ""
    items: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    fetched_at: str = Field(default_factory=utc_now_iso)
    evidence: EvidenceLevel = "metadata_only"


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)


class ReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=4096)


class ChannelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel_url: str = Field(min_length=1, max_length=4096)
    max_videos: int = Field(default=10, ge=1, le=50)


class VideoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=4096)
    include_frames: bool = False


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url_a: str = Field(min_length=1, max_length=4096)
    url_b: str = Field(min_length=1, max_length=4096)
    include_frames: bool = False


class ToProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    title: str = Field(min_length=1, max_length=100)
    source_url: str = Field(min_length=1, max_length=4096)
    transcript: str = Field(default="", max_length=50000)
