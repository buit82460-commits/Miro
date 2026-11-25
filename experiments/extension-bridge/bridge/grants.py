"""Grant theo tab cho duong doc (Phien A, spike) — da va B1/B2.

B1 (fake gesture): backend KHONG tin truong `gesture` do caller gui.
`gesture` chi la thong tin mo ta; grant chi duoc cap khi DU:
- session hop le (kenh extension da xac thuc qua X-Session/X-Token),
- tab da co trong registry (extension that da bao cao, observed moi),
- origin thuoc allowlist.
Extension phai tu kiem tra tab active + quyen truoc khi xin grant
(background.js); server khong coi gesture la bang chung.

- Key: (browser_instance_id, tab_id).
- Moi grant: {origin, capability="read", expires_at, grant_seq}.
- Moi yeu cau doc phai qua: dung instance + dung tab + dung origin live
  (B2: URL hien tai, khong dung URL registry cu) + capability read +
  grant con hieu luc. Thieu 1 -> tu choi + thu hoi khi mismatch.
"""
from __future__ import annotations

import time

GRANT_TTL_S = 120
READ_CAPABILITY = "read"
READ_SPECS = ("title", "meta", "text-limited", "actor-login",
              "video-identity", "feed-video")
ALLOWED_ORIGINS = ("https://www.tiktok.com",)

# Field cho phep theo spec (schema co dinh, cat 2000). actor-login chi doc
# tin hieu login co cau truc, KHONG caption/comment/text tu do.
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


class GrantStore:
    def __init__(self, clock=None):
        self._clock = clock or time.time
        self._grants = {}  # (instance, tab) -> grant dict
        self._used_grant_seq = set()  # (instance, tab, seq) chong replay

    def auto_grant(self, browser_instance_id, tab_id, origin,
                   capability=READ_CAPABILITY, ttl=GRANT_TTL_S):
        """Slice 01B: server tu cap runtime grant ngan han trong pham vi
        policy da xac nhan. Khong nhan seq tu caller (khong replay);
        grant_seq = epoch cu + 1, don dieu noi bo."""
        if capability != READ_CAPABILITY:
            return {"ok": False, "error": "CAPABILITY_DENIED"}
        try:
            tab_id = int(tab_id)
        except (TypeError, ValueError):
            return {"ok": False, "error": "TAB_INVALID"}
        origin = str(origin or "")
        if not origin.startswith(ALLOWED_ORIGINS):
            return {"ok": False, "error": "ORIGIN_NOT_GRANTED"}
        prev = self._grants.get((str(browser_instance_id), tab_id))
        try:
            prev_seq = int((prev or {}).get("grant_seq") or 0)
        except (TypeError, ValueError):
            prev_seq = 0
        seq = prev_seq + 1
        now = self._clock()
        self._grants[(str(browser_instance_id), tab_id)] = {
            "origin": origin,
            "capability": READ_CAPABILITY,
            "expires_at": now + ttl,
            "grant_seq": seq,
            "auto": True,
        }
        return {"ok": True, "expires_in": ttl, "grant_seq": seq,
                "auto": True}

    def grant(self, browser_instance_id, tab_id, origin, seq,
              capability=READ_CAPABILITY, ttl=GRANT_TTL_S):
        """Cap grant doc cho 1 tab. `gesture` cu bi loai: khong nhan.

        Yeu cau seq don dieu cua session (chong replay grant); caller phai
        la kenh extension da xac thuc (server kiem tra truoc khi goi).
        """
        if capability != READ_CAPABILITY:
            return {"ok": False, "error": "CAPABILITY_DENIED"}
        try:
            tab_id = int(tab_id)
        except (TypeError, ValueError):
            return {"ok": False, "error": "TAB_INVALID"}
        try:
            seq = int(seq)
        except (TypeError, ValueError):
            return {"ok": False, "error": "SEQ_INVALID"}
        origin = str(origin or "")
        if not origin.startswith(ALLOWED_ORIGINS):
            return {"ok": False, "error": "ORIGIN_NOT_GRANTED"}
        key = (str(browser_instance_id), tab_id, seq)
        if key in self._used_grant_seq:
            return {"ok": False, "error": "GRANT_REPLAY"}
        self._used_grant_seq.add(key)
        now = self._clock()
        self._grants[(str(browser_instance_id), tab_id)] = {
            "origin": origin,
            "capability": READ_CAPABILITY,
            "expires_at": now + ttl,
            "grant_seq": seq,
        }
        return {"ok": True, "expires_in": ttl}

    def check(self, browser_instance_id, tab_id, live_origin,
              capability="read"):
        """Kiem tra grant voi origin LIVE (B2), khong dung URL cu."""
        try:
            tab_id = int(tab_id)
        except (TypeError, ValueError):
            return {"ok": False, "error": "TAB_INVALID"}
        g = self._grants.get((str(browser_instance_id), tab_id))
        if g is None:
            return {"ok": False, "error": "GRANT_REQUIRED"}
        if g["expires_at"] <= self._clock():
            self._grants.pop((str(browser_instance_id), tab_id), None)
            return {"ok": False, "error": "GRANT_EXPIRED"}
        if capability != READ_CAPABILITY or g["capability"] != READ_CAPABILITY:
            return {"ok": False, "error": "CAPABILITY_DENIED"}
        if str(live_origin or "") != g["origin"]:
            # B2: navigation khac origin -> vo hieu grant ngay.
            self._grants.pop((str(browser_instance_id), tab_id), None)
            return {"ok": False, "error": "ORIGIN_MISMATCH"}
        return {"ok": True}

    def epoch(self, browser_instance_id, tab_id):
        """Grant epoch hien tai cua tab (grant_seq luc cap).

        Tra int epoch, hoac None khi khong co grant hop le. Transport dung
        de gan lease binding: observation chi duoc doc khi epoch khop.
        """
        try:
            tab_id = int(tab_id)
        except (TypeError, ValueError):
            return None
        g = self._grants.get((str(browser_instance_id), tab_id))
        if g is None:
            return None
        if g["expires_at"] <= self._clock():
            self._grants.pop((str(browser_instance_id), tab_id), None)
            return None
        try:
            return int(g.get("grant_seq"))
        except (TypeError, ValueError):
            return None

    def revoke_tab(self, browser_instance_id, tab_id):
        """Thu hoi grant khi navigation khac origin / dong tab / revoke."""
        return self._grants.pop((str(browser_instance_id), int(tab_id)),
                                None) is not None

    def revoke_instance(self, browser_instance_id):
        gone = [k for k in self._grants if k[0] == str(browser_instance_id)]
        for k in gone:
            del self._grants[k]
        return len(gone)


def validate_read_spec(spec):
    """Chi chap nhan spec doc co dinh; khong JS tuy y tu backend."""
    if str(spec or "") in READ_SPECS:
        return {"ok": True, "spec": str(spec)}
    return {"ok": False, "error": "READ_SPEC_DENIED"}
