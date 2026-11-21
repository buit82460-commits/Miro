"""Khung grant/command port gọn từ C:\\dubtool\\spikes\\chrome-extension-v1.

Minh họa 4 quy tắc (không nối pipe, không pairing, không UI):
1. Grant gắn profile + session + tab + expiry (<= 120s).
2. command() kiểm tra lại grant + session, từ chối mặc định.
3. requestId chống replay trong session.
4. Chỉ allowlist action, không click/publish tổng quát.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

ALLOWED_ACTIONS = {"readDOM", "fill", "clickSafeButton", "detach"}
MAX_GRANT_TTL_S = 120


@dataclass
class Grant:
    profile_binding_id: str
    session_id: str
    tab_binding_id: str
    tab_id: int
    expires_at: float  # epoch seconds


@dataclass
class Controller:
    online: dict[str, str] = field(default_factory=dict)  # profile -> session
    grants: dict[str, Grant] = field(default_factory=dict)  # tab_binding -> grant
    seen_requests: set[str] = field(default_factory=set)

    def grant(self, g: Grant) -> None:
        ttl = g.expires_at - time.time()
        if not (0 < ttl <= MAX_GRANT_TTL_S):
            raise ValueError("INVALID_GRANT")
        if self.online.get(g.profile_binding_id) != g.session_id:
            raise ValueError("STALE_SESSION")
        # Một tabId chỉ giữ 1 grant mới nhất.
        for key, old in list(self.grants.items()):
            if key != g.tab_binding_id and old.tab_id == g.tab_id:
                del self.grants[key]
        self.grants[g.tab_binding_id] = g

    def command(self, profile_binding_id: str, session_id: str,
                tab_binding_id: str, action: str, request_id: str) -> dict:
        if action not in ALLOWED_ACTIONS:
            raise ValueError("ACTION_NOT_ALLOWED")
        if self.online.get(profile_binding_id) != session_id:
            raise ValueError("STALE_SESSION")
        grant = self.grants.get(tab_binding_id)
        if grant is None:
            raise ValueError("TAB_NOT_AUTHORIZED")
        if grant.expires_at <= time.time():
            raise ValueError("TAB_AUTHORIZATION_EXPIRED")
        if request_id in self.seen_requests:
            raise ValueError("REQUEST_REPLAY")
        self.seen_requests.add(request_id)
        return {"ok": True, "action": action, "tab_binding_id": tab_binding_id}
