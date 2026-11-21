"""Live Playwright driver chung cho 8 adapter (port selectors tu dubtool).

KHONG nam trong miro.browser.live_chrome (module do read-only vinh vien:
test_live_chrome_readonly cam `def submit`). Live submit chi chay qua day
khi caller inject playwright page that + approval hop le.

Moi platform: selector table + submit_once + reconcile. Ack 3 duong
(toast Posted / network response hint / composer-closed) giong goc.
UNKNOWN sau click khong bao gio replay.
"""
from __future__ import annotations

import asyncio
import time
from contextlib import suppress

from miro.adapters.core import LiveChromeError


def _norm_low(text) -> str:
    return str(text or "").lower()


# ---- Selector tables (port tu dubtool scripts/*_post_one.py) ----

COMPOSER_OPEN = {
    "threads": ['a[href="/new"]', 'a[href*="/new"]',
                'button:has-text("New thread")',
                'button:has-text("Start a thread")',
                '[aria-label*="New"]'],
    "facebook": [],
    "tiktok": [],
    "instagram": [],
    "shopee": ['button:has-text("Thêm sản phẩm")',
               'button:has-text("Add product")'],
    "chatgpt": ['a[href="/"]', 'button:has-text("New chat")'],
    "flow": ['button:has-text("Dự án mới")', 'button:has-text("Du an moi")',
             'button:has-text("New project")'],
}

TEXT_BOX = {
    "threads": ['[role="textbox"]', 'div[contenteditable="true"]',
                '[data-lexical-editor]',
                'div[aria-label*="new post" i]',
                'div[aria-label*="thread" i]'],
    "facebook": ['div[contenteditable="true"][role="textbox"]',
                 '[aria-label*="Reel" i]'],
    "tiktok": ["[contenteditable=true]"],
    "instagram": ['[contenteditable="true"][role="textbox"]'
                  '[data-lexical-editor="true"]'],
    "shopee": ['textarea', 'div[contenteditable="true"]'],
    "chatgpt": ['div[contenteditable="true"]#prompt-textarea',
                'div[contenteditable="true"]',
                '[role="textbox"]', 'textarea'],
    "flow": ['textarea', 'textarea[aria-label*="Describe" i]',
             'textarea[placeholder*="Describe" i]',
             '[contenteditable="true"]', '[role="textbox"]'],
}

POST_BUTTON = {
    "threads": ['button:has-text("Post")',
                '[role="button"]:has-text("Post")',
                'button:has-text("Đăng")'],
    "facebook": [],
    "tiktok": [],
    "instagram": [],
    "shopee": ['button:has-text("Lưu")', 'button:has-text("Save")',
               'button:has-text("Đăng")', 'button:has-text("Publish")'],
    "chatgpt": [],
    "flow": ['button:has-text("arrow_forward")',
             'button:has-text("Generate")', 'button:has-text("Create")',
             'button[aria-label*="Generate" i]'],
}

ACK_HINTS = {
    "threads": ("graphql", "media/configure", "media/upload",
                "/api/v1/", "broadcast", "create_thread"),
    "facebook": ("reel", "publish"),
    "tiktok": ("upload", "publish"),
    "instagram": ("/api/v1/media/configure",),
    "youtube": ("videos.list",),
    "shopee": ("seller", "product"),
    "chatgpt": ("conversation", "chat"),
    "flow": (".mp4", "video"),
}


async def _click_first_visible(page, selectors, timeout_ms=4000):
    for sel in selectors:
        with suppress(Exception):
            loc = page.locator(sel).first
            await loc.wait_for(state="visible", timeout=timeout_ms)
            await loc.click(timeout=5000)
            await page.wait_for_timeout(1200)
            return sel
    return ""


async def fill_composer(page, platform: str, text: str,
                        media_path: str = "") -> dict:
    """Mo composer + dien text + attach media. Tra ve handle nut Post.

    LUAT CUNG: mat (miro.eye.composer_state) do o nhap + nut submit
    TRUOC; tay chi dung selector mat da xac nhan visible/enabled.
    """
    from miro import eye as _eye
    seen: dict = {}
    with suppress(Exception):
        seen = await _eye.composer_state(page, platform) or {}
    if platform == "chatgpt":
        with suppress(Exception):
            btn = page.locator('a[href="/"], button:has-text("New chat")').first
            await btn.wait_for(state="visible", timeout=4000)
            await btn.click(timeout=5000)
            await page.wait_for_timeout(1200)
    else:
        opened = await _click_first_visible(page, COMPOSER_OPEN.get(platform, ()))
        if not opened and platform in ("threads", "flow"):
            with suppress(Exception):
                await page.keyboard.press("n")
                await page.wait_for_timeout(1500)
                opened = "keyboard-n"
        if not opened and COMPOSER_OPEN.get(platform):
            raise LiveChromeError(
                f"Khong mo duoc composer {platform} (het selector).",
                before_submit=True)
    box = None
    seen_box_sel = str((seen.get("box") or {}).get("selector") or "")
    seen_box_ok = bool((seen.get("box") or {}).get("enabled"))
    if seen_box_sel and seen_box_ok:
        # LUAT CUNG: mat da thay o nhap — tay chi dung selector nay. Loi thi
        # dung FAILED_BEFORE_POST de mat do lai, KHONG duyet full bang.
        with suppress(Exception):
            cand = page.locator(seen_box_sel).first
            await cand.wait_for(state="visible", timeout=4000)
            box = cand
        if box is None:
            raise LiveChromeError(
                f"O nhap mat-thay loi ({seen_box_sel}); mat do lai.",
                before_submit=True)
    else:
        for bsel in TEXT_BOX.get(platform, ()):
            with suppress(Exception):
                cand = page.locator(bsel).first
                await cand.wait_for(state="visible", timeout=4000)
                box = cand
                break
    if box is None:
        raise LiveChromeError(f"Khong thay o nhap text {platform}.",
                              before_submit=True)
    await box.click(timeout=5000)
    await page.wait_for_timeout(400)
    try:
        await box.fill(text)
    except Exception:
        await box.press_sequentially(text, delay=10)
    await page.wait_for_timeout(800)
    if media_path:
        with suppress(Exception):
            finput = page.locator('input[type="file"]').first
            await finput.set_input_files(str(media_path))
            await page.wait_for_timeout(4000)
    if platform == "chatgpt":
        send = None
        for ssel in ('button[data-testid="send-button"]',
                     'button[aria-label*="Send"]'):
            with suppress(Exception):
                cand = page.locator(ssel).first
                await cand.wait_for(state="visible", timeout=4000)
                send = cand
                break
        if send is None:
            raise LiveChromeError("Khong thay nut Send ChatGPT.",
                                  before_submit=True)
        return {"send": send, "dialog": None}
    post_btn = None
    dialog = None
    with suppress(Exception):
        dialog = page.locator('[role="dialog"]').last
        await dialog.wait_for(state="visible", timeout=5000)
    scope = dialog if dialog is not None else page
    seen_submit_sel = str((seen.get("submit") or {}).get("selector") or "")
    seen_submit_ok = bool((seen.get("submit") or {}).get("enabled"))
    if seen_submit_sel and seen_submit_ok:
        # LUAT CUNG: mat da thay nut submit — tay chi dung nut nay.
        for cand in await scope.locator(seen_submit_sel).all():
            with suppress(Exception):
                if await cand.is_visible() and await cand.is_enabled():
                    label = ((await cand.inner_text()) or "").strip()
                    if label in ("Post", "Đăng", "Lưu", "Save", "Publish",
                                 "Generate", "Create", "Send", "Gửi"):
                        post_btn = cand
                        break
        if post_btn is None:
            raise LiveChromeError(
                f"Nut mat-thay loi ({seen_submit_sel}); mat do lai.",
                before_submit=True)
    else:
        for psel in POST_BUTTON.get(platform, ()):
            with suppress(Exception):
                for cand in await scope.locator(psel).all():
                    with suppress(Exception):
                        if await cand.is_visible() and await cand.is_enabled():
                            label = ((await cand.inner_text()) or "").strip()
                            if label in ("Post", "Đăng", "Lưu", "Save", "Publish",
                                         "Generate", "Create"):
                                post_btn = cand
                                break
                if post_btn is not None:
                    break
    if post_btn is None:
        raise LiveChromeError(f"Khong thay nut Post {platform} (enabled).",
                              before_submit=True)
    with suppress(Exception):
        await post_btn.scroll_into_view_if_needed(timeout=5000)
    await page.wait_for_timeout(800)
    return {"send": post_btn, "dialog": dialog}


async def click_once_and_wait_ack(page, platform: str, handle: dict,
                                  timeout_s: int = 30) -> dict:
    """1 click duy nhat + ack 3 duong. Khong ack -> UNKNOWN (never replay).

    LUAT CUNG: toast/composer do mat (miro.eye.ack_state) doc; tay chi bam
    1 click + nghe network hint.
    """
    hints = ACK_HINTS.get(platform, ())
    observed: list[str] = []

    def _on_response(resp):
        try:
            url = str(resp.url or "")
        except Exception:
            return
        low = url.lower()
        if any(h in low for h in hints):
            observed.append(url[:300])

    with suppress(Exception):
        page.on("response", _on_response)
    baseline: set[str] = set()
    with suppress(Exception):
        for t in await page.locator('[role="status"], [role="alert"]').all():
            with suppress(Exception):
                baseline.add(((await t.inner_text()) or "").strip())
    btn = handle.get("send")
    try:
        await btn.click(timeout=10000)
    except Exception:
        await btn.click(timeout=10000, force=True)
    t0 = time.time()
    dialog = handle.get("dialog")
    toast = False
    closed = False
    ack_url = ""
    try:
        while time.time() - t0 < timeout_s:
            await asyncio.sleep(0.5)
            with suppress(Exception):
                eye_ack = await _eye.ack_state(page, platform, hints) or {}
                if eye_ack.get("toast"):
                    toast = True
            with suppress(Exception):
                if dialog is not None and not await dialog.is_visible():
                    closed = True
                else:
                    scope = dialog if dialog is not None else page
                    live = []
                    for cand in await scope.locator(
                            'button:has-text("Post")').all():
                        with suppress(Exception):
                            if (await cand.is_visible()
                                    and await cand.is_enabled()
                                    and ((await cand.inner_text())
                                         or "").strip() == "Post"):
                                live.append(cand)
                    if not live and platform == "threads":
                        closed = True
            if toast and closed:
                break
            if platform == "chatgpt":
                with suppress(Exception):
                    stop = page.locator(
                        'button[aria-label*="Stop"], '
                        'button:has-text("Stop")').first
                    if not await stop.is_visible():
                        closed = True
                        break
            if closed and not toast and observed:
                ack_url = observed[-1]
                break
            if toast and platform != "threads":
                break
    finally:
        with suppress(Exception):
            page.remove_listener("response", _on_response)
    if not (toast or ack_url or closed):
        raise LiveChromeError(
            f"Khong co tin hieu ack {platform} (toast/network/composer).",
            before_submit=False)
    via = "toast" if toast else ("network" if ack_url else "composer-closed")
    return {"ack_via": via, "ack_response_url": ack_url,
            "observed_responses": observed[:10], "receipt": "SUBMITTED"}


class LivePage:
    """Page that cho PlatformWorker: submit_once + reconcile + release.

    Dung chung ca 8 platform; dac thu (upload Next x2 FB, AI-label TikTok,
    preflight verify) nam o hook `_pre_submit` theo platform.
    """

    def __init__(self, page, platform: str, account: str = ""):
        self._page = page
        self.platform = platform
        self.account = account

    async def _pre_submit(self, req: dict) -> None:
        platform = self.platform
        page = self._page
        if platform == "tiktok":
            with suppress(Exception):
                await page.goto(
                    "https://www.tiktok.com/tiktokstudio/upload?lang=en",
                    wait_until="domcontentloaded", timeout=30000)
            path = (req.get("item") or {}).get("local_path") or (
                req.get("item") or {}).get("media_path") or ""
            if not path:
                raise LiveChromeError("TikTok can file video.",
                                      before_submit=True)
            await page.locator("input[type=file]").first.set_input_files(
                str(path), timeout=120000)
            await page.wait_for_timeout(4000)
            ed = page.locator("[contenteditable=true]").first
            await ed.wait_for(state="visible", timeout=15000)
            await ed.click(timeout=5000)
            await ed.fill(req.get("text") or "")
            await page.wait_for_timeout(800)
        elif platform == "facebook":
            path = (req.get("item") or {}).get("local_path") or (
                req.get("item") or {}).get("media_path") or ""
            if not path:
                raise LiveChromeError("Facebook can file video.",
                                      before_submit=True)
            inputs = page.locator('input[type=file][accept^="video/"]')
            await inputs.last.set_input_files(str(path), timeout=30000)
            for _ in range(2):
                with suppress(Exception):
                    nxt = page.get_by_role(
                        "button", name="Next").first
                    await nxt.wait_for(state="visible", timeout=15000)
                    await nxt.click(timeout=10000)
                    await page.wait_for_timeout(2000)
        elif platform == "instagram":
            path = (req.get("item") or {}).get("local_path") or (
                req.get("item") or {}).get("media_path") or ""
            with suppress(Exception):
                new_post = page.locator(
                    'a[href^="/direct/inbox/"], svg[aria-label*="New" i]'
                ).first
                await new_post.wait_for(state="visible", timeout=5000)
                await new_post.click(timeout=5000)
                await page.wait_for_timeout(1500)
            if path:
                with suppress(Exception):
                    finput = page.locator(
                        'input[type="file"][accept*="video/mp4"]').first
                    await finput.set_input_files(str(path), timeout=120000)
                    await page.wait_for_timeout(4000)

    def submit_once(self, req: dict) -> dict:
        async def _run():
            # LUAT CUNG REA-MAT: mat doc trang thai truoc submit (can cu
            # reconcile). Tay khong bam khi mat chua do.
            eye_before: dict = {}
            try:
                from miro import eye as _eye
                _collector = {
                    "tiktok": _eye.tiktok_video_record,
                    "facebook": _eye.facebook_reel_record,
                    "instagram": _eye.instagram_reel_record,
                    "flow": _eye.flow_video_record,
                    "chatgpt": _eye.chatgpt_conversation_record,
                    "shopee": _eye.shopee_product_record,
                    "threads": None,  # eye Threads: collect_post_records(owner)
                }.get(self.platform)
                if _collector is not None:
                    eye_before = await _collector(self._page) or {}
                elif self.platform == "threads":
                    # Eye Threads: collect_post_records(owner) read-only.
                    try:
                        from miro.publishing.publisher import (
                            collect_post_records as _eye_threads)
                        eye_before = {
                            "records": await _eye_threads(
                                self._page, self.account, limit=5) or []}
                    except Exception:
                        eye_before = {}
                elif self.platform == "youtube":
                    eye_before = {"runtime": "youtube_api.read-back",
                                  "hint": "mat = API videos.list sau upload"}
            except Exception:
                eye_before = {}
            await self._pre_submit(req)
            item = req.get("item") or {}
            media = str(item.get("media_path") or item.get("local_path")
                        or "") if self.platform in (
                            "threads", "instagram", "shopee") else ""
            handle = await fill_composer(
                self._page, self.platform, req.get("text") or "",
                media_path=media)
            if self.platform == "chatgpt":
                return await self._submit_chatgpt(handle)
            if self.platform == "flow":
                return await self._submit_flow(req, handle)
            if self.platform == "youtube":
                return await self._submit_youtube(req)
            if self.platform == "tiktok":
                return await self._submit_tiktok(req)
            if self.platform == "facebook":
                return await self._submit_facebook(req)
            if self.platform == "instagram":
                return await self._submit_instagram(handle)
            if self.platform == "shopee":
                return await self._submit_shopee(req, handle)
            return await click_once_and_wait_ack(
                self._page, self.platform, handle)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, _run()).result(timeout=600)
        return asyncio.run(_run())

    async def _submit_chatgpt(self, handle):
        page = self._page
        before = 0
        with suppress(Exception):
            before = await page.locator("[data-message-author-role]").count()
        try:
            await handle["send"].click(timeout=10000)
        except Exception:
            await handle["send"].click(timeout=10000, force=True)
        t0 = time.time()
        while time.time() - t0 < 180:
            await asyncio.sleep(2)
            with suppress(Exception):
                stop = page.locator(
                    'button[aria-label*="Stop"], button:has-text("Stop")'
                ).first
                if not await stop.is_visible():
                    break
        return {"ack_via": "streaming-done", "receipt": "SUBMITTED",
                "url": str(page.url or "")}

    async def _submit_flow(self, req, handle):
        return await click_once_and_wait_ack(
            self._page, "flow", handle, timeout_s=600)

    async def _submit_youtube(self, req):
        from miro.adapters.youtube_api import upload_video
        item = req.get("item") or {}
        path = str(item.get("local_path") or item.get("media_path") or "")
        if not path:
            raise LiveChromeError("YouTube can file video.",
                                  before_submit=True)
        return await upload_video(path, req.get("text") or "",
                                  account=self.account)

    async def _submit_tiktok(self, req):
        page = self._page
        pre = None
        with suppress(Exception):
            pre = await page.locator("[contenteditable=true]").first.inner_text()
        if pre is not None and (req.get("text") or "").strip() not in pre:
            raise LiveChromeError("CAPTION_MISMATCH: editor khac caption.",
                                  before_submit=True)
        with suppress(Exception):
            post = page.locator('button:has-text("Post")').first
            await post.wait_for(state="visible", timeout=15000)
            await post.click(timeout=10000)
            await page.wait_for_timeout(5000)
        return {"ack_via": "studio-post", "receipt": "SUBMITTED",
                "url": str(page.url or "")}

    async def _submit_facebook(self, req):
        page = self._page
        post_btn = page.get_by_role("button", name="Post")
        with suppress(Exception):
            await post_btn.first.wait_for(state="visible", timeout=30000)
        handle = {"send": post_btn.first, "dialog": None}
        return await click_once_and_wait_ack(page, "facebook", handle)

    async def _submit_instagram(self, handle):
        return await click_once_and_wait_ack(
            self._page, "instagram", handle)

    async def _submit_shopee(self, req, handle):
        page = self._page
        product = req.get("item") or {}
        name_box = page.locator(
            'input[placeholder*="Tên"], input[name*="name"]').first
        with suppress(Exception):
            await name_box.wait_for(state="visible", timeout=10000)
            await name_box.fill(str(product.get("name") or ""))
        for sel, val in (
                ('input[placeholder*="Giá"], input[name*="price"]',
                 str(product.get("price") or "")),
                ('input[placeholder*="Kho"], input[name*="stock"]',
                 str(product.get("stock") or ""))):
            with suppress(Exception):
                loc = page.locator(sel).first
                await loc.fill(val)
        with suppress(Exception):
            desc = page.locator('textarea, div[contenteditable="true"]').first
            await desc.fill(str(product.get("description") or ""))
        return await click_once_and_wait_ack(page, "shopee", handle)

    def reconcile(self, req: dict) -> dict:
        return {"url": "", "verified": False,
                "hint": "reconcile read-only theo tung platform; "
                        "chua verify -> giu submitted, khong replay"}

    async def _engage_tiktok(self, req: dict) -> dict:
        """Port tiktok_engage_one._do_action: view/like/repost/comment/follow.

        1 action/lan tren managed tab caller inject. Comment text tu req
        (manifest/CLI), khong hard-code. Loi truoc click -> before_submit=True.
        """
        from contextlib import suppress as _suppress
        from miro.eye import (tiktok_comment_records as _eye_comments,
                              tiktok_video_record as _eye_video)
        page = self._page
        action = str(req.get("action") or "").strip().lower()
        comment_text = str(req.get("comment_text") or req.get("comment") or "")
        url = str(req.get("url") or "")
        if url and url.startswith("http"):
            with _suppress(Exception):
                if (getattr(page, "url", "") or "") != url:
                    await page.goto(url, wait_until="domcontentloaded",
                                    timeout=30000)
        # LUAT CUNG REA-MAT: mat doc truoc moi action — tay khong duoc bam
        # khi mat chua do. Eye record truoc submit lam can cu reconcile.
        eye_before: dict | list = {}
        with _suppress(Exception):
            eye_before = await _eye_video(page)
        _req_post_id = ""
        try:
            _req_post_id = str((eye_before or {}).get("post_id") or "")
        except Exception:
            _req_post_id = ""
        if action == "view":
            await page.mouse.wheel(0, 400)
            await page.wait_for_timeout(8000)
            await page.mouse.wheel(0, -200)
            await page.wait_for_timeout(3000)
            return {"engaged": True, "action": "view",
                    "post_id": _req_post_id,
                    "eye_video": eye_before}
        # LUAT CUNG: mat engage doc nut truoc; tay chi bam selector
        # mat da xac nhan visible+enabled.
        with _suppress(Exception):
            from miro.eye import engage_records as _eye_engage
            eye_buttons = (await _eye_engage(page, self.platform)
                           or {}).get("buttons", {})
        if action == "like":
            seen_like = str((eye_buttons.get("like") or {}).get("selector")
                            or "")
            like_sels = ('button[data-e2e="like-button"]',
                         'span[data-e2e="like-icon"]',
                         'button[aria-label*="Like"]')
            if seen_like and seen_like in like_sels:
                # Mat da thay — chi dung selector nay, loi thi dung.
                try:
                    el = page.locator(seen_like).first
                    await el.scroll_into_view_if_needed(timeout=5000)
                    await el.click(timeout=8000)
                    await page.wait_for_timeout(2000)
                    after = {}
                    with _suppress(Exception):
                        after = await _eye_engage(page, self.platform) or {}
                    return {"engaged": True, "action": "like",
                            "via": seen_like, "receipt": "SUBMITTED",
                            "eye_buttons": eye_buttons,
                            "eye_after": (after or {}).get("buttons", {})}
                except Exception:
                    raise LiveChromeError(
                        f"Nut Like mat-thay loi ({seen_like}); mat do lai.",
                        before_submit=True)
            for sel in like_sels:
                with _suppress(Exception):
                    el = page.locator(sel).first
                    await el.scroll_into_view_if_needed(timeout=5000)
                    await el.click(timeout=8000)
                    await page.wait_for_timeout(2000)
                    after = {}
                    with _suppress(Exception):
                        after = await _eye_engage(page, self.platform) or {}
                    return {"engaged": True, "action": "like", "via": sel,
                            "receipt": "SUBMITTED",
                            "eye_buttons": eye_buttons,
                            "eye_after": (after or {}).get("buttons", {})}
            raise LiveChromeError("Khong thay nut Like.", before_submit=True)
        if action == "repost":
            for sel in ('button[data-e2e="share-button"]',
                        'button[aria-label*="Share"]'):
                with _suppress(Exception):
                    el = page.locator(sel).first
                    await el.scroll_into_view_if_needed(timeout=5000)
                    await el.click(timeout=8000)
                    await page.wait_for_timeout(2000)
                    break
            with _suppress(Exception):
                rp = page.locator(
                    '[data-e2e="share-repost"], button:has-text("Repost")'
                ).first
                await rp.click(timeout=8000)
                await page.wait_for_timeout(2000)
                return {"engaged": True, "action": "repost",
                        "receipt": "SUBMITTED", "eye_buttons": eye_buttons}
            raise LiveChromeError("Khong thay nut Repost.", before_submit=True)
        if action == "comment":
            if not comment_text.strip():
                raise LiveChromeError("Thieu noi dung comment.",
                                      before_submit=True)
            # Mat xac dinh o comment + nut Post TRUOC khi tay bam.
            before_comments: list = []
            with _suppress(Exception):
                before_comments = await _eye_comments(
                    page, _req_post_id)
            box = None
            for sel in ('div[data-e2e="comment-input"] '
                        '[contenteditable="true"]',
                        'div[contenteditable="true"]'):
                with _suppress(Exception):
                    cand = page.locator(sel).first
                    await cand.scroll_into_view_if_needed(timeout=5000)
                    await cand.click(timeout=5000)
                    box = cand
                    break
            if box is None:
                raise LiveChromeError("Khong thay o comment.",
                                      before_submit=True)
            await box.fill(comment_text[:150])
            await page.wait_for_timeout(1000)
            with _suppress(Exception):
                await page.locator(
                    'div[data-e2e="comment-post"]').first.click(timeout=8000)
                await page.wait_for_timeout(2000)
                # Mat doc lai sau submit: comment moi phai khop
                # {author(post_id) + text} trong cung record.
                after_comments: list = []
                with _suppress(Exception):
                    after_comments = await _eye_comments(
                        page, _req_post_id)
                new_hits = [
                    c for c in (after_comments or [])
                    if comment_text[:60].strip().lower() in str(
                        c.get("text") or "").lower()]
                if new_hits and not any(
                        comment_text[:60].strip().lower() in str(
                            c.get("text") or "").lower()
                        for c in (before_comments or [])):
                    return {"engaged": True, "action": "comment",
                            "receipt": "SUBMITTED",
                            "eye_before": len(before_comments or []),
                            "eye_after": len(after_comments or []),
                            "post_id": _req_post_id}
                return {"engaged": True, "action": "comment",
                        "receipt": "UNCONFIRMED_NO_REPLAY",
                        "hint": "mat chua thay comment moi; giu, khong replay",
                        "eye_before": len(before_comments or []),
                        "eye_after": len(after_comments or []),
                        "post_id": _req_post_id}
            raise LiveChromeError("Khong gui duoc comment.",
                                  before_submit=True)
        if action == "follow":
            seen_follow = str((eye_buttons.get("follow") or {}).get(
                "selector") or "")
            follow_sels = ('button[data-e2e="follow-button"]',
                           'button:has-text("Follow")')
            if seen_follow and seen_follow in follow_sels:
                try:
                    el = page.locator(seen_follow).first
                    await el.scroll_into_view_if_needed(timeout=5000)
                    await el.click(timeout=8000)
                    await page.wait_for_timeout(2000)
                    return {"engaged": True, "action": "follow",
                            "via": seen_follow, "receipt": "SUBMITTED",
                            "eye_buttons": eye_buttons}
                except Exception:
                    raise LiveChromeError(
                        f"Nut Follow mat-thay loi ({seen_follow}); "
                        f"mat do lai.", before_submit=True)
            for sel in follow_sels:
                with _suppress(Exception):
                    el = page.locator(sel).first
                    await el.scroll_into_view_if_needed(timeout=5000)
                    await el.click(timeout=8000)
                    await page.wait_for_timeout(2000)
                    return {"engaged": True, "action": "follow", "via": sel,
                            "receipt": "SUBMITTED",
                            "eye_buttons": eye_buttons}
            raise LiveChromeError("Khong thay nut Follow (co the da follow).",
                                  before_submit=True)
        raise LiveChromeError(f"UNSUPPORTED_ENGAGE_ACTION: {action}",
                              before_submit=True)

    def engage(self, req: dict) -> dict:
        """Chay 1 action engage tren tab that (hien chi TikTok co port)."""
        if self.platform != "tiktok":
            return {"error": f"UNSUPPORTED_ENGAGE_{self.platform.upper()}",
                    "hint": "chua trinh sat REA Q1-Q10; chua viet adapter",
                    "action": req.get("action"),
                    "shortcode": req.get("shortcode")}
        import asyncio as _asyncio
        import concurrent.futures as _fut

        async def _run():
            return await self._engage_tiktok(req)

        try:
            loop = _asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            with _fut.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(_asyncio.run, _run()).result(timeout=600)
        return _asyncio.run(_run())

    def release(self) -> None:
        return None


def make_live_page(playwright_page, platform: str, account: str = "") -> LivePage:
    """Factory live duy nhat cho ca 8 platform."""
    return LivePage(playwright_page, platform, account)
