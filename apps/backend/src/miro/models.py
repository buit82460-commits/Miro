"""Pydantic models mirroring contracts/render.json."""

from pydantic import BaseModel, Field


class RenderRequest(BaseModel):
    request_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)
    content_hash: str = Field(min_length=1)
    spec: dict = Field(default_factory=dict)


class RenderResponse(BaseModel):
    render_id: str
    status: str
    replayed: bool = False


class ConflictDetail(BaseModel):
    detail: str
    existing_render_id: str
