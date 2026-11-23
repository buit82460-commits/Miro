"""Test khoa: phan tich media chi qua miro/media_intel (adapter duy nhat).

Cam import cv2 / rea_video / sherpa_onnx de phan tich media o ngoai
miro/media_intel/* (MEDIA_BYPASS -> fail CI).
Ngoai le hop le (khong phai phan tich media):
- studio/separate.py: lazy `find_spec("demucs")/find_spec("torch")`
  de tach nhac dub (contract separate_clip giu nguyen), khong phai
  phan tich noi dung video.
- tests + fakes.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

ROOT = Path(__file__).resolve().parents[1] / "src" / "miro"
PAT = re.compile(r"^\s*(import\s+cv2|from\s+cv2\s+import|"
                 r"import\s+rea_video|from\s+rea_video\s+import|"
                 r"import\s+sherpa_onnx|from\s+sherpa_onnx\s+import)")
ALLOW = ("/media_intel/", "studio/separate.py")


def test_no_direct_media_analysis_outside_adapter():
    bad = []
    for path in ROOT.rglob("*.py"):
        rel = str(path).replace("\\", "/")
        if any(a in rel for a in ALLOW):
            continue
        if "/tests/" in rel or "test_" in Path(rel).name:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if PAT.search(line):
                bad.append((rel, i, line.strip()[:100]))
    assert bad == [], f"duong phan tich media truc tiep ngoai adapter: {bad}"


def test_media_trust_boundary_and_cost_gate():
    from miro import media_intel as mi
    # provenance sai -> DENY
    with pytest.raises(mi.MediaBypassError):
        mi.check_media_evidence({"provenance": "rea-eye"})
    with pytest.raises(mi.MediaBypassError):
        mi.check_media_evidence({"provenance": "media-analysis"})
    # thieu file_sha256 -> DENY
    with pytest.raises(mi.MediaBypassError):
        mi.check_media_evidence({"provenance": "media-analysis"})
    ok = mi.check_media_evidence({"provenance": "media-analysis",
                                  "file_sha256": "a" * 64})
    assert ok["file_sha256"] == "a" * 64
    # runtime deny
    with pytest.raises(mi.MediaBypassError):
        mi.deny_direct_media("cv2")
    # cost gate: thieu approval -> DENY
    with pytest.raises(mi.MediaBypassError):
        mi.require_generation_approval(None)
    with pytest.raises(mi.MediaBypassError):
        mi.require_generation_approval({"approved": False})
    assert mi.require_generation_approval(
        {"approved": True})["approved"] is True
