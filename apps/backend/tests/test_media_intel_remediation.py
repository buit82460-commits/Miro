"""Test wiring remediation audit B: startup sweep + returncode that.

Chay: python -m pytest tests/test_media_intel_remediation.py -q
"""
from pathlib import Path

import pytest

mi = pytest.importorskip("miro.media_intel")


def test_startup_sweep_wired_in_lifespan():
    import inspect
    from miro import main
    assert hasattr(main, "_lifespan")
    src = inspect.getsource(main._lifespan)
    assert "sweep_stale_workspaces" in src


def test_startup_sweep_cleans_dead_workspace(tmp_path, monkeypatch):
    import tempfile
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr("tempfile.tempdir", None)
    # gia lap workspace chet: manifest cu + pid khong ton tai
    ws_info = mi.new_job_workspace("deadstartup")
    ws = Path(ws_info["path"])
    import json, time
    mf = json.loads((ws / "manifest.json").read_text(encoding="utf-8"))
    mf["created_at"] = time.time() - 7200
    mf["pid"] = 999999999
    (ws / "manifest.json").write_text(json.dumps(mf), encoding="utf-8")
    res = mi.sweep_stale_workspaces(max_age_s=3600)
    assert "deadstartup" in res["swept"]
    assert not ws.exists()


def test_run_native_cli_rejects_nonzero_exit(monkeypatch, tmp_path):
    import subprocess
    real_run = subprocess.run

    def fake_run(cmd, *a, **k):
        if isinstance(cmd, list) and "rea_video" in cmd:
            return subprocess.CompletedProcess(cmd, 1, stdout="",
                                               stderr="boom")
        return real_run(cmd, *a, **k)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="ANALYSIS_FAILED"):
        mi._run_native_cli(["decompose", "x"], timeout=60)
