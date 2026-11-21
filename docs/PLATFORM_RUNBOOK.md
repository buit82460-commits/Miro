# Runbook chuẩn cho mọi nền tảng (Threads / Facebook / YouTube / TikTok / platform mới)

> Quy tắc vàng: **mỗi platform có đúng 1 adapter được duy trì. Muốn đăng lên platform nào thì chỉ gọi adapter của platform đó. CẤM tạo script mới cho từng batch/account/video.**

## 1. Bản đồ adapter hiện tại (module Miro — port từ dubtool `scripts/*_post_one.py`)

| Platform | Adapter chuẩn (MAINTAINED) | Nguồn port | Trạng thái |
|---|---|---|---|
| Threads | `miro.publishing.publisher.Publisher` (guard/journal/reconcile) + `miro.threads.worker.ThreadsWorker` (2-phase batch) + `miro.browser.threads_page.ManagedThreadsPage` (nối page thật, ĐẠT read-only) | `C:\dubtool\scripts\threads_post_one.py` | `submit()` CHƯA đấu dây — worker chỉ read-only/reconcile |
| Facebook | Chưa port — khi port: `Publisher` + worker riêng + page riêng, đăng ký vào bảng này | `C:\dubtool\scripts\facebook_post_one.py` | CHƯA CÓ |
| TikTok | Chưa port — khi port: `Publisher` + worker riêng + page riêng, đăng ký vào bảng này | `C:\dubtool\scripts\tiktok_post_one.py` | CHƯA CÓ (login `@kemkhongta` Profile 20 đã verify) |
| YouTube | Chưa port — dùng API (`privacyStatus=public`), không browser click | `C:\dubtool\scripts\youtube_post_one.py` | CHƯA CÓ |
| Instagram | Chưa port — khi port: `Publisher` + worker riêng + page riêng, đăng ký vào bảng này | `C:\dubtool\scripts\instagram_post_one.py` | CHƯA CÓ |
| Platform mới | Tạo **1 module adapter duy nhất** `apps/backend/src/miro/<platform>/` theo mẫu mục 5, đăng ký vào bảng này | Mẫu mục 2 | CẤM file lẻ `post_<batch>.py` |
| Điều phối tab dùng chung (Chrome Profile 20) | `miro.browser.runtime.BrowserRuntime` (`acquire_tab`) + `miro.browser.lease_store.LeaseStore` + `miro.browser.live_chrome` (read-only) | `C:\dubtool\core\tab_acquisition.py` + `core\browser_runtime.py` | ĐẠT read-only |
| Điều khiển Windows (EXPERIMENTAL) | `miro.desktop.act` + `miro.desktop.dispatch` + `miro.desktop.gate` + `miro.desktop.backend` | dubtool `shared/desktop_*.py` | ĐẠT D1/D2 |

## 2. Flow chuẩn — đăng 1 bài (mẫu cho mọi platform)

Port từ dubtool `PLATFORM_RUNBOOK.md` §2 (flow đã chạy 10/10 public), giữ nguyên guard:

### Bước 1 — Manifest (read-only, không chạm browser)

Mỗi batch một thư mục, ví dụ `var/<batch-id>/`:

- `download.json` — manifest **bất biến**: `saved[]` gồm `shortcode`, `local_path`, `sha256`, `caption`, `bytes`. Caption lấy từ manifest, KHÔNG hard-code.
- `publication-<platform>.json` — source of truth chống đăng trùng: `account`, `items[]`, `status`.
- `attempt-<id>.json` — journal bền cho từng lần Post (checkpoint trước click, receipt sau click).
- `preflight-<id>.json` — bằng chứng editor/preview/audience/AI-label/account khớp trước Post.

Trong Miro: manifest → `LibraryService`/`RenderStore`; publication → `PublicationStore`; journal → `attempts/` (`Publisher.attempts`); preflight → `check_approval` + `verify_actor` trong `Publisher._pre_post_checks`.

### Bước 2 — Guard chống trùng (bắt buộc trước mọi lần Post)

```python
if any(x["shortcode"] == shortcode for x in publication["items"]):
    return {"skipped": "ALREADY_IN_PUBLICATION"}
if journal_path.exists():
    return {"skipped": "UNRECONCILED_ATTEMPT"}  # chỉ reconcile, KHÔNG replay
```

`UNKNOWN` sau Post không bao giờ tự replay. Chỉ reconcile read-only theo
source identity + account + caption + thời điểm.

Trong Miro: `guard_duplicate` (`publishing/publisher.py`) + `ThreadsWorker`
DUPLICATE_TAGS guard cả batch.

### Bước 3 — Đăng 1 bài (adapter tự làm, theo thứ tự)

Tìm tab platform sẵn có (không mở tab mới bừa bãi) → `verify_actor` → mở composer →
đính kèm media → điền caption từ manifest → kiểm editor + preview khớp → kiểm
`Everyone`/audience → AI label nếu cần → kiểm đúng account → checkpoint
preflight → journal `submit` TRƯỚC click → `submit()` (**journal trước click,
1 click duy nhất**) → poll receipt (5s/lần, tối đa 12 lần) → `reconcile()` →
merge vào `publication-<platform>.json`.

Kết quả: `{"posted": ..., "url": ...}` hoặc
`{"posted": ..., "receipt": "UNCONFIRMED_NO_REPLAY"}` (giữ UNKNOWN, không replay)
hoặc `{"skipped": ...}` / `{"error": ...}`.

### Bước 4 — Đối soát (verify & reconcile)

- Sau mỗi bài: `reconcile()` snapshot bảng platform, ghép caption → URL, cập nhật `publication`, `latest-posts`.
- Cuối batch: đối soát tổng 1 lần. Chỉ `verified_public` khi đúng account + đúng caption + audience đúng.
- State machine: `READY → QUEUED → UPLOADING → SUBMITTING → SUBMITTED → VERIFYING → VERIFIED | UNKNOWN | FAILED_CONFIRMED`. Mất kết nối sau Post mà không có receipt chắc chắn → `UNKNOWN`.

### Bước 5 — Report & handoff

Cập nhật `publication`, `docs/verify-threads-loop.md` (mục platform/account),
daily-fixes nếu có lỗi. Ghi rõ VERIFIED / UNKNOWN, không tự khẳng định hoàn thành
khi thiếu bằng chứng.

## 3. Viết adapter composer-submit chuẩn (mẫu Threads — copy cho mọi platform)

Port từ `C:\dubtool\scripts\threads_post_one.py` (`_fill_composer` :271 + `_submit_once` :476 + `_post_live_chrome_on_page` :670):

```
composer (mở + điền + đính kèm) → journal submit TRƯỚC click → 1 click Post →
ack 3 đường (network response URL hint / toast Posted / composer-closed fallback) →
reconcile read-only → UNKNOWN không replay.
```

- **Mở composer**: thử selector theo thứ tự (nút New thread → `keyboard "n"` fallback). Hết selector → `FAILED_BEFORE_POST`, không click bừa.
- **Điền text**: `[role="textbox"]` / `contenteditable` / lexical-editor. `fill(text)`, chờ commit.
- **Đính kèm media**: `input[type="file"]` + `set_input_files`. Video gate trước: ≤100MB, ≤300s, header đọc được (`check_video`).
- **Nút Post**: tìm trong `dialog` scope, label exact `Post`, visible + enabled. Không thấy → `FAILED_BEFORE_POST`.
- **Journal trước click duy nhất**: `atomic_save(journal, {status: "submit", ...})` rồi mới click. 1 click, không retry click.
- **Ack**: network response URL hint (`graphql`, `media/configure`, `create_thread`...) HOẶC toast Posted mới HOẶC composer đóng. Hết 30s không ack → UNKNOWN, dừng submit batch.
- **Mắt–não**: eye (`collect_post_records`) là nơi DUY NHẤT đọc DOM; adapter chỉ điều khiển + quyết định + ghi sổ. 1 thời điểm chỉ 1 bên đọc tab.

## 4. Thêm platform mới / account mới (không tạo file rác)

1. Copy mục 3 thành module `apps/backend/src/miro/<platform>/`, thay phần UI đặc thù, **giữ nguyên**: guard trùng, journal, preflight, submit-1-click, reconcile, state machine, caption/account từ manifest.
2. Mọi JSON runtime đọc qua `load_json_if_exists` (chịu BOM), mọi JSON ghi qua `atomic_save` (UTF-8 no-BOM, tmp+replace). CẤM `read_text(encoding='utf-8')` cho file runtime và CẤM PowerShell `Set-Content` ghi JSON trực tiếp.
3. Mỗi tài nguyên điều khiển (file lệnh, tab, browser session) có đúng 1 owner tại một thời điểm — lock liên tiến trình, stale-lock thu hồi theo PID.
4. Đăng ký adapter mới vào bảng mục 1 của file này. Không đăng ký = không được dùng cho batch production.
5. Runtime Mode chỉ gọi adapter đã kiểm thử, không tự sửa source. Muốn sửa adapter → Maintenance Mode riêng, có regression test, không sửa khi batch production đang chạy.

## 5. Giới hạn platform (ghi rõ, không bịa)

| Platform | Giới hạn đã biết (verify khi trinh sát) |
|---|---|
| Threads | 500 ký tự/post; không draft; audience reply không chọn ở composer này; delete manual trong app |
| TikTok | `Everyone` audience; AI label bật khi cần; poll receipt 5s×12 |
| YouTube | Dùng API, không browser click; verify `privacyStatus=public` + đúng channelId |
| Facebook | Reels: Next × 2 + `set_audience(Public)`; candidate-diff 120s |
| Platform mới | Điền sau trinh sát Q8, không bịa trước |

## 6. Checklist trinh sát REA chuẩn cho mọi platform mới (bắt buộc trước khi viết adapter)

> Quy tắc: **không viết adapter mới khi chưa điền đủ checklist này.** Áp dụng cho mọi platform chưa có trong bảng mục 1. Trinh sát ở chế độ **read-only**: chỉ điều hướng + đọc snapshot/console/network, KHÔNG bấm nút tạo/sửa/xóa/lưu, KHÔNG điền form, KHÔNG gửi request có side-effect.

### 6a. Câu hỏi bắt buộc (mỗi câu phải có Evidence mới được tick)

| # | Câu hỏi | Evidence bắt buộc | Ví dụ |
|---|---|---|---|
| Q1 | Login: đã đăng nhập sẵn trong Profile 20? Actor là ai? | Snapshot chứa tên actor + URL trang | `@haodaojrk5` trên Threads |
| Q2 | Entry URL: trang bắt đầu là URL nào? | Page URL sau navigate | `https://www.threads.com/` |
| Q3 | Chặn onboarding: có kẹt form đăng ký/xác minh nào không? | Snapshot form chặn + URL redirect | Không (Threads) |
| Q4 | Composer: mở bằng URL trực tiếp được hay bắt buộc click? Field bắt buộc nào? | Snapshot composer + field | Threads: click New thread, textbox + Post |
| Q5 | Submit: nút gửi tên gì, 1 click hay nhiều bước? Journal-able? | Tên nút + số bước | Threads: 1 nút Post |
| Q6 | Ack: tín hiệu sau submit (toast/URL đổi/composer đóng)? Chờ bao lâu? | Mô tả ack quan sát được | Threads chờ composer đóng ~30s |
| Q7 | Receipt: đối soát bằng gì? Ghép với item qua field nào? | URL + field ghép | Threads: profile readback, ghép text/tag |
| Q8 | Giới hạn: quota/ngày, ký tự, media, UNSUPPORTED? | Số + nguồn | Threads 500 ký tự, không draft |
| Q9 | Guard: source identity là gì, journal ở đâu, publication file nào? | Tên file + màn hình guard | `attempt-<id>.json` + `publication-threads.json` |
| Q10 | Rollback: xóa/sửa thủ công ở đâu? Có API delete? | URL trang quản lý hoặc "manual only" | Threads: manual trong app |

Tick khi đủ 10/10. Thiếu bất kỳ Q nào → adapter ghi `UNSUPPORTED` cho phần đó trong docstring, không tự bịa flow.

### 6b. Bản đồ đường đi chuẩn (mẫu điền sau trinh sát)

```
login (Q1: actor + URL) → entry (Q2) → [onboarding? (Q3)] → composer (Q4: fields)
→ submit (Q5: nút + số click) → ack (Q6) → receipt (Q7: readback + field ghép)
→ giới hạn (Q8) | guard (Q9) | rollback (Q10)
```

### 6c. Áp thử: Threads `@haodaojrk5` (trinh sát live 21/11/2026, Profile 20)

```
login: ĐÃ đăng nhập (actor `@haodaojrk5` trong nav Profile link, title "Hào Đào")
→ entry: `https://www.threads.com/` → profile `https://www.threads.com/@haodaojrk5`
→ ONBOARDING: KHÔNG KẸT
→ composer: CHƯA MỞ LIVE (mới read-only; selector từ adapter gốc: New thread → textbox → Post)
→ submit/ack/receipt: CHƯA XÁC MINH LIVE (flow từ adapter gốc, chờ duyệt + test)
→ giới hạn: 500 ký tự, không draft, delete manual
→ guard: `Publisher.attempts/` (journal) + `PublicationStore` (publication)
→ rollback: manual trong app Threads
```

**Kết luận:** đủ Q1–Q3 + Q8–Q10, Q4–Q7 chờ duyệt live-test composer. Adapter submit port từ code gốc đã verify offline, chỉ chạy live sau duyệt.

## 7. Luật mắt–não (REA eye — áp dụng toàn hệ thống, mọi platform)

> **REA = mắt duy nhất. Miro = não + tay.** Mọi khâu nhìn (toast, hashtag, link, video) chỉ REA/mắt-chung làm, trả dữ liệu về. Adapter không tự đọc DOM để đối chiếu — chỉ điều khiển (bấm/điền/upload), quyết định (khớp tag, chốt receipt) và ghi sổ (journal/publication/guard).

- **Luật sắt:** 1 thời điểm chỉ 1 bên đọc tab. Mắt đọc thì adapter đứng chờ; mắt rút adapter mới thao tác.
- **Hợp đồng bản ghi (`collect_post_records` / `match_eye_records`):** mỗi bài 1 record `{author, tag, url, post_id, has_video, text}` trong cùng 1 khung bài. Não chỉ chốt khi author + tag + post_id/link cùng 1 record — cấm ghép tag bài này với link bài bên cạnh.
- **Chuẩn hóa tag:** lowercase + collapse whitespace + boundary 6 số (`#dub\d{6}(?!\d)`).
- **Áp dụng:** Threads đã tách xong. Platform còn lại tách dần khi chạm tới, không vá lẻ 2 mắt song song.
- **Rule cứng tab:** nếu phiên đang chạy đã có tab do chính nó mở/tái dùng, tuyệt đối không mở thêm tab mới khi chưa được user yêu cầu. Mắt và tay dùng chung đúng 1 tab: mắt đọc xong rút, tay mới vào.
