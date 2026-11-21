"""Registry rollback dung ban truoc + persist qua reload (mo phong restart)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("MIRO_BE_DB_DIR", str(tmp_path))
    from miro.connections import store as conn_store
    from miro.platforms import store as plat_store
    plat_store.reset()
    conn_store.reset()
    return plat_store, conn_store


def test_platform_rollback_restores_previous_snapshot(monkeypatch, tmp_path):
    plat_store, _ = _isolate(monkeypatch, tmp_path)
    v0 = plat_store.snapshot()["version"]
    plat_store.upsert_platform({"id": "x1", "name": "X1"})
    v1 = plat_store.snapshot()["version"]
    plat_store.update_capability("youtube", "publish", {"status": "BLOCKED"})
    assert plat_store.snapshot()["version"] == v1 + 1

    out = plat_store.rollback(v1)
    assert out["version"] == v1
    yt = next(p for p in out["platforms"] if p["id"] == "youtube")
    assert yt["capabilities"]["publish"]["status"] != "BLOCKED"  # ban truoc khi sua
    assert any(p["id"] == "x1" for p in out["platforms"])  # x1 da co o v1

    out0 = plat_store.rollback(v0)
    assert out0["version"] == v0
    assert not any(p["id"] == "x1" for p in out0["platforms"])


def test_platform_persist_across_reload(monkeypatch, tmp_path):
    plat_store, _ = _isolate(monkeypatch, tmp_path)
    plat_store.upsert_platform({"id": "zz", "name": "ZZ"})
    v1 = plat_store.snapshot()["version"]
    plat_store.reload()  # mo phong restart process
    live = plat_store.snapshot()
    assert live["version"] == v1
    assert any(p["id"] == "zz" for p in live["platforms"])


def test_connections_persist_across_reload(monkeypatch, tmp_path):
    _, conn_store = _isolate(monkeypatch, tmp_path)
    conn_store.put({"id": "tiktok:a", "platform": "tiktok", "account_id": "a",
                    "status": "pending", "is_default": False})
    conn_store.reload()  # mo phong restart process
    got = conn_store.get("tiktok:a")
    assert got is not None and got["account_id"] == "a"
    assert [a["id"] for a in conn_store.list_accounts("tiktok")] == ["tiktok:a"]
