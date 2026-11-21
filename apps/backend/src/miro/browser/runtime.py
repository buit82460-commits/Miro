"""BrowserRuntime: 1 nơi mở CDP, lease single-owner, verify profile/account, worker dừng khi hết quyền.

Luồng (gộp dubtool BrowserRuntime + JARVIS live_chrome_worker):
- open(): 1 kết nối CDP duy nhất tới Chrome có sẵn (không launch, không mở
  browser thay thế). Mất kết nối -> WAITING_CONFIRMATION, không tự reconnect loop.
- bind_profile(): bằng chứng chrome://version (#profile_path) cùng window thì
  mới verified; khác profile path -> PROFILE_MISMATCH.
- acquire_tab(): tab khớp đang leased -> TabBusy (không tạo tab trùng);
  tab có upload/form-dirty/flag-watched cần navigate -> TabProtected.
- read(): verify account trước + sau khi đọc (pattern JARVIS actor()), lease
  mất giữa chừng -> WorkerStopped, không replay.
- Worker hết quyền (LeaseLost/hết TTL) -> WorkerStopped: dừng, không thử lại.
"""
from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass, field

from miro.browser.errors import (
    LeaseBusy,
    LeaseLost,
    ProfileUnverified,
    RegistryError,
    TabBusy,
    TabProtected,
    WorkerStopped,
)
from miro.browser.lease_store import LeaseStore, tab_resource

_DEFAULT_TTL = 300


@dataclass
class AcquiredTab:
    page: object
    record: dict
    lease: dict
    runtime: BrowserRuntime
    reused: bool
    _released: bool = False

    async def renew(self, ttl: int = _DEFAULT_TTL) -> dict:
        try:
            self.lease = self.runtime.store.renew(self.lease, ttl)
        except LeaseLost as error:
            raise WorkerStopped("WORKER_STOPPED: " + str(error)) from None
        return self.lease

    async def read(self, max_chars: int = 4000) -> dict:
        return await self.runtime.read_tab(self, max_chars=max_chars)

    async def navigate(self, url: str) -> dict:
        return await self.runtime.navigate_tab(self, url)

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        with suppress(LeaseLost):
            self.runtime.store.release(self.lease)


@dataclass
class BrowserRuntime:
    """Single-owner runtime trên 1 CDP browser object (playwright đã connect)."""

    browser: object  # playwright browser (connect_over_cdp), hoặc fake trong test
    instance_id: str
    store: LeaseStore
    allowed_origins: tuple[str, ...] = ()
    account_providers: dict = field(default_factory=dict)
    profiles: dict = field(default_factory=dict)
    pages: dict = field(default_factory=dict)  # targetId -> page
    closed: bool = False

    # -- CDP open (1 nơi) --------------------------------------------------
    @classmethod
    async def open(cls, connect, endpoint: str, database, **kwargs) -> BrowserRuntime:
        """Mở đúng 1 kết nối CDP tới Chrome có sẵn. `connect` là
        coroutine (address) -> browser, để production truyền
        driver.chromium.connect_over_cdp, test truyền fake."""
        try:
            browser = await connect(endpoint)
        except Exception as error:
            raise RegistryError("WAITING_CONFIRMATION: CDP connection unconfirmed; "
                                "no automatic reconnect loop") from error
        instance_id = hashlib.sha256(endpoint.encode()).hexdigest()
        store = database if isinstance(database, LeaseStore) else LeaseStore(database)
        return cls(browser=browser, instance_id=instance_id, store=store, **kwargs)

    def close(self) -> None:
        self.closed = True

    def _ensure_live(self) -> None:
        if self.closed:
            raise RegistryError("BROWSER_DISCONNECTED")
        connected = getattr(self.browser, "is_connected", None)
        if callable(connected) and not connected():
            raise RegistryError("BROWSER_DISCONNECTED")

    def _check_lease(self, lease: dict) -> None:
        try:
            self.store.validate(lease)
        except LeaseLost as error:
            raise WorkerStopped("WORKER_STOPPED: " + str(error)) from None

    # -- profile verify ----------------------------------------------------
    async def bind_profile(self, user_data_dir: str, profile_directory: str) -> dict:
        """Verify qua bằng chứng chrome://version: #profile_path khớp đường dẫn
        yêu cầu. Không suy đoán profile từ context mặc định."""
        import os
        import re

        self._ensure_live()
        if not isinstance(profile_directory, str) or not re.fullmatch(r"Default|Profile \d{1,5}", profile_directory):
            raise RegistryError("INVALID_PROFILE_DIRECTORY")
        expected = os.path.normcase(os.path.realpath(os.path.join(user_data_dir, profile_directory)))
        evidence = []
        for page in self._all_pages():
            url = getattr(page, "url", "")
            if isinstance(url, str) and url.rstrip("/") == "chrome://version":
                try:
                    actual = (await page.locator("#profile_path").inner_text()).strip()
                except Exception:
                    continue
                if os.path.normcase(os.path.realpath(actual)) == expected:
                    evidence.append(page)
        if not evidence:
            raise ProfileUnverified(
                "PROFILE_UNVERIFIED: open chrome://version in the requested profile; "
                "no default-context inference or fallback")
        identifier = hashlib.sha256(expected.encode()).hexdigest()[:32]
        profile = {"id": identifier, "profileDirectory": profile_directory,
                   "profilePath": os.path.join(user_data_dir, profile_directory),
                   "browserInstanceId": self.instance_id,
                   "status": "verified", "verifiedAt": time.time()}
        self.profiles[identifier] = profile
        self.store.put("profile", identifier, profile)
        return profile

    def _all_pages(self) -> list:
        pages: list = []
        for context in list(getattr(self.browser, "contexts", []) or []):
            pages.extend(list(getattr(context, "pages", []) or []))
        return pages

    # -- page state guards -------------------------------------------------
    async def _inspect_page_state(self, page) -> dict:
        try:
            state = await page.evaluate("""() => {
                let activeUpload = Boolean(window.__miroUploadActive ||
                    document.documentElement?.dataset?.miroUploading === '1');
                if (!activeUpload) {
                    for (const input of document.querySelectorAll('input[type="file"]')) {
                        if (input.files && input.files.length > 0) { activeUpload = true; break; }
                    }
                }
                let dirtyForm = Boolean(window.__miroDirtyForm ||
                    typeof window.onbeforeunload === 'function');
                return {activeUpload, dirtyForm};
            }""")
            if isinstance(state, dict):
                return {"activeUpload": bool(state.get("activeUpload")),
                        "dirtyForm": bool(state.get("dirtyForm"))}
        except Exception:
            pass
        return {"activeUpload": False, "dirtyForm": False}

    # -- account verify (pattern JARVIS: trước + sau) ----------------------
    async def _verify_account(self, page, record: dict) -> str:
        platform_id = record.get("platformId")
        provider = self.account_providers.get(platform_id)
        try:
            if provider is not None:
                actual = str(await provider(page))
            else:
                raise RegistryError("ACCOUNT_VERIFIER_UNAVAILABLE: sensitive operations denied")
        except RegistryError:
            raise
        except Exception as error:
            raise RegistryError("ACCOUNT_MISMATCH: " + type(error).__name__) from None
        expected = str(record.get("expectedAccountId") or "")
        if expected and actual != expected:
            raise RegistryError("ACCOUNT_MISMATCH: page account does not match task account")
        if not actual:
            raise RegistryError("ACCOUNT_MISMATCH: could not verify page account")
        return actual

    # -- acquire -----------------------------------------------------------
    async def acquire_tab(self, request: dict, caller: str) -> AcquiredTab:
        self._ensure_live()
        profile = self.profiles.get(request.get("profileBindingId", ""))
        if profile is None:
            raise ProfileUnverified("PROFILE_UNVERIFIED: bind current live profile evidence first")
        platform_id = request.get("platformId")
        url = request.get("url")
        if url and self.allowed_origins and not any(url.startswith(o) for o in self.allowed_origins):
            raise RegistryError("URL_NOT_REGISTERED")
        lease_ttl = int(request.get("leaseTtl", _DEFAULT_TTL))
        if not 1 <= lease_ttl <= 1800:
            raise RegistryError("INVALID_LEASE_TTL")

        candidates = [r for r in self.store.list("tab")
                      if r.get("profileBindingId") == profile["id"]
                      and r.get("browserInstanceId") == self.instance_id
                      and r.get("platformId") == platform_id
                      and r.get("status") == "open"]
        if url:
            exact = [r for r in candidates if r.get("url") == url]
            candidates = exact or candidates
        saw_busy = False
        for record in sorted(candidates, key=lambda r: r.get("lastUsedAt", 0)):
            resource = tab_resource(self.instance_id, record["targetId"])
            if self.store.is_locked(resource):
                saw_busy = True
                continue
            try:
                lease = self.store.acquire(resource, caller + ":" + uuid.uuid4().hex[:8], lease_ttl)
            except LeaseBusy:
                saw_busy = True
                continue
            page = self.pages.get(record["targetId"])
            if page is None or getattr(page, "is_closed", lambda: True)():
                with suppress(LeaseLost):
                    self.store.release(lease)
                record.update(status="closed")
                self.store.put("tab", record["id"], record)
                continue
            page_url = getattr(page, "url", None)
            current = page_url if isinstance(page_url, str) else record.get("url")
            needs_nav = bool(url and current != url)
            if needs_nav:
                state = await self._inspect_page_state(page)
                if state.get("activeUpload") or state.get("dirtyForm") or record.get("flagWatch"):
                    with suppress(LeaseLost):
                        self.store.release(lease)
                    raise TabProtected(
                        "TAB_PROTECTED_NO_NAVIGATE: active upload, unsaved form, "
                        "or Flag-watched region preserved")
            if needs_nav:
                with suppress(LeaseLost):
                    self.store.release(lease)
                raise RegistryError("TAB_ORIGIN_CHANGED: tab moved away; validate/reassign role")
            record["lastUsedAt"] = time.time()
            record = self.store.put("tab", record["id"], record)
            return AcquiredTab(page=page, record=record, lease=lease, runtime=self, reused=True)
        if saw_busy:
            raise TabBusy("TAB_BUSY: matching tab is currently leased; no duplicate tab created")
        raise RegistryError("NO_MATCHING_TAB_AVAILABLE")

    # -- read / navigate (giữ lease, verify kép) ----------------------------
    async def read_tab(self, acquired: AcquiredTab, max_chars: int = 4000) -> dict:
        if not isinstance(max_chars, int) or not 1 <= max_chars <= 20000:
            raise RegistryError("INVALID_READ_LIMIT")
        self._ensure_live()
        self._check_lease(acquired.lease)
        page, record = acquired.page, acquired.record
        if getattr(page, "is_closed", lambda: True)():
            raise RegistryError("TAB_CLOSED: rediscover; do not reuse another target ID")
        current_url = getattr(page, "url", None)
        if isinstance(current_url, str) and current_url != record.get("url"):
            raise RegistryError("TAB_ORIGIN_CHANGED: tab moved away; validate/reassign role")
        await self._verify_account(page, record)
        try:
            content = await page.evaluate(
                "(limit)=>({url:location.href,title:document.title,"
                "text:(document.body?.innerText||'').slice(0,limit)})", max_chars)
        except Exception as error:
            raise RegistryError("READ_FAILED: " + type(error).__name__) from None
        self._check_lease(acquired.lease)  # hết quyền giữa chừng -> dừng, không trả dữ liệu
        if isinstance(content, dict) and isinstance(content.get("url"), str) \
                and content["url"] != record.get("url"):
            raise RegistryError("TAB_CHANGED_DURING_READ: tab moved away mid-read")
        await self._verify_account(page, record)  # đổi account giữa chừng -> dừng
        record["lastUsedAt"] = time.time()
        self.store.put("tab", record["id"], record)
        return {"tab": record, "content": content, "leaseFence": acquired.lease["fence"]}

    async def navigate_tab(self, acquired: AcquiredTab, url: str) -> dict:
        self._ensure_live()
        self._check_lease(acquired.lease)
        state = await self._inspect_page_state(acquired.page)
        if state.get("activeUpload") or state.get("dirtyForm") or acquired.record.get("flagWatch"):
            raise TabProtected(
                "TAB_PROTECTED_NO_NAVIGATE: active upload, unsaved form, "
                "or Flag-watched region preserved")
        try:
            await acquired.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as error:
            raise RegistryError("NAVIGATE_FAILED: " + type(error).__name__) from None
        self._check_lease(acquired.lease)
        acquired.record["url"] = url
        acquired.record["lastUsedAt"] = time.time()
        self.store.put("tab", acquired.record["id"], acquired.record)
        return acquired.record
