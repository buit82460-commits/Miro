# Editor handlers — DubTool 8 tab -> Miro

> File nay map tung thao tac trong `C:\dubtool\app.py` (build_ui, 8 tab)
> sang ham Miro trong `apps/backend/src/miro/studio/handlers.py`.
> Nguyen tac: moi call truyen `request_id` + `expected_revision`;
> gui lai cung ma tra dung `render_id`; LLM tat van chay local.

| # | Tab DubTool | Ham DubTool (`app.py`) | Ham Miro (`StudioHandlers`) | Ghi chu idempotency |
|---|-------------|------------------------|-----------------------------|---------------------|
| 1 | Nhap | `do_download(source, file)` | `do_download(source, request_id, expected_revision)` | `render-<sha16(request_id)>`; tai lai khong tao job moi |
| 1 | Nhap | `do_run_to_translate(...)` | `translate(video_id, request_id, expected_revision, src_lang, tgt_lang)` | local glossary `[tgt] src`; khong goi API |
| 1 | Nhap | `on_voice_selected` / `filter_voices` | (client-side; chon `voice` string truyen vao `revoice`) | khong can server state |
| 2 | Phu de | `load_segments(video_id)` | `load_segments(video_id)` | read-only |
| 2 | Phu de | `save_segments(video_id, df)` | `save_segments(video_id, rows, request_id, expected_revision)` | bump revision; render_done=false |
| 2 | Phu de | `do_tts_mix_render(...)` | `tts_mix_render(video_id, request_id, expected_revision)` | fake mp4 local, khong GPU |
| 3 | Giong | `revoice(video_id, seg_id, voice)` | `revoice(video_id, seg_id, voice, request_id, expected_revision)` | cung request_id tra dung render_id |
| 4 | Hinh | `preview_frame(...)` | `preview_frame(video_id, request_id, overlay, expected_revision)` | preview 5s khong doi revision |
| 4 | Hinh | `add_overlay(...)` | `add_overlay(video_id, overlay, request_id, expected_revision)` | overlay list trong project; render_done=false |
| 5 | Xuat | `do_final_render(..., burn)` | `do_final_render(video_id, request_id, expected_revision, burn_subtitles, overlays)` | fake final mp4; khong ffmpeg |
| 5 | Xuat | `open_output_dir()` | (client mo thu muc output local) | khong can port |
| 6 | AI Editor | `editor_load` / `editor_projects` | `_project(video_id)` (noi bo) | doc state noi bo |
| 6 | AI Editor | `editor_plan(instruction, previous, use_ai, ...)` | `editor_plan(video_id, instruction, request_id, expected_revision, previous, use_ai)` | `use_ai` bi bo qua: luon fallback `local_rules.local_plan`; khong can LLM key |
| 6 | AI Editor | `editor_render(plan, preview)` | `editor_render(video_id, plan, request_id, expected_revision, preview)` | preview khong bump revision; final co bump |
| 6 | AI Editor | `editor_restore` | `editor_restore(video_id, request_id, expected_revision)` | reset plan rong |
| 6 | AI Editor | `editor_import_audio(file)` | (defer: thu vien am thanh user) | chua port — khong chan R2/R3 |
| 7 | YouTube | `studio_sources` / `use_studio_source` / `submit_studio` | `submit_studio(video_id, title, description, tags, request_id, expected_revision)` | chi tao draft `prod-<hash>`; KHONG upload; doi render_done=true (409 neu chua) |
| 8 | Timeline | `open_multitrack(video_id)` | `open_multitrack(video_id, request_id, expected_revision)` | tra `/timeline?project=studio-...`; doi render_done=true (409 neu chua) |

## Luong goi chuan (client)

1. `do_download(source, request_id=R1)` -> lay `video_id`, `revision`.
2. Moi call tiep theo truyen `expected_revision` = revision moi nhat da thay.
3. Retry/timeout: gui lai **cung `request_id`** -> nhan dung `render_id` + `idempotent_replay=true`.
4. Sai revision (timeline doi giua chung): server tra 409 -> client reload roi tao `request_id` moi.

## Che do khong LLM / khong GPU

- `editor_plan(..., use_ai=True)` van chay: bo qua LLM, dung `local_rules`.
- Test R2/R3 dung file gia (`FAKE-*` mp4/marker), khong goi ffmpeg/whisper/GPU.
