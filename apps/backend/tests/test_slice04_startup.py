"""Slice 04 one-click startup: launcher quan ly BE+Bridge+FE thong nhat.

- start tu choi khi manifest con song (khong sinh process trung).
- port BE/Bridge ban -> fail-closed (khong doat port app khac).
- FE port mac dinh ban -> dung port tu do ke tiep trong range hep.
- service fe giai quyet duoc tren Windows (npm run dev).
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "C:/Miro/windows")

import miro as launcher


def test_fe_service_resolves_npm_dev():
    built = launcher.service_command("fe")
    assert built is not None
    cmd, cwd, extra = built
    assert "dev" in cmd
    assert "NEXT_PUBLIC_API_BASE" in extra


def test_free_port_skips_busy():
    with patch.object(launcher, "_port_in_use", side_effect=lambda p: p == 3100):
        assert launcher._free_port(3100, 3150) == 3101
    with patch.object(launcher, "_port_in_use", return_value=True):
        assert launcher._free_port(3100, 3101) is None


def test_start_refuses_when_launcher_alive(tmp_path):
    man = tmp_path / "m.json"
    man.write_text('{"root": "%s", "launcher": 123456}' % str(launcher.ROOT), encoding="utf-8")
    with patch.object(launcher, "MANIFEST", man), \
         patch.object(launcher, "_pid_alive", return_value=True):
        assert launcher.cmd_start(["be"], open_browser=False) == 1
