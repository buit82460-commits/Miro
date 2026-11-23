# Miro Docs — bản đồ tài liệu (BẮT BUỘC ĐỌC ĐẦU PHIÊN)

> Mọi agent (người, subagent, 3-agent reader/code/checker) **BẮT BUỘC đọc file này
> TRƯỚC TIÊN** khi bắt đầu bất kỳ task nào trong repo Miro. Không được bỏ qua.

## 1. Thứ tự đọc bootstrap (cứng)

1. **File này** (`docs/README.md`) — nắm bản đồ.
2. `docs/verify/verify-threads-loop.md` + `docs/verify/verify-foundation.md` —
   biết việc nào ĐẠT/CHƯA (đọc mục mới nhất trước).
3. `docs/PLATFORM_RUNBOOK.md` — **khi vào task đăng bài** (bảng adapter + flow
   chuẩn + checklist trinh sát REA Q1–Q10).
4. `docs/reread/reread-foundation.md` + `docs/reread/crosscheck-foundation.md` —
   khi cần nền tasks/desktop/launcher.
5. Theo task, đọc tiếp file chuyên đề trong các thư mục dưới.
6. Tra cứu quy trình 3-agent (2 reader → code → Checker ĐẠT mới commit → push):
   `docs/ba-ben/`.

Không đọc lại file đã đọc trong phiên nếu nội dung không đổi.

## 2. Bản đồ thư mục

| Thư mục / File | Nội dung |
|---|---|
| `docs/PLATFORM_RUNBOOK.md` | Runbook chuẩn mọi platform: 1 adapter/platform, flow đăng, mắt–não, checklist REA Q1–Q10 |
| `docs/foundation/` | Nền + kiến trúc: `architecture.md`, `source-freeze.md` (mốc legacy), `baseline-m0.md`, `runtime-deps.md`, `coverage.md`, `platform-matrix.md`, `bao-cao-tong-hop.md` |
| `docs/readers/` | Đọc sâu nguồn legacy: `reader-dubtool.md`, `reader-jarvis.md`, `browser-read-notes.md`, `desktop-read-notes.md`, `fe-read-notes.md`, `editor-handlers.md` |
| `docs/reread/` | Đối chiếu code C vs A: `reread-{foundation,eye,publisher,studio,tab}.md` + `crosscheck-*.md` (kiểm độc lập, kết luận: reread ĐÚNG) |
| `docs/verify/` | Biên bản Checker: `verify-{foundation,threads-loop,publisher,studio,studio-audio,browser,security-fix}.md` + `live-read-profile20.md` (runbook live-read) |
| `docs/capability/` | Bản đồ năng lực 52 lĩnh vực / 12 nhóm: `capability-map.md` (quy hoạch tham khảo, chưa phải code) |
| `docs/security/` | Hardening: `eye-gate.md` (gate 8 điểm WRITE), `security-contract-extension.md`, `SECURITY_INTEGRATION_REPORT.md`, `INTEGRATION_SECURITY_REVIEW.md`, `REA_READ_SECURITY_REVIEW.md`, `REA_REMEDIATION_REVIEW_B.md`, `harness-allowlist-report.md` |
| `docs/ba-ben/` | **Ngoài luồng**: trao đổi 3 bên A/B/C. Đọc/ghi tự do, KHÔNG BAO GIỜ `git add/commit/push` thư mục này |

## 3. Lưu ý

- `docs/ba-ben/` là vùng ngoài luồng — mọi file hỏi-đáp trong đó phải có đủ
  slot A/B/C (ghi "không có" nếu trống).
- Publication + journal là source of truth, không suy đoán trạng thái đăng.
- Luật cứng REA-mắt: mọi thao tác trình duyệt qua Browser Gateway
  (`miro/browser/gateway.py`). Chi tiết xem `PLATFORM_RUNBOOK.md` §7.
