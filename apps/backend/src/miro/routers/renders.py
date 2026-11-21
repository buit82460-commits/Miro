"""Render router — idempotent create per contracts/render.json.

Store SQLite persistent (storage/registry.RenderStore): restart BE khong
mat du lieu. Cung request_id + cung noi dung -> replay; cung request_id +
khac noi dung -> 409.
"""

from fastapi import APIRouter, HTTPException, status

from miro.models import ConflictDetail, RenderRequest, RenderResponse
from miro.storage.registry import RenderStore

router = APIRouter(prefix="/renders", tags=["renders"])

_store = RenderStore()


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RenderResponse)
def create_render(body: RenderRequest) -> RenderResponse:
    try:
        res, _ = _store.create(body.request_id, body.project_id,
                               body.expected_revision, body.content_hash,
                               dict(body.spec or {}))
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ConflictDetail(
                detail="request_id already used with different content",
                existing_render_id=str(exc.args[0]),
            ).model_dump(),
        )
    return RenderResponse(**res)


@router.get("/{render_id}", response_model=RenderResponse)
def get_render(render_id: str) -> RenderResponse:
    found = _store.get(render_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return RenderResponse(**found)
