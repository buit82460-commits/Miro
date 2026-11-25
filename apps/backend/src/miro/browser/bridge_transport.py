"""Production Bridge transport (Phien A) — Gateway -> Extension Bridge READ.

Thay the CDP Page capability khi CDP khong kha dung (Chrome policy chan
9222 tren default user-data-dir). Khong mo CDP/9222, khong Playwright truc
tiep, khong fake Page, khong arbitrary evaluate.

Luat:
- Chi doc observation tu tab da grant (instance/tab/origin/TTL/epoch).
- Observation = UNTRUSTED, schema co dinh theo SPEC_FIELDS.
- Gateway la diem vao duy nhat; transport nay la read-only entry.
- Revoke/navigation/expiry/stale/replay/mismatch -> fail-closed.
- Actor toi da ACTOR_CLAIMED; VERIFIED can kenh doc lap (BLOCKED hien tai).
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

BRIDGE_BASE = "http://127.0.0.1:18767"
OBS_TTL_S = 300

READ_SPECS = ("title", "meta", "text-limited", "actor-login",
              "video-identity", "feed-video")
SPEC_FIELDS = {
    "title": ("title", "url"),
    "meta": ("title", "url", "description", "h1"),
    "text-limited": ("title", "url", "text"),
    "actor-login": ("title", "url", "has_login_button", "profile_href",
                    "has_upload_link"),
    "video-identity": ("title", "url", "aweme_id", "caption_preview",
                       "has_video"),
    "feed-video": ("title", "url", "video_url", "aweme_id", "author",
                   "caption_preview", "has_video"),
}


def _post(base, path, body, session_id="", token="", timeout=10,
           backend_key=""):
    data = json.dumps(body or {}).encode()
    headers = {"Content-Type": "application/json",
               "X-Session": session_id, "X-Token": token}
    if backend_key:
        headers["X-Backend-Key"] = backend_key
    req = urllib.request.Request(base + path, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _get(base, path, timeout=10):
    with urllib.request.urlopen(base + path, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


class BridgeClient:
    """HTTP client toi bridge server (loopback). Khong mo CDP.

    Credential separation:
    - Backend role (tao request/huy): X-Backend-Key (MIRO_BRIDGE_BACKEND_KEY).
    - Extension role (thuc thi/gui result): X-Session/X-Token (pairing).
    - task_id/lease owner KHONG phai HTTP auth, chi de truy vet.
    """

    def __init__(self, base=BRIDGE_BASE, session_id="", token="",
                 timeout=10, backend_key=""):
        self.base = base.rstrip("/")
        self.session_id = session_id
        self.token = token
        self.timeout = timeout
        self.backend_key = (backend_key
                            or os.environ.get("MIRO_BRIDGE_BACKEND_KEY")
                            or "")

    def health(self):
        return _get(self.base, "/health", self.timeout)

    def tabs(self):
        return _get(self.base, "/tabs", self.timeout)

    def request_read(self, tab_id, spec, *, instance="profile20-main",
                     timeout_s=30, task_id=""):
        # BACKEND ROLE: tao production request, auth = backend key.
        if spec not in READ_SPECS:
            return {"ok": False, "error": "READ_SPEC_DENIED"}
        try:
            tab_id = int(tab_id)
        except (TypeError, ValueError):
            return {"ok": False, "error": "TAB_INVALID"}
        return _post(self.base, "/read",
                     {"tabId": tab_id, "read": spec, "instance": instance,
                      "timeout_s": timeout_s, "task_id": task_id},
                     "", "", self.timeout, self.backend_key)

    def cancel_read(self, request_id):
        # BACKEND ROLE: huy request dang cho (task cancel/stop).
        return _post(self.base, "/cancel", {"request_id": request_id},
                     "", "", self.timeout, self.backend_key)

    def observations(self):
        return _get(self.base, "/observations", self.timeout)

    def revoke(self):
        return _post(self.base, "/revoke", {},
                     self.session_id, self.token, self.timeout)


def clean_observation(obs):
    """Validate schema co dinh, cat 2000, tu choi field la."""
    if not isinstance(obs, dict):
        return {"ok": False, "error": "BAD_RESULT"}
    if obs.get("spec") not in READ_SPECS:
        return {"ok": False, "error": "READ_SPEC_DENIED"}
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
    if set(data.keys()) - set(allowed):
        return {"ok": False, "error": "BAD_RESULT"}
    if obs.get("untrusted", True) is not True:
        return {"ok": False, "error": "OBSERVATION_MUST_BE_UNTRUSTED"}
    return {"ok": True, "spec": obs.get("spec"),
            "live_origin": obs.get("live_origin"), "data": clean,
            "untrusted": True,
            "request_id": str(obs.get("request_id") or ""),
            "task_id": str(obs.get("task_id") or ""),
            "manual": bool(obs.get("manual", False)),
            "instance_id": str(obs.get("instance_id") or ""),
            "tab_id": obs.get("tab_id"),
            "grant_epoch": obs.get("grant_epoch", 0),
            "seq": obs.get("seq"),
            "observed_at": obs.get("observed_at")}


def wait_observation(client, *, tab_id, spec, timeout=30,
                     request_id="", clock=None, is_cancelled=None):
    """Poll /observations cho observation moi dung tab+spec (+request_id).

    is_cancelled: callback -> True thi huy request tren server va tra
    REQUEST_CANCELLED ngay (task stop), khong doi het timeout.
    Manual observation (manual:true, request_id rong) KHONG bao gio duoc
    nhan lam ket qua production request co request_id.
    """
    clock = clock or time.time
    deadline = clock() + timeout
    seen = set()
    while clock() < deadline:
        if callable(is_cancelled):
            try:
                if is_cancelled():
                    try:
                        if request_id:
                            client.cancel_read(request_id)
                    except Exception:
                        pass
                    return {"ok": False, "error": "REQUEST_CANCELLED"}
            except Exception:
                pass
        try:
            out = client.observations()
        except Exception as exc:
            return {"ok": False,
                    "error": "BRIDGE_UNAVAILABLE: " + type(exc).__name__}
        if not isinstance(out, dict) or not out.get("ok"):
            err = (out or {}).get("error", "BRIDGE_ERROR") \
                if isinstance(out, dict) else "BRIDGE_ERROR"
            return {"ok": False, "error": "BRIDGE_" + str(err)}
        items = out.get("observations") or []
        for ob in items:
            if not isinstance(ob, dict):
                continue
            if int(ob.get("tab_id") or -1) != int(tab_id):
                continue
            if str(ob.get("spec") or "") != str(spec):
                continue
            if request_id and ob.get("manual"):
                continue
            if request_id and str(ob.get("request_id") or "") != str(request_id):
                continue
            key = (ob.get("tab_id"), ob.get("spec"),
                   ob.get("observed_at"), ob.get("seq"))
            if key in seen:
                continue
            seen.add(key)
            c = clean_observation(ob)
            if c.get("ok"):
                return {"ok": True, "observation": c}
        time.sleep(1)
    return {"ok": False, "error": "OBSERVATION_TIMEOUT"}


async def read_via_bridge(session_id, token, *, instance_id, tab_id,
                          live_origin, spec, base=BRIDGE_BASE,
                          timeout=30, grant_epoch=None, url=None,
                          backend_key="", task_id="",
                           is_cancelled=None):
    """Production READ qua Bridge: request -> doi observation -> validate.

    Tra {"ok": True, "observation"} hoac {"ok": False, "error"}.
    Khong CDP, khong Page, khong WRITE. Request tao bang backend key;
    extension gui result bang session/token (credential separation).
    """
    from miro.browser.observation import check_observed_binding
    from miro.eye import evaluate_actor_signals

    client = BridgeClient(base, session_id, token,
                          backend_key=backend_key)
    req = client.request_read(tab_id, spec, instance=instance_id,
                              timeout_s=timeout, task_id=task_id)
    if not isinstance(req, dict) or not req.get("ok"):
        err = (req or {}).get("error", "READ_REQUEST_DENIED") \
            if isinstance(req, dict) else "READ_REQUEST_DENIED"
        # /read tra AUTHORIZED qua {"read": spec, "status": "AUTHORIZED"}
        if not ((req or {}).get("status") == "AUTHORIZED"
                or (req or {}).get("ok")):
            return {"ok": False, "error": str(err)}
    rid = str((req or {}).get("request_id") or "")
    w = wait_observation(client, tab_id=tab_id, spec=spec,
                         timeout=timeout, request_id=rid,
                         is_cancelled=is_cancelled)
    if not w.get("ok"):
        return w
    obs = w["observation"]
    if str(obs.get("live_origin") or "") != str(live_origin or ""):
        return {"ok": False, "error": "ORIGIN_MISMATCH"}
    if str(obs.get("instance_id") or "") != str(instance_id or ""):
        return {"ok": False, "error": "OBSERVED_INSTANCE_MISMATCH"}
    try:
        if int(obs.get("tab_id")) != int(tab_id):
            return {"ok": False, "error": "OBSERVED_TAB_MISMATCH"}
    except (TypeError, ValueError):
        return {"ok": False, "error": "OBSERVED_TAB_MISMATCH"}
    b = check_observed_binding(
        obs_instance=obs.get("instance_id"), obs_tab=obs.get("tab_id"),
        obs_url=obs.get("data", {}).get("url") or obs.get("live_origin"),
        obs_epoch=obs.get("grant_epoch", 0),
        observed_at=obs.get("observed_at"),
        instance_id=instance_id, tab_id=tab_id, url=url,
        grant_epoch=grant_epoch, ttl=OBS_TTL_S)
    if not b.get("ok"):
        return b
    return {"ok": True, "observation": obs}
