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

_ALLOWED_LOCATOR_KINDS = ("role", "testid", "css", "text")
_ALLOWED_READ_OPS = ("text", "title", "url", "attr-safe", "count")
_BANNED_TOKENS = ("evaluate", "javascript:", "<script", "function(",
                  "=>", "__proto__", "constructor", "proxy(", "fetch(",
                  "xmlhttprequest")


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
             capability="read", lease=None):
        """Doc observation da grant. Tra {"ok": True, "observation"} hoac
        {"ok": False, "error"}. Kiem tra theo thu tu: transport -> grant ->
        observation ton tai -> schema -> freshness -> replay.

        lease (optional, A1): {"instance_id", "tab_id", "url", "grant_epoch",
        "ttl"} — observation chi duoc tra khi gan dung lease binding:
        pre-validation (live_origin + grant epoch truoc khi mo observation) va
        post-validation (epoch/URL/freshness sau khi mo observation). Lech bat
        ky diem nao -> tu choi fail-closed, khong tra du lieu cu.
        """
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
        # Pre-validation: lease binding truoc khi mo observation.
        lease_check = self._precheck_lease(
            lease, browser_instance_id, tab_id, live_origin)
        if lease_check is not None:
            return lease_check
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
        # Post-validation: grant epoch/URL/freshness sau khi mo observation
        # (revocation hoac navigation giua chung -> bo, khong tra du lieu).
        post = self._postcheck_lease(lease, browser_instance_id, tab_id,
                                     live_origin, obs)
        if post is not None:
            return post
        self._seen_seq.add(key)
        epoch = self._grants.epoch(browser_instance_id, tab_id)
        return {"ok": True, "observation": {
            "spec": obs["spec"], "live_origin": live_origin,
            "data": clean, "untrusted": True,
            "instance_id": str(browser_instance_id), "tab_id": tab_id,
            "url": clean.get("url") or live_origin,
            "grant_epoch": epoch, "observed_at": obs.get("observed_at"),
        }}

    def _precheck_lease(self, lease, browser_instance_id, tab_id,
                        live_origin):
        """Pre-validation: lease binding truoc khi mo observation.

        Tra None khi hop le hoac khong co lease (backward-compat), nguoc lai
        tra {"ok": False, "error"} de read() tu choi ngay.
        """
        if lease is None:
            return None
        if not isinstance(lease, dict):
            return {"ok": False, "error": "LEASE_INVALID"}
        if str(lease.get("instance_id") or "") != str(browser_instance_id):
            return {"ok": False, "error": "OBSERVED_INSTANCE_MISMATCH"}
        try:
            if int(lease.get("tab_id")) != int(tab_id):
                return {"ok": False, "error": "OBSERVED_TAB_MISMATCH"}
        except (TypeError, ValueError):
            return {"ok": False, "error": "OBSERVED_TAB_MISMATCH"}
        expected_epoch = self._grants.epoch(browser_instance_id, tab_id)
        if expected_epoch is None:
            return {"ok": False, "error": "GRANT_REQUIRED"}
        try:
            if int(lease.get("grant_epoch")) != int(expected_epoch):
                return {"ok": False, "error": "OBSERVED_EPOCH_MISMATCH"}
        except (TypeError, ValueError):
            return {"ok": False, "error": "OBSERVED_EPOCH_MISMATCH"}
        return None

    def _postcheck_lease(self, lease, browser_instance_id, tab_id,
                         live_origin, obs):
        """Post-validation sau khi mo observation: epoch + URL + freshness.

        Tra None khi hop le hoac khong co lease (backward-compat).
        Revocation/navigation giua pre va post -> tu choi.
        """
        if lease is None:
            return None
        expected_epoch = self._grants.epoch(browser_instance_id, tab_id)
        if expected_epoch is None:
            return {"ok": False, "error": "GRANT_REQUIRED"}
        try:
            if int(lease.get("grant_epoch")) != int(expected_epoch):
                return {"ok": False, "error": "OBSERVED_EPOCH_MISMATCH"}
        except (TypeError, ValueError):
            return {"ok": False, "error": "OBSERVED_EPOCH_MISMATCH"}
        obs_url = (obs.get("data") or {}).get("url") or obs.get("live_origin")
        if str(obs_url or "") != str(live_origin or ""):
            return {"ok": False, "error": "OBSERVED_URL_MISMATCH"}
        try:
            age = self._clock() - float(obs.get("observed_at", 0))
        except (TypeError, ValueError):
            return {"ok": False, "error": "OBSERVED_AT_INVALID"}
        try:
            ttl = int((lease or {}).get("ttl", OBS_TTL_S))
        except (TypeError, ValueError):
            return {"ok": False, "error": "OBSERVED_TTL_INVALID"}
        if not 1 <= ttl <= 1800 or age < 0 or age > min(ttl, OBS_TTL_S):
            return {"ok": False, "error": "EVIDENCE_STALE"}
        return None

    def check_locator(self, locator):
        """Locator hep Agent duoc phep: kind cho phep + value ngan + khong
        dau hieu JS/evaluate. Ngoai danh sach -> tu choi."""
        if not isinstance(locator, dict):
            return {"ok": False, "error": "LOCATOR_INVALID"}
        kind = locator.get("kind")
        value = locator.get("value")
        if kind not in _ALLOWED_LOCATOR_KINDS:
            return {"ok": False, "error": "LOCATOR_KIND_DENIED"}
        if not isinstance(value, str) or not value.strip():
            return {"ok": False, "error": "LOCATOR_INVALID"}
        limit = 256 if kind != "text" else 120
        if len(value) > limit:
            return {"ok": False, "error": "LOCATOR_TOO_WIDE"}
        lowered = value.lower()
        for token in _BANNED_TOKENS:
            if token in lowered:
                return {"ok": False, "error": "LOCATOR_EVALUATE_DENIED"}
        if kind == "css" and ">>" in value:
            return {"ok": False, "error": "LOCATOR_TOO_WIDE"}
        return {"ok": True, "kind": kind, "value": value}

    def check_read_op(self, op):
        """Chi op doc cho phep; evaluate hoac op ghi bi tu choi."""
        if str(op or "") in _ALLOWED_READ_OPS:
            return {"ok": True, "op": str(op)}
        return {"ok": False, "error": "READ_SPEC_DENIED"}

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
