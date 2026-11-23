"""Test crash/restart recovery THAT (process kill, khong mock).

Chay: python -m pytest tests/test_media_intel_recovery.py -q
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

mi = pytest.importorskip("miro.media_intel")

WORKER = Path(__file__).with_name("crash_worker.py")


def read_manifest(ws: Path) -> dict:
    return json.loads((ws / "manifest.json").read_text(encoding="utf-8"))


def test_kill_mid_analysis_then_sweep(tmp_path=None):
    job = "killtest1"
    ws = mi.workspace_root() / f"mi-{job}"
    if ws.exists():
        import shutil
        shutil.rmtree(ws, ignore_errors=True)
    proc = subprocess.Popen(
        [sys.executable, str(WORKER), job],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        line = proc.stdout.readline()
        assert "WORKER_READY" in line, line
        live_ws = mi.workspace_root() / f"mi-{job}"
        assert live_ws.is_dir()
        mf = read_manifest(live_ws)
        assert mf["status"] == "running"
        assert mf["pid"] == proc.pid
        proc.kill()  # SIGKILL tuong duong: process chet, file sot lai
        proc.wait(timeout=30)
        assert not proc.poll() is None
        assert live_ws.is_dir(), "workspace phai SOT lai sau kill (mo phong crash)"
        time.sleep(1.1)  # de psutil het nhin thay pid
        res = mi.sweep_stale_workspaces(max_age_s=3600)
        assert job in res["swept"], res
        assert not live_ws.exists(), "sweep phai xoa workspace job da chet"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)


def test_sweep_keeps_live_job_and_library_files(tmp_path):
    keep = mi.new_job_workspace("keeptest")
    try:
        lib_file = tmp_path / "library_asset.mp4"
        lib_file.write_bytes(b"\x00" * 16)
        other = mi.new_job_workspace("othertest")
        try:
            res = mi.sweep_stale_workspaces(max_age_s=3600)
            assert "keeptest" in res["kept"]
            assert "othertest" in res["kept"]
            assert Path(keep["path"]).is_dir()
            assert lib_file.is_file(), "KHONG duoc xoa file ngoai workspace"
        finally:
            mi.finish_job_workspace(other["path"], status="done")
    finally:
        mi.finish_job_workspace(keep["path"], status="done")


def test_timeout_and_cancelled_swept_even_if_pid_reused(tmp_path):
    ws_info = mi.new_job_workspace("timeouttest")
    ws = Path(ws_info["path"])
    mf = json.loads((ws / "manifest.json").read_text(encoding="utf-8"))
    mf["status"] = "timeout"
    (ws / "manifest.json").write_text(json.dumps(mf), encoding="utf-8")
    res = mi.sweep_stale_workspaces(max_age_s=3600)
    assert "timeouttest" in res["swept"]
    assert not ws.exists()


def test_parallel_jobs_isolation():
    a = mi.new_job_workspace("parA")
    b = mi.new_job_workspace("parB")
    try:
        pa, pb = Path(a["path"]), Path(b["path"])
        (pa / "a.bin").write_bytes(b"A")
        (pb / "b.bin").write_bytes(b"B")
        assert pa.is_dir() and pb.is_dir()
        mi.finish_job_workspace(pa, status="done")
        assert not pa.exists()
        assert pb.is_file() if False else pb.is_dir()
        assert (pb / "b.bin").is_file(), "job song song khong bi anh huong"
    finally:
        mi.finish_job_workspace(b["path"], status="done")
    assert not Path(b["path"]).exists()


def test_finish_refuses_outside_workspace(tmp_path):
    outside = tmp_path / "not-a-workspace"
    outside.mkdir()
    assert mi.finish_job_workspace(outside) is False
    assert outside.is_dir()
