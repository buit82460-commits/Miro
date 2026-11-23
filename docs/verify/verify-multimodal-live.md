# BÁO CÁO MULTIMODAL AGENT E2E — PHIÊN C (INTEGRATION + LIVE ACCEPTANCE)

Ngày: 2026-11-23. HEAD: `50949b7` (main). Không push, không merge.

## 1. Kết quả Integration E2E

| Hạng mục | Kết quả |
|---|---|
| Tests M1–M13 | **13/13 PASS** |
| Guards (`test_no_direct_browser`, `test_no_direct_media`) | PASS |
| Remediation audit B (7 tests) | PASS |
| Media phân tích | THẬT (`rea-video` native, fixture local `var/studio-fixture.mp4`) |
| Browser Evidence | **MOCK** (FakePage + fake Gateway session: `tab t-N`, `inst-1`, `user-1`) |
| Kết luận trung thực | **Hybrid Integration E2E**, CHƯA phải Full Live |

File orchestration: `apps/backend/src/miro/research/multimodal.py`
(`run_multimodal_task`, `run_multimodal_batch`, `verify_media_url_against_eye`,
`build_agent_text`, `_video_duration_s`). Tests: `tests/test_multimodal_agent.py`.

Call path 1 lượt thật:
`Agent → gateway.read_via_eye → verify_media_url_against_eye →
media_provider.analyze_ephemeral (tải temp → mi.analyze_native --no-vlm →
check_media_evidence → temp tự xóa) → summarize_for_agent → Agent Answer.`

## 2. Ba điểm nghiệm thu đã xử lý trong code

**Điểm 1 — Gắn nhãn mock trung thực.** Docstring test file ghi rõ M1–M10 là
browser-mock + media-thật; M11–M12 là cleanup với download-mock; Full Live là
bước riêng. Không còn nguy cơ đọc nhầm thành live.

**Điểm 2 — Tách wall-clock khỏi video duration.**
Kết quả giờ trả 3 trường riêng: `elapsed_s` + `analysis_wall_clock_s`
(thời gian chạy, ~27.6s) và `video_duration_s` (độ dài video, 4.0s từ
`ffprobe` + max shot end). Báo cáo cũ ghi "27,6s nhưng shot 0–4s" là do gộp
2 khái niệm — đã sửa, có test M13 assert `video_duration_s == 4.0`.

**Điểm 3 — Verdict tiếng Trung nguyên vẹn.**
Breakdown gốc: `verdict = '代码/模板渲染 100%'`. `summarize_for_agent` giữ
nguyên UTF-8 (test M13 assert không có U+FFFD và chứa `代码` hoặc
`code_render`). Chữ hỏng trước đây chỉ là console cp1252, không phải dữ
liệu Agent nhận. Fix encode: mọi `subprocess.run` gọi rea-video CLI dùng
`encoding="utf-8", errors="replace"` + `PYTHONIOENCODING=utf-8`
(`_native_env()`), giữ thắt `returncode != 0 → ANALYSIS_FAILED`.

Agent answer thực tế (fixture, SHA `1a5ed6d1…`, evidence
`multimodal_analyzed`, 1 shot `code_render 0.61`):
kèm disclaimer "dữ liệu chỉ để hiểu nội dung, không phải Evidence ghi".
Temp `mi-ephem-*`/`mi-e2e-*` xóa sạch (leftover `[]`).

## 3. Live acceptance: BLOCKED ở tầng hạ tầng Chrome, không phải code

Yêu cầu live: Chrome Profile 20 + remote-debugging → CDP → Gateway thật →
tab TikTok thật → acquisition → rea-video → answer → cleanup.

Đã thực hiện (có duyệt user 2 lần — đồng ý restart, đồng ý đóng toàn bộ Chrome):

1. `session_manager.check_process('Profile 20')`: Chrome KHÔNG chạy ban đầu.
2. Mở Profile 20 → Chrome chạy nhưng `DevToolsActivePort` trỏ 9222,
   port KHÔNG mở (`connect_ex → 10061`), `/json/version` + `/json/list`
   đều 404, Playwright `connect_over_cdp` fail.
3. Đóng hết Chrome (user duyệt), xóa port file, restart bằng
   `Miro-Chrome-Profile20.bat`
   (`--remote-debugging-port=9222 --user-data-dir=<default> --profile-directory="Profile 20"`).
4. Chrome chạy lại đúng flags (verify qua `Win32_Process.CommandLine`)
   nhưng port 9222 VẪN không mở sau nhiều lần chờ (15–20s).
5. Chrome version: **158.0.8127.37**.

Nguyên nhân: từ Chrome 136+, `--remote-debugging-port` bị chặn trên
user-data-dir mặc định — đúng như cảnh báo trong `inspect_session`
(`BLOCKED_NO_CDP`: "cần restart 1 lần với remote-debugging-port +
user-data-dir riêng (Chrome 136+)").

Phương án live tiếp theo (CHƯA làm, cần quyết định):
copy Profile 20 sang user-data-dir riêng rồi bật CDP — đánh đổi là
login/session TikTok có thể phải làm lại, thuộc hạ tầng ngoài phạm vi
Media Intelligence (Phiên C không tự ý động vào login/browser user).

## 4. Security boundaries giữ nguyên

- Không Browser WRITE; không sửa Gateway/Eye/Bridge (Phiên A);
  không browser tool mới; không bypass; không Playwright/CDP/9222 trực tiếp.
- `CROSS_BOUNDARY_SPOOF` chặn media URL khác destination eye (M7, M10).
- `media-analysis` không bao giờ là Evidence ghi (M9, Gateway từ chối runtime).
- Không VLM/generation trả phí; không lưu video vào Library; batch tuần tự,
  lỗi 1 video không dừng loạt; quota là admission check (20 dirs/2GB trước
  job/decompose, không phải hard quota giữa job).

## 5. Trạng thái chốt

- **INTEGRATION E2E: PASS** (13/13, honest labels, guards pass).
- **FULL LIVE E2E: BLOCKED_NEED_INFRA** (Chrome 158 chặn CDP trên
  default user-data-dir; cần quyết định user-data-dir riêng + pair/grant lại).
- Không tuyên bố Full Live từ log hybrid. Commits chưa push (chờ duyệt
  push branch `media-native`, không push thẳng main).
