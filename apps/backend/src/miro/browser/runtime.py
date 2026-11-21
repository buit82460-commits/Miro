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
from urllib.parse import parse_qsl, urlsplit

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

_DEFAULT_TTL = 180  # khớp JARVIS worker ttl; acquire vượt quá phải truyền tường minh


def _origin_of(url: str) -> tuple | None:
    """Origin chuẩn hóa (scheme, host, port) để so khớp policy.

    Trả None khi URL không parse được hoặc thiếu scheme http(s)/host.
    Port mặc định: 443 cho https, 80 cho http. Host lowercase.
    """
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(str(url))
    except Exception:
        return None
    scheme = (parts.scheme or "").lower()
    host = (parts.hostname or "").lower()
    if scheme not in ("http", "https") or not host:
        return None
    port = parts.port
    if port is None:
        port = 443 if scheme == "https" else 80
    return (scheme, host, port)


def _check_origin(url: str, allowed_origins: tuple[str, ...] | list[str]) -> None:
    """Fail-closed: URL phải cùng origin (scheme/host/port) với policy.

    Không parse được hoặc lệch origin -> RegistryError URL_NOT_REGISTERED,
    caller từ chối trước mọi side-effect.
    """
    wanted = _origin_of(url)
    if wanted is None:
        raise RegistryError(
            "URL_NOT_REGISTERED: URL khong hop le hoac khong thuoc policy origin")
    for allowed in allowed_origins or ():
        if _origin_of(allowed) == wanted:
            return
    raise RegistryError(
        "URL_NOT_REGISTERED: URL lech policy origin (scheme/host/port)")


_IGNORED_QUERY_KEYS = frozenset({
    "fbclid", "utm_source", "utm_medium", "utm_campaign",
    "utm_term", "utm_content", "_rdc", "_rdr",
})
"""Query tracking bo qua khi so destination (port tu A `browser_runtime`)."""


def _urls_same_destination(first: str, second: str) -> bool:
    """Cung destination: scheme/host/port + path (strip `/` cuoi) + query
    khong tracking bang nhau. Parse loi -> False."""
    try:
        a = urlsplit(str(first))
        b = urlsplit(str(second))
    except Exception:
        return False
    if not a.scheme or not b.scheme or not a.hostname or not b.hostname:
        return False
    if ((a.scheme or "").lower(), (a.hostname or "").lower(), a.port,
            a.path.rstrip("/")) != ((b.scheme or "").lower(),
            (b.hostname or "").lower(), b.port, b.path.rstrip("/")):
        return False
    qa = sorted((k, v) for k, v in parse_qsl(a.query) if k not in _IGNORED_QUERY_KEYS)
    qb = sorted((k, v) for k, v in parse_qsl(b.query) if k not in _IGNORED_QUERY_KEYS)
    return qa == qb


def default_user_data_dir() -> str:
    """Chrome user-data-dir mặc định kiểu dubtool:
    `%LOCALAPPDATA%\\Google\\Chrome\\User Data`."""
    import os

    return os.path.join(os.environ.get("LOCALAPPDATA", ""),
                        "Google", "Chrome", "User Data")


def chrome_endpoint(user_data_dir: str = "", *, endpoint: str = "") -> str:
    """Đọc DevToolsActivePort -> ws endpoint (mẫu dubtool
    `social_live_chrome.chrome_endpoint`).

    - `endpoint` (fallback `--remote-debugging-port`/`--endpoint`): Chrome mở
      cờ remote-debugging riêng thì dùng thẳng, không đọc file.
    - Mặc định đọc `<user_data_dir>/DevToolsActivePort` (trống thì lấy
      `%LOCALAPPDATA%\\Google\\Chrome\\User Data`): dòng 1 = port, dòng 2 =
      route `/devtools/browser/...` -> `ws://127.0.0.1:{port}{route}`.
    File thiếu/sai -> CDP_UNAVAILABLE kèm hướng dẫn bật Allow remote debugging
    ở chrome://inspect. Không tự mở Chrome thay thế."""
    import os
    import re

    given = (endpoint or "").strip()
    if given:
        return given
    directory = (user_data_dir or "").strip() or default_user_data_dir()
    hint = ("CDP_UNAVAILABLE: Chrome remote-debugging chua bat; mo "
            "chrome://inspect/#remote-debugging trong Chrome va bat "
            "Allow remote debugging truoc; khong tu mo browser thay the")
    port_file = os.path.join(directory, "DevToolsActivePort")
    try:
        with open(port_file, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        raise RegistryError(hint) from None
    try:
        port = int((lines[0] if lines else "").strip())
        route = (lines[1] if len(lines) > 1 else "").strip()
        valid = 1 <= port <= 65535 and re.fullmatch(
            r"/devtools/browser/[A-Za-z0-9-]+", route) is not None
    except (ValueError, IndexError):
        valid = False
        port, route = 0, ""
    if not valid:
        raise RegistryError(
            "CDP_UNAVAILABLE: DevToolsActivePort khong hop le; mo "
            "chrome://inspect/#remote-debugging va bat Allow remote "
            "debugging truoc") from None
    return f"ws://127.0.0.1:{port}{route}"


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
    verify_actor: object = None  # async (page, record) -> account_id; inject per-task
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
        for record in self.store.list("tab"):
            if record.get("browserInstanceId") == self.instance_id:
                record.update(status="disconnected")
                self.store.put("tab", record["id"], record)
                with suppress(RegistryError):
                    self.store.invalidate(
                        tab_resource(self.instance_id, record.get("targetId", "")))

    async def disconnect(self) -> None:
        """Mất kết nối CDP: đánh dấu disconnected + invalidate lease, dừng mọi
        worker (WorkerStopped), KHÔNG tự reconnect, KHÔNG replay UNKNOWN."""
        self.close()

    def _ensure_live(self) -> None:
        if self.closed:
            raise RegistryError("BROWSER_DISCONNECTED: no auto-reconnect; rebind required")
        connected = getattr(self.browser, "is_connected", None)
        if callable(connected) and not connected():
            self.close()
            raise RegistryError("BROWSER_DISCONNECTED: no auto-reconnect; rebind required")

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
                    # LUAT CUNG: mat doc #profile_path qua eye.profile_path_record.
                    from miro import eye as _eye
                    rec = await _eye.profile_path_record(page) or {}
                    actual = str(rec.get("profile_path") or "").strip()
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
        # LUAT CUNG: mat doc upload/dirty qua eye.upload_state (read-only).
        # Runtime guard chi nhan records, khong evaluate truc tiep.
        try:
            from miro import eye as _eye
            snap = await _eye.upload_state(page) or {}
            return {"activeUpload": bool(snap.get("activeUpload")),
                    "dirtyForm": bool(snap.get("dirtyForm"))}
        except Exception:
            pass
        return {"activeUpload": False, "dirtyForm": False}

    # -- account verify (pattern JARVIS: trước + sau) ----------------------
    async def _verify_actor(self, page, record: dict, lease: dict | None = None) -> str:
        """Verify actor 2 lớp: callback `verify_actor` inject theo task được
        ưu tiên, fallback `account_providers[platform]` (7 cách dubtool §7:
        FB USER_ID, IG @username+ds_user_id, TikTok avatar/audience,
        Threads/ChatGPT/Flow/Shopee body/URL).
        Mismatch -> invalidate lease (worker cũ mất quyền) + WorkerStopped."""
        platform_id = record.get("platformId")
        provider = self.verify_actor
        if provider is None:
            provider = self.account_providers.get(platform_id)
        if provider is None:
            raise RegistryError("ACCOUNT_VERIFIER_UNAVAILABLE: sensitive operations denied")
        try:
            try:
                result = provider(page, record)
            except TypeError:
                result = provider(page)
            if asyncio.iscoroutine(result):
                result = await result
            actual = str(result)
        except (WorkerStopped, RegistryError):
            raise
        except Exception as error:
            raise RegistryError("ACCOUNT_MISMATCH: " + type(error).__name__) from None
        expected = str(record.get("expectedAccountId") or "")
        mismatch = (expected and actual != expected) or (not actual)
        if mismatch:
            if lease is not None:
                with suppress(LeaseLost, RegistryError):
                    self.store.invalidate(lease["resource"])
            raise WorkerStopped(
                "WORKER_STOPPED: ACCOUNT_MISMATCH: page account does not match task account")
        return actual

    async def _verify_account(self, page, record: dict, lease: dict | None = None) -> str:
        return await self._verify_actor(page, record, lease)

    # -- acquire -----------------------------------------------------------
    async def acquire_tab(self, request: dict, caller: str) -> AcquiredTab:
        self._ensure_live()
        profile = self.profiles.get(request.get("profileBindingId", ""))
        if profile is None:
            raise ProfileUnverified("PROFILE_UNVERIFIED: bind current live profile evidence first")
        platform_id = request.get("platformId")
        url = request.get("url")
        if url and self.allowed_origins:
            _check_origin(url, self.allowed_origins)
        lease_ttl = int(request.get("leaseTtl", _DEFAULT_TTL))
        if not 1 <= lease_ttl <= 1800:
            raise RegistryError("INVALID_LEASE_TTL")

        candidates = [r for r in self.store.list("tab")
                      if r.get("profileBindingId") == profile["id"]
                      and r.get("browserInstanceId") == self.instance_id
                      and r.get("platformId") == platform_id
                      and r.get("status") == "open"]
        channel_id = request.get("channelId")
        flag = request.get("flag")
        if url:
            exact = [r for r in candidates
                     if _urls_same_destination(r.get("url", ""), url)]
            candidates = exact or candidates

        def _rank(record: dict) -> tuple:
            exact_url = 0 if (url and _urls_same_destination(
                record.get("url", ""), url)) else 1
            exact_channel = 0 if (channel_id is not None
                                  and record.get("channelId") == channel_id) else 1
            flag_match = 0 if (flag is not None
                               and record.get("flag") == flag) else 1
            return (exact_url, exact_channel, flag_match,
                    float(record.get("lastUsedAt", 0)))

        saw_busy = False
        saw_protected = False
        for record in sorted(candidates, key=_rank):
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
            needs_nav = bool(url and not _urls_same_destination(current or "", url))
            if needs_nav:
                state = await self._inspect_page_state(page)
                if state.get("activeUpload") or state.get("dirtyForm") or record.get("flagWatch"):
                    with suppress(LeaseLost):
                        self.store.release(lease)
                    saw_protected = True
                    continue
            if needs_nav:
                with suppress(LeaseLost):
                    self.store.release(lease)
                raise RegistryError("TAB_ORIGIN_CHANGED: tab moved away; validate/reassign role")
            record["lastUsedAt"] = time.time()
            record = self.store.put("tab", record["id"], record)
            return AcquiredTab(page=page, record=record, lease=lease, runtime=self, reused=True)
        if saw_busy:
            raise TabBusy("TAB_BUSY: matching tab is currently leased; no duplicate tab created")
        if saw_protected:
            raise TabProtected(
                "TAB_PROTECTED_NO_NAVIGATE: active upload, unsaved form, "
                "or Flag-watched region preserved")
        raise RegistryError(
            "TAB_REQUIRED_OPEN_FIRST: mo san 1 tab cua platform "
            f"'{platform_id}' trong Chrome truoc; "
            "connector khong tu tao (new_page) hay navigate tab moi")

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
        if isinstance(current_url, str) and not _urls_same_destination(
                current_url, record.get("url", "")):
            raise RegistryError("TAB_ORIGIN_CHANGED: tab moved away; validate/reassign role")
        await self._verify_actor(page, record, acquired.lease)
        try:
            # LUAT CUNG: mat doc noi dung tab qua eye.tab_state.
            from miro import eye as _eye
            content = await _eye.tab_state(page) or {}
            content["text"] = str(content.get("text") or "")[:max_chars]
            content["url"] = str(content.get("url") or current_url or "")
        except Exception as error:
            raise RegistryError("READ_FAILED: " + type(error).__name__) from None
        self._check_lease(acquired.lease)  # hết quyền giữa chừng -> dừng, không trả dữ liệu
        if isinstance(content, dict) and isinstance(content.get("url"), str) \
                and not _urls_same_destination(content["url"], record.get("url", "")):
            raise RegistryError("TAB_CHANGED_DURING_READ: tab moved away mid-read")
        await self._verify_actor(page, record, acquired.lease)  # đổi account giữa chừng -> dừng
        record["lastUsedAt"] = time.time()
        self.store.put("tab", record["id"], record)
        return {"tab": record, "content": content, "leaseFence": acquired.lease["fence"]}

    async def navigate_tab(self, acquired: AcquiredTab, url: str) -> dict:
        self._ensure_live()
        self._check_lease(acquired.lease)
        if self.allowed_origins:
            _check_origin(url, self.allowed_origins)
        await self._verify_actor(acquired.page, acquired.record, acquired.lease)
        state = await self._inspect_page_state(acquired.page)
        if state.get("activeUpload") or state.get("dirtyForm") or acquired.record.get("flagWatch"):
            raise TabProtected(
                "TAB_PROTECTED_NO_NAVIGATE: active upload, unsaved form, "
                "or Flag-watched region preserved")
        try:
            # LUAT CUNG: mat doc tab truoc navigate (can cu doi chieu).
            from miro import eye as _eye_nav
            _nav_before = await _eye_nav.tab_state(acquired.page) or {}
            _ = _nav_before.get("url")
        except Exception:
            pass
        try:
            await acquired.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as error:
            raise RegistryError("NAVIGATE_FAILED: " + type(error).__name__) from None
        self._check_lease(acquired.lease)
        final_url = getattr(acquired.page, "url", None)
        if isinstance(final_url, str) and self.allowed_origins:
            _check_origin(final_url, self.allowed_origins)
        await self._verify_actor(acquired.page, acquired.record, acquired.lease)
        acquired.record["url"] = url
        acquired.record["lastUsedAt"] = time.time()
        self.store.put("tab", acquired.record["id"], acquired.record)
        return acquired.record


@dataclass
class ManagedChromeSession:
    """MỘT đường truy cập Chrome duy nhất cho cả batch (merge dubtool
    acquire_managed_tab + JARVIS live_chrome worker).

    - open(): đọc DevToolsActivePort -> đúng 1 connect_over_cdp suốt batch;
      cuối batch close() = disconnect CDP (KHÔNG tắt Chrome).
    - Adapter và REA chỉ nhận tab/dữ liệu qua session này, không tự connect.
    - Disconnect giữa chừng -> BROWSER_DISCONNECTED/UNKNOWN, không reconnect,
      không replay; reconnect thủ công phải open() session mới.
    """

    runtime: BrowserRuntime
    endpoint: str
    closed: bool = False

    @classmethod
    async def open(cls, connect, user_data_dir: str, database,
                   *, endpoint: str = "", **kwargs) -> ManagedChromeSession:
        endpoint = chrome_endpoint(user_data_dir, endpoint=endpoint)
        connect_calls = getattr(connect, "calls", None)
        before = len(connect_calls) if isinstance(connect_calls, list) else None
        runtime = await BrowserRuntime.open(connect, endpoint, database, **kwargs)
        session = cls(runtime=runtime, endpoint=endpoint)
        if isinstance(connect_calls, list) and len(connect_calls) - (before or 0) != 1:
            raise RegistryError("CONNECT_ONCE: one connect_over_cdp per batch")
        return session

    async def acquire_managed_tab(self, *, platform_id: str, url: str,
                                  caller: str, channel_id: str | None = None,
                                  flag: str = "PUBLISH", lease_ttl: int = _DEFAULT_TTL,
                                  **extra) -> AcquiredTab:
        """Cổng duy nhất adapter/REA lấy tab: tái dùng theo rank
        (exact_url, exact_channel, flag_match, lastUsedAt); TAB_BUSY không
        tạo tab mới; hết candidate -> NO_MATCHING_TAB (không tự tạo)."""
        if self.closed:
            raise RegistryError("BROWSER_DISCONNECTED: session closed; open a new one")
        request = {"platformId": platform_id, "url": url,
                   "profileBindingId": extra.get("profileBindingId", ""),
                   "channelId": channel_id, "flag": flag,
                   "leaseTtl": lease_ttl, **extra}
        if "profileBindingId" not in extra:
            profiles = list(self.runtime.profiles.values())
            verified = [p for p in profiles if p.get("status") == "verified"]
            if len(verified) != 1:
                raise ProfileUnverified(
                    "PROFILE_UNVERIFIED: bind exactly one live profile first")
            request["profileBindingId"] = verified[0]["id"]
        return await self.runtime.acquire_tab(request, caller)

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        disconnect = getattr(self.runtime.browser, "disconnect", None)
        if callable(disconnect):
            with suppress(Exception):
                result = disconnect()
                if asyncio.iscoroutine(result):
                    await result
        self.runtime.close()
