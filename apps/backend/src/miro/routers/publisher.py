"""Publisher router — idempotent publish per contracts/publisher.json.

Khung tham chiếu contract, chưa nối queue thật. Chi tiết worker/attempt
được merge sau từ nhánh nghiệp vụ.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/publications", tags=["publisher"])


class PublishRequest(BaseModel):
    publication_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    render_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)


class PublishResponse(BaseModel):
    publication_id: str
    attempt_id: str
    status: str
    replayed: bool = False


_store: dict[tuple[str, str], PublishResponse] = {}


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PublishResponse)
def publish(body: PublishRequest) -> PublishResponse:
    key = (body.publication_id, body.attempt_id)
    existing = _store.get(key)
    if existing is not None:
        return PublishResponse(**{**existing.model_dump(), "replayed": True})
    res = PublishResponse(
        publication_id=body.publication_id, attempt_id=body.attempt_id, status="queued"
    )
    _store[key] = res
    return res


@router.get("/{publication_id}", response_model=list[PublishResponse])
def get_publication(publication_id: str) -> list[PublishResponse]:
    items = [r for (pid, _), r in _store.items() if pid == publication_id]
    if not items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return items
