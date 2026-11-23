"""DOM Observation Interface — hợp đồng READ duy nhất Agent được dùng qua Gateway.

Kênh kiểm soát (fail-closed, không arbitrary evaluate, không direct CDP/
Playwright/9222 cho Agent):

- Agent KHÔNG tự evaluate JS, KHÔNG tự query DOM, KHÔNG cầm page/CDP handle.
  Mọi quan sát DOM đi qua transport đã grant (BridgeReadTransport) và chỉ trả
  về observation theo schema cố định dưới đây.
- Mỗi observation gắn lease binding: instance + tab + URL + grant epoch + TTL.
  Lệch 1 điểm -> từ chối, không trả dữ liệu cũ.
- Locator hẹp: chỉ các kind cho phép, giới hạn độ dài, cấm mọi dấu hiệu JS/
  evaluate. Ngoài danh sách -> READ_SPEC_DENIED.
- evaluate-readonly: op đọc chỉ thuộc {"text", "title", "url", "attr-safe",
  "count"}. Không op ghi, không navigate, không click/type.

 Luồng: acquire lease -> transport.read (pre/post validation) ->
 check_observed_binding -> eye collector đối chiếu trên tab thật ->
 Evidence (rea-eye) hoặc từ chối.
"""
from __future__ import annotations

import time

OBS_TTL_S = 300
LEASE_TTL_MAX_S = 1800

ALLOWED_LOCATOR_KINDS = ("role", "testid", "css", "text")

MAX_LOCATOR_LEN = 256
MAX_TEXT_MATCH_LEN = 120

ALLOWED_READ_OPS = ("text", "title", "url", "attr-safe", "count")

_BANNED_LOCATOR_TOKENS = (
    "evaluate", "javascript:", "<script", "function(", "=>",
    "__proto__", "constructor", "proxy(", "fetch(", "xmlhttprequest",
)


def check_narrow_locator(locator) -> dict:
    """Locator hẹp: kind cho phép + value ngắn + không dấu hiệu JS.

    Fail-closed: locator không phải dict, thiếu kind/value, kind lạ, value
    quá dài hay chứa token cấm -> {"ok": False, ...}.
    """
    if not isinstance(locator, dict):
        return {"ok": False, "error": "LOCATOR_INVALID"}
    kind = locator.get("kind")
    value = locator.get("value")
    if kind not in ALLOWED_LOCATOR_KINDS:
        return {"ok": False, "error": "LOCATOR_KIND_DENIED"}
    if not isinstance(value, str) or not value.strip():
        return {"ok": False, "error": "LOCATOR_INVALID"}
    limit = MAX_LOCATOR_LEN if kind != "text" else MAX_TEXT_MATCH_LEN
    if len(value) > limit:
        return {"ok": False, "error": "LOCATOR_TOO_WIDE"}
    lowered = value.lower()
    for token in _BANNED_LOCATOR_TOKENS:
        if token in lowered:
            return {"ok": False, "error": "LOCATOR_EVALUATE_DENIED"}
    if kind == "css" and ">>" in value:
        return {"ok": False, "error": "LOCATOR_TOO_WIDE"}
    return {"ok": True, "kind": kind, "value": value}


def check_read_op(op) -> dict:
    """Chỉ op đọc cho phép; mọi op khác (kể cả evaluate) bị từ chối."""
    if str(op or "") in ALLOWED_READ_OPS:
        return {"ok": True, "op": str(op)}
    return {"ok": False, "error": "READ_SPEC_DENIED"}


def check_observed_binding(*, obs_instance, obs_tab, obs_url, obs_epoch,
                           observed_at, instance_id, tab_id, url=None,
                           grant_epoch=None, ttl=OBS_TTL_S,
                           clock=None) -> dict:
    """Binding OBSERVED-level: instance/tab/URL/epoch/TTL. Fail-closed.

    - obs_*: giá trị gắn trên observation lúc thu thập.
    - instance_id/tab_id/url/grant_epoch: lease Agent đang giữ.
    - ttl: freshness tối đa (giây), mặc định 300.
    Lệch bất kỳ điểm nào -> {"ok": False, "error"}; không trả dữ liệu.
    """
    from miro.browser.runtime import _urls_same_destination

    if str(obs_instance or "") != str(instance_id or "") or not instance_id:
        return {"ok": False, "error": "OBSERVED_INSTANCE_MISMATCH"}
    try:
        if int(obs_tab) != int(tab_id):
            return {"ok": False, "error": "OBSERVED_TAB_MISMATCH"}
    except (TypeError, ValueError):
        return {"ok": False, "error": "OBSERVED_TAB_MISMATCH"}
    if url is not None and not _urls_same_destination(
            str(obs_url or ""), str(url)):
        return {"ok": False, "error": "OBSERVED_URL_MISMATCH"}
    if grant_epoch is not None:
        try:
            if int(obs_epoch) != int(grant_epoch):
                return {"ok": False, "error": "OBSERVED_EPOCH_MISMATCH"}
        except (TypeError, ValueError):
            return {"ok": False, "error": "OBSERVED_EPOCH_MISMATCH"}
    try:
        now = (clock or time.time)()
        age = now - float(observed_at)
    except (TypeError, ValueError):
        return {"ok": False, "error": "OBSERVED_AT_INVALID"}
    try:
        ttl = int(ttl)
    except (TypeError, ValueError):
        return {"ok": False, "error": "OBSERVED_TTL_INVALID"}
    if not 1 <= ttl <= LEASE_TTL_MAX_S:
        return {"ok": False, "error": "OBSERVED_TTL_INVALID"}
    if age < 0 or age > min(ttl, OBS_TTL_S):
        return {"ok": False, "error": "EVIDENCE_STALE"}
    return {"ok": True}


def validate_dom_observation(observation, lease, *, clock=None) -> dict:
    """Validate observation gắn lease trước khi giao cho eye đối chiếu.

    observation: {"spec", "locator", "op", "live_origin", "url",
                  "instance_id", "tab_id", "grant_epoch", "observed_at",
                  "untrusted": True, "data": {...}}.
    lease: {"instance_id", "tab_id", "url", "grant_epoch"} Agent đang giữ.
    """
    obs = observation if isinstance(observation, dict) else {}
    lease = lease if isinstance(lease, dict) else {}
    if obs.get("untrusted", True) is not True:
        return {"ok": False, "error": "OBSERVATION_MUST_BE_UNTRUSTED"}
    loc = check_narrow_locator(obs.get("locator"))
    if not loc.get("ok"):
        return loc
    op = check_read_op(obs.get("op"))
    if not op.get("ok"):
        return op
    return check_observed_binding(
        obs_instance=obs.get("instance_id"), obs_tab=obs.get("tab_id"),
        obs_url=obs.get("url") or obs.get("live_origin"),
        obs_epoch=obs.get("grant_epoch"),
        observed_at=obs.get("observed_at"),
        instance_id=lease.get("instance_id"), tab_id=lease.get("tab_id"),
        url=lease.get("url"), grant_epoch=lease.get("grant_epoch"),
        ttl=lease.get("ttl", OBS_TTL_S), clock=clock)
