"""Planner: chia mot yeu cau thanh cac step tuan tu.

Port gon tu JARVIS app/planner/models.py: step anh xa 1:1 sang mot tool,
buoc tong hop (neu co) phai la cuoi cung, toi da 10 step.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=300)
    args: dict = Field(default_factory=dict)


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=2000)
    steps: list[PlanStep] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _check(self) -> "Plan":
        if not self.steps:
            raise ValueError("Plan phai co it nhat 1 step.")
        for i, step in enumerate(self.steps):
            if step.tool == "report.synthesize" and i != len(self.steps) - 1:
                raise ValueError("report.synthesize chi duoc la step cuoi cung.")
        return self


class Planner:
    """Luat chia step mac dinh cho tac vu editor doi giong."""

    def plan_voice_change(self, video_id: str, segment_ids: list[str],
                          voice_id: str, revision: int) -> Plan:
        if not segment_ids:
            raise ValueError("Can it nhat 1 segment de doi giong.")
        return Plan(
            goal=f"Doi giong {len(segment_ids)} segment sang '{voice_id}'.",
            steps=[
                PlanStep(
                    tool="editor.preview",
                    description="Xem truoc trang thai hien tai (read-only).",
                    args={"video_id": video_id},
                ),
                PlanStep(
                    tool="editor.set_voice",
                    description=f"Doi giong {len(segment_ids)} segment sang {voice_id}.",
                    args={
                        "video_id": video_id,
                        "segment_ids": segment_ids,
                        "voice_id": voice_id,
                        "expected_revision": revision,
                    },
                ),
            ],
        )

    def plan_for_route(self, tool: str, args: dict, goal: str) -> Plan:
        if tool == "editor.set_voice":
            return self.plan_voice_change(
                args["video_id"], list(args.get("segment_ids", [])),
                args["voice_id"], int(args.get("expected_revision", 0)),
            )
        return Plan(
            goal=goal,
            steps=[PlanStep(tool=tool, description=f"Chay {tool}.", args=dict(args))],
        )
