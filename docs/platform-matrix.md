# Ma trận Platform × Capability (registry v3, 2026-11-21)

Nguồn: `C:\dubtool\config\platform-domains.json`, `C:\dubtool\scripts\<platform>_post_one.py`,
`C:\dubtool\docs\PLATFORM_RUNBOOK.md`, `D:\JARVIS-Assistant\backend\app\integrations\social_video.py`
+ `tiktok_endpoints.py`. Registry code: `apps/backend/src/miro/platforms/` · UI: Cài đặt → Nền tảng
(`apps/web/src/app/settings/platforms/page.tsx`, API `/api/settings/platforms`).

Trạng thái: SUPPORTED (xanh) · PARTIAL (vàng) · BLOCKED (đỏ, chờ điều kiện) · UNSUPPORTED (xám).

## Tổng quan 8 × 6

| Platform | list | download | draft | publish | reconcile | watch | Đọc | Đăng |
|---|---|---|---|---|---|---|---|---|
| YouTube | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | READY | READY |
| Instagram | PARTIAL | SUPPORTED | UNSUPPORTED | SUPPORTED | SUPPORTED | PARTIAL | DEGRADED | DEGRADED |
| Facebook | PARTIAL | SUPPORTED | UNSUPPORTED | SUPPORTED | SUPPORTED | PARTIAL | DEGRADED | DEGRADED |
| TikTok | SUPPORTED | SUPPORTED | PARTIAL | SUPPORTED | SUPPORTED | SUPPORTED | READY | DEGRADED |
| Threads | PARTIAL | SUPPORTED | UNSUPPORTED | SUPPORTED | SUPPORTED | PARTIAL | DEGRADED | DEGRADED |
| ChatGPT | PARTIAL | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | DEGRADED | READY |
| Google Flow | PARTIAL | SUPPORTED | UNSUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | DEGRADED | DEGRADED |
| Shopee | SUPPORTED | PARTIAL | UNSUPPORTED | BLOCKED | SUPPORTED | SUPPORTED | DEGRADED | BLOCKED |

Đọc = list/download/reconcile/watch · Đăng = draft/publish. Shopee publish BLOCKED do kẹt
onboarding Seller Centre 1/5 (thiếu địa chỉ lấy hàng + SĐT) — hướng affiliate chỉ nghiên cứu
`shopee.vn`, adapter Seller Centre không test live (AGENTS.md + RUNBOOK 8c).

## Chi tiết runtime / input / output / bằng chứng

### YouTube — Data API, không browser
| Cap | Runtime | Input → Output | Bằng chứng |
|---|---|---|---|
| list | videos.list / Studio snapshot | channelId → videoId/url/privacyStatus | `youtube_post_one.py:reconcile` + `publication-youtube.json` |
| download | yt-dlp max-filesize guard | watch URL → mp4 + probe.json | `social_video.py:youtube_download` |
| draft | upload visibility private/unlisted + schedule | shortcode → videoId (private) | `youtube_post_one.py:upload_one` |
| publish | `upload --visibility public --account <channelId>` | manifest → videoId/url + publication | `publication-youtube.json` 10/10 olichopper |
| reconcile | videos.list privacyStatus + channel match (read-only) | videoId → verified_public/UNKNOWN | `youtube_post_one.py:reconcile()` |
| watch | API poll + publication record | videoId → status/audience | `publication-youtube.json items[]` |

Kênh: **Bảnh Love You** (default) + Love Cr7 — luôn nhắc 1 dòng trước khi đăng (AGENTS.md).

### Instagram — Profile 20 CDP + upstream social-auto-upload
| Cap | Runtime | Input → Output | Bằng chứng |
|---|---|---|---|
| list | snapshot `a[href*="/reel/"]` | profile URL → shortcodes | `instagram_download_one.py` rule |
| download | `instagram_download_one.py` per-reel URL | reel URL → mp4 + .info.json + .sha256 | adapter verify SHA-256 |
| draft | — | UNSUPPORTED (publish ngay) | docstring adapter |
| publish | `instagram_post_one.py --batch`, 1-click | manifest → media id + publication | `_submit_once` |
| reconcile | `/api/v1/media/configure` owner+caption | journal → verified/UNKNOWN | adapter reconcile |
| watch | CDP readback (verify only, no edit) | media id → snapshot | docstring: caption edit UNSUPPORTED |

### Facebook — Profile 20 CDP + social_facebook_reels
| Cap | Runtime | Input → Output | Bằng chứng |
|---|---|---|---|
| list | reels_tab candidate diff 120s | profile reels_tab → candidate IDs | RUNBOOK mục 3 |
| download | plugin video.php hd_src/sd_src | /reel/ URL → mp4 + caption + counts | `social_video.py:facebook_extract` |
| draft | — | UNSUPPORTED (Next×2 + Share) | `facebook_post_one.py` flow |
| publish | `facebook_post_one.py` verify_actor×2, audience Public | manifest → reel URL + publication | `publication-facebook.json` |
| reconcile | `reconcile_olichopper_facebook.py` + receipt (read-only) | jobId → verified/unknown/failed | `reports/social-attempts/<jobId>.json` |
| watch | watch payload view/reaction/share (tối đa 2 comment) | video id → counts | `facebook_extract counts` |

### TikTok — Studio CDP + tikwm mirror (đọc)
| Cap | Runtime | Input → Output | Bằng chứng |
|---|---|---|---|
| list | `tiktok_endpoints.py` 5 endpoint | --kind → slim items | `tiktok_endpoints.py:discover` |
| download | tikwm api + comment/list (≤10 trang) | video URL → meta/comments/mp4/frames | `social_video.py:tiktok_*` |
| draft | Studio staging (Uploaded) | upload → staged pre-submit | `tiktok_post_one.py` flow |
| publish | `tiktok_post_one.py` caption/Everyone/AI-label + 1 click | manifest → URL + publication | batch maoziqi59 10/10 public |
| reconcile | Studio snapshot caption→URL (read-only) | attempt → verified/UNKNOWN | `publish_maoziqi59_tiktok.py` |
| watch | poll receipt 5s×12 | shortcode → posted/UNCONFIRMED | adapter poll receipt |

### Threads — Profile 20 CDP, REA eye contract
500 ký tự/post · text + tối đa 1 media · delete/draft/audience UNSUPPORTED (manual trong app).

### ChatGPT — Profile 20 CDP, event waits
`chat + read + new + rename + delete + model + profile` qua 1 adapter; prompt ≤8000 chars;
draft ≈ `new_chat` (session chưa gửi).

### Google Flow — Profile 20 CDP text-to-video
prompt ≤4000 chars · poll render ≤600s → download MP4 + SHA-256 · delete/draft UNSUPPORTED.

### Shopee — BLOCKED publish, affiliate research
publish `run_shortcode/--batch` tồn tại nhưng **không test live** (kẹt onboarding);
list/orders read-only + nghiên cứu `shopee.vn` (search/sản phẩm/đánh giá/giá/affiliate) SUPPORTED.

## Registry versioning (update + rollback giữ task cũ)
- Mọi mutation (thêm/nhân bản/đăng ký mới, sửa capability) bump version + snapshot bản cũ (giữ 20).
- Task pin version lúc tạo → rollback LIVE không phá task cũ.
- API: `GET /platforms` · `POST /platforms` (upsert) · `POST /platforms/{id}/clone` ·
  `PATCH /platforms/{id}/capabilities/{cap}` · `POST /platforms/rollback {version}` ·
  `GET /platforms/history`.
