# Biên bản xác minh — Studio audio (commit 38acc8b)

- Commit kiểm tra: `38acc8b0486862f0da6648db1e4a2c96a65989c6`
  (studio: fix render mặc định thiếu -map 1:a → MP4 ra tiếng gốc dù đã mix + fallback an toàn khi thiếu mix)
- Kết quả: **ĐẠT**

## Đối chiếu diff vs review
- Lỗi review: nhánh render mặc định (không overlay/subtitles/preview) thiếu `-map 1:a` → MP4 ra tiếng gốc.
- Diff 38acc8b sửa đúng: cả 3 nhánh (preview / filter / mặc định) đều `-map` audio qua biến
  `audio_map` (`1:a` khi có mix, `0:a` fallback khi thiếu mix); input mix chỉ thêm khi file tồn tại.
- Hiện trạng `apps/backend/src/miro/studio/pipeline.py` (`render_video`, dòng ~363-388) khớp diff.

## Lệnh chạy
```
cd C:\Miro\apps\backend
python -m pytest tests/test_studio_render_audio_map.py tests/test_studio_real_pipeline.py tests/test_studio_idempotency.py -q
```

## Kết quả
```
19 passed, 1 warning in 10.39s
```
(test audio map mới đo tần số thật C13–C15: 440Hz gốc vs 880Hz mix — pass.)
