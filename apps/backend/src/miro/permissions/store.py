"""Permissions: scope checks, revision-gated approval, revocation.

Every remote mutation requires a granted scope. Approvals bind to the exact
project revision reviewed — approving revision N never authorizes revision N+1.
Revocation blocks further mutations until re-approved.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..tasks.models import utc_now_iso


class PermissionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: str
    revision: int
    approved_by: str = "user"
    approved_at: str = Field(default_factory=utc_now_iso)
    revoked: bool = False


class PermissionStore:
    def __init__(self):
        self._approvals: dict[str, dict[str, Approval]] = {}

    def grant(self, task_id: str, item_index: int, scope: str, revision: int, approved_by: str = "user") -> Approval:
        key = str(item_index)
        approval = Approval(scope=scope, revision=revision, approved_by=approved_by)
        self._approvals.setdefault(task_id, {})[key] = approval
        return approval

    def revoke(self, task_id: str, item_index: int) -> None:
        existing = self._approvals.get(task_id, {}).get(str(item_index))
        if existing is None:
            raise PermissionError("APPROVAL_NOT_FOUND", "No approval to revoke.")
        existing.revoked = True

    def check(self, task_id: str, item_index: int, scope: str, revision: int) -> Approval:
        existing = self._approvals.get(task_id, {}).get(str(item_index))
        if existing is None or existing.revoked:
            raise PermissionError("APPROVAL_REQUIRED", "Mutation requires a fresh approval.")
        if existing.scope != scope:
            raise PermissionError("SCOPE_DENIED", f"Approval covers scope '{existing.scope}', not '{scope}'.")
        if existing.revision != revision:
            raise PermissionError(
                "STALE_REVISION",
                f"Approval binds to revision {existing.revision}; project is at {revision}.",
            )
        return existing
