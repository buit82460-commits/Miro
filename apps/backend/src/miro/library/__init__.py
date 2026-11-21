"""Miro Library — asset/nguon/file/quan he su dung.

Nguon tham chieu (legacy, chi doc de hieu layout):
- C:\\dubtool\\cache\\studio\\<studio-id>\\project.json  (assets: {id: {path, sha256, kind, name}})
- C:\\dubtool\\cache\\studio\\<studio-id>\\assets\\<sha256>.mp4
- C:\\dubtool\\reports\\resource-batches\\<batch>\\batch.json (nguon tai ve)
- D:\\JARVIS-Assistant\\backend (jobs FastAPI — quan he render/bai dang tham chieu o day)

Chuc nang:
- nhap asset + dedupe theo sha256
- tag / bo suu tap
- relink file di chuyen (quet theo ten file hoac hash)
- luu tru / xoa an toan (bao project dung chung)
- truy 2 chieu asset <-> render <-> bai dang
"""

from .models import Asset, Collection, PostRef, RenderRef
from .service import LibraryService
from .store import LibraryStore

__all__ = ["Asset", "Collection", "RenderRef", "PostRef", "LibraryStore", "LibraryService"]
