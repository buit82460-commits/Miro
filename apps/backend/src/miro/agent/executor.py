"""Executor: chay plan step-by-step, gan approval + revision moi hanh dong that.

- Read-only tool: chay ngay, khong doi approval.
- Mutating tool: check PermissionStore (scope + revision) truoc khi goi remote;
  remote tu tang revision; receipt luu lai approval/revision tung step.
- Remote mac dinh la EditorRemote gia lap (mock du an editor/segments).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..permissions.store import PermissionError, PermissionStore
from .planner import Plan
from .registry import ToolRegistry


@dataclass
class StepResult:
    tool: str
    ok: bool
    revision: int | None = None
    detail: dict = field(default_factory=dict)


@dataclass
class EditorRemote:
    """Gia lap backend editor co revision (nhu FakeRemote cua tasks/service)."""

    revision: int = 1
    voices: dict[str, dict] = field(default_factory=dict)

    def mutate_voice(self, video_id: str, segment_ids: list[str],
                     voice_id: str, expected_revision: int) -> dict:
        if expected_revision != self.revision:
            raise PermissionError(
                "STALE_REVISION",
                f"Project dang o revision {self.revision}, khong phai {expected_revision}.",
            )
        for seg in segment_ids:
            self.voices[f"{video_id}:{seg}"] = {"voice_id": voice_id}
        self.revision += 1
        return {"revision": self.revision, "segments_updated": segment_ids}

    def preview(self, video_id: str) -> dict:
        items = {k: v for k, v in self.voices.items() if k.startswith(f"{video_id}:")}
        return {"preview_url": f"preview://{video_id}", "segments": items}


class AgentExecutor:
    def __init__(self, registry: ToolRegistry, permissions: PermissionStore | None = None,
                 remote: EditorRemote | None = None):
        self.registry = registry
        self.permissions = permissions or PermissionStore()
        self.remote = remote or EditorRemote()
        self.receipts: list[dict] = []

    def run(self, task_id: str, item: int, plan: Plan) -> list[StepResult]:
        results: list[StepResult] = []
        for step in plan.steps:
            spec = self.registry.get(step.tool)
            if not spec.mutating:
                detail = self._run_readonly(step.tool, step.args)
                results.append(StepResult(tool=step.tool, ok=True,
                                          revision=self.remote.revision, detail=detail))
                self.receipts.append({"tool": step.tool, "approval": "auto",
                                      "revision": self.remote.revision})
                continue
            expected = int(step.args.get("expected_revision", 0))
            self.permissions.check(task_id, item, scope=spec.scope, revision=expected)
            detail = self._run_mutating(step.tool, step.args, expected)
            results.append(StepResult(tool=step.tool, ok=True,
                                      revision=detail.get("revision"), detail=detail))
            self.receipts.append({"tool": step.tool, "approval": "granted",
                                  "revision": detail.get("revision")})
        return results

    def _run_readonly(self, tool: str, args: dict) -> dict:
        if tool == "editor.preview":
            return self.remote.preview(str(args.get("video_id", "")))
        if tool == "web.search":
            return {"items": []}
        if tool == "web.read":
            return {"content": ""}
        if tool == "report.synthesize":
            collected = args.get("collected", [])
            return {"final_answer": f"Tong hop {len(collected)} buoc.", "sources": []}
        raise KeyError(f"Read-only tool '{tool}' chua co trien khai.")

    def _run_mutating(self, tool: str, args: dict, expected_revision: int) -> dict:
        if tool == "editor.set_voice":
            return self.remote.mutate_voice(
                str(args["video_id"]), list(args["segment_ids"]),
                str(args["voice_id"]), expected_revision,
            )
        if tool == "editor.cut":
            if expected_revision != self.remote.revision:
                raise PermissionError("STALE_REVISION", "Revision da cu.")
            self.remote.revision += 1
            return {"revision": self.remote.revision,
                    "plan": args.get("ranges", [])}
        raise KeyError(f"Mutating tool '{tool}' chua co trien khai.")
