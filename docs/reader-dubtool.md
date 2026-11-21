# Reader Dubtool — kết quả đọc sâu phục vụ bọc Miro (vòng 1, 2026-11-21)

Nguồn DUY NHẤT: `C:\dubtool` (không đọc JARVIS). Tài liệu này là đầu vào bắt buộc cho agent viết code + Checker.
Quy ước chung Dubtool (AGENTS.md): 1 platform = 1 adapter `scripts/<platform>_post_one.py`; JSON runtime đọc qua
`shared/json_io.load_json`, ghi qua `shared/execution_policy.atomic_save` (UTF-8 no-BOM, tmp+replace);
cấm `read_text(encoding='utf-8')` cho runtime JSON và cấm PowerShell `Set-Content` ghi JSON trực tiếp.
Guard chống trùng: đã có trong publication → skip; đã có attempt journal → chỉ reconcile read-only, KHÔNG replay UNKNOWN.
Mỗi tài nguyên điều khiển (file lệnh, tab, browser session) đúng 1 owner tại một thời điểm (lock liên tiến trình).

## 1. Pipeline — `core/pipeline.py` + `core/cache.py` (phục vụ Studio bọc thật)

### 1.1 `Pipeline.run` — `core/pipeline.py:415-448`
- Chữ ký: `run(source, src_lang="auto", tgt_lang="vi", default_voice=None, steps=None, progress_cb=None, overlays=None, burn_subtitles=False) -> {video_id, steps_run, output, segments}`.
- `STEPS` cố định thứ tự (`pipeline.py:28`): `["download","audio","stt","translate","tts","sync","mix","render"]`.
- `video_id`: `_find_video_id(source)` (`:123-133`) — file local → `"local-"+hash_file`; URL đã chạy → tra `cache/*/project.json` theo `source`; chưa có → `"pending-"+hash_text(source)` (`:417-419`).
- `steps` là subset vẫn chạy đúng thứ tự STEPS; khi chạy riêng (`requested` non-empty) thì `_hydrate(ctx)` (`:392-412`) nạp lại `video_path/wav/mix/segments/timeline` từ cache trước khi chạy.
- Mỗi step bọc try/except → `raise RuntimeError(f"Bước {step} lỗi: {e}")` (`:439-440`); `KeyboardInterrupt` giữ cache (`:436-438`).
- `progress_cb(i/total*100)` trước mỗi step + 100 cuối (`:429-442`); `output=None` thì lấy lại `project.output` (`:443-446`).
- `revoice_segment(video_id, seg_id, ...)` (`:451-482`): sửa 1 câu → xóa marker downstream tts/sync/mix/render + file `tts/{seg}_*.wav` + cắt `steps_done`, rồi `run(steps=["tts","sync","mix","render"])`.

### 1.2 8 step — entry + cache key/signature (invariant: step sau dùng file step trước để lại trong cùng work dir `cache/<video_id>/`)

| Step | Hàm (`pipeline.py`) | Chạy lại khi | Bỏ qua khi (cache hit) → hydrate ctx |
|---|---|---|---|
| download | `_step_download` `:136-152` | `force` hoặc `not is_done(vid,"download",hash_text(source))` | `video_path` = file mp4 đầu trong cache hoặc source |
| audio | `_step_audio` `:182-193` | `force`/marker sai/hash file video đổi/thiếu `stt.wav`/`orig.wav` | `stt_wav`, `orig_wav` |
| stt | `_step_stt` `:195-211` | `force`/marker sai (`[hash(stt.wav), src_lang, config stt]`)/thiếu `segments.json` | `segments` từ `_load_segments` |
| translate | `_step_translate` `:213-261` | `force`/marker sai (`[src_texts, src, tgt, tcfg, llm endpoint/model/provider]`)/thiếu | `segments` từ cache |
| tts | `_step_tts` `:282-316` | `force` hoặc `_current` sai (signature `[tgt_lang, voice, config tts, (id,tgt_text,voice_id)...]` + mọi `tts_path` tồn tại) | giữ `segments` (đã có `tts_path`) |
| sync | `_step_sync` `:318-333` | `force`/signature `[segments, config sync]` sai/thiếu `timeline.json` | `timeline` từ cache |
| mix | `_step_mix` `:335-355` | `force`/signature `[timeline, hash(orig.wav), config mix/tts]` sai/thiếu `mix.wav` | `mix_wav` |
| render | `_step_render` `:357-389` | `force`/signature `[hash(video), hash(mix), overlays, burn_subtitles, hash(srt?)]` sai/`old_output` mất | `output = project.output` |

Chi tiết hành vi từng step:
- download (`:136-152`): `get_video(source, cache_dir)` từ `core.download`; sau chạy lưu project `{source,title,src_lang,tgt_lang,default_voice}` (`save_project` `:92-103`, file `project.json` tại `cache/<vid>/project.json` qua `_project_path` `:83-84`).
- audio (`:182-193`): `extract_audio(video) -> {stt_wav, orig_wav}` (`core.audio`), key = `hash_file(video_path)` — đổi file nguồn là chạy lại.
- stt (`:195-211`): `check_vram_before_load(min_free_mib=3000)` + `_load_cuda_dlls()` (Windows torch/lib, `:34-45`) rồi `transcribe(vid, stt_wav, workdir, language, beam_size, progress_cb)` (`core.stt`); `free_vram()` + `log_vram("sau stt")` sau xong.
- translate (`:213-281`): `src=="auto"` → đọc `stt_info.json:detected_language`; chỉ hỗ trợ `vi/en/zh` else RuntimeError. Ưu tiên LLM (`LLMTranslator.from_env(root/.env)`; batch 20 câu, `max_units = slot*cps*1.25`, `_translate_with_llm` `:263-280`) → lỗi thì fallback NLLB local (`Translator(...)` + optional glossary, `translate_segments`); luôn `flag_too_long`. Lưu `segments.json` + `dub.srt` (`_save_segments` `:161-169`).
- tts (`:282-316`): `get_engine(tgt_lang)` (`core.tts`); từng câu: `voice_id = seg.voice_id or default_voice` (thiếu → RuntimeError), `get_voice(voices_dir, voice_id)` phải `lang==tgt_lang`, `normalize_for_tts`, file `tts/{id}_{hash(norm+voice+"1.0")}.wav`, tồn tại thì dùng lại; cuối `engine.unload()+free_vram()`.
- sync (`:318-333`): `sync_segments(segments, workdir, max_speed, gap_s)` → `(timeline, report)` lưu `timeline.json`; marker data = `{**report, signature}`.
- mix (`:335-355`): `build_dub_track(timeline, tts_dir, total, sr)` + `mix_tracks(dub, orig, orig_gain_db, sr)` + `normalize_loudness` + `write_mix` → `mix.wav` (`core.mix`, `core.ffmpeg_utils.wav_duration_s`).
- render (`:357-389`): `_probe_size` (ffprobe w,h, `:48-56`); `build_filter(overlays,w,h)` (`core.overlay`); burn_subtitles nối `subtitles='esc_path(dub.srt)'` (`_escape_sub_path` `:59-60` — `\`→`/`, `:`→`\:`, `'`→`\'`); output `output/<vid>_dubbed_<ts>.mp4`; lưu project `{output, overlays, output_settings:{burn_subtitles}, editor_export:{}, editor_pending:False}`.

### 1.3 Cache + invalidation — `core/cache.py:1-57` + `_mark_step` (`pipeline.py:105-120`)
- Marker: `cache/<video_id>/<step>[.<input_hash>].done` (`done_path/is_done/mark_done`; `hash_file`/`hash_text` = SHA-1[:12]).
- `_mark_step(step, input_hash, data)`: **xóa mọi marker downstream** (`STEPS sau step`) + xóa marker cùng step khác hash → `mark_done` → cập nhật `project.steps_done` (loại downstream, append step). Invariant: rebuild step trước **luôn** invalidate step sau, kể cả transcript giống nhau (comment `:106-107`).
- `_current(vid, step, signature, files)` (`:174-180`, dùng cho tts/sync/mix/render): marker `step.done` (không hash) chứa JSON `{signature}` + mọi file tồn tại.
- TTS marker không có input_hash trong tên file nhưng signature JSON bù lại (`:315`); download/audio/stt/translate dùng `is_done(vid, step, ih)`.

## 2. Browser — `core/browser_runtime.py` + `core/tab_acquisition.py` (phục vụ Browser bọc thật)

### 2.1 `BrowserRuntime` — `core/browser_runtime.py:39-1036`
- Triết lý: **never launches Chrome; read/navigation only** (`:1`); không có arbitrary JS/click/publish API (`dispatch` `:1027` từ chối).
- Khởi tạo (`:40-54`): `(browser, instance_id, database, mapping, account_providers)`; `generation=uuid4`; hook `context.on('page') → _new_page → _observe`.
- `bind_profile(root, directory)` (`:94-108`): chỉ chấp nhận `Default|Profile \d{1,5}`; **bằng chứng sống**: `inventory()` đọc `chrome://version` → `#profile_path` khớp `realpath(root/dir)` else `PROFILE_UNVERIFIED`; `profile.id = sha256(path)[:32]`; lưu store kind `profile`.
- `_observe` (`:169-226`): bỏ qua page đóng; check window thuộc profile else `profile_unverified`; `platform_for(url)` ngoài registry → `out_of_scope`; phân loại flag qua `classify(url)` (`core.browser_registry`); `origin_changed` → invalidate task binding; giữ `flagSource=manual` (roleValid theo `flagBasisUrl` cùng origin); `flagWatch` chỉ giữ khi manual + cùng origin/basis. Record tab: `{id=tab_key, targetId, profileBindingId, sessionId=profile:context:generation, platformId, channelId, url/hostname/title/flags/roleValid/taskBinding/status=open, lastVerifiedAt/UsedAt}`.
- `_validate(key)` (`:307-331`): kiểm tra instance, profile, page sống, `targetId+browserContextId` không đổi, window còn thuộc profile, url không đổi origin + `require_url(platform, url)`; cập nhật `lastVerifiedAt`.
- Lease (`_held` `:333-359`): `store.acquire(tab_resource, caller:uuid10, 60s)` + heartbeat renew 10s; `CancelledError` do mất lease → `LeaseLost('LEASE_LOST: no replay')`.
- `read(key, caller, max_chars 1..20000)` (`:361-380`): giữ lease → validate → `page.evaluate(innerText slice)` → URL đổi giữa chừng → `TAB_CHANGED_DURING_READ`.
- `navigate(key, platform_id, url, caller)` (`:512-530`): `require_url` trước; cấm nếu `_navigation_breaks_flag` (khác destination + flagWatch/protected flag `CHAT_WATCH/FLAG_WATCH/LIVE_UPLOAD/DIRTY_FORM`) hoặc page bẩn (`_inspect_page_state` `:422-481`: upload_flag/file_input/progress, dirty textarea/input/contenteditable/beforeunload) → `TAB_PROTECTED_NO_NAVIGATE`; route-guard chặn navigation lệch platform trong lúc `goto`.
- `create_tab` (`:557-608`): giữ `profile-create` lock → anchor trong windowIds → `Target.createTarget(about:blank)` → verify window thuộc profile else **đóng tab vừa tạo** (`NEW_TAB_PROFILE_UNVERIFIED`) → navigate → observe → `createdByRegistry/creationReason(+channelId/taskId)` → `registry.record_tab_creation`.
- `acquire_tab(request, caller)` (`:610-753`): coordinator lock `acquire-coord:{instance}:{profile}:{platform}` → `discover` → lọc open tabs (ownerTaskId, channel, flag+roleValid) → rank `(exact_url, exact_channel, flag_match, lastUsedAt)` → bỏ lease đang active (`TAB_BUSY`, **không tạo tab mới**) → validate + kiểm tra upload/flag bẩn → reuse (navigate nếu cần + gắn channel/flag/task) trả `{tab, lease, reused:True}`; hết candidate: `TAB_BUSY` nếu bận / `NO_MATCHING_TAB` nếu `allowCreate=False` / tạo mới từ `entryUrls[flag]` (`NO_FREE_VALID_ROLE_TAB` nếu thiếu URL hợp lệ).
- `task(request, caller)` (`:789-935`): resume phải khớp `taskId+caller+tabId+target+instance+profile+platform+flag+ownerTaskId`, URL cùng origin, role còn valid; binding revoked → lỗi; thực thi = `read_locked` + trả `taskBinding`.
- `verify_account` (`:937-962`): provider theo platform (facebook → `scripts.social_live_chrome.actor_id`), mismatch → `ACCOUNT_MISMATCH` + lưu `unverified`.
- `dispatch(request)` (`:964-1027`): các action `inventory/snapshot/register_platform/bind_profile/discover/annotate/read/task/acquire_tab/renew_tab/release_tab/create_tab/navigate/verify_account/close_owned_tab` (chỉ tab registry-created mới được đóng).
- `_reconcile_stale_instances` (`:247-305`): sau restart Chrome, khớp tab cũ (open/disconnected/needs_validation) với tab sống theo `channelId` → cùng URL → cùng origin duy nhất; giữ manual flag; đánh dấu cũ `superseded/closed` + invalidate lease.
- `close()` (`:1029-1036`): đánh dấu mọi record của generation `disconnected` + task `runtime_disconnected`.

### 2.2 `acquire_managed_tab` — `core/tab_acquisition.py:110-183`
- Chữ ký: `acquire_managed_tab(browser, *, platform_id, destination_url, channel_id=None, flag="PUBLISH", task_id=None, caller, creation_reason, endpoint, database, user_data_dir, profile_directory="Profile 20", allow_create=True, navigate_if_needed=True, lease_ttl=300) -> AcquiredTab`.
- `instance_id = sha256(endpoint)` hoặc `"cdp-local"`; DB default `config/browser-registry.sqlite`.
- `_profile_acquire_lock` (`:91-107`): lock liên tiến trình `acquire-profile:{instance}:{profile}` 30s/timeout 20s chống bind song song.
- `_bind_or_probe_profile` (`:70-87`): bind thất bại `PROFILE_UNVERIFIED` → mở tạm `chrome://version/` để lấy bằng chứng rồi đóng sau acquire (đổi anchor sang tab thật `:157-161`).
- Luôn `registry.register(destination_url)` trước acquire; `AcquiredTab(page, record, lease, runtime, reused, creation_reason, channel_id, tab_count_before/after)`; `release()` = `release_tab` + `runtime.closed=True` (không đánh dấu tab Chrome đóng, `:66-68`); lỗi giữa chừng đóng trang probe + `closed=True`.
- Adapter IG dùng y nguyên mẫu này (`instagram_post_one.py:254-275`: `platform_id="instagram"`, `destination=https://www.instagram.com/<user>/`, `channel_id=username`, `flag="PUBLISH"`, `caller="instagram_post_one"`, `creation_reason="instagram_reel_publish"` + `bring_to_front` + verify actor, lỗi → release rồi raise). TikTok tương tự (`tiktok_post_one.py:70-87`) nhưng có nhánh legacy: nếu `find_tab` bị monkey-patch hoặc browser không phải playwright-CDP thì fallback tìm tab `tiktokstudio/upload|content` thủ công (`:55-75`).

## 3. Desktop — `shared/desktop_gate.py` + `shared/desktop_dispatch.py` + `scripts/desktop_act.py`

### 3.1 Gate — `shared/desktop_gate.py:1-71`
- `owner_path(base, job_id)`: `base/job_owner.json` nếu chưa có hoặc khớp job; else `base/owners/<safe_job>.json` (`_safe_job` thay ký tự lạ bằng `_`).
- `init_job(base, job_id, holder="A")` → `{job_id, epoch:1, holder}`, `atomic_save`.
- `transfer_job(base, job_id, new_holder)`: giữ `DispatchLock(dispatch.lock)` → đọc fresh → `epoch+1`, đổi holder; sai job → `ValueError("JOB_MISMATCH")`.
- `gate(base, job_id, worker, worker_epoch) -> (allowed, detail)`: thiếu/khác job → `(False, JOB_MISMATCH)`; epoch lệch → `(False, {STALE_EPOCH, worker, worker_epoch, current_epoch, current_holder})`.

### 3.2 Dispatch — `shared/desktop_dispatch.py:1-156`
- Bất biến: **không worker nào gọi `desktop_backend` mutation trực tiếp**; mọi op qua `dispatch()` dưới 1 file lock, đọc fresh epoch → deny stale → chạy op → ghi receipt `receipt-<run_id>.json {job, worker, run, result, at}` (không bao giờ ghi đè, `run_id=uuid4[:8]`); deny ghi `denied-<run_id>.json`.
- `DispatchLock` (`:35-73`): `msvcrt.LK_NBLCK` byte đầu file (Windows), timeout 60s → `DISPATCH_LOCK_BUSY`; `transfer_job` dùng chung lock nên không thể chen giữa check và op.
- `dispatch(base, job_id, worker, worker_epoch, op, *args, hold_before_op=None, **kwargs)` (`:76-107`): `hold_before_op` là hook test Ca1 — sau hold check epoch lần 2 (`denied-after-hold`).
- `dispatch_window(base, window_id, job_id, worker, worker_epoch, op, ..., window_lock_dir=None)` (`:115-156`): lồng **base lock → window lock** (`<state_dir>/window-locks/window-<safe_wid>.lock`; `transfer_job` chỉ lấy base lock nên không deadlock); giữ từ check epoch đến read-back → select-tab + write nguyên tử theo window; nếu `result.cache_stale` thì **không** ghi receipt.

### 3.3 Entry `scripts/desktop_act.py:1-462`
- Params (`parse_argv` `:48-62`): `app/window/doc/control=textfield/action(read|write|append|find-doc|find-window)/text/text_file(utf-8-sig, exact bytes)/job_id=desktop-act-001/worker=B/base=.tmp/desktop-jobs/cache=on`; `text_file` ưu tiên giữ unicode.
- `main` (`:294-458`): tạo base; `init_job` nếu chưa có; gate sớm epoch → deny ghi `attempt.json` + `STOP STALE_EPOCH_DENIED`.
- Fast path cache (`:322-354`): key `app||doc` trong `session-cache.json`; read → verify tab selected + get_value → `receipt.json {via:cache-hit}` (read-only, không qua dispatch); write/append → `try_cached_write` (`:213-291`): `set_session(cached)` → **`dispatch_window`** với `_op`: get_states(tab_ref) → stale→`cache_stale` (fallback full path, không lỗi); switched tab → find+select trong lock; append đọc before; set-value (lỗi ref/window-not-found khi chưa reselected → `cache_stale`, else fail); read-back qua `build_write_result` (`:165-177`: write đòi `after==text`, append đòi `after==before+text` sau chuẩn hóa `\r\n`; sai → `{ok:False, stage:verify, reconciled:True, replayed:False, content_met:False}`); ok+reselected → cập nhật cache.
- Full path (`:356-458`): `ensure_session` (session_start `dubtool-act`, retry force_new khi LIST/FIND fail do session chết); `resolve_window` (lọc title substring, lấy match đầu); `resolve_doc` — **doc phải đúng 1, else STOP `DOC_NOT_UNIQUE_STOP` trước write**; read: select nếu cần → find control → get_value → `receipt.json {via:full-path}`; write/append: `_full_op` (select+find+set+read-back) trong `dispatch_window` → `emit_write` (`:186-210`): deny→`attempt.json`+`STALE_EPOCH_DENIED`; fail→`attempt.json`+`WRITE_FAILED`; ok→cache entry mới + stdout `{ok, doc, before, after, run, via, total_s, backend_calls...}`.
- `ensure_selected_by_ref` (`:140-162`): click tối đa 4 lần (2 lần đầu semantic, sau headed) + re-observe qua find; verify bằng `get_states`.

## 4. 7 adapter còn lại — guard/journal/receipt/reconcile từng cái

Mẫu chung (instagram/shopee/chatgpt/flow + youtube guarded-mutation): `_enforce_adapter_integrity()` đầu mọi side-effect (fail-closed khi `adapter_baseline.json` drift → từ chối đăng); `guard_duplicate(base, shortcode, journal_name)` → skip `ALREADY_IN_PUBLICATION` (đã có url/receipt trong publication) hoặc `UNRECONCILED_ATTEMPT` (journal tồn tại → reconcile read-only, không replay); journal ghi TRƯỚC click/submit duy nhất; UNKNOWN → `UNCONFIRMED_NO_REPLAY` + chỉ reconcile. Facebook/TikTok cùng triết lý nhưng journal nằm trong batch dir thay vì `reports/social-attempts/`.

### 4.1 Instagram — `scripts/instagram_post_one.py`
- Guard (`:140-151`): publication `publication-instagram.json` có `shortcode+url` → `ALREADY_IN_PUBLICATION`; journal `reports/social-attempts/<job>.json` (`job_id_for = "instagram-"+shortcode`, `:99-100`) tồn tại → `UNRECONCILED_ATTEMPT`.
- `_merge_publication` (`:153-160`): thay entry cùng shortcode, set `account`, `atomic_save`.
- Live submit `_upload_live_chrome_on_page` (`:286-428`): verify actor (`@username`+`ds_user_id`, `:198-230`) + `_ensure_clean_instagram_page` (`:245-252`); **journal BEFORE single click** (`:362-373`); nghe response `/api/v1/media/configure` (`on_response` `:377-402`): verified → journal `verified + media_pk/caption` → caller merge publication; không receipt → `unknown_needs_reconcile` + `UNCONFIRMED_NO_REPLAY, never replay` (`:408-428`).
- `_submit_once` (`:463-487`, injected `upload_fn`/cookie-mode): cùng pattern journal-trước-submit; disconnect (`_is_disconnect` `:61-67`) → `UNKNOWN` + hint disconnect.
- Caption (`:119-138`): gộp title/description không trùng, cắt `MAX_CAPTION=2200`; `delete_post` (`:658-691`) journaled riêng `instagram-delete-<key>.json`, không replay.
- Reconcile: đọc receipt configure (owner+caption) — xem `docs/platform-matrix.md` dòng IG.

### 4.2 Facebook — `scripts/facebook_post_one.py`
- Guard inline (`run_batch :126-140`, `run_shortcode :196-205`): publication `publication-facebook.json` có `shortcode+url` → skip; journal `reports/social-attempts/<job>.json` (`job_id_for :68-70`) tồn tại → `UNRECONCILED_ATTEMPT, never replay`. Account default `61595997638624` nếu publication chưa có (`:128, :198`).
- `_post_with_page` (`:102-115`): verify actor 2 lần + audience Public (theo platform-matrix); merge publication (thay shortcode, `atomic_save` `:109-113`).
- Disconnect → `receipt UNKNOWN + reconcile read-only` (`:174-175, :224-225`); không receipt → `UNCONFIRMED_NO_REPLAY + hint scripts/reconcile_olichopper_facebook.py` (`:178-179, :228-229`).

### 4.3 YouTube — `scripts/youtube_post_one.py` (Data API, không browser)
- Guard upload (`upload_one :203-220`): đã có `shortcode+videoId` trong `publication-youtube.json` → `ALREADY_IN_PUBLICATION`; journal `reports/social-attempts/youtube-<shortcode>.json` tồn tại → `UNRECONCILED_ATTEMPT`. `_publication/_record_publication` (`:189-200`): source of truth `{account=channelId, items[]:{shortcode/videoId/url/status}}`.
- Upload (`:203-284`): `_check_channel_match` trước submit (`:230` — sai kênh → block); journal trước bytes (`:250`); `_resumable_put` (`:288-322`): đứt transport giữa PUT → journal `bytes may have reached` + `UNCONFIRMED_NO_REPLAY`, không replay; bytes nhận nhưng video chưa list → journal + `UNCONFIRMED_NO_REPLAY` + merge publication với videoId (`:273-284`).
- `_guarded_mutation(kind, video_id)` (`:325-337`, dùng cho visibility/update/schedule/delete): integrity + channel match + journal `youtube-<id>-<kind>.json` tồn tại → skip; `_finish_mutation` (`:340-343`) ghi journal cuối.
- `reconcile(video_id)` (`:479-492`): **read-only, không bị journal chặn**; `videos.list` → `{present, title, privacyStatus, uploadStatus, publishAt, url, channel}`; CLI: `upload|visibility|update|schedule|delete|reconcile` (`:495-538`).

### 4.4 TikTok — `scripts/tiktok_post_one.py`
- Guard (`run_shortcode :97-100`, draft `:278`, `run_draft :362-364`): publication `publication.json` có shortcode → `ALREADY_IN_PUBLICATION`; `base/attempt-<shortcode>.json` (nằm trong batch dir, không phải social-attempts) tồn tại → `UNRECONCILED_ATTEMPT`. Manifest `download.json:saved[]` cung cấp `{shortcode, local_path, sha256, caption}` (`:93-94`); account `publication.account or "kemkhongta"` (`:36-37`).
- Pre-submit checks (`:119-176`): chờ `fname+Uploaded`, caption fill + verify `norm` 2 chỗ (editor + preview `count>=2`), audience `Everyone`, AI-label bật (+ modal `Turn on`), avatar menu đúng `tiktok.com/@<account>`; preflight `preflight-<sc>.json` (`:178-182`) rồi `pub.submit` (module `publish_maoziqi59_tiktok` `:27`).
- Reconcile (`:185-199`): poll 2 vòng `snapshot(page)` → `latest-posts.json`; khớp duy nhất `norm(caption)` → `pub.reconcile` → `{posted, url, audience}`; else `UNCONFIRMED_NO_REPLAY`.
- Draft path riêng (`_draft_with_page :255-288`, journal `draft-<sc>.json`, status `saved_draft` → skip; không ghi publication, không cho URL công khai).

### 4.5 Shopee — `scripts/shopee_post_one.py` (Seller Centre; AGENTS.md: KHÔNG test live, hướng affiliate là nghiên cứu `shopee.vn`)
- Guard (`guard_duplicate :121-131`): publication `publication-shopee.json` có `shortcode+url` → skip; journal `reports/social-attempts/<job>.json` tồn tại → `UNRECONCILED_ATTEMPT`. `_merge_publication` (`:133-140`) như mẫu IG.
- `_post_live_chrome_on_page` (`:237-267`): journal BEFORE submit (`:239`); `_reconcile_product` readback Seller Centre (`:198-212`) → có receipt → journal `verified + url` + merge; không → `UNCONFIRMED_NO_REPLAY`.
- Actor verify `username haodaojr` (`:143-157`); phụ: `update_profile` (journal `shopee-profile-<acc>.json`), `read_orders` → `orders-readonly.json` (read-only, `:319-344`).

### 4.6 ChatGPT — `scripts/chatgpt_post_one.py`
- Guard (`:114-124`): publication `publication-chatgpt.json` có `shortcode+(url|reply_sha256)` → skip; journal tồn tại → `UNRECONCILED_ATTEMPT`. `_merge_publication` (`:127-134`).
- Live (`run_shortcode :269-321`, `run_batch :323-404`): journal `posted:false, streaming` TRƯỚC submit (`:283`); `_submit_once` (`:175-219`) 1 lần → `_wait_reply_done` (event, `:150-173`) → `_extract_reply` (`:221-228`) → journal `verified + reply_sha256/url` + merge; không receipt → `UNCONFIRMED_NO_REPLAY`; disconnect → `UNKNOWN`.
- Phụ đều journaled: `new_chat` (draft ≈ session chưa gửi), `rename_conversation`, `delete_conversation` (journal `chatgpt-delete-<code>.json`, tồn tại → skip, `:514-550`), `get_or_set_model`, `verify_profile` (`:446-626`). Prompt ≤8000 chars (platform-matrix).

### 4.7 Google Flow — `scripts/flow_post_one.py` (text-to-video)
- Guard (`:115-125`): publication `publication-flow.json` có `shortcode+(url|video_sha256)` → skip; journal `reports/social-attempts/flow-<shortcode>.json` → `UNRECONCILED_ATTEMPT`. `_merge_publication` (`:128-135`).
- `_generate_live_chrome` (`:396-432`): journal BEFORE Generate click (`:398`); `_wait_render_done` event-based, timeout `RENDER_TIMEOUT_S` (`:245-280`); xong → download MP4 + `sha256_of` (`:138-144`) → journal `verified + url/sha256` + merge; không receipt → `UNCONFIRMED_NO_REPLAY`; prompt ≤4000 chars, `_apply_cheapest_settings` (`:301-313`).
- `reconcile_one` (`:545-565`) read-only mở trang video Flow qua tab `RESEARCH`; `download_one` (`:575-605`) tải remote file; `verify_profile` journaled (`:607-633`).

## 6. Vòng 2 (2026-11-21) — Studio bọc Pipeline.run thật (merge mới)

Phạm vi vòng 2: `core/pipeline.py::Pipeline.run` + 8 step + cache/invalidation +
`core/cache.py` (đã ghi chi tiết ở §1 vòng 1 — vòng 2 chỉ bổ sung góc nhìn Studio gọi),
và `app.py` các tab Studio gọi pipeline thế nào. Kết luận quan trọng: **`app.py`
KHÔNG có request_id/revision/guard kiểu Studio** — đó là cơ chế của
`core/studio_store.py` + `core/studio_service.py` (timeline nhiều clip), còn pipeline
dub 8 bước dùng `project.json/steps_done + *.done + signature`, hai hệ guard khác nhau,
nối với nhau duy nhất qua `create_from_dubtool` / `handoff`.

### 6.1 Cách `app.py` gọi pipeline (file:dòng)
- `_pipeline()` (`app.py:22-23`): mỗi handler tạo `Pipeline()` mới (đọc `config.yaml`,
  `configure_env(offline=True)`, tạo `cache/output/temp`). Không có singleton, không có
  request_id — idempotency dựa vào `video_id + *.done + signature` trong cache.
- Tab Nhập — `do_download` (`app.py:42-62`): `p.run(src, steps=["download"])`; sau đó
  tự `ffprobe` lấy duration hiển thị (không qua pipeline). `state_video` (gr.State) giữ
  `video_id` cho các tab sau.
- Tab Nhập — `do_run_to_translate` (`app.py:65-82`): `p.run(src, src_lang, tgt_lang,
  default_voice, steps=["download","audio","stt","translate"])`; trả `rows`
  `[id,start,end,src_text,tgt_text,flags]` cho Dataframe tab Phụ đề.
- Tab Phụ đề — `save_segments` (`app.py:106-123`): ghi `segments.json` trực tiếp rồi
  **tự xóa marker downstream** `tts/sync/mix/render` (`done_path(video_id, step)`,
  `core/cache.py`) + cắt `steps_done` — cùng pattern với
  `Pipeline.revoice_segment` nhưng KHÔNG qua `_mark_step` (không xóa marker cùng-step
  khác-hash, không đụng tới `download/audio/stt/translate`). Invariant: sửa text =
  chạy lại từ `tts`.
- Tab Phụ đề — `do_tts_mix_render` (`app.py:126-142`): `p.run(source or
  proj["source"], src_lang/proj, tgt_lang/proj, default_voice/chọn, steps=["tts",
  "sync","mix","render"])`. Nguồn lấy từ textbox, fallback `project.json:source`.
- Tab Giọng — `revoice` (`app.py:154-167`): parse `seg_id` int (lỗi → `gr.Error`) rồi
  `p.revoice_segment(video_id, seg_id, new_voice, progress_cb)` — xóa marker
  tts→render + file `tts/{seg}_*.wav` rồi `run(steps=[tts,sync,mix,render])`.
- Tab Hình — `add_overlay` (`app.py:195-209`): append `project.overlays[]`
  `{type,x,y,w,h,t_start,t_end,text,font}` + `save_project` + **chỉ xóa marker
  `render`** (overlay không ảnh hưởng audio → không đụng tts/sync/mix). Invariant:
  overlay đổi = render lại duy nhất.
- Tab Xuất — `do_final_render` (`app.py:213-229`): như `do_tts_mix_render` nhưng thêm
  `overlays=proj.overlays, burn_subtitles=burn`.
- Tab Đưa sang YouTube — `submit_studio` (`app.py:257-266`): `YouTubeStudio().submit(
  video_id, title, description, tags)` → trả `{productionId}` + thông điệp "hàng chờ
  duyệt, CHƯA tải lên YouTube". Tab Timeline — `open_multitrack` (`app.py:343-352`):
  `get_studio_service().create_from_dubtool(video_id)` → link `/timeline?project=...`.

### 6.2 Guard kiểu Studio (revision) — `core/studio_store.py`, `core/studio_service.py`
- `studio_store._expect` (`studio_store.py:116-119`): mọi mutation so
  `expected_revision` với `state.project.revision`; lệch → `ConflictError("Dự án đã
  thay đổi ở phiên khác. Nạp lại...")`. Mỗi `_replace` (`:121-128`) bump
  `revision+1`, push undo (giới hạn `HISTORY_LIMIT`), xóa redo.
- Render dedupe + stale (`studio_service._start_render :259-281`): hàng đợi tối đa 4
  job (`queued+running`); job trùng `(project_id, revision, preview)` đang active →
  trả job cũ (không render lại). `_run_render` (`:289-349`): checkpoint receipt
  `(output,audio,segments)+hashes` còn đủ file thì dùng lại; recover render sang
  `attempt-<n>/` mới (encoder mồ côi không ghi đè); trước render và sau render đều so
  `_signature(project)` (`:293, :327`) — timeline đổi giữa chừng → job `stale`, không
  được handoff YouTube.
- `handoff` (`studio_service.py:449-497`): đòi `export.signature == _signature(project)`
  + digest 3 file khớp export, transcript thật (không tự bịa), rồi chép
  `mix.wav/segments.json/render.done/plan.json` vào `cache/timeline-<project>/editor/
  <job>/` + `project.json {editor_pending:False, editor_export:{output,audio,segments,
  marker,plan_hash}}` và `render.done {signature}` — chính là cầu nối để bản timeline
  đi tiếp qua `YouTubeStudio().submit` như một "video dubtool".

### 6.3 Cầu `create_from_dubtool` — `studio_service.py:411-447`
- Guard vào (`:413-418`): `video_id` khớp `[A-Za-z0-9_-]{1,160}`; đọc
  `cache/<vid>/project.json` qua `_bounded` (chặn path traversal); đòi
  `not editor_pending` và `render.done` tồn tại else conflict "Render bản cuối trước".
- Dựng project Studio mới theo đúng w/h probe từ `output`, import output làm asset,
  map `segments.json → cues` (cắt theo duration, giữ `src/tgt/flags`), thêm track
  video + 1 clip full-duration, ghi `dubtool-sources.json {asset: {video_id,
  synthetic}}` giữ provenance media tổng hợp.

### 6.4 Invariant bổ sung vòng 2 (Studio bọc Pipeline trong C)
1. Giữ nguyên ngữ nghĩa `steps` subset + `_hydrate` (`pipeline.py:392-412, :420-448`):
   chạy riêng bước sau phải nạp lại wav/segments/timeline từ cache, không đòi chạy
   lại từ đầu.
2. Sửa phụ đề/text (`save_segments`, `revoice_segment`) → invalidate từ `tts`;
   thêm overlay → invalidate chỉ `render`. Không gộp hai đường này.
3. Hai hệ guard không thay thế nhau: pipeline dùng `*.done + signature + steps_done`;
   Studio timeline dùng `revision + signature + render.done`. Cầu nối duy nhất là
   `create_from_dubtool` (dub→timeline) và `handoff` (timeline→duyệt YouTube); C phải
   giữ cả hai cửa với cùng điều kiện conflict.
4. `submit_studio` chỉ đưa vào hàng chờ duyệt — cấm bọc thành "đăng luôn YouTube".

## 5. Invariant bắt buộc Miro phải giữ khi bọc lại
1. Thứ tự STEPS + invalidation downstream của `_mark_step` (kể cả khi nội dung giống nhau); `revoice_segment` chỉ xóa marker tts→render.
2. JSON runtime qua `load_json/atomic_save`; publication là source of truth account/caption; caption/account từ manifest, không hard-code.
3. Guard trùng 2 lớp (publication + journal) trước mọi side-effect; UNKNOWN/`UNCONFIRMED_NO_REPLAY` chỉ reconcile read-only, không replay; disconnect không reconnect/restart Chrome trong adapter.
4. Browser: không tự mở Chrome; profile phải có bằng chứng `chrome://version` sống; tab lease 1 owner, TAB_BUSY không tạo tab mới; protected/dirty tab không navigate; đóng tab chỉ khi registry-created.
5. Desktop: mọi mutation qua `dispatch(_window)` dưới lock + epoch check tươi (2 lần khi có hold); receipt `receipt-<run>` bất biến; doc ambiguity → STOP trước write; write verify bằng read-back chuẩn hóa newline.
6. YouTube channel-match trước mọi mutation; Shopee không test live Seller Centre; IG không đưa URL profile `/reels/` cho yt-dlp (per-reel URL + SHA-256, AGENTS.md).
