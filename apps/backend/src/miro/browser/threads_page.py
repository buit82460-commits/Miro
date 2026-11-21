"""ThreadsPage that: production page noi mat that vao worker (luat A).

- read_eye(intent): goi eye port collect_post_records(page, owner) — eye la noi
  DUY NHAT chay locator; adapter chi truyen page handle + nhan records.
- collect_records(owner): 1-collect cho Phase B (quet 1 lan, nao match offline).
- submit/verify_actor/renew/release: uy thac AcquiredTab + ManagedChromeSession.
"""
from __future__ import annotations


class ManagedThreadsPage:
    """ThreadsPage production tren 1 AcquiredTab (ManagedChromeSession)."""

    def __init__(self, acquired, owner: str):
        self._tab = acquired
        self.owner = owner

    @property
    def _page(self):
        return self._tab.page

    def verify_actor(self, owner: str) -> bool:
        record = getattr(self._tab, "record", None)
        actual = ""
        if isinstance(record, dict):
            actual = record.get("expectedAccountId") or ""
        if not actual:
            actual = self.owner
        return str(actual or "").lower().lstrip("@") == str(owner or "").lower().lstrip("@")


    async def _collect_async(self, owner: str) -> list[dict]:
        from miro.publishing.publisher import collect_post_records
        try:
            return await collect_post_records(self._page, owner or self.owner)
        except Exception:
            return []

    def collect_records(self, owner: str = "") -> list[dict]:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(asyncio.run, self._collect_async(owner or self.owner))
                try:
                    return fut.result(timeout=120)
                except Exception:
                    return []
        try:
            return asyncio.run(self._collect_async(owner or self.owner))
        except Exception:
            return []

    def read_eye(self, intent) -> list[dict]:
        records = self.collect_records(getattr(intent, "owner", "") or self.owner)
        return [r for r in records if isinstance(r, dict) and "post_id" in r]

    def submit(self, intent) -> dict:
        raise AssertionError(
            "submit qua composer Threads chua dau day; worker chi chay "
            "read-only/reconcile cho den khi co adapter submit that")

    def renew(self, ttl: int = 300):
        import asyncio

        try:
            result = self._tab.renew(ttl)
            if asyncio.iscoroutine(result):
                asyncio.run(result)
        except Exception:
            pass

    def release(self) -> None:
        import asyncio

        try:
            result = self._tab.release()
            if asyncio.iscoroutine(result):
                asyncio.run(result)
        except Exception:
            pass

    def disconnect(self) -> None:
        return None
