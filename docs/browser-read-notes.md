# Browser / control — ghi chú đọc sâu (JARVIS-Assistant vs dubtool)

Ngày: 2026-11-21. Phạm vi: `D:\JARVIS-Assistant\backend\app\integrations`,
`D:\JARVIS-Assistant\backend\app\api\routes\live_chrome.py`,
`D:\JARVIS-Assistant\backend\app\agents\browser_access.py`,
`D:\JARVIS-Assistant\research\repos\{browser-use,rea,agent-reach}`,
`C:\dubtool\{shared\desktop_gate.py,shared\desktop_dispatch.py,shared\desktop_backend.py,shared\browser_contracts.py,shared\browser_client.py,shared\chrome_health.py,core\browser_runtime.py,core\browser_registry.py,scripts\social_chrome_daemon.py,scripts\social_live_chrome.py,scripts\social_browser.py,integrations\youtube-agent\dubtool\browser-manager.js}`.
Chỉ ghi docs, không sửa code.

## 1. Ai mở CDP?

### JARVIS (`live_chrome_worker.py` + `live_chrome.py`)
- `live_chrome_worker.endpoint(directory)`: đọc `<user_data_dir>/DevToolsActivePort`,
  parse dòng 1 = port, dòng 2 = route `/devtools/browser/<id>`, trả
  `ws://127.0.0.1:<port><route>`. Parse lỗi → `CDP_UNAVAILABLE`.
- `browser_id(address) = sha256(ws_endpoint)`. Dùng làm `browserInstanceId`
  (khớp khái niệm instance bên dubtool).
- `_run_unleased()`: `socket.create_connection(127.0.0.1:port)` kiểm tra sống,
  rồi `playwright.chromium.connect_over_cdp(address, timeout=120s, no_defaults=True)`.
  **Không bao giờ** `browser.close()/context.close()` — chỉ disconnect khi driver
  shutdown. Cleanup bên `LiveChromeService._run()`: kill đúng tiến trình `node`
  có `playwright` trong exe path, **không kill Chrome**.
- Mỗi request `tabs/bind/read` = **1 subprocess worker mới**
  (`JARVIS_LIVE_CHROME_PYTHON`, mặc định
  `C:\dubtool\integrations\social-runtime\Scripts\python.exe`), timeout 175s,
  stdin/stdout JSON 1 dòng. `tabs` chạy **không lease**.
- `LiveChromeService` giữ `asyncio.Lock` (serialize trong-process) + `bindings {}`
  (in-memory, mất khi backend restart). Capability duy nhất: `READ`.
  Routes: `POST /browser-live/tabs`, `POST /browser-live/bindings`,
  `POST /browser-live/bindings/{id}/read`, `DELETE` (xóa binding).
- `guard_legacy_browser` (`app/agents/browser_access.py`): mode `existing_cdp`
  (xem `backend/.env: JARVIS_BROWSER_ACCESS_MODE=existing_cdp`) **chặn mọi adapter
  launch cũ** (`EXISTING_CDP_REQUIRED`), bắt bind qua `/browser-live` trước.
- `scripts/social_browser.py` (TikTok) là kiểu **launch riêng**
  (`chromium.launch(channel='chrome')`) — thuộc diện bị guard chặn khi ở mode này.

### Dubtool (`social_chrome_daemon.py` + `social_live_chrome.py`)
- `ExistingChromeConnection`: **1 kết nối CDP duy nhất, giữ lâu (persistent)**
  cho mỗi Studio runtime, cũng `connect_over_cdp(..., no_defaults=True)`.
- `chrome_endpoint()` đọc `%LOCALAPPDATA%/Google/Chrome/User Data/DevToolsActivePort`
  (không tham số hóa user-data-dir như JARVIS worker).
- Chính sách fail-closed: health = `new_browser_cdp_session` + `Browser.getVersion`;
  lỗi → `WAITING_CONFIRMATION`, `failures>=2` thì khóa, **không auto-reconnect**,
  chỉ `owner_recover`显式 mới nối lại. `driver.stop()` chỉ dừng driver của owner,
  không động vào Chrome.
- **Owner process duy nhất**: `serve_owner()` giữ `owner.lock`
  (Windows `msvcrt.LK_NBLCK` / POSIX `flock`), ghi `owner.json {pid, processStamp}`,
  `key.txt` (0600), socket TCP `127.0.0.1:<ephemeral>`, auth HMAC key.
  `ensure_owner()` spawn detached `Popen --serve`; `owner_request()` gửi JSON 1 dòng
  qua socket. State dir: `config/browser-owner/` (hoặc `DUBTOOL_OWNER_STATE_DIR`).
- HTTP facade (`integrations/youtube-agent/dubtool/browser-manager.js`):
  `POST /api/dubtool/browser/shared/:action` (peer: `X-Browser-Client` +
  `X-Browser-Key` so với `config/browser-clients.json`, `timingSafeEqual`)
  và `/api/dubtool/browser/manager/:action` (API key, admin).
  Serialize bằng cờ `social.busy` trong-process.
- `shared/chrome_health.py`: health check 3 tầng read-only
  (DevToolsActivePort → `/json/version` → `connect_over_cdp`+`getVersion`+đếm tab),
  phân loại `BROWSER_UNAVAILABLE / STALE_ENDPOINT / CONSENT_REQUIRED /
  CDP_UNRESPONSIVE / HEALTHY`. Không launch/kill/copy cookie/click Allow.

## 2. Ai giữ lease?

### Điểm chung (cùng 1 file SQLite)
- Canonical: `C:\dubtool\shared\browser_contracts.py` v1
  (`CONTRACT_VERSION = 1`), `D:\...\integrations\browser_contracts.py` là **bản copy**
  (docstring ghi "distributable unchanged").
- `SharedStore(file)`: bảng `records(kind,id,data)` + `leases(resource,fence,owner,
  token_hash,expires,pid,process_stamp,state)`. `process_identity()` verify PID
  (Windows: `OpenProcess` + `GetProcessTimes`, không `os.kill(pid,0)`).
- Key: `tab_resource(instance, target) = 'tab:<browser_id>:<targetId>'` — hai bên
  dùng cùng công thức.
- Mặc định **cùng file DB**: JARVIS `JARVIS_BROWSER_LEASE_DB` mặc định
  `C:\dubtool\config\browser-registry.sqlite` = DB mà owner dubtool dùng
  (`DUBTOOL_BROWSER_REGISTRY` hoặc `config/browser-registry.sqlite`). Hợp tác
  cross-process qua `BEGIN IMMEDIATE` + `busy_timeout=5000`.
- Ngữ nghĩa: `acquire` từ chối khi lease active chưa hết hạn (`LeaseBusy:
  TAB_LEASE_BUSY`); lease hết hạn mà owner cũ còn sống/không verify được →
  `OWNERSHIP_UNKNOWN` (không cướp). `validate` sau op; `release` chỉ token-holder.

### Khác nhau
| | JARVIS worker | Dubtool runtime/owner |
|---|---|---|
| Giữ lease khi nào | Chỉ `bind`/`read` (`run()`); `tabs` **không lease** | Mọi op có tab (`read/navigate/acquire_tab/task/create_tab/annotate/verify_account`) qua `_held()`/`_held_existing()` |
| Owner string | `"jarvis-existing-worker"`, ttl 180s, **không heartbeat**, `held()` rồi `release` cuối, `validate()` 1 lần | `caller + ':' + uuid8` (vd `dubtool-publisher`, `peer:jarvis`, taskId), ttl 60s (acquire_tab 300s) + **heartbeat renew mỗi 10s**, cancel task nếu renew lỗi |
| Coordinator | Không có (chỉ `asyncio.Lock` trong-process của `LiveChromeService`) | `_acquire_coordinator()` (lock `asyncio.Lock` + lease `acquire-coord:<inst>:<profile>:<platform>` 30s) chống đua tạo tab trùng |
| Lease treo/khôi phục | Hết hạn tự hết hiệu lực; không invalidate chủ động | `_invalidate()` + `store.invalidate(resource)` khi tab đóng/origin đổi/restar­t; `_reconcile_stale_instances()` gán lại tab sau khi Chrome restart |
| Snapshot lease | Không expose | `registry.snapshot()` trả `leases` + `machineId`; `BrowserManager` peer được `renew_tab/release_tab` |

### Không liên quan browser: `desktop_gate` / `desktop_dispatch`
- `C:\dubtool\shared\desktop_gate.py` + `desktop_dispatch.py` + `desktop_backend.py`
  quản lý **desktop automation (agent-desktop CLI, vd Notepad)** — không phải tab browser.
- Cơ chế riêng: **epoch ownership** theo `job_id`
  (`job_owner.json` / `owners/<job>.json`, `init_job`/`transfer_job`, `gate()`
  deny `STALE_EPOCH`), `DispatchLock(base/dispatch.lock)` chung cho
  `transfer_job` và `dispatch()` (check epoch tươi → gọi backend → receipt
  `receipt-<run_id>.json`). Đừng nhầm với tab lease SQLite ở trên.

## 3. Verify account / profile thế nào?

### JARVIS worker (`live_chrome_worker.py`)
1. `verify_profile(browser, selected_id, pages, request)`:
   - Tìm đúng 1 tab `chrome://version` có `targetId == profile_target_id` (do client truyền).
   - `Browser.getWindowForTarget` cho cả 2 tab → **cùng `windowId`** mới qua.
   - Đọc `#profile_path` trong trang `chrome://version`, so `normcase(realpath)`
     với `<user_data_dir>/<profile_directory>` (`Default|Profile N`).
   - Re-check URL vẫn là `chrome://version` sau khi đọc.
2. `actor(page, expected)`: `page.url` phải là facebook hostname hợp lệ
   (đã strip query/fragment qua `public_url()`); đọc
   `window.require('CurrentUserInitialData').USER_ID`, phải khớp `account_id`
   (`^\d{1,30}$`), else `ACCOUNT_MISMATCH` / `ORIGIN_CHANGED`.
3. Thứ tự mỗi op: verify profile → verify actor → chạy `bind/read` → **verify lại
   cả hai** → trả `profile_verified:true, profile_evidence:
   "existing_version_same_window"`. Chỉ hỗ trợ `tabs/bind/read`
   (text `body.innerText` cắt `max_chars`, không cookie/storage/HTML/JS thô).

### Dubtool (`browser_runtime.py` + `social_live_chrome.py`)
1. `bind_profile(root, directory)`: quét `inventory()` toàn bộ contexts/pages,
   lấy `profilePath` từ `#profile_path` của các tab `chrome://version`, so
   `normcase(realpath)` với kỳ vọng; ghi profile record
   `{id=sha256(path)[:32], windowIds, evidenceTargetIds, status:verified}` vào store.
2. `_observe()`: mỗi tab phải cùng `windowId` với profile, `platform_for(url)`
   hợp lệ (platform đã `register`), `require_url(platformId, url)` trước mọi
   navigate/read; `framenavigated/close` → `_invalidate()` (kèm
   `invalidate(tab_resource)`, đánh `needs_verification` cho account liên quan).
3. `verify_account(key, expected, caller)` (dưới `_held` + `_validate`):
   provider theo platform, mặc định facebook = `actor_id(page)` đọc
   `CurrentUserInitialData.USER_ID`; khớp → ghi account record
   `{status:verified, verifiedTargetId, connectionGeneration, browserInstanceId}`;
   lệch → `ACCOUNT_MISMATCH` + ghi `unverified`. Không có verifier cho platform
   khác → `ACCOUNT_VERIFIER_UNAVAILABLE` (deny sensitive op).
4. `social_live_chrome.operate_live` (đường publish cũ qua owner): verify qua
   `expectedProfileUrl` (`profile.php?id=`) + `expectedIdentity
   (sha256('facebook:'+uid))`, chặn đổi origin/identity giữa chừng.
5. `BrowserManager` (JS): `bind_profile` mặc định `userDataDir =
   %LOCALAPPDATA%/Google/Chrome/User Data` nếu client không truyền.

## 4. Khác biệt 2 bên (tóm tắt)

1. **Mô hình kết nối**: JARVIS = subprocess ngắn hạn mỗi request
   (ngoại trừ `tabs` không lease); dubtool = 1 owner process giữ CDP persistent
   + serialize + health/WAITING_CONFIRMATION. Hai kết nối CDP đồng thời vào cùng
   Chrome vẫn tương thích ở mức protocol nhưng gây **2 nguồn snapshot/inventory
   khác nhau** và lease chỉ phối hợp qua SQLite (không qua socket owner).
2. **Phạm vi lease**: JARVIS chỉ khóa lúc `bind/read` (ttl 180, không heartbeat);
   dubtool khóa mọi op tab (ttl 60 + heartbeat) + coordinator chống tạo tab trùng
   + invalidate/reconcile vòng đời tab. JARVIS không thấy `TAB_BUSY` từ op dài
   của dubtool cho đến khi tự `acquire` thất bại.
3. **Verify**: cùng nguyên lý (chrome://version cùng window + realpath profile +
   USER_ID) nhưng tham số khác: JARVIS client truyền `user_data_dir +
   profile_directory + profile_target_id + account_id` mỗi request; dubtool bind
   1 lần thành `profileBindingId` rồi mọi op tham chiếu id đó (+ `platformId`,
   `taskId`, `flag`). Đường publish cũ của dubtool còn dùng
   `expectedProfileUrl/expectedIdentity`, đường registry mới dùng
   `profileBindingId/sessionId`.
4. **Peer HTTP**: dubtool đã có `POST /api/.../shared/:action` + `SharedBrowserClient`
   (cả hai repo đều có file client giống nhau); nhưng `live_chrome_worker` hiện
   **không đi qua HTTP owner** mà tự `connect_over_cdp` + tự `acquire` lease SQLite.
   Kết quả: tuân thủ lease nhưng **bỏ qua** `social.busy`, `owner.health`,
   `read_only` mode, và audit `events.jsonl` của owner.
5. **Repo tham khảo**: `research/repos/browser-use` (tự launch/điều khiển browser
   riêng — trái với `existing_cdp`, chỉ giá trị tham khảo pattern),
   `research/repos/agent-reach` (kênh `web` search/read qua Exa/Jina HTTP, cô lập
   subprocess + scrub secret — đã tích hợp làm `AgentReachAdapter`, không chạm CDP),
   `research/repos/rea` (reverse-engineering binaries/MCP — không liên quan điều
   khiển browser). Không dùng 3 repo này để mở CDP production.

## 5. Khuyến nghị thống nhất 1 bản

1. **1 owner CDP duy nhất = dubtool owner** (`social_chrome_daemon.serve_owner`).
   JARVIS không `connect_over_cdp` trực tiếp nữa (kể cả worker); mọi op đi qua
   `SharedBrowserClient` → `POST /api/dubtool/browser/shared/:action`
   (peer `jarvis`, key trong `config/browser-clients.json`).
   Giữ `live_chrome_worker` chỉ làm **health/probe read-only** hoặc bỏ hẳn đường
   CDP trực tiếp khi peer path ổn định.
2. **1 file lease/registry duy nhất**: chuẩn hóa `JARVIS_BROWSER_LEASE_DB =
   DUBTOOL_BROWSER_REGISTRY = C:\dubtool\config\browser-registry.sqlite`;
   canonical duy nhất `C:\dubtool\shared\browser_contracts.py`, bên JARVIS import
   hoặc sync có checksum thay vì copy thủ công (hiện 2 file trùng nội dung,
   dễ lệch `CONTRACT_VERSION`).
3. **1 vocab verify**: client JARVIS gửi `userDataDir/profileDirectory/
   profileTargetId/accountId` → server quy về `bind_profile` 1 lần, trả
   `profileBindingId`; các read sau chỉ dùng `profileBindingId + tabId/targetId`.
   Bỏ `expectedProfileUrl/expectedIdentity` ở đường mới; giữ `chrome://version`
   cùng-window + `realpath` + `CurrentUserInitialData.USER_ID` làm 3 trụ duy nhất.
   `tabs` cũng nên qua owner (kèm lease ngắn hạn hoặc snapshot có `runtimeVerified`)
   để không còn đường đọc lậu ngoài lease.
4. **1 chính sách concurrency**: mọi op tab (kể cả read của JARVIS) qua
   `_held` + heartbeat + `TAB_BUSY`/`OWNERSHIP_UNKNOWN` hiện có; JARVIS bỏ
   `asyncio.Lock` cục bộ thay bằng lease server-side; peer được phép
   `renew_tab/release_tab` đã có trong `PEER_ACTIONS` — dùng nó cho op dài.
   Giữ nguyên tắc: không tab takeover, không fallback tab khác, không retry post
   khi UNKNOWN (đã có ở cả hai bên).
5. **Giữ tách bạch desktop epoch**: `desktop_gate/dispatch` (agent-desktop/Notepad)
   không gộp vào tab lease; chỉ cần ghi rõ trong tài liệu vận hành để agent sau
   không nhầm `STALE_EPOCH` (desktop) với `LEASE_LOST` (browser).
6. Thứ tự triển khai gợi ý: (a) cấu hình peer `jarvis` + test `snapshot/discover/
   read/verify_account` qua HTTP; (b) chuyển `/browser-live` thành proxy mỏng trên
   `SharedBrowserClient`; (c) xóa/huỷ đường `connect_over_cdp` trong worker;
   (d) dedup `browser_contracts.py`; (e) bổ sung test `TAB_BUSY` + `PROFILE_UNVERIFIED`
   + `ACCOUNT_MISMATCH` qua peer path. Mỗi bước có reproduce trước khi xóa đường cũ.
