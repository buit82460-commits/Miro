"""Publisher router — idempotent publish per contracts/publisher.json.

Khoa luy dang = cap (publication_id, attempt_id), store SQLite persistent
(storage/registry.PublicationStore). Retry cung cap -> replay, khong dang trung.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from miro.storage.registry import PublicationStore

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


_store = PublicationStore()


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PublishResponse)
def publish(body: PublishRequest) -> PublishResponse:
    res, _ = _store.publish(body.publication_id, body.attempt_id,
                            body.render_id, body.channel)
    return PublishResponse(**res)


@router.get("/{publication_id}", response_model=list[PublishResponse])
def get_publication(publication_id: str) -> list[PublishResponse]:
    items = _store.list_by_publication(publication_id)
    if not items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return [PublishResponse(**i) for i in items]
