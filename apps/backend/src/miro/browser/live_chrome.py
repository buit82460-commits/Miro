"""Live Chrome connector (Profile 20) — read-only, tách riêng khỏi runtime.

- `connect_over_cdp(endpoint)`: đúng 1 kết nối CDP tới Chrome CÓ SẴN qua
  Playwright async API. Không launch, không new_context, không mở browser
  thay thế. Playwright chưa cài → PLAYWRIGHT_MISSING (fail-closed).
  Chrome chưa bật remote-debugging → CDP_UNAVAILABLE.
- `open_session(...)`: ManagedChromeSession.open với connector thật.
- `read_url_once(...)`: entry point read-only — open + bind profile +
  acquire managed tab + read 1 URL + release + disconnect CDP. KHÔNG có
  post/submit/navigate trong module này (tìm `def post`/`submit(`: không có).
- CLI: `python -m miro.browser.live_chrome --url ... --user-data-dir ...`
  chỉ đọc và in text; thoát nonzero khi không verify được actor/profile.

Không tự ý mở Chrome: mọi lỗi kết nối đều raise, không retry/reconnect loop.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from pathlib import Path

from miro.browser.errors import RegistryError
from miro.browser.runtime import ManagedChromeSession, _urls_same_destination

PROFILE_DIRECTORY = "Profile 20"
THREADS_ORIGIN = "https://www.threads.com/"


async def connect_over_cdp(endpoint: str):
    """1 connect_over_cdp tới Chrome có sẵn. Playwright là dependency tùy chọn
    của connector này (runtime/test không cần)."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RegistryError(
            "PLAYWRIGHT_MISSING: cai playwright de chay live-read; "
            "khong tu mo browser thay the") from None
    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.connect_over_cdp(endpoint)
    except Exception as error:
        try:
            await pw.stop()
        except Exception:
            pass
        raise RegistryError(
            "CDP_UNAVAILABLE: Chrome remote-debugging chua bat; "
            "khong tu mo browser thay the (" + type(error).__name__ + ")") from None
    try:
        browser._miro_pw_stop = pw.stop  # type: ignore[attr-defined]
    except Exception:
        pass
    return browser


async def threads_actor(page, record=None) -> str:
    """Verify actor read-only cho Threads: @username từ URL bài/profile.
    Không đọc cookie/storage, không click."""
    url = getattr(page, "url", "") or ""
    match = re.search(r"threads\.com/@([A-Za-z0-9._]{1,30})", str(url))
    if not match:
        raise RegistryError("ACCOUNT_MISMATCH: khong thay @username Threads tren tab")
    return match.group(1)


async def _cdp_target_id(session: ManagedChromeSession, page) -> str:
    """targetId CDP that (kieu A `browser_runtime._target`).

    Thu tuu: attr `target_id` tren page -> CDP
    `context.new_cdp_session(page)` + `Target.getTargetInfo` -> "" (caller
    fallback key on dinh theo object)."""
    target = getattr(page, "target_id", None)
    if isinstance(target, str) and target:
        return target
    if callable(target):
        try:
            resolved = target()
            if asyncio.iscoroutine(resolved):
                resolved = await resolved
            if resolved:
                return str(resolved)
        except Exception:
            pass
    for context in list(getattr(session.runtime.browser, "contexts", []) or []):
        if page not in list(getattr(context, "pages", []) or []):
            continue
        factory = getattr(context, "new_cdp_session", None)
        if not callable(factory):
            break
        cdp = factory(page)
        if asyncio.iscoroutine(cdp):
            cdp = await cdp
        try:
            info = cdp.send("Target.getTargetInfo")
            if asyncio.iscoroutine(info):
                info = await info
            target_id = ((info or {}).get("targetInfo") or {}).get("targetId")
            if target_id:
                return str(target_id)
        except Exception:
            break
        finally:
            detach = getattr(cdp, "detach", None)
            if callable(detach):
                try:
                    out = detach()
                    if asyncio.iscoroutine(out):
                        await out
                except Exception:
                    pass
        break
    return ""


async def register_live_tab(session: ManagedChromeSession, url: str, *,
                      platform_id: str, profile_id: str,
                      expected_account: str = "") -> dict:
    """Đăng ký tab Chrome có sẵn đang mở đúng URL vào store để acquire.
    Không tạo tab, không navigate.

    Luật 1-tab/platform: platform đã có tab open (cùng browser + profile +
    platform, status open) thì dùng đúng tab đó (reused), KHÔNG đăng ký
    tab thứ 2 — kể cả khi URL yêu cầu khác (acquire/read verify URL sau).
    Chưa có tab nào mà vẫn ở trạng thái verify (không hạ chuẩn verify) →
    TAB_REQUIRED_OPEN_FIRST: mở tab trước, không tự new_page/goto.
    Tab chưa mở sẵn → TAB_REQUIRED_OPEN_FIRST."""
    store = session.runtime.store
    existing = [r for r in store.list("tab")
                if r.get("browserInstanceId") == session.runtime.instance_id
                and r.get("profileBindingId") == profile_id
                and r.get("platformId") == platform_id
                and r.get("status") == "open"]
    if existing:
        record = sorted(existing,
                        key=lambda r: float(r.get("lastUsedAt", 0)))[0]
        page = session.runtime.pages.get(record.get("targetId", ""))
        if page is None or getattr(page, "is_closed", lambda: True)():
            for candidate in session.runtime._all_pages():
                current = getattr(candidate, "url", None)
                if isinstance(current, str) and _urls_same_destination(
                        current, record.get("url", "")):
                    session.runtime.pages[record["targetId"]] = candidate
                    break
        record["lastUsedAt"] = time.time()
        return store.put("tab", record["id"], record)
    for page in session.runtime._all_pages():
        current = getattr(page, "url", None)
        if isinstance(current, str) and _urls_same_destination(current, url):
            target_id = await _cdp_target_id(session, page)
            if not target_id:
                target_id = f"live-{id(page):x}"
            session.runtime.pages[target_id] = page
            record = {
                "id": f"{session.runtime.instance_id}:{target_id}",
                "targetId": target_id, "url": url,
                "profileBindingId": profile_id,
                "browserInstanceId": session.runtime.instance_id,
                "platformId": platform_id,
                "expectedAccountId": expected_account,
                "status": "open", "lastUsedAt": 0.0,
            }
            return session.runtime.store.put("tab", record["id"], record)
    raise RegistryError(
        "TAB_REQUIRED_OPEN_FIRST: mo san 1 tab cua platform "
        f"'{platform_id}' trong Chrome Profile 20 truoc; "
        "connector khong tu tao/navigate tab")


async def read_url_once(*, connect=connect_over_cdp, user_data_dir: str,
                        database, url: str,
                        profile_directory: str = PROFILE_DIRECTORY,
                        platform_id: str = "threads",
                        expected_account: str = "",
                        max_chars: int = 4000) -> dict:
    """Entry point read-only: open (1 CDP) → bind profile → acquire → read →
    release → disconnect CDP. Trả {url, account, text, leaseFence}."""
    session = await ManagedChromeSession.open(
        connect, user_data_dir, database,
        allowed_origins=(THREADS_ORIGIN,),
        account_providers={"threads": threads_actor})
    stop_pw = None
    try:
        profile = await session.runtime.bind_profile(user_data_dir, profile_directory)
        await register_live_tab(session, url, platform_id=platform_id,
                           profile_id=profile["id"],
                           expected_account=expected_account)
        acquired = await session.acquire_managed_tab(
            platform_id=platform_id, url=url, caller="live-read",
            profileBindingId=profile["id"])
        try:
            data = await acquired.read(max_chars=max_chars)
        finally:
            await acquired.release()
        content = data.get("content") or {}
        return {"url": content.get("url") or url,
                "account": acquired.record.get("expectedAccountId") or "",
                "title": content.get("title") or "",
                "text": content.get("text") or "",
                "leaseFence": data.get("leaseFence")}
    finally:
        try:
            stop_pw = getattr(session.runtime.browser, "_miro_pw_stop", None)
        except Exception:
            stop_pw = None
        await session.close()
        if callable(stop_pw):
            try:
                result = stop_pw()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Live-read 1 URL Threads qua Chrome Profile 20 co san (chi doc).")
    parser.add_argument("--url", required=True, help="URL bai Threads can doc")
    parser.add_argument("--user-data-dir", required=True,
                        help="Chrome user-data-dir dang chay remote-debugging")
    parser.add_argument("--db", default="",
                        help="Duong dan lease store sqlite (mac dinh: ./var/live-read-leases.sqlite)")
    parser.add_argument("--profile-directory", default=PROFILE_DIRECTORY)
    parser.add_argument("--platform-id", default="threads")
    parser.add_argument("--expected-account", default="",
                        help="@username Threads (khong @ cung duoc); de trong = chi doc username tu tab")
    parser.add_argument("--max-chars", type=int, default=4000)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    db = args.db or str(Path.cwd() / "var" / "live-read-leases.sqlite")
    try:
        out = asyncio.run(read_url_once(
            user_data_dir=args.user_data_dir, database=db, url=args.url,
            profile_directory=args.profile_directory,
            platform_id=args.platform_id,
            expected_account=args.expected_account.lstrip("@"),
            max_chars=args.max_chars))
    except RegistryError as error:
        print("LIVE_READ_DENIED: " + str(error), file=sys.stderr)
        return 2
    except Exception as error:
        print("LIVE_READ_FAILED: " + type(error).__name__ + ": " + str(error),
              file=sys.stderr)
        return 1
    print("URL: " + out["url"])
    print("ACCOUNT: @" + out["account"] if out["account"] else "ACCOUNT: (tu tab)")
    print("TITLE: " + (out["title"] or ""))
    print("---TEXT---")
    print(out["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
