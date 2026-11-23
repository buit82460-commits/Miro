"""Bridge read transport cho Gateway (Phien A, read-only, spike).

Gateway la diem vao duy nhat cua Agent. Transport nay KHONG mo Playwright/CDP/
port 9222, KHONG fake Playwright Page, KHONG tu gan nhan actor VERIFIED.

Luat:
- Chi doc observation tu tab da co grant DOM hop le (instance/tab/origin/TTL).
- Observation = UNTRUSTED, co schema co dinh (title/meta/text-limited), field
  cat <=2000. Bat ky payload la nao -> tu choi.
- Freshness <=300s; replay seq -> tu choi; revoke/navigation/mismatch ->
  observation cu khong du dieu kien.
- Actor: title/observation KHONG du de xac minh actor. Transport nay luon tra
  ACTOR_UNVERIFIED (fail-closed); Evidence chi duoc tao khi co kenh xac minh
  actor doc lap (REA/Eye tren page that). Khong bao gio tu nhan VERIFIED.
"""
from __future__ import annotations

import time

from bridge.grants import GrantStore, READ_SPECS, SPEC_FIELDS

OBS_TTL_S = 300
FIELDS = ("title", "url", "text", "description", "h1",
          "has_login_button", "profile_href", "has_upload_link")


class BridgeReadTransport:
    def __init__(self, grants, observations, clock=None):
        self._grants = grants if grants is not None else GrantStore(
            clock=clock)
        self._observations = observations if observations is not None else {}
        self._clock = clock or time.time
        self._seen_seq = set()  # (instance, tab, seq) chong replay
        self._closed = False

    def close(self):
        self._closed = True

    def read(self, *, browser_instance_id, tab_id, live_origin, seq,
             capability="read"):
        """Doc observation da grant. Tra {"ok": True, "observation"} hoac
        {"ok": False, "error"}. Kiem tra theo thu tu: transport -> grant ->
        observation ton tai -> schema -> freshness -> replay."""
        if self._closed:
            return {"ok": False, "error": "TRANSPORT_CLOSED"}
        try:
            tab_id = int(tab_id)
        except (TypeError, ValueError):
            return {"ok": False, "error": "TAB_INVALID"}
        try:
            seq = int(seq)
        except (TypeError, ValueError):
            return {"ok": False, "error": "SEQ_INVALID"}
        g = self._grants.check(browser_instance_id, tab_id, live_origin,
                               capability)
        if not g.get("ok"):
            return {"ok": False, "error": g.get("error", "GRANT_REQUIRED")}
        key = (str(browser_instance_id), tab_id, seq)
        obs = self._observations.get(key)
        if obs is None:
            return {"ok": False, "error": "OBSERVATION_NOT_FOUND"}
        if key in self._seen_seq:
            return {"ok": False, "error": "OBSERVATION_REPLAY"}
        if not isinstance(obs, dict) or obs.get("spec") not in READ_SPECS:
            return {"ok": False, "error": "READ_SPEC_DENIED"}
        if obs.get("live_origin") != live_origin:
            return {"ok": False, "error": "ORIGIN_MISMATCH"}
        data = obs.get("data")
        if not isinstance(data, dict):
            return {"ok": False, "error": "BAD_RESULT"}
        allowed = SPEC_FIELDS.get(obs.get("spec"))
        if allowed is None:
            return {"ok": False, "error": "READ_SPEC_DENIED"}
        clean = {}
        for f in allowed:
            v = data.get(f, "")
            if not isinstance(v, str):
                return {"ok": False, "error": "BAD_RESULT"}
            clean[f] = v[:2000]
        extra = set(data.keys()) - set(allowed)
        if extra:
            return {"ok": False, "error": "BAD_RESULT"}
        try:
            age = self._clock() - float(obs.get("observed_at", 0))
        except (TypeError, ValueError):
            return {"ok": False, "error": "OBSERVED_AT_INVALID"}
        if age < 0 or age > OBS_TTL_S:
            return {"ok": False, "error": "EVIDENCE_STALE"}
        if obs.get("untrusted", True) is not True:
            return {"ok": False, "error": "OBSERVATION_MUST_BE_UNTRUSTED"}
        self._seen_seq.add(key)
        return {"ok": True, "observation": {
            "spec": obs["spec"], "live_origin": live_origin,
            "data": clean, "untrusted": True,
            "instance_id": str(browser_instance_id), "tab_id": tab_id,
        }}

    def verify_actor(self, observation):
        """Xac minh actor tu observation actor-login co schema.

        VERIFIED chi khi DU 3 tin hieu doc lap tren cung DOM:
        - has_login_button == "" (khong con nut Log in),
        - profile_href bat dau "/@" (link profile that trong header),
        - has_upload_link == "1" (co loi Upload chi hien khi login).
        Thieu 1 -> ACTOR_UNVERIFIED + missing (fail-closed).
        Spec khac (title/meta/text-limited) -> luon UNVERIFIED.
        """
        obs = observation or {}
        if obs.get("spec") != "actor-login":
            return {"ok": False, "error": "ACTOR_UNVERIFIED",
                    "hint": "title/observation khong phai bang chung chu tai "
                            "khoan; can spec actor-login hoac kenh xac minh "
                            "actor doc lap"}
        data = obs.get("data") or {}
        missing = []
        if str(data.get("has_login_button") or "") != "":
            missing.append("has_login_button")
        href = str(data.get("profile_href") or "")
        if not href.startswith("/@") or len(href) < 3:
            missing.append("profile_href")
        if str(data.get("has_upload_link") or "") != "1":
            missing.append("has_upload_link")
        if missing:
            return {"ok": False, "error": "ACTOR_UNVERIFIED",
                    "missing": missing}
        handle = "@" + href[2:].split("/")[0].split("?")[0]
        return {"ok": True, "actor": handle}
