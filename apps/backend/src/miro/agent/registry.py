"""Tool registry: dang ky tool voi input/output schema ro rang.

Moi tool khai bao capability (de router chon), input/output fields,
va co phai tac dong that (mutating) hay khong. Mutating tool doi hoi
approval + revision khi executor chay.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolSpec:
    name: str
    capability: str
    description: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    mutating: bool = False
    scope: str = "edit"


@dataclass
class ToolRegistry:
    _tools: dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._tools:
            raise ValueError(f"Tool '{spec.name}' da dang ky.")
        self._tools[spec.name] = spec
        return spec

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError:
            raise KeyError(f"Tool '{name}' chua dang ky.") from None

    def by_capability(self, capability: str) -> list[ToolSpec]:
        return [t for t in self._tools.values() if t.capability == capability]

    def names(self) -> list[str]:
        return sorted(self._tools)


def default_registry() -> ToolRegistry:
    """Bo tool mac dinh: hop nhat dubtool core + JARVIS agents."""
    reg = ToolRegistry()
    reg.register(ToolSpec(
        name="editor.set_voice",
        capability="voice_change",
        description="Doi giong doc cua mot hoac nhieu segment (dubtool core/voices).",
        inputs=("video_id", "segment_ids", "voice_id", "expected_revision"),
        outputs=("revision", "segments_updated"),
        mutating=True,
    ))
    reg.register(ToolSpec(
        name="editor.cut",
        capability="timeline_cut",
        description="Cat timeline theo keep_ranges (dubtool core/edit_timeline).",
        inputs=("video_id", "ranges", "expected_revision"),
        outputs=("revision", "plan"),
        mutating=True,
    ))
    reg.register(ToolSpec(
        name="editor.preview",
        capability="timeline_preview",
        description="Dung preview khong doi trang thai (read-only).",
        inputs=("video_id",),
        outputs=("preview_url", "duration"),
        mutating=False,
    ))
    reg.register(ToolSpec(
        name="web.search",
        capability="search",
        description="Tim kiem web cong khai (JARVIS router web_search).",
        inputs=("query", "limit"),
        outputs=("items",),
        mutating=False,
    ))
    reg.register(ToolSpec(
        name="web.read",
        capability="read",
        description="Doc mot trang web (JARVIS router web_read).",
        inputs=("url",),
        outputs=("content",),
        mutating=False,
    ))
    reg.register(ToolSpec(
        name="report.synthesize",
        capability="synthesize",
        description="Tong hop ket qua cac buoc (JARVIS planner synthesize).",
        inputs=("collected",),
        outputs=("final_answer", "sources"),
        mutating=False,
    ))
    return reg
