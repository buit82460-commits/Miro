"""Render router — idempotent create per contracts/render.json.

Khung tham chiếu contract, chưa nối store thật. Logic nghiệp vụ chi tiết
(render pipeline, revision check) được merge sau từ nhánh nghiệp vụ.
"""

from fastapi import APIRouter, HTTPException, status

from miro.models import ConflictDetail, RenderRequest, RenderResponse

router = APIRouter(prefix="/renders", tags=["renders"])

_store: dict[str, tuple[RenderRequest, RenderResponse]] = {}


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RenderResponse)
def create_render(body: RenderRequest) -> RenderResponse:
    existing = _store.get(body.request_id)
    if existing is not None:
        prev_req, prev_res = existing
        same_content = (
            prev_req.project_id == body.project_id
            and prev_req.expected_revision == body.expected_revision
            and prev_req.content_hash == body.content_hash
        )
        if same_content:
            return RenderResponse(**{**prev_res.model_dump(), "replayed": True})
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ConflictDetail(
                detail="request_id already used with different content",
                existing_render_id=prev_res.render_id,
            ).model_dump(),
        )
    res = RenderResponse(render_id=f"rnd_{body.request_id}", status="queued")
    _store[body.request_id] = (body, res)
    return res


@router.get("/{render_id}", response_model=RenderResponse)
def get_render(render_id: str) -> RenderResponse:
    for _, res in _store.values():
        if res.render_id == render_id:
            return res
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
