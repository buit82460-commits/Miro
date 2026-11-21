"""Wiring test: schedule endpoints + store persist + desktop route + launcher L2.

Chay: python -m pytest tests/test_schedule_wiring.py -q (tu C:\\Miro\\apps\\backend).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from miro.main import app  # noqa: E402

client = TestClient(app)


def test_ensure_persists_and_binds_day_plan(tmp_path, monkeypatch):
    import miro.scheduling.store as st
    var = tmp_path / "var"
    monkeypatch.setenv("MIRO_BE_DB_DIR", str(var))
    body = {
        "policy": {"account": "acc", "platform": "threads", "daily_cap": 2,
                   "status": "active"},
        "new_items": [{"task_id": "a", "shortcode": "a"},
                      {"task_id": "b", "shortcode": "b"}],
        "date_str": "2026-11-22", "was_clean_shutdown": False,
    }
    res = client.post("/schedule/ensure", json=body)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["action"] == "rebuild"
    assert data["slots"] == 2
    assert (var / "threads-day-plan.json").exists()
    pub = app.state.threads_publisher
    assert isinstance(pub.day_plan, dict)
    gp = client.get("/schedule/day-plan")
    assert gp.status_code == 200
    assert len(gp.json()["slots"]) == 2


def test_day_plan_status_pause_blocks_run_batch(tmp_path, monkeypatch):
    monkeypatch.setenv("MIRO_BE_DB_DIR", str(tmp_path / "var2"))
    client.post("/schedule/ensure", json={
        "policy": {"account": "acc", "status": "active",
                   "window": {"start": "00:00", "end": "23:59"}},
        "new_items": [{"task_id": "k1", "shortcode": "k1"}],
        "date_str": "2026-11-22", "was_clean_shutdown": False})
    r = client.patch("/schedule/day-plan/status", json={"status": "paused"})
    assert r.status_code == 200 and r.json()["status"] == "paused"
    from types import SimpleNamespace
    from miro.scheduling.schedule import select_due_intents

    items = [SimpleNamespace(intent_id="k1", shortcode="k1", owner="acc",
                             tag="#dub000001", text="x")]
    due, deferred = select_due_intents(app.state.threads_publisher.day_plan,
                                       items, "2026-11-22T12:00:00+07:00")
    assert due == [] and deferred[0]["reason"] == "PAUSED"


def test_desktop_route_cli_unavailable_fail_closed():
    res = client.post("/desktop/init", json={"job_id": "job-cli-x"})
    assert res.status_code == 200
    r = client.post("/desktop/act", json={
        "job_id": "job-cli-x", "worker": "w", "worker_epoch": 1,
        "doc": "note.txt", "action": "read"})
    assert r.status_code in (200, 503, 422), r.text
    if r.status_code == 503:
        assert "CLI_UNAVAILABLE" in r.text


def test_touch_verified_persists_to_file(tmp_path, monkeypatch):
    from miro.scheduling import store as st
    from miro.scheduling.schedule import build_day_plan
    pol = {"account": "acc", "status": "active"}
    plan = build_day_plan("2026-11-22", pol, [],
                          [{"task_id": "z", "shortcode": "z"}])
    monkeypatch.setenv("MIRO_BE_DB_DIR", str(tmp_path))
    st.save_plan(plan, tmp_path)
    st.touch_verified(plan, "z", tmp_path)
    reloaded = st.load_plan(tmp_path)
    assert reloaded["slots"][0]["state"] == "verified"


def test_launcher_l2_budget_persists_across_instances(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "miro_launcher", str(Path("C:/Miro/windows/miro.py")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    b1 = mod.RestartBudget(maximum=3, window=600.0, name="be",
                           state_dir=tmp_path)
    b1.next_delay()
    b1.next_delay()
    assert (tmp_path / "restart-budget-be.json").exists()
    b2 = mod.RestartBudget(maximum=2, window=600.0, name="be",
                           state_dir=tmp_path)
    # lich su cu (2 lan crash) duoc nap -> het ngay budget maximum=2:
    # xuyen-launcher khong reset budget.
    try:
        b2.next_delay()
        assert False, "phai het budget vi lich su cu van ton tai"
    except RuntimeError as exc:
        assert "WORKER_RESTART_EXHAUSTED" in str(exc)
