"""Miro agent package: capability router, planner, tool registry, executor.

Port y tuong tu D:/JARVIS-Assistant (router decision, planner steps,
approval classifier) va C:/dubtool core (editor/TTS/voices) ve mot ban
thong nhat tren stack Miro (Pydantic + PermissionStore, revision-gated).
"""
from .executor import AgentExecutor, EditorRemote, StepResult
from .planner import Plan, PlanStep, Planner
from .registry import ToolRegistry, ToolSpec, default_registry
from .router import CapabilityRouter, RouteDecision

__all__ = [
    "AgentExecutor",
    "CapabilityRouter",
    "EditorRemote",
    "Plan",
    "PlanStep",
    "Planner",
    "RouteDecision",
    "StepResult",
    "ToolRegistry",
    "ToolSpec",
    "default_registry",
]
