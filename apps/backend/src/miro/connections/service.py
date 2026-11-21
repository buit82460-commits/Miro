"""Connection service: them account, verify danh tinh that, pause/reconnect/revoke.

Port quy uoc:
- dubtool core/browser_runtime.py::verify_account: dung account + dung tab
  (profile binding + platform khop, observed tu provider khop expected),
  sai -> ACCOUNT_MISMATCH, khong replay.
- dubtool config/browser-clients.json: verify_account la action duoc phep.
- JARVIS backend/app/approval: quyet dinh can duyet ghi receipt (o day chi
  luu verification evidence dang sha, khong luu secret).
"""

from __future__ import annotations

import hashlib

from miro.browser.errors import RegistryError
from miro.connections import store as _store
from miro.connections.defaults import business_default
from miro.connections.models import AccountCreate, AccountOut, VerifyEvidence

_CRED_PREFIXES = ("vault:", "ref:", "env:", "keychain:", "oauth:", "secret:")


def _check_credential_ref(ref: str) -> str:
    value = (ref or "").strip()
    if not value:
        raise RegistryError("CREDENTIAL_REF_REQUIRED: credential chi luu tham chieu, khong plaintext")
    lowered = value.lower()
    if not lowered.startswith(_CRED_PREFIXES):
        raise RegistryError(
            "CREDENTIAL_PLAINTEXT_DENIED: chi nhan tham chieu "
            "(vault:/ref:/env:/keychain:/oauth:/secret:), khong luu secret that"
        )
    return value


def _norm(value: str) -> str:
    return (value or "").strip()


def _out(item: dict) -> AccountOut:
    return AccountOut(
        id=item["id"],
        platform=item["platform"],
        account_id=item["account_id"],
        display_name=item.get("display_name", ""),
        credential_ref=item.get("credential_ref"),
        profile_binding_id=item.get("profile_binding_id", ""),
        browser_instance_id=item.get("browser_instance_id", ""),
        is_default=bool(item.get("is_default")),
        status=item["status"],
        verified_at=item.get("verified_at"),
        verified_target_id=item.get("verified_target_id", ""),
        evidence_sha=item.get("evidence_sha", ""),
    )


def add_account(body: AccountCreate) -> AccountOut:
    platform = _norm(body.platform).lower()
    account_id = _norm(body.account_id)
    if not platform or not account_id:
        raise RegistryError("ACCOUNT_ID_REQUIRED")
    ref = _check_credential_ref(body.credential_ref)
    key = f"{platform}:{account_id}"
    if _store.get(key) is not None:
        raise RegistryError("ACCOUNT_EXISTS")
    default_hint = business_default(platform)
    auto_default = bool(default_hint and default_hint["account_id"] == account_id)
    if auto_default:
        _store.unset_default(platform)
    item = {
        "id": key,
        "platform": platform,
        "account_id": account_id,
        "display_name": _norm(body.display_name) or account_id,
        "credential_ref": ref,
        "profile_binding_id": _norm(body.profile_binding_id),
        "browser_instance_id": _norm(body.browser_instance_id),
        "is_default": auto_default,
        "status": "pending",
        "verified_at": None,
        "verified_target_id": "",
        "evidence_sha": "",
    }
    return _out(_store.put(item))


def get_account(account_id: str) -> AccountOut:
    item = _store.get(_norm(account_id))
    if item is None:
        raise RegistryError("ACCOUNT_NOT_FOUND")
    return _out(item)


def list_accounts(platform: str = "", status: str = "") -> list[AccountOut]:
    return [_out(a) for a in _store.list_accounts(_norm(platform).lower(), _norm(status))]


def _check_evidence(item: dict, ev: VerifyEvidence) -> str:
    if _norm(ev.platform_id).lower() != item["platform"]:
        raise RegistryError("ACCOUNT_MISMATCH: tab khac platform voi account")
    if item.get("profile_binding_id"):
        if _norm(ev.profile_binding_id) != item["profile_binding_id"]:
            raise RegistryError("ACCOUNT_MISMATCH: tab khac profile binding (thiet bi) voi account")
    if _norm(ev.observed_account_id) != item["account_id"]:
        item.update(status="unverified", verified_at=None,
                    verified_target_id="", evidence_sha="")
        _store.put(item)
        raise RegistryError(
            f"ACCOUNT_MISMATCH: tab dang dung {ev.observed_account_id}, "
            f"khac account dich {item['account_id']}"
        )
    # Verify kep truoc/sau op (port JARVIS live_chrome worker verify profile+actor
    # truoc VA sau moi op): caller gui snapshot sau, doi chieu voi snapshot truoc.
    after = _norm(ev.observed_account_id_after)
    if after and after != _norm(ev.observed_account_id):
        item.update(status="unverified", verified_at=None,
                    verified_target_id="", evidence_sha="")
        _store.put(item)
        raise RegistryError("ACCOUNT_MISMATCH: account doi giua chung (truoc/sau khac nhau)")
    if _norm(ev.profile_path_after) and _norm(ev.profile_path):
        import os as _os
        if _os.path.normcase(_os.path.realpath(_norm(ev.profile_path_after))) != \
                _os.path.normcase(_os.path.realpath(_norm(ev.profile_path))):
            raise RegistryError("PROFILE_MISMATCH: profile path doi giua chung")
    return _norm(ev.observed_account_id)


# Hook de worker (lease store) invalidate lease khi account bi revoke/doi.
# Test that inject fake; production noi voi LeaseStore o worker.
_revoke_hook = None


def set_revoke_hook(fn) -> None:
    global _revoke_hook
    _revoke_hook = fn


def _notify_revoked(item: dict) -> None:
    if _revoke_hook is None:
        return
    try:
        _revoke_hook(item)
    except Exception:
        pass


def verify_account(account_id: str, ev: VerifyEvidence) -> AccountOut:
    item = _store.get(_norm(account_id))
    if item is None:
        raise RegistryError("ACCOUNT_NOT_FOUND")
    if item["status"] == "revoked":
        raise RegistryError("ACCOUNT_REVOKED: them lai account truoc khi verify")
    _check_evidence(item, ev)
    if not item.get("profile_binding_id") and _norm(ev.profile_binding_id):
        item["profile_binding_id"] = _norm(ev.profile_binding_id)
    if _norm(ev.browser_instance_id):
        item["browser_instance_id"] = _norm(ev.browser_instance_id)
    raw = f"{item['platform']}:{item['account_id']}:{ev.tab_id}:{ev.target_id}".encode()
    item.update(
        status="connected",
        verified_at=_store.now(),
        verified_target_id=_norm(ev.target_id),
        evidence_sha=hashlib.sha256(raw).hexdigest(),
    )
    return _out(_store.put(item))


def pause_account(account_id: str) -> AccountOut:
    item = _store.get(_norm(account_id))
    if item is None:
        raise RegistryError("ACCOUNT_NOT_FOUND")
    if item["status"] != "connected":
        raise RegistryError("ACCOUNT_NOT_CONNECTED: chi tam dung account dang ket noi")
    item["status"] = "paused"
    return _out(_store.put(item))


def reconnect_account(account_id: str, ev: VerifyEvidence,
                      credential_ref: str = "") -> AccountOut:
    item = _store.get(_norm(account_id))
    if item is None:
        raise RegistryError("ACCOUNT_NOT_FOUND")
    if item["status"] not in ("paused", "unverified", "pending"):
        raise RegistryError("ACCOUNT_RECONNECT_REFUSED: chi ket noi lai tu paused/unverified/pending")
    if credential_ref:
        item["credential_ref"] = _check_credential_ref(credential_ref)
    if item.get("credential_ref") is None:
        raise RegistryError("CREDENTIAL_REF_REQUIRED: cap lai tham chieu credential truoc khi ket noi lai")
    _check_evidence(item, ev)
    raw = f"{item['platform']}:{item['account_id']}:{ev.tab_id}:{ev.target_id}".encode()
    item.update(
        status="connected",
        verified_at=_store.now(),
        verified_target_id=_norm(ev.target_id),
        evidence_sha=hashlib.sha256(raw).hexdigest(),
    )
    return _out(_store.put(item))


async def verify_via_browser(account_id: str, runtime, tab_record: dict,
                             caller: str = "connections-verify") -> AccountOut:
    """Verify tai khoan that qua Browser M1: acquire tab (lease) + verify actor
    truoc/sau read, roi moi chuyen connected. Tab mat/lease bi giu/account lech
    -> loi ro, khong fallback tab khac (port JARVIS live_chrome worker Đ2).
    """
    item_key = _norm(account_id)
    item = _store.get(item_key)
    if item is None:
        raise RegistryError("ACCOUNT_NOT_FOUND")
    if item["status"] == "revoked":
        raise RegistryError("ACCOUNT_REVOKED: them lai account truoc khi verify")
    if runtime is None:
        raise RegistryError("BROWSER_UNAVAILABLE: can Browser M1 runtime de verify that")
    request = {
        "profileBindingId": item.get("profile_binding_id") or tab_record.get("profileBindingId", ""),
        "platformId": item["platform"],
        "url": tab_record.get("url", ""),
        "leaseTtl": 180,
        "expectedAccountId": item["account_id"],
        "channelId": tab_record.get("channelId"),
    }
    expected_profile = item.get("profile_binding_id") or ""
    if expected_profile and request["profileBindingId"] != expected_profile:
        raise RegistryError("ACCOUNT_MISMATCH: tab khac profile binding (thiet bi) voi account")
    lease = None
    acquired = None
    try:
        acquired = await runtime.acquire_tab(request, caller)
    except Exception as exc:
        from miro.browser.errors import LeaseBusy as _LeaseBusy
        if isinstance(exc, _LeaseBusy) or "BUSY" in type(exc).__name__.upper() \
                or "BUSY" in str(exc).upper():
            raise RegistryError(f"TAB_LEASE_BUSY: {exc}") from None
        raise
    try:
        result = await acquired.read()
        # read_tab cua runtime da verify actor truoc/sau (WorkerStopped neu lech).
        # Lay observed that tu provider de doi chieu lan cuoi; khong fallback.
        observed = ""
        provider = getattr(runtime, "verify_actor", None) or \
            (runtime.account_providers or {}).get(item["platform"])
        if provider is not None:
            try:
                import asyncio as _asyncio
                out = provider(acquired.page, acquired.record)
                if _asyncio.iscoroutine(out):
                    out = await out
                observed = str(out or "")
            except Exception:
                observed = ""
        if not observed:
            raise RegistryError("ACCOUNT_MISMATCH: khong doc duoc observed identity tu tab")
        ev = VerifyEvidence(
            tab_id=tab_record.get("targetId", ""),
            platform_id=item["platform"],
            profile_binding_id=request["profileBindingId"],
            observed_account_id=observed,
            target_id=tab_record.get("targetId", ""),
        )
        return verify_account(item_key, ev)
    finally:
        if acquired is not None:
            try:
                await acquired.release()
            except Exception:
                pass


def revoke_account(account_id: str) -> AccountOut:
    item = _store.get(_norm(account_id))
    if item is None:
        raise RegistryError("ACCOUNT_NOT_FOUND")
    item.update(status="revoked", credential_ref=None, is_default=False,
                verified_target_id="", evidence_sha="")
    out = _out(_store.put(item))
    # Thu hoi quyen co hieu luc o worker: invalidate lease de worker cu mat quyen ngay.
    _notify_revoked(item)
    return out


def set_default(account_id: str) -> AccountOut:
    item = _store.get(_norm(account_id))
    if item is None:
        raise RegistryError("ACCOUNT_NOT_FOUND")
    if item["status"] == "revoked":
        raise RegistryError("ACCOUNT_REVOKED: khong dat revoked lam mac dinh")
    _store.unset_default(item["platform"], keep_id=item["id"])
    item["is_default"] = True
    return _out(_store.put(item))


def resolve_default(platform: str) -> dict:
    pid = _norm(platform).lower()
    for item in _store.list_accounts(pid):
        if item.get("is_default") and item.get("status") != "revoked":
            return {"platform": pid, "account": _out(item).model_dump(), "source": "user_default"}
    hint = business_default(pid)
    if hint is not None:
        return {"platform": pid, "account": hint, "source": "business_default"}
    return {"platform": pid, "account": None, "source": "none"}
