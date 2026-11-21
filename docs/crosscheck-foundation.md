# Đối chiếu độc lập reread-foundation (commit 1174cf9)

Ngày: 2026-11-21. Đọc trực tiếp A (`C:\dubtool`) + C (`C:\Miro`), xác minh từng claim.
Ký hiệu: ✅ ĐÚNG · ⚠️ ĐÚNG MỘT PHẦN / cần hiệu chỉnh · ❌ SAI (không có mục nào sai hẳn).

## 1. Tasks T1–T4 + bug gốc A

| Mục | Kết luận | Bằng chứng |
|---|---|---|
| T1 resume không verify signature | ✅ ĐÚNG (thiếu chính) | C `tasks/service.py:317-327` chỉ chặn `pending_mutation`, không so snapshot nào; A `studio_service.py:381` chặn `CHECKPOINT_STALE` trước resubmit |
| T2 mất dedupe revision-level | ✅ ĐÚNG (thiếu chính) | C `service.py:122-130` chỉ fingerprint theo `request_id`; A `studio_service.py:270-272` dedupe `(project_id, revision, preview)` trong active |
| T3 `_guarded` retry unreachable | ✅ ĐÚNG, kèm sắc thái (dưới) | C `pipeline.py:52,551-561` chỉ bắt `(OSError, TimeoutError, ConnectionError)`; engine ném `PipelineError(RuntimeError)` ở mọi step (`:134,198,290,387...`), `run():783-786` gói mọi `Exception` lạ thành `PipelineError` trước khi `_guarded` kịp thấy lỗi gốc. Sắc thái: `OSError` thô (vd file ops ngoài engine) vẫn lọt vào nhánh retry — nhưng mọi lỗi pipeline chuẩn thì không |
| T4 không đánh stale sau render | ✅ ĐÚNG (thiếu) | C `_step_render` (`pipeline.py:709-732`) không đọc signature timeline trước/sau render; `save_project` (`:468-478`) ghi vô điều kiện; A check ở `studio_service.py:324-330` |
| T5 restart gộp NEEDS_ATTENTION | ✅ ĐÚNG (nhẹ, đúng như ghi) | C `service.py:294-315` ba nhánh → NEEDS_ATTENTION; A `:61-73` phân biệt RECOVER-tự-động (retryCount++, resubmit `:80-81`) |
| Bug gốc A1 sleep-giữ-pool-1 | ✅ ĐÚNG | A `:35` `max_workers=1` + `:346-349` `time.sleep(delay)` rồi đệ quy trong worker |
| Bug gốc A2 `process_identity` rối | ✅ ĐÚNG | A `:64` + `browser_contracts.py:29-61`: `(None,None)` khi không xác minh được → rẽ vào blocked (fail-closed nhưng đọc khó) |
| Bug gốc A3 stop chỉ ở 2 biên | ✅ ĐÚNG | A chỉ gọi `_render_control_boundary` ở `:292` và `:319`; `render_project` (`:315`) chạy xuyên |
| Bug gốc A4 TOCTOU resume | ✅ ĐÚNG | A check `:381` rồi submit `:388`, bù bằng re-check trong `_run_render` `:293-294`; C không có cả hai |

Không bỏ sót: cap-4 (`handlers.py:29,53` + A `:253-256`), receipt-reuse một nửa (`pipeline.py:709-732` vs A `:306-318`), 2-phase stop + watchdog (`service.py:242-291` — port đủ, giữ), `restart()` ba mã lỗi đúng như mô tả.

## 2. Desktop D1–D4 + bug gốc A

| Mục | Kết luận | Bằng chứng |
|---|---|---|
| D1 window-lock default per-base | ✅ ĐÚNG (sai chính) | C `dispatch.py:119` default `base/"window-locks"`; A `desktop_dispatch.py:130` default `ensure_state_dir()/"window-locks"` (chung mọi base, docstring `:117-127` nêu rõ lý do) |
| D2 không verify tab-selected | ✅ ĐÚNG (thiếu chính) | C `act.py:138-163` `_write` đi thẳng find→write→read-back, không `get_states`/click-reselect; grep `get_states\|ensure_selected\|force_new\|attempt` trong C `act.py` = rỗng; A `desktop_act.py:140-162` + `_full_op :421-444` |
| D3 không tự hồi session | ✅ ĐÚNG (thiếu) | C `act.py` không có `ensure_session`/`force_new`; A `:359-381` retry 1 lần với `LIST_WINDOWS_FAILED`/`FIND_DOC_FAILED` |
| D4 không `attempt.json`/call-count | ✅ ĐÚNG (thiếu nhẹ) | C `act.py` không ghi `attempt.json`; A `:190-191,201-203,383-385` + `summarize_calls :180-184` |
| D5 lock no-op ngoài Windows | ✅ ĐÚNG (kế thừa, đúng như ghi) | C `dispatch.py:36-48` chỉ `msvcrt` khi `nt`, y hệt A `:48-59` |
| Bug gốc desktop 1–4 | ✅ ĐÚNG cả 4 | (1) A `desktop_dispatch.py:48,67-73` no-op ngoài `nt`; (2) A read full-path `desktop_act.py:393-412` ngoài lock, C cho read qua `dispatch_window` (`act.py:126-131`) — siết hơn, giữ cách C; (3) A `emit_write :196-199` chỉ lưu cache khi `ok`; (4) A `:366-381` retry đúng 2 mã lỗi |

Không bỏ sót: `transfer_job(lock_path)` khác chữ ký (C `gate.py:70` vs A `desktop_gate.py:46`), `current_epoch` chỉ có ở C (`gate.py:63`), `_save` tmp+replace không fsync + đọc `utf-8-sig` (C `gate.py:22-42` — tương đương A qua `json_io`/`atomic_save`), `backend.py` allowlist + scrub env + `write()` alias + `MIRO_AGENT_DESKTOP_BIN` (C `:30-39,68-77,207-209` — tốt hơn A, giữ), state-dir/session-name khác tên là cố ý.

## 3. Launcher L1–L4

| Mục | Kết luận | Bằng chứng (`windows/miro.py`) |
|---|---|---|
| L1 stop trễ trong backoff | ✅ ĐÚNG | `:311-315`: `time.sleep(delay)` (tới 30s) rồi mới check `CONTROL`; check vòng 1s ở `:301` không bù được |
| L2 history mất khi launcher restart | ✅ ĐÚNG | `RestartBudget.history` (`:68-83`) chỉ trong RAM, không persist ra `STATE_DIR` |
| L3 `wait_ready` tuần tự 90s/service | ✅ ĐÚNG, đúng mức "ghi nhận" | `:292-294` loop từng service |
| L4 log `w` + handle không rotate | ✅ ĐÚNG (nhẹ) | `:286` mở `"w"`, restart tái dùng `handles[index]` (`:318-320`) nối tiếp cùng file |
| "Không có launcher tương đương phía A" | ✅ ĐÚNG | `C:\dubtool\windows\` không tồn tại (glob rỗng) — `windows/miro.py` là đồ mới của C |

## 4. Chốt

- **Không có mục nào SAI.** T1/T2/D1/D2/L1 đúng là thiếu/sai chính; T3/T4/D3/D4/L2-L4 đúng mức độ đã ghi.
- **Một sắc thái cần hiệu chỉnh ở T3**: nhánh retry `_guarded` không phải "không bao giờ kích hoạt" theo nghĩa tuyệt đối — `OSError` thô vẫn bắt được; đúng ra là **mọi lỗi pipeline chuẩn (đã gói thành `PipelineError`) không bao giờ retry**. Đề xuất sửa 1 dòng trong reread: `T3 (sai): _guarded retry unreachable` → `... unreachable với PipelineError`.
- **Không phát hiện bỏ sót**: mọi hành vi A đối chiếu (cap, dedupe, recover, pause/amendments, receipt, cache fast-path, read-back, epoch/lock/receipt, DACL) đều đã xuất hiện trong reread-foundation với file:dòng khớp code thật.
