"""Mock tests cho Connections: them/verify dung-sai account-tab, pause/reconnect/revoke, default.

Khong can Chrome that, khong Post that. Run: python -m pytest tests/test_connections.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from miro.connections import store as conn_store
from miro.main import app


def _client():
    conn_store.reset()
    return TestClient(app)


def _add(client, platform="tiktok", account_id="kemkhongta"):
    res = client.post("/connections/accounts", json={
        "platform": platform,
        "account_id": account_id,
        "display_name": account_id,
        "credential_ref": "vault://miro/tiktok/kemkhongta",
        "profile_binding_id": "profile-20",
        "browser_instance_id": "chrome-1",
    })
    assert res.status_code == 201, res.text
    return res.json()


def _ev(tab="tab-1", platform="tiktok", profile="profile-20", observed="kemkhongta"):
    return {"tab_id": tab, "platform_id": platform, "profile_binding_id": profile,
            "observed_account_id": observed, "target_id": "target-1"}


def test_add_rejects_plaintext_credential():
    client = _client()
    res = client.post("/connections/accounts", json={
        "platform": "tiktok", "account_id": "x",
        "credential_ref": "mat-khau-that-123",
    })
    assert res.status_code == 400
    assert "CREDENTIAL_PLAINTEXT_DENIED" in res.text


def test_business_default_auto_selected():
    client = _client()
    body = _add(client)
    assert body["is_default"] is True
    res = client.get("/connections/defaults/tiktok")
    assert res.json()["source"] == "user_default"


def test_verify_right_account_right_tab_connects():
    client = _client()
    body = _add(client)
    res = client.post(f"/connections/accounts/{body['id']}/verify", json=_ev())
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "connected"


def test_verify_wrong_account_mismatch():
    client = _client()
    body = _add(client)
    res = client.post(f"/connections/accounts/{body['id']}/verify",
                      json=_ev(observed="tai-khoan-khac"))
    assert res.status_code == 400
    assert "ACCOUNT_MISMATCH" in res.text


def test_verify_wrong_profile_binding_mismatch():
    client = _client()
    body = _add(client)
    res = client.post(f"/connections/accounts/{body['id']}/verify",
                      json=_ev(profile="profile-khac"))
    assert res.status_code == 400
    assert "ACCOUNT_MISMATCH" in res.text


def test_pause_reconnect_revoke_cycle():
    client = _client()
    body = _add(client)
    aid = body["id"]
    assert client.post(f"/connections/accounts/{aid}/verify", json=_ev()).status_code == 200
    assert client.post(f"/connections/accounts/{aid}/pause").json()["status"] == "paused"
    res = client.post(f"/connections/accounts/{aid}/reconnect",
                      json={"evidence": _ev(), "credential_ref": "ref://miro/tiktok/new"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "connected"
    revoked = client.post(f"/connections/accounts/{aid}/revoke").json()
    assert revoked["status"] == "revoked"
    assert revoked["credential_ref"] is None


def test_set_default_only_by_user():
    client = _client()
    first = _add(client, account_id="kemkhongta")
    second = _add(client, account_id="kemkhongta-2")
    assert second["is_default"] is False  # khong phai default nghiep vu -> khong tu default
    res = client.post(f"/connections/accounts/{second['id']}/default")
    assert res.status_code == 200
    assert client.get(f"/connections/accounts/{first['id']}").json()["is_default"] is False
