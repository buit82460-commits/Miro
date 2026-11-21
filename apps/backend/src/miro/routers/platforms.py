"""Platform registry router — Settings → Platforms.

Read (list/download/reconcile/watch) and publish (draft/publish) tracks
are reported separately. Mutations are versioned: every change bumps the
registry version and keeps history so old tasks (pinned to a version)
keep working; rollback restores a previous LIVE snapshot.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from miro.platforms import store

router = APIRouter(prefix="/platforms", tags=["platforms"])


class CapabilityPatch(BaseModel):
    status: str | None = None
    runtime: str | None = None
    input: str | None = None
    output: str | None = None
    evidence: str | None = None


class PlatformUpsert(BaseModel):
    id: str = Field(min_length=1)
    name: str = ""
    runtime: str = ""
    accounts: list[str] = Field(default_factory=list)
    entry_urls: dict[str, str] = Field(default_factory=dict)
    capabilities: dict = Field(default_factory=dict)


class CloneRequest(BaseModel):
    new_id: str = ""


class RollbackRequest(BaseModel):
    version: int = Field(ge=1)


@router.get("")
def list_platforms() -> dict:
    return store.list_platforms()


@router.get("/history")
def get_history() -> dict:
    return {"history": [{"version": s["version"]} for s in store.history()]}


@router.post("", status_code=status.HTTP_201_CREATED)
def upsert_platform(body: PlatformUpsert) -> dict:
    try:
        return store.upsert_platform(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{platform_id}/clone", status_code=status.HTTP_201_CREATED)
def clone_platform(platform_id: str, body: CloneRequest) -> dict:
    try:
        return store.clone_platform(platform_id, body.new_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="platform not found") from None


@router.patch("/{platform_id}/capabilities/{capability}")
def patch_capability(platform_id: str, capability: str, body: CapabilityPatch) -> dict:
    try:
        return store.update_capability(
            platform_id, capability, {k: v for k, v in body.model_dump().items() if v is not None}
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="platform not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/rollback")
def rollback(body: RollbackRequest) -> dict:
    try:
        return store.rollback(body.version)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
