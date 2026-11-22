"""Tests 3 adapter freelance moi: job_for validate (fake only, 0 browser)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.adapters import freelancer_vn, upwork, vlance  # noqa: E402


def test_vlance_job_for_ok_and_secret_rejected():
    ok = vlance.job_for({"title": "Web", "description": "Lam web ban hang"})
    assert ok["title"] == "Web"
    with pytest.raises(ValueError, match="MISSING_TITLE"):
        vlance.job_for({"description": "x"})
    with pytest.raises(ValueError, match="SECRET_REJECTED"):
        vlance.job_for({"title": "Web",
                        "description": "lien he 0901234567"})


def test_freelancer_vn_job_for():
    ok = freelancer_vn.job_for({"title": "App", "description": "Viet app"})
    assert ok["title"] == "App"
    with pytest.raises(ValueError, match="MISSING_DESCRIPTION"):
        freelancer_vn.job_for({"title": "App"})


def test_upwork_job_for_skills_cap():
    ok = upwork.job_for({"title": "Blog", "description": "Viet blog",
                         "skills": ["a", "b", "c"]})
    assert ok["skills"] == ["a", "b", "c"]
    with pytest.raises(ValueError, match="TOO_MANY_SKILLS"):
        upwork.job_for({"title": "B", "description": "d",
                        "skills": [f"s{i}" for i in range(11)]})
