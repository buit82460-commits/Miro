"""Versioned platform registry — 8 platforms x 6 capabilities.

Source of truth for Settings → Platforms screen.
Seed data surveyed 2026-11-21 from:
- C:\\dubtool\\config\\platform-domains.json (8 platform ids + entry URLs)
- C:\\dubtool\\scripts\\<platform>_post_one.py (MAINTAINED adapters)
- C:\\dubtool\\docs\\PLATFORM_RUNBOOK.md (adapter map + guard rules)
- D:\\JARVIS-Assistant\\backend\\app\\integrations\\social_video.py + tiktok_endpoints.py
"""

REGISTRY_VERSION = 3

CAPABILITIES = ("list", "download", "draft", "publish", "reconcile", "watch")

# status: SUPPORTED | PARTIAL | BLOCKED | UNSUPPORTED
PLATFORM_REGISTRY = [
    {
        "id": "youtube", "name": "YouTube", "version": 3,
        "runtime": "Data API via scripts/youtube_post_one.py (no browser); tokens integrations/youtube-agent/config/youtube-accounts.json",
        "accounts": ["Banh Love You (UCrUkQHY9OUP-Z_5muDDR6Bg, default)", "Love Cr7 (UCgSdYCAsvA5fnoXD6cOtPqg)"],
        "entry_urls": {"RESEARCH": "https://www.youtube.com/", "PUBLISH": "https://www.googleapis.com/youtube/v3"},
        "capabilities": {
            "list": {"status": "SUPPORTED", "runtime": "youtube API videos.list / Studio snapshot", "input": "channelId", "output": "videoId/url/privacyStatus", "evidence": "scripts/youtube_post_one.py:reconcile + publication-youtube.json"},
            "download": {"status": "SUPPORTED", "runtime": "yt-dlp (youtube_download, max-filesize guard)", "input": "watch URL", "output": "mp4 + probe.json", "evidence": "D:\\JARVIS-Assistant\\backend\\app\\integrations\\social_video.py:youtube_download"},
            "draft": {"status": "SUPPORTED", "runtime": "upload visibility=private/unlisted + schedule ISO8601", "input": "shortcode + --visibility", "output": "videoId (private)", "evidence": "scripts/youtube_post_one.py:upload_one visibility/schedule"},
            "publish": {"status": "SUPPORTED", "runtime": "youtube_post_one.py upload --visibility public --account <channelId>", "input": "manifest download.json (shortcode/sha256/caption)", "output": "videoId/url + publication-youtube.json", "evidence": "scripts/youtube_post_one.py + reports/.../publication-youtube.json (10/10 olichopper)"},
            "reconcile": {"status": "SUPPORTED", "runtime": "read-only videos.list privacyStatus=public + channel match", "input": "videoId", "output": "verified_public | UNKNOWN (never replay)", "evidence": "scripts/youtube_post_one.py:reconcile()"},
            "watch": {"status": "SUPPORTED", "runtime": "API poll + publication record", "input": "videoId", "output": "status/audience receipt", "evidence": "publication-youtube.json items[].status"},
        },
    },
    {
        "id": "instagram", "name": "Instagram", "version": 3,
        "runtime": "Chrome Profile 20 CDP + core/tab_acquisition.acquire_managed_tab + upstream integrations/social-auto-upload",
        "accounts": ["Profile 20 logged-in actor (verify @username + ds_user_id)"],
        "entry_urls": {"RESEARCH": "https://www.instagram.com/"},
        "capabilities": {
            "list": {"status": "PARTIAL", "runtime": "Profile 20 snapshot a[href*=\"/reel/\"] shortcode scan (read-only)", "input": "profile URL", "output": "shortcode list", "evidence": "scripts/instagram_download_one.py docstring rule + PLATFORM_RUNBOOK rule tai IG"},
            "download": {"status": "SUPPORTED", "runtime": "scripts/instagram_download_one.py (yt-dlp per-reel URL, no profile URL)", "input": "https://www.instagram.com/reel/<code>/", "output": "mp4 + .info.json + .sha256", "evidence": "scripts/instagram_download_one.py:resolve_url/verify SHA-256"},
            "draft": {"status": "UNSUPPORTED", "runtime": "upstream publishes immediately only", "input": "-", "output": "-", "evidence": "scripts/instagram_post_one.py docstring: draft UNSUPPORTED"},
            "publish": {"status": "SUPPORTED", "runtime": "scripts/instagram_post_one.py run_shortcode/--batch, 1-click submit", "input": "manifest download.json (file/sha256/caption)", "output": "media id + publication-instagram.json", "evidence": "scripts/instagram_post_one.py:_submit_once + publication-instagram.json"},
            "reconcile": {"status": "SUPPORTED", "runtime": "read-only /api/v1/media/configure response (owner + caption match)", "input": "attempt journal", "output": "verified | UNKNOWN (no replay)", "evidence": "scripts/instagram_post_one.py reconcile path"},
            "watch": {"status": "PARTIAL", "runtime": "CDP readback (no edit API)", "input": "media id", "output": "owner/caption snapshot", "evidence": "adapter docstring: caption edit UNSUPPORTED, verify only"},
        },
    },
    {
        "id": "facebook", "name": "Facebook", "version": 3,
        "runtime": "Chrome Profile 20 CDP + scripts/social_facebook_reels.py::publish_reel",
        "accounts": ["61595997638624 (default batch olichopper)"],
        "entry_urls": {"RESEARCH": "https://www.facebook.com/"},
        "capabilities": {
            "list": {"status": "PARTIAL", "runtime": "reels_tab candidate diff (beforeIds -> new IDs, 120s poll)", "input": "profile.php?id=<account>&sk=reels_tab", "output": "candidate reel IDs", "evidence": "docs/PLATFORM_RUNBOOK.md muc 3 + scripts/reconcile_olichopper_facebook.py"},
            "download": {"status": "SUPPORTED", "runtime": "plugin video.php embed (hd_src/sd_src) + chunked download", "input": "/reel/<id> or watch?v=<id>", "output": "mp4 + caption + counts", "evidence": "social_video.py:facebook_extract (hd_src/sd_src + 2 comment page_size)"},
            "draft": {"status": "UNSUPPORTED", "runtime": "composer Next x2 + Share, no draft save", "input": "-", "output": "-", "evidence": "scripts/facebook_post_one.py flow (upload->Next x2->submit_once)"},
            "publish": {"status": "SUPPORTED", "runtime": "scripts/facebook_post_one.py run_shortcode (verify_actor x2 + set_audience Public)", "input": "manifest download.json", "output": "reel URL + publication-facebook.json", "evidence": "scripts/facebook_post_one.py + publication-facebook.json"},
            "reconcile": {"status": "SUPPORTED", "runtime": "read-only scripts/reconcile_olichopper_facebook.py + facebook_receipt.py", "input": "jobId olichopper-fb-<shortcode>", "output": "verified | unknown_needs_reconcile | failed-before-post", "evidence": "reports/social-attempts/<jobId>.json"},
            "watch": {"status": "PARTIAL", "runtime": "watch page payload (view/reaction/share/creation_time) + reels_tab", "input": "video id", "output": "counts (page_size=2 comments max)", "evidence": "social_video.py:facebook_extract counts"},
        },
    },
    {
        "id": "tiktok", "name": "TikTok", "version": 3,
        "runtime": "Chrome Profile 20 CDP (Studio upload) + tikwm mirror for read",
        "accounts": ["kemkhongta (batch maoziqi59, default)"],
        "entry_urls": {"RESEARCH": "https://www.tiktok.com/", "PUBLISH": "https://www.tiktok.com/upload"},
        "capabilities": {
            "list": {"status": "SUPPORTED", "runtime": "tiktok_endpoints.py (hashtag/sound/trending/related/replies) + Studio content list", "input": "--kind hashtag|sound|trending|related|replies", "output": "slim video/comment items", "evidence": "D:\\JARVIS-Assistant\\backend\\app\\integrations\\tiktok_endpoints.py:discover"},
            "download": {"status": "SUPPORTED", "runtime": "tikwm api/?url + api/comment/list (max 10 pages) + chunked mp4", "input": "tiktok video URL", "output": "metadata + comments + mp4/frames/probe", "evidence": "social_video.py:tiktok_metadata/tiktok_comments/download_video"},
            "draft": {"status": "PARTIAL", "runtime": "Studio upload staging (Uploaded state) before submit; no standalone draft API", "input": "shortcode upload", "output": "staged upload (pre-submit)", "evidence": "scripts/tiktok_post_one.py flow: upload -> cho Uploaded -> submit()"},
            "publish": {"status": "SUPPORTED", "runtime": "scripts/tiktok_post_one.py (caption/audience Everyone/AI-label/account checks + 1 click)", "input": "manifest download.json + publication.json guard", "output": "post URL + publication.json", "evidence": "scripts/tiktok_post_one.py + reports/resource-batches/maoziqi59-tiktok-20261118 (10/10 public)"},
            "reconcile": {"status": "SUPPORTED", "runtime": "read-only Studio snapshot caption->URL match", "input": "attempt-<id>.json", "output": "verified_public | UNKNOWN (no replay)", "evidence": "scripts/publish_maoziqi59_tiktok.py reconcile"},
            "watch": {"status": "SUPPORTED", "runtime": "poll receipt 5s x12 + journal merge", "input": "shortcode", "output": "posted/url | UNCONFIRMED_NO_REPLAY", "evidence": "scripts/tiktok_post_one.py poll receipt"},
        },
    },
    {
        "id": "threads", "name": "Threads", "version": 3,
        "runtime": "Chrome Profile 20 CDP + acquire_managed_tab (platform threads)",
        "accounts": ["@haodaojrk5 (threads.com/@haodaojrk5)"],
        "entry_urls": {"RESEARCH": "https://www.threads.com/"},
        "capabilities": {
            "list": {"status": "PARTIAL", "runtime": "profile readback collect_post_records (REA eye contract)", "input": "profile URL", "output": "[{author,tag,url,post_id}] records", "evidence": "scripts/threads_post_one.py:_match_post_on_page/_reconcile_group + core/rea_eye.py"},
            "download": {"status": "SUPPORTED", "runtime": "download_one via yt-dlp (read-only)", "input": "post URL or id", "output": "media + text + sha256", "evidence": "scripts/threads_post_one.py:download_one"},
            "draft": {"status": "UNSUPPORTED", "runtime": "publishes immediately only", "input": "-", "output": "-", "evidence": "adapter docstring: draft UNSUPPORTED"},
            "publish": {"status": "SUPPORTED", "runtime": "run_shortcode/--batch text + optional 1 media, 1-click submit", "input": "manifest (text<=500 chars)", "output": "post URL + publication-threads.json", "evidence": "scripts/threads_post_one.py:run_shortcode/_submit_once"},
            "reconcile": {"status": "SUPPORTED", "runtime": "read-only profile readback owner+text match", "input": "attempt journal threads-<shortcode>.json", "output": "verified | UNKNOWN", "evidence": "reports/social-attempts/threads-<shortcode>.json"},
            "watch": {"status": "PARTIAL", "runtime": "profile readback poll (~30s composer close)", "input": "post text", "output": "post record match", "evidence": "PLATFORM_RUNBOOK Q5-Q7 Threads"},
        },
    },
    {
        "id": "chatgpt", "name": "ChatGPT", "version": 3,
        "runtime": "Chrome Profile 20 CDP + shared/event_waits (no blind sleep)",
        "accounts": ["Profile 20 ChatGPT user (verify_profile)"],
        "entry_urls": {"RESEARCH": "https://chatgpt.com/"},
        "capabilities": {
            "list": {"status": "PARTIAL", "runtime": "conversation list read via CDP", "input": "batch_dir", "output": "conversation list", "evidence": "scripts/chatgpt_post_one.py read/new/rename/delete/model CLI"},
            "download": {"status": "SUPPORTED", "runtime": "read_conversation (read-only)", "input": "conversation URL or id", "output": "transcript JSON", "evidence": "scripts/chatgpt_post_one.py:read_conversation"},
            "draft": {"status": "SUPPORTED", "runtime": "new_chat (unsent session = draft equivalent)", "input": "batch_dir + account", "output": "conversation id", "evidence": "scripts/chatgpt_post_one.py:new_chat"},
            "publish": {"status": "SUPPORTED", "runtime": "run_shortcode/--batch one prompt + wait streaming end", "input": "manifest (prompt<=8000 chars)", "output": "reply + publication-chatgpt.json", "evidence": "scripts/chatgpt_post_one.py:_submit_once"},
            "reconcile": {"status": "SUPPORTED", "runtime": "read-only reply readback", "input": "attempt journal", "output": "verified | UNKNOWN", "evidence": "adapter reconcile readback"},
            "watch": {"status": "SUPPORTED", "runtime": "model get/set + profile verify (read-only)", "input": "model/profile cmd", "output": "model id / login actor", "evidence": "scripts/chatgpt_post_one.py:get_or_set_model/verify_profile"},
        },
    },
    {
        "id": "flow", "name": "Google Flow", "version": 3,
        "runtime": "Chrome Profile 20 CDP (platform flow) + yt-dlp/playwright fetch download",
        "accounts": ["Profile 20 Google actor (verify_profile)"],
        "entry_urls": {"RESEARCH": "https://flow.google.com/"},
        "capabilities": {
            "list": {"status": "PARTIAL", "runtime": "profile verify + reconcile_one readback", "input": "batch_dir", "output": "render list (readback)", "evidence": "scripts/flow_post_one.py:verify_profile/reconcile_one"},
            "download": {"status": "SUPPORTED", "runtime": "download_one via yt-dlp/playwright fetch + SHA-256", "input": "videoUrlOrId", "output": "mp4 verified", "evidence": "scripts/flow_post_one.py:download_one"},
            "draft": {"status": "UNSUPPORTED", "runtime": "generates immediately only", "input": "-", "output": "-", "evidence": "adapter docstring: draft UNSUPPORTED"},
            "publish": {"status": "SUPPORTED", "runtime": "run_shortcode/--batch prompt->submit once->poll render<=600s->download MP4", "input": "manifest (prompt<=4000 chars)", "output": "video URL + publication-flow.json", "evidence": "scripts/flow_post_one.py:run_shortcode/_submit_once"},
            "reconcile": {"status": "SUPPORTED", "runtime": "read-only reconcile_one", "input": "videoUrlOrId", "output": "verified | UNKNOWN", "evidence": "scripts/flow_post_one.py:reconcile_one"},
            "watch": {"status": "SUPPORTED", "runtime": "event-based poll render completion", "input": "shortcode", "output": "render status + video URL", "evidence": "shared/event_waits.wait_for_url_or_text + RENDER_TIMEOUT_S=600"},
        },
    },
    {
        "id": "shopee", "name": "Shopee", "version": 3,
        "runtime": "Chrome Profile 20 CDP Seller Centre (research direction: shopee.vn affiliate, NO seller onboarding)",
        "accounts": ["haodaojr (haodaojrk5@gmail.com) — KET onboarding Seller Centre 1/5"],
        "entry_urls": {"RESEARCH": "https://shopee.vn/"},
        "capabilities": {
            "list": {"status": "SUPPORTED", "runtime": "read_orders read-only + shopee.vn search/product read (affiliate research)", "input": "batch_dir + account", "output": "orders / product metadata", "evidence": "scripts/shopee_post_one.py:read_orders + AGENTS.md quy tac Shopee (nghien cuu shopee.vn)"},
            "download": {"status": "PARTIAL", "runtime": "product page read (search/trang san pham/danh gia/gia/link affiliate)", "input": "shopee.vn product URL", "output": "product JSON (no seller write)", "evidence": "AGENTS.md: trinh sat REA tap trung shopee.vn"},
            "draft": {"status": "UNSUPPORTED", "runtime": "Seller Centre publishes on save", "input": "-", "output": "-", "evidence": "adapter docstring: draft UNSUPPORTED"},
            "publish": {"status": "BLOCKED", "runtime": "run_shortcode/--batch (dang/sua san pham) — KHONG test live khi chua xong onboarding", "input": "manifest (name + price>0 + stock>=0)", "output": "BLOCKED: onboarding 1/5 thieu dia chi + SDT", "evidence": "PLATFORM_RUNBOOK 8c + reports/resource-batches/shopee-20261120/download.json saved:[]"},
            "reconcile": {"status": "SUPPORTED", "runtime": "read-only Seller Centre readback (khi unblocked)", "input": "attempt journal shopee-<shortcode>.json", "output": "verified | UNKNOWN", "evidence": "scripts/shopee_post_one.py reconcile path"},
            "watch": {"status": "SUPPORTED", "runtime": "orders + update_profile read paths", "input": "orders/profile cmd", "output": "orders JSON / shop profile", "evidence": "scripts/shopee_post_one.py:update_profile/read_orders"},
        },
    },
]

READ_CAPABILITIES = ("list", "download", "reconcile", "watch")
PUBLISH_CAPABILITIES = ("draft", "publish")


def get_platform(pid: str) -> dict | None:
    return next((p for p in PLATFORM_REGISTRY if p["id"] == pid), None)
