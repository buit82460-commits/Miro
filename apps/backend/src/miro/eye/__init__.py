"""REA eye collectors — MAT DUY NHAT cho moi thao tac trinh duyet (luat cung).

Quy tac: moi thao tac tren trinh duyet BAT BUOC co eye collector tuong ung
o day. Tay (adapter LivePage/worker) chi nhan page handle + records tu mat,
KHONG tu chay locator DOM de doi chieu. Tay lam khi mat chua do = vi pham
luat cung (AGENTS.md "LUAT CUNG REA-MAT").

Contract record:
- Post/feed: {author, tag, url, post_id, has_video, text}
- Comment:   {author, text, time, post_id}
"""
from __future__ import annotations

from contextlib import suppress


async def _one(page, selector: str):
    """Lay 1 locator chiu ca page that (.first) va fake (tra thang)."""
    raw = page.locator(selector)
    return getattr(raw, "first", raw)


async def _texts(locator, limit: int = 50) -> list[str]:
    out: list[str] = []
    with suppress(Exception):
        els = await locator.all()
    for el in (els or [])[: max(0, limit)]:
        with suppress(Exception):
            text = ((await el.inner_text()) or "").strip()
            if text:
                out.append(text)
    return out


async def _first_visible_text(page, selectors: list[str]) -> str:
    for sel in selectors:
        with suppress(Exception):
            raw = page.locator(sel)
            loc = getattr(raw, "first", raw)
            await loc.wait_for(state="visible", timeout=3000)
            return ((await loc.inner_text()) or "").strip()
    return ""


# ---- TikTok ----

async def tiktok_comment_records(page, aweme_id: str = "",
                                 limit: int = 20) -> list[dict]:
    """Eye comment TikTok: doc khung comment, moi comment 1 record
    {author, text, time, post_id}. Locator hep trong scope comment."""
    records: list[dict] = []
    items: list = []
    with suppress(Exception):
        items = await page.locator(
            '[data-e2e="comment-item"], [data-e2e="comment-level-1"], '
            'div[class*="CommentItem"], div[class*="comment-item"]').all()
    if not items:
        with suppress(Exception):
            texts = await _texts(page.locator(
                'div:has(> span[data-e2e="comment-time"]), '
                'div:has(> p:has-text("ago"))'), limit * 2)
        for text in texts[: max(1, limit)]:
            records.append({"author": "", "text": text[:300],
                            "time": "", "post_id": str(aweme_id or "")})
        return records
    for item in (items or [])[: max(1, limit)]:
        with suppress(Exception):
            raw = ((await item.inner_text()) or "").strip()
            author = ""
            with suppress(Exception):
                a = await _one(item, 'a[href^="/@"]')
                href = await a.get_attribute("href")
                if href and href.startswith("/@"):
                    author = "@" + href[2:].split("/")[0].split("?")[0]
            import re
            time_hit = re.search(
                r"(\d+\s*(?:s|m|h|d|w|giây|phút|giờ|ngày|tuần)\s*ago"
                r"|\d{4}-\d{2}-\d{2})", raw)
            records.append({
                "author": author,
                "text": raw[:300],
                "time": time_hit.group(1) if time_hit else "",
                "post_id": str(aweme_id or ""),
            })
    return records


async def tiktok_video_record(page) -> dict:
    """Eye video TikTok: caption + counts + aweme_id tu URL hien tai."""
    import re
    url = ""
    with suppress(Exception):
        url = str(page.url or "")
    aweme = ""
    hit = re.search(r"/video/(\d+)", url or "")
    if hit:
        aweme = hit.group(1)
    caption = await _first_visible_text(page, [
        '[data-e2e="browse-video-desc"]',
        'h1[data-e2e="video-desc"]',
        '[data-e2e="video-desc"]',
    ])
    counts = {}
    for key, sel in (("likes", '[data-e2e="like-count"]'),
                     ("comments", '[data-e2e="comment-count"]'),
                     ("shares", '[data-e2e="share-count"]')):
        with suppress(Exception):
            loc = await _one(page, sel)
            counts[key] = ((await loc.inner_text())
                           or "").strip()
    return {"url": url, "post_id": aweme, "caption": caption,
            "counts": counts}


async def tiktok_profile_record(page) -> dict:
    """Eye profile TikTok: nickname + handle + counts + bio."""
    import re
    url = ""
    with suppress(Exception):
        url = str(page.url or "")
    handle = ""
    hit = re.search(r"/@([^/?]+)", url or "")
    if hit:
        handle = "@" + hit.group(1)
    name = await _first_visible_text(page, [
        '[data-e2e="user-title"]', 'h1[data-e2e="user-title"]', "h1"])
    counts = {}
    for key, sel in (("following", '[data-e2e="following-count"]'),
                     ("followers", '[data-e2e="followers-count"]'),
                     ("likes", '[data-e2e="likes-count"]')):
        with suppress(Exception):
            loc = await _one(page, sel)
            counts[key] = ((await loc.inner_text())
                           or "").strip()
    return {"handle": handle, "name": name, "url": url, "counts": counts}


# ---- Threads ----

async def threads_profile_record(page, owner: str = "") -> dict:
    """Eye profile Threads: actor + bio + counts tu snapshot DOM."""
    from miro.publishing.publisher import collect_post_records
    records = await collect_post_records(page, owner, limit=5)
    return {"owner": owner, "records": records}


# ---- Facebook ----

async def facebook_reel_record(page) -> dict:
    """Eye reel Facebook: url reel + caption hien thi."""
    url = ""
    with suppress(Exception):
        url = str(page.url or "")
    caption = await _first_visible_text(page, [
        'div[data-ad-preview="message"]',
        'div[dir="auto"]:has-text("reel")',
    ])
    return {"url": url, "caption": caption[:300]}


# ---- Instagram ----

async def instagram_reel_record(page) -> dict:
    """Eye reel Instagram: shortcode + caption tu URL + meta."""
    import re
    url = ""
    with suppress(Exception):
        url = str(page.url or "")
    code = ""
    hit = re.search(r"/reel/([A-Za-z0-9_-]+)", url or "")
    if hit:
        code = hit.group(1)
    caption = await _first_visible_text(page, [
        'h1', 'div[role="dialog"] div[dir="auto"]'])
    return {"url": url, "post_id": code, "caption": caption[:300]}


# ---- YouTube (Data API — eye = read-back API, khong DOM) ----

def youtube_video_record(item: dict) -> dict:
    """Eye YouTube: chuan hoa read-back videos.list thanh record."""
    snippet = (item or {}).get("snippet") or {}
    status = (item or {}).get("status") or {}
    return {"post_id": (item or {}).get("id", ""),
            "title": (snippet or {}).get("title", ""),
            "privacyStatus": (status or {}).get("privacyStatus", ""),
            "url": f"https://www.youtube.com/watch?v={(item or {}).get('id', '')}"}


# ---- Shopee (read-only research, BLOCKED live Seller) ----

async def shopee_product_record(page) -> dict:
    """Eye san pham shopee.vn: ten + gia + danh gia."""
    url = ""
    with suppress(Exception):
        url = str(page.url or "")
    name = await _first_visible_text(page, [
        'div[class*="product-title"]', "h1"])
    price = await _first_visible_text(page, [
        'div[class*="product-price"]', 'span[class*="price"]'])
    return {"url": url, "name": name[:200], "price": price[:100]}


# ---- ChatGPT ----

async def chatgpt_conversation_record(page) -> dict:
    """Eye hoi thoai ChatGPT: url + so turn + preview reply cuoi."""
    url = ""
    with suppress(Exception):
        url = str(page.url or "")
    turns = 0
    with suppress(Exception):
        turns = await page.locator("[data-message-author-role]").count()
    preview = ""
    with suppress(Exception):
        last = page.locator("[data-message-author-role='assistant']").last
        preview = ((await last.inner_text())
                   or "").strip()[-300:]
    return {"url": url, "turns": turns, "reply_preview": preview}


# ---- Flow ----

async def flow_video_record(page) -> dict:
    """Eye video Flow: url + trang thai render + video src (neu co)."""
    url = ""
    with suppress(Exception):
        url = str(page.url or "")
    src = ""
    with suppress(Exception):
        vid = await _one(page, "video")
        src = (await vid.get_attribute("src")) or ""
    return {"url": url, "video_src": src,
            "rendered": bool(src)}


# ---- Upload/dirty state: mat doc (read-only) thay evaluate truc tiep ----

async def upload_state(page) -> dict:
    """Eye upload/dirty: tab co file dang upload / form dirty khong.

    Read-only (evaluate chi doc, khong bam). Runtime guard goi mat nay
    truoc navigate/submit; True => cam (TAB_PROTECTED_NO_NAVIGATE).
    """
    out: dict = {"activeUpload": False, "dirtyForm": False}
    with suppress(Exception):
        loc = await _one(page, 'input[type="file"]')
        try:
            n = await loc.count()
        except Exception:
            n = 0
        if n and n > 0:
            with suppress(Exception):
                has_files = await page.evaluate(
                    """() => {
                        try {
                            for (const i of document.querySelectorAll(
                                'input[type="file"]')) {
                                if (i.files && i.files.length > 0) return true;
                            }
                        } catch (e) {}
                        return false;
                    }""")
                if has_files is True:
                    out["activeUpload"] = True
    with suppress(Exception):
        flag = await page.evaluate(
            """() => Boolean(
                window.__miroUploadActive ||
                document.documentElement?.dataset?.miroUploading === '1')""")
        if flag is True:
            out["activeUpload"] = True
    with suppress(Exception):
        dirty = await page.evaluate(
            """() => Boolean(
                window.__miroDirtyForm ||
                typeof window.onbeforeunload === 'function')""")
        if dirty is True:
            out["dirtyForm"] = True
    return out


EYE_COVERAGE = {
    "threads": ["threads_profile_record (via collect_post_records)",
                "composer_state (composer/post_btn/upload)",
                "ack_state (toast/network/composer-closed)",
                "tab_state (profile/verify/navigate/read)"],
    "facebook": ["facebook_reel_record",
                 "composer_state (composer/post_btn/upload)",
                 "ack_state (toast/network/composer-closed)",
                 "tab_state (profile/verify/navigate/read)"],
    "tiktok": ["tiktok_comment_records", "tiktok_video_record",
               "tiktok_profile_record",
               "engage_records (like/repost/follow/view + receipt)",
               "composer_state (composer/post_btn/upload)",
               "ack_state (toast/network/composer-closed)",
               "tab_state (profile/verify/navigate/read)"],
    "instagram": ["instagram_reel_record",
                  "composer_state (composer/post_btn/upload)",
                  "ack_state (toast/network/composer-closed)",
                  "tab_state (profile/verify/navigate/read)"],
    "youtube": ["youtube_video_record (API read-back)",
                "tab_state (profile/verify/navigate/read)"],
    "shopee": ["shopee_product_record (read-only)",
               "composer_state (composer/save_btn/form)",
               "ack_state (toast/network/composer-closed)",
               "tab_state (profile/verify/navigate/read)"],
    "chatgpt": ["chatgpt_conversation_record",
                "composer_state (composer/send_btn)",
                "ack_state (streaming-done)",
                "tab_state (profile/verify/navigate/read)"],
    "flow": ["flow_video_record",
             "composer_state (composer/generate_btn)",
             "ack_state (video-src/stable)",
             "tab_state (profile/verify/navigate/read)"],
    "desktop": ["desktop_window_record (resolve_window read-only)",
                "desktop_doc_record (resolve_doc read-only)"],
}


# ---- Engage (like/repost/follow/view): mat doc nut + trang thai TRUOC bam ----

async def engage_records(page, platform: str = "tiktok") -> dict:
    """Eye engage: trang thai cac nut (like/repost/follow) + video hien tai.

    Tay chi bam nut mat da thay (visible+enabled); receipt sau bam do
    mat doc lai o caller.
    """
    out: dict = {"platform": platform, "buttons": {}, "video": {}}
    with suppress(Exception):
        out["video"] = await tiktok_video_record(page) if platform == "tiktok" \
            else {}
    sels = {"like": ['button[data-e2e="like-button"]',
                     'span[data-e2e="like-icon"]',
                     'button[aria-label*="Like"]'],
            "repost": ['button[data-e2e="share-button"]',
                       'button[aria-label*="Share"]'],
            "follow": ['button[data-e2e="follow-button"]',
                       'button:has-text("Follow")'],
            "comment_btn": ['div[data-e2e="comment-post"]',
                            'button[data-e2e="comment-post"]']}
    for name, cand in sels.items():
        for sel in cand:
            with suppress(Exception):
                loc = await _one(page, sel)
                await loc.wait_for(state="visible", timeout=2000)
                out["buttons"][name] = {
                    "selector": sel,
                    "enabled": bool(await loc.is_enabled()),
                    "label": (((await loc.inner_text()) or "").strip()[:80]),
                }
                break
    return out


# ---- Composer: mat doc o nhap + nut submit TRUOC khi tay dien/bam ----

async def composer_state(page, platform: str) -> dict:
    """Eye composer: o nhap text + nut submit + file input.

    Tra handle mo ta (selector + enabled); tay chi dung dung selector
    mat da xac nhan visible.
    """
    from miro.adapters.live import COMPOSER_OPEN, POST_BUTTON, TEXT_BOX
    state: dict = {"platform": platform, "box": {}, "submit": {},
                   "file_input": False, "dialog": False}
    for sel in TEXT_BOX.get(platform, []):
        with suppress(Exception):
            loc = await _one(page, sel)
            await loc.wait_for(state="visible", timeout=3000)
            state["box"] = {"selector": sel,
                            "enabled": bool(await loc.is_enabled())}
            break
    for sel in POST_BUTTON.get(platform, []):
        with suppress(Exception):
            loc = await _one(page, sel)
            await loc.wait_for(state="visible", timeout=3000)
            if await loc.is_enabled():
                label = ((await loc.inner_text()) or "").strip()
                if label in ("Post", "Đăng", "Lưu", "Save", "Publish",
                             "Generate", "Create", "Send", "Gửi"):
                    state["submit"] = {"selector": sel, "label": label,
                                       "enabled": True}
                    break
    with suppress(Exception):
        finput = await _one(page, 'input[type="file"]')
        state["file_input"] = await finput.count() > 0
    with suppress(Exception):
        state["dialog"] = await page.locator(
            '[role="dialog"]').last.is_visible()
    return state


# ---- Ack: mat doc tin hieu sau click (toast/network/composer) ----

async def ack_state(page, platform: str,
                    hints: tuple = ()) -> dict:
    """Eye ack: toast Posted + composer dong/mo + network hint da thay.

    Tay goi sau click 1 lan de lay receipt; khong co tin hieu = UNKNOWN.
    """
    state: dict = {"toast": False, "closed": False, "hints": list(hints)}
    with suppress(Exception):
        for t in await page.locator('[role="status"], [role="alert"]').all():
            with suppress(Exception):
                msg = ((await t.inner_text()) or "").strip().lower()
                if msg and ("posted" in msg or "đã đăng" in msg
                            or "published" in msg) and "posting" not in msg:
                    state["toast"] = True
                    break
    return state


# ---- Tab: mat doc profile/verify/navigate/read (runtime.py) ----

async def tab_state(page) -> dict:
    """Eye tab: url + title + text preview (thay evaluate truc tiep)."""
    out: dict = {"url": "", "title": "", "text": ""}
    with suppress(Exception):
        out["url"] = str(page.url or "")
    with suppress(Exception):
        out["title"] = str(await page.title() or "")
    with suppress(Exception):
        body = page.locator("body")
        first = getattr(body, "first", body)
        out["text"] = ((await first.inner_text()) or "")[:2000]
    if not out["text"]:
        # Fallback: page khong co body text qua locator (fake/legacy) thi
        # doc qua evaluate read-only — van la mat, khong phai tay.
        with suppress(Exception):
            legacy = await page.evaluate(
                "(limit)=>({url:location.href,title:document.title,"
                "text:(document.body?.innerText||'').slice(0,limit)})", 2000)
            if isinstance(legacy, dict):
                out["text"] = str(legacy.get("text") or "")[:2000]
                out["url"] = out["url"] or str(legacy.get("url") or "")
                out["title"] = out["title"] or str(legacy.get("title") or "")
    return out


async def profile_path_record(page) -> dict:
    """Eye profile chrome://version: #profile_path (thay locator truc tiep)."""
    path = ""
    with suppress(Exception):
        raw = page.locator("#profile_path")
        loc = getattr(raw, "first", raw)
        path = ((await loc.inner_text()) or "").strip()
    return {"profile_path": path}


# ---- Desktop: mat doc window/doc TRUOC khi click (act.py) ----

def desktop_window_record(ops, app=None, title_substr=None) -> dict:
    """Eye desktop: list_windows read-only (mat), chua click."""
    res = ops.list_windows(app=app)
    if not isinstance(res, dict) or not res.get("ok"):
        return {"ok": False, "windows": []}
    items = res.get("windows") or []
    if title_substr:
        needle = str(title_substr).lower()
        items = [w for w in items
                 if needle in str(w.get("title", "")).lower()]
    return {"ok": True, "windows": items}


def desktop_doc_record(ops, window_id, doc) -> dict:
    """Eye desktop: find tab read-only (mat), chua click."""
    res = ops.find(window_id, role="tab", name=doc)
    if not isinstance(res, dict) or not res.get("ok"):
        return {"ok": False, "matches": []}
    return {"ok": True, "matches": res.get("matches") or []}
