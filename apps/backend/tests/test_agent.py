"""Mock test: task editor giao agent doi giong dung segment/revision."""
from __future__ import annotations

import pytest

from miro.agent import AgentExecutor, CapabilityRouter, EditorRemote, Planner, default_registry
from miro.permissions.store import PermissionError, PermissionStore


def _stack():
    reg = default_registry()
    perms = PermissionStore()
    remote = EditorRemote(revision=3)
    return reg, perms, remote


def test_router_picks_voice_tool():
    reg, _, _ = _stack()
    decision = CapabilityRouter(reg).route("doi giong 2 doan sang Hai Dang")
    assert decision.capability == "voice_change"
    assert decision.tool == "editor.set_voice"


def test_agent_changes_voice_for_exact_segments_and_revision():
    reg, perms, remote = _stack()
    planner = Planner()
    plan = planner.plan_voice_change("vid-1", ["s1", "s3"], "vi-hai-dang", revision=3)
    assert plan.steps[-1].tool == "editor.set_voice"
    perms.grant("task-1", 0, "edit", revision=3)
    results = AgentExecutor(reg, perms, remote).run("task-1", 0, plan)
    assert results[-1].ok and results[-1].revision == 4
    assert remote.voices == {
        "vid-1:s1": {"voice_id": "vi-hai-dang"},
        "vid-1:s3": {"voice_id": "vi-hai-dang"},
    }
    # Segment ngoai danh sach khong bi doi.
    assert "vid-1:s2" not in remote.voices


def test_mutating_without_approval_is_blocked():
    reg, perms, remote = _stack()
    plan = Planner().plan_voice_change("vid-1", ["s1"], "vi-hai-dang", revision=3)
    with pytest.raises(PermissionError) as exc:
        AgentExecutor(reg, perms, remote).run("task-1", 0, plan)
    assert exc.value.code == "APPROVAL_REQUIRED"
    assert remote.revision == 3  # khong doi trang thai khi chua duyet


def test_stale_revision_is_rejected():
    reg, perms, remote = _stack()
    plan = Planner().plan_voice_change("vid-1", ["s1"], "vi-hai-dang", revision=2)
    perms.grant("task-1", 0, "edit", revision=2)
    with pytest.raises(PermissionError) as exc:
        AgentExecutor(reg, perms, remote).run("task-1", 0, plan)
    assert exc.value.code == "STALE_REVISION"
