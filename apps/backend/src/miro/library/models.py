"""Library models: asset, collection, render/post refs (quan he su dung)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Asset:
    id: str
    sha256: str
    path: str
    name: str
    kind: str = "video"
    size: int = 0
    tags: list[str] = field(default_factory=list)
    collections: list[str] = field(default_factory=list)
    archived: bool = False
    missing: bool = False


@dataclass
class Collection:
    id: str
    name: str
    asset_ids: list[str] = field(default_factory=list)


@dataclass
class RenderRef:
    render_id: str
    project_id: str
    asset_ids: list[str] = field(default_factory=list)


@dataclass
class PostRef:
    publication_id: str
    platform: str
    render_id: str = ""
    asset_ids: list[str] = field(default_factory=list)
    url: str = ""
