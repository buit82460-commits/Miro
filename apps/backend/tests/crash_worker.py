"""Worker con: mo workspace co manifest, ghi file gia, roi TREO cho bi kill.

Chay that 1 process rieng de test crash recovery (kill -9 tuong duong).
Khong import miro o day cung duoc — chi can tao dung layout manifest.
Dung: python crash_worker.py <job_id>
"""
import json
import sys
import time
from pathlib import Path

job_id = sys.argv[1] if len(sys.argv) > 1 else "testkill"
root = Path(__import__("tempfile").gettempdir()) / "mi-work"
ws = root / f"mi-{job_id}"
ws.mkdir(parents=True, exist_ok=True)
import os
(ws / "manifest.json").write_text(json.dumps({
    "job_id": job_id, "pid": os.getpid(), "created_at": time.time(),
    "status": "running", "tool": "miro-media-intel-p0",
    "provider": "rea-video"}), encoding="utf-8")
(ws / "src.mp4").write_bytes(b"\x00" * 1024)
(ws / "out").mkdir(exist_ok=True)
(ws / "out" / "partial.json").write_text("{}", encoding="utf-8")
print(f"WORKER_READY {job_id} pid={os.getpid()} ws={ws}", flush=True)
while True:
    time.sleep(1)
