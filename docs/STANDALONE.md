# Miro Standalone — cach mo va dung doc lap (Slice 04)

## Khoi dong 1 cham
- Cach 1 (khuyen nghi): chay `Miro-Standalone.bat` — Launcher len BE + Bridge + FE, tu mo UI `/runtime`.
- Cach 2: `python windows/miro.py start --only be,bridge,fe` (`--no-browser` neu khong muon tu mo UI).
- Kiem tra: `python windows/miro.py status` — ca 3 `alive=True health=http-200`.
- Tat dung cach: `python windows/miro.py stop` (Ctrl+C chi dung launcher foreground).

## Cong dich vu
- BE: http://127.0.0.1:8770 (LM TaskService, research, media_intel, tasks).
- Bridge: http://127.0.0.1:18767 (Extension + Chrome Profile 20).
- FE: http://127.0.0.1:3100 (Next.js; proxy /api -> BE that qua beforeFiles rewrite).
- Ports doi duoc qua MIRO_BE_PORT / MIRO_BRIDGE_PORT / MIRO_FE_PORT.
- FE port mac dinh ban: Launcher tu dung port tu do ke tiep (3101-3150), manifest ghi port that.
- Gioi han: FE van la `npm run dev` (chua phai production build) — cho Slice sau neu can.

## Dung UI
- `/runtime`: BE / wiring / bridge tabs / so tasks (poll 5s).
- `/tasks-live`: giao viec da nghiem thu (actor/video/search TikTok) qua POST /tasks/run-message.
- `/tasks-live/[id]`: trang thai + evidence + events + nut Dung task.
- Task luu tai `var/tasks.db`, chuyen trang / dong mo lai khong mat.
- Khong co mock ket qua: trang live bao loi that khi BE mat ket noi.

## Gioi han da biet (giu PARTIAL/BLOCKED)
- STT/sherpa (can approval), VLM (denied), 3/5 video KANS 377 audio-only.
- Cold-restart pairing van bug rieng.
- L3 multi-task concurrency, L4 storyboard embed trong detail: PARTIAL.
