"""Browser Gateway — đường truy cập trình duyệt duy nhất của agent.

READ: chỉ eye collector được quan sát. WRITE: chỉ adapter được side-effect.
Mọi đường trực tiếp (playwright snapshot/click/evaluate ngoài eye/adapter)
bị coi là BYPASS và Gateway từ chối tại runtime.
"""
from __future__ import annotations

import time
from contextlib import suppress

from miro.browser.errors import RegistryError, WorkerStopped


def _now() -> float:
    return time.time()


def check_evidence(evidence: dict, *, tab_id: str = "",
                   instance_id: str = "") -> dict:
    """Evidence hop le: url + tab identity + timestamp tuoi (<300s).

    Khong phai giay phep vinh vien — xem docs/security/eye-gate.md: truoc moi
    WRITE con phai check instance/actor/url/lease/approval (check_write_gate).
    """
    if not isinstance(evidence, dict):
        raise RegistryError("EVIDENCE_INVALID: khong phai dict")
    if str(evidence.get("provenance") or "") != "rea-eye":
        if str(evidence.get("provenance") or "") == "media-analysis":
            raise RegistryError(
                "EVIDENCE_INVALID: ket qua media-analysis chi de hieu noi dung, "
                "KHONG phai Evidence ghi (khong thay verify actor/tab de Post); "
                "muon Post phai co rea-eye Evidence tuoi dung tab")
        raise RegistryError("EVIDENCE_INVALID: provenance phai la rea-eye; "
                            "snapshot ngoai Gateway khong phai Evidence")
    url = str(evidence.get("url") or "")
    if not url.startswith("http"):
        raise RegistryError("EVIDENCE_INVALID: thieu url")
    stamp = evidence.get("observed_at", 0)
    try:
        age = _now() - float(stamp)
    except (TypeError, ValueError):
        raise RegistryError("EVIDENCE_INVALID: thieu observed_at")
    if age < 0 or age > 300:
        raise RegistryError("EVIDENCE_STALE: qua 300s, mat doc lai")
    if tab_id and str(evidence.get("tab_id") or "") != tab_id:
        raise RegistryError("EVIDENCE_TAB_MISMATCH: evidence tab A khong "
                            "dung cho tab B")
    if not evidence.get("tab_id"):
        raise RegistryError("EVIDENCE_INVALID: thieu tab_id")
    if instance_id and str(evidence.get("instance_id") or "") != instance_id:
        raise RegistryError("EVIDENCE_WRONG_INSTANCE: evidence khong thuoc "
                            "browser instance nay")
    return evidence


async def check_write_gate(session, acquired, evidence: dict,
                           approval: dict | None,
                           auth: dict | None = None) -> dict:
    """Gate WRITE (docs/security/eye-gate.md). Fail-closed tuyet doi.

    - `auth` BAT BUOC o production: authorization context do caller dang tin
      cay truyen tu task/intent state (KHONG lay tu approval). Thieu hoac
      thieu field bat buoc -> DENY (AUTH_REQUIRED), ke ca khi approval co
      `approved is True`. Khong co che do warn-then-pass.
    - runtime.write_task_context is installed by the trusted task service,
      not by a request. It must reload current intent state for the executing
      task, including active/scope/revision/fingerprint/account/destination.
      No production resolver is wired yet: default WRITE is disabled.
      Lease owner binding is an additional check, never task authority.
    - approval phai khop `auth` tung truong: task_id/scope/revision/
      fingerprint (APPROVAL_TASK_MISMATCH/SCOPE_DENIED/STALE_REVISION/
      FINGERPRINT_CONFLICT).
    - Moi WRITE qua Gateway mac dinh la account-bound: thieu verifier,
      actor rong hoac khong khop -> DENY. Khong co nhanh `system`, khong co
      env bypass, khong dung `actor=""` de bo qua so sanh.

    Tra ve record sau khi pass. Bat ky diem nao rot -> raise, khong bam.
    """
    from miro.browser.runtime import _urls_same_destination

    record = dict(getattr(acquired, "record", {}) or {})
    target = str(record.get("targetId", ""))
    instance = str(getattr(getattr(acquired, "runtime", None),
                           "instance_id", "") or "")
    ev = check_evidence(evidence or {}, tab_id=target,
                        instance_id=instance)
    # The service owns this resolver. A lease/caller string proves tab ownership,
    # not task authorization. No resolver means WRITE stays disabled.
    resolver = getattr(acquired.runtime, "write_task_context", None)
    if not callable(resolver):
        raise RegistryError("AUTH_REQUIRED: trusted task resolver unavailable")
    owner = str((getattr(acquired, "lease", None) or {}).get("owner") or "")
    caller = owner.rsplit(":", 1)[0]
    trusted = resolver(caller)
    if not isinstance(trusted, dict) or trusted.get("active") is not True:
        raise RegistryError("AUTH_REQUIRED: current task/intent unavailable or inactive")
    for key in ("task_id", "scope", "revision", "fingerprint"):
        if not isinstance(auth, dict) or key not in trusted or auth.get(key) != trusted[key]:
            raise RegistryError("AUTH_REQUIRED: auth differs from current task/intent: " + key)
    if (trusted.get("platform_id") != record.get("platformId")
            or trusted.get("account_id") != record.get("expectedAccountId")
            or not trusted.get("account_id")
            or not _urls_same_destination(str(trusted.get("url") or ""),
                                          str(ev.get("url") or ""))):
        raise RegistryError("AUTH_REQUIRED: task destination/account mismatch")
    # -- A1: binding approval <-> auth (trusted task context) ---------------
    if not isinstance(auth, dict):
        raise RegistryError("AUTH_REQUIRED: thieu authorization context "
                            "tu task/intent state; khong WRITE bang "
                            "approval troi")
    task_id = str(auth.get("task_id") or "")
    scope = str(auth.get("scope") or "")
    fingerprint = str(auth.get("fingerprint") or "")
    try:
        revision = int(auth.get("revision"))
    except (TypeError, ValueError):
        raise RegistryError("AUTH_REQUIRED: auth thieu revision hop le") \
            from None
    if not task_id or not scope or not fingerprint:
        raise RegistryError("AUTH_REQUIRED: auth thieu "
                            "task_id/scope/fingerprint")
    lease = getattr(acquired, "lease", None)
    owner = str((lease or {}).get("owner", "") or "")
    if not isinstance(lease, dict) or not owner:
        raise RegistryError("AUTH_REQUIRED: khong co lease de gan auth")
    if owner.rsplit(":", 1)[0] != task_id:
        raise RegistryError("APPROVAL_TASK_MISMATCH: auth.task_id '" +
                            task_id + "' khong phai chu lease '" +
                            owner.split(":")[0] + "'")
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        raise RegistryError("WRITE_DENIED: thieu approval hop le cua dung task")
    if str(approval.get("task_id") or "") != task_id:
        raise RegistryError("APPROVAL_TASK_MISMATCH: approval cua task '" +
                            str(approval.get("task_id") or "") +
                            "', task hien tai '" + task_id + "'")
    if str(approval.get("scope") or "") != scope:
        raise RegistryError("SCOPE_DENIED: approval scope '" +
                            str(approval.get("scope") or "") + "', can '" +
                            scope + "'")
    try:
        approval_rev = int(approval.get("revision"))
    except (TypeError, ValueError):
        raise RegistryError("STALE_REVISION: approval thieu revision") \
            from None
    if approval_rev != revision:
        raise RegistryError("STALE_REVISION: approval gan revision " +
                            str(approval.get("revision")) + "; hien tai " +
                            str(revision))
    if str(approval.get("fingerprint") or "") != fingerprint:
        raise RegistryError("FINGERPRINT_CONFLICT: intent doi sau khi "
                            "duyet; can duyet lai")
    page = acquired.page
    current_url = getattr(page, "url", None)
    if isinstance(current_url, str) and not _urls_same_destination(
            current_url, str(ev.get("url") or "")):
        raise RegistryError("TAB_ORIGIN_CHANGED: tab da navigate di noi "
                            "khac sau khi mat doc; mat doc lai")
    try:
        getattr(acquired.runtime.store, "validate")(acquired.lease)
    except Exception as exc:
        raise RegistryError("LEASE_LOST: quyen tab het hieu luc truoc "
                            "write (" + type(exc).__name__ + ")") from None
    verify = getattr(getattr(acquired, "runtime", None), "_verify_actor",
                     None)
    actor_now = ""
    if not ev.get("actor") or not record.get("expectedAccountId"):
        raise RegistryError("WRITE_DENIED: evidence and expected actor required")
    if callable(verify):
        try:
            actor_now = await verify(page, record, acquired.lease) or ""
        except RegistryError as exc:
            # A2: account-bound WRITE thieu verifier -> DENY tuyet doi.
            # Khong nuot thanh actor="", khong env bypass, khong nhanh system.
            if "ACCOUNT_VERIFIER_UNAVAILABLE" not in str(exc):
                raise
            raise RegistryError("WRITE_DENIED: no actor verifier "
                                "('" + str(exc)[:80] + "')") from None
        if actor_now and ev.get("actor") and actor_now != ev.get("actor"):
            raise RegistryError("EVIDENCE_ACTOR_CHANGED: actor doi tu "
                                + str(ev.get("actor")) + " sang "
                                + str(actor_now) + "; mat doc lai")
        expected = str(record.get("expectedAccountId") or "")
        if expected and actor_now and actor_now != expected:
            from miro.browser.errors import WorkerStopped
            raise WorkerStopped("WORKER_STOPPED: ACCOUNT_MISMATCH")
    else:
        raise RegistryError("WRITE_DENIED: no actor verifier (runtime "
                            "khong co _verify_actor)")
    # Account-bound: actor bat buoc non-empty sau verify. Khong dung
    # actor="" de bo qua so sanh.
    if not actor_now:
        raise RegistryError("WRITE_DENIED: actor khong xac minh duoc; "
                            "khong WRITE mu")
    return record


async def read_via_eye(session, *, platform_id: str, url: str, caller: str,
                       eye_fn, expected_account: str = "") -> dict:
    """READ duy nhất: acquire tab -> verify actor -> eye collector -> release.

    Trả evidence {url, tab_id, actor, observed_at, record, provenance}.
    Không phát sinh side-effect (không goto/navigate trong hàm này).
    """
    from miro.browser.session_manager import reuse_or_open_tab

    out = await reuse_or_open_tab(session, platform_id=platform_id, url=url,
                                  caller=caller)
    acquired = out["handle"]
    record = getattr(acquired, "record", {})
    target = str((record or {}).get("targetId", ""))
    try:
        page = acquired.page
        actor = ""
        verify = getattr(getattr(acquired, "runtime", None),
                         "_verify_actor", None)
        if callable(verify):
            # Khong nuot WorkerStopped/ACCOUNT_MISMATCH: lease stale hoac
            # doi account giua chung phai dung (T9). Chi bo qua khi khong
            # co verifier (ACCOUNT_VERIFIER_UNAVAILABLE -> actor rong).
            try:
                actor = await verify(page, record, acquired.lease) or ""
            except RegistryError as exc:
                if "ACCOUNT_VERIFIER_UNAVAILABLE" in str(exc):
                    actor = ""
                else:
                    raise
        if expected_account and actor and actor != expected_account:
            raise WorkerStopped("WORKER_STOPPED: ACCOUNT_MISMATCH")
        if expected_account and not actor:
            raise RegistryError("EVIDENCE_UNVERIFIED: khong xac minh duoc "
                                "actor nhung task doi account cu the; mat doc lai")
        data = await eye_fn(page) or {}
        # Chong race: lease het / tab navigate / doi actor GIUA luc doc
        # -> bo evidence, khong tra du lieu cu.
        try:
            getattr(acquired.runtime.store, "validate")(acquired.lease)
        except Exception as exc:
            raise RegistryError("LEASE_LOST_DURING_READ: het quyen giua luc "
                                "doc (" + type(exc).__name__ + ")") from None
        from miro.browser.runtime import _urls_same_destination
        cur = getattr(page, "url", None)
        if isinstance(cur, str) and not _urls_same_destination(
                cur, str((record or {}).get("url") or url)):
            raise RegistryError("TAB_CHANGED_DURING_READ: tab doi giua luc "
                                "mat doc; bo evidence")
        if callable(verify) and actor:
            try:
                actor_after = await verify(page, record,
                                           acquired.lease) or ""
            except RegistryError as exc:
                if "ACCOUNT_VERIFIER_UNAVAILABLE" not in str(exc):
                    raise
                actor_after = actor
            if actor_after and actor_after != actor:
                raise RegistryError("EVIDENCE_ACTOR_CHANGED: actor doi giua "
                                    "luc mat doc; bo evidence")
        instance = str(getattr(getattr(acquired, "runtime", None),
                               "instance_id", "") or "")
        evidence = {"url": str(data.get("url") or url),
                    "tab_id": target,
                    "instance_id": instance,
                    "actor": actor or str(data.get("actor") or ""),
                    "observed_at": _now(),
                    "record": data,
                    "provenance": "rea-eye",
                    "platform": platform_id}
        return evidence
    finally:
        with suppress(Exception):
            await acquired.release()


async def write_via_adapter(session, *, platform_id: str, url: str,
                            caller: str, evidence: dict,
                            approval: dict | None,
                            adapter_fn, auth: dict | None = None) -> dict:
    """WRITE duy nhất: gate (docs/security/eye-gate.md) roi moi goi adapter.

    - `auth` BAT BUOC o production: authorization context tu task/intent
      state do caller dang tin truyen; thieu -> DENY (AUTH_REQUIRED).
    - evidence qua check_evidence + check_write_gate (instance/tab tuoi,
      actor, url destination, lease, auth binding, approval dung task).
    - adapter_fn: async (page) -> receipt dict.
    Sau thao tac: receipt phai co (ack/toast/url), khong co -> UNKNOWN giu.
    """
    from miro.browser.session_manager import reuse_or_open_tab

    out = await reuse_or_open_tab(session, platform_id=platform_id, url=url,
                                  caller=caller)
    acquired = out["handle"]
    try:
        await check_write_gate(session, acquired, evidence, approval,
                               auth=auth)
    except Exception:
        with suppress(Exception):
            await acquired.release()
        raise
    try:
        receipt = await adapter_fn(acquired.page)
    finally:
        # Kiem lai lease sau khi bam: het quyen giua luc bam -> receipt
        # khong dang tin, giu UNKNOWN thay vi tin receipt.
        try:
            getattr(acquired.runtime.store, "validate")(acquired.lease)
        except Exception:
            receipt = None
        with suppress(Exception):
            await acquired.release()
    if not isinstance(receipt, dict) or not receipt:
        return {"receipt": "UNCONFIRMED_NO_REPLAY", "posted": False,
                "hint": "khong co receipt; giu UNKNOWN, khong replay"}
    return receipt


def deny_direct_browser(tool_name: str) -> None:
    """Runtime từ chối đường trực tiếp ngoài Gateway."""
    raise RegistryError(
        f"BYPASS_DENIED: '{tool_name}' truc tiep bi cam; di qua Browser "
        "Gateway (read_via_eye/read_actor_via_bridge/read_video_via_bridge"
        "/write_via_adapter) + eye collector.")


async def read_actor_via_bridge(session_id: str, token: str, *,
                                instance_id: str, tab_id: int,
                                live_origin: str, url: str | None = None,
                                grant_epoch=None, base: str = "",
                                timeout: int = 30, backend_key: str = "",
                                task_id: str = "",
                                is_cancelled=None) -> dict:
    """Production READ actor qua Bridge (không CDP/không Page).

    Bridge observation (actor-login) -> evaluate_actor_signals -> Evidence
    rea-eye toi da ACTOR_CLAIMED. Fail-closed moi diem binding.
    """
    from miro.browser.bridge_transport import (
        BRIDGE_BASE, read_via_bridge as _read_bridge)
    from miro.eye import evaluate_actor_signals

    r = await _read_bridge(
        session_id, token, instance_id=instance_id, tab_id=tab_id,
        live_origin=live_origin, spec="actor-login",
        base=base or BRIDGE_BASE, timeout=timeout,
        grant_epoch=grant_epoch, url=url, backend_key=backend_key,
        task_id=task_id)
    if not isinstance(r, dict) or not r.get("ok"):
        return r if isinstance(r, dict) else {
            "ok": False, "error": "BRIDGE_READ_FAILED"}
    obs = r.get("observation") or {}
    data = obs.get("data") if isinstance(obs.get("data"), dict) else {}
    sig = evaluate_actor_signals(data)
    if not sig.get("ok"):
        return {"ok": False, "error": str(sig.get("error") or "ACTOR_UNVERIFIED"),
                "missing": sig.get("missing", []),
                "status": sig.get("status", "ACTOR_CLAIMED_FAILED")}
    return {"ok": True,
            "evidence": {"url": str((data or {}).get("url") or url or ""),
                         "tab_id": str(tab_id),
                         "instance_id": str(instance_id),
                         "actor": str(sig.get("actor") or ""),
                         "actor_status": "ACTOR_CLAIMED",
                         "observed_at": obs.get("observed_at") or _now(),
                         "record": {"observation": data},
                         "provenance": "rea-eye",
                         "platform": "tiktok",
                         "lease": {"instance_id": str(instance_id),
                                   "tab_id": int(tab_id),
                                   "url": url,
                                   "grant_epoch": obs.get("grant_epoch", 0)}},
            "observation": obs}


async def read_video_via_bridge(session_id: str, token: str, *,
                                instance_id: str, tab_id: int,
                                live_origin: str, url: str | None = None,
                                grant_epoch=None, base: str = "",
                                timeout: int = 30,
                                expected_aweme: str = "") -> dict:
    """Production READ video-identity qua Bridge (không CDP/không Page).

    Validate: aweme_id tu URL that khop expected (neu task yeu cau);
    has_video phai co; caption chi preview. Tra Evidence rea-eye
    (video identity, khong phai actor verify).
    """
    import re
    from miro.browser.bridge_transport import (
        BRIDGE_BASE, read_via_bridge as _read_bridge)

    r = await _read_bridge(
        session_id, token, instance_id=instance_id, tab_id=tab_id,
        live_origin=live_origin, spec="video-identity",
        base=base or BRIDGE_BASE, timeout=timeout,
        grant_epoch=grant_epoch, url=url)
    if not isinstance(r, dict) or not r.get("ok"):
        return r if isinstance(r, dict) else {
            "ok": False, "error": "BRIDGE_READ_FAILED"}
    obs = r.get("observation") or {}
    data = obs.get("data") if isinstance(obs.get("data"), dict) else {}
    page_url = str(data.get("url") or "")
    aweme = str(data.get("aweme_id") or "")
    if not aweme:
        hit = re.search(r"/video/(\d+)", page_url or "")
        if hit:
            aweme = hit.group(1)
    if not aweme or not re.match(r"^\d{5,30}$", aweme):
        return {"ok": False, "error": "VIDEO_IDENTITY_MISSING"}
    if not str(data.get("has_video") or ""):
        return {"ok": False, "error": "VIDEO_ELEMENT_MISSING"}
    if expected_aweme and aweme != str(expected_aweme):
        return {"ok": False, "error": "VIDEO_IDENTITY_MISMATCH"}
    if url:
        from miro.browser.runtime import _urls_same_destination
        if not _urls_same_destination(page_url, str(url)):
            return {"ok": False, "error": "OBSERVED_URL_MISMATCH"}
    return {"ok": True,
            "evidence": {"url": page_url,
                         "tab_id": str(tab_id),
                         "instance_id": str(instance_id),
                         "aweme_id": aweme,
                         "caption_preview": str(
                             data.get("caption_preview") or "")[:300],
                         "has_video": True,
                         "observed_at": obs.get("observed_at") or _now(),
                         "record": {"observation": data},
                         "provenance": "rea-eye",
                         "platform": "tiktok",
                         "lease": {"instance_id": str(instance_id),
                                   "tab_id": int(tab_id),
                                   "url": url or page_url,
                                   "grant_epoch": obs.get("grant_epoch", 0)}},
            "observation": obs}


async def read_feed_video_via_bridge(session_id: str, token: str, *,
                                     instance_id: str, tab_id: int,
                                     live_origin: str, grant_epoch=None,
                                     base: str = "",
                                     timeout: int = 30) -> dict:
    """Production READ video dau feed TikTok qua Bridge (trang chu).

    Spec "feed-video": mo anchor /video/ that dau tien trong DOM (feed
    For You), tra Evidence rea-eye {author, aweme_id, video_url,
    caption_preview, has_video}. Mat doc truoc, adapter quyet dinh sau.
    URL trang van la homepage — dung video_url mo duoc, khong dung page_url.
    """
    import re
    from miro.browser.bridge_transport import (
        BRIDGE_BASE, read_via_bridge as _read_bridge)

    r = await _read_bridge(
        session_id, token, instance_id=instance_id, tab_id=tab_id,
        live_origin=live_origin, spec="feed-video",
        base=base or BRIDGE_BASE, timeout=timeout,
        grant_epoch=grant_epoch, url=live_origin)
    if not isinstance(r, dict) or not r.get("ok"):
        return r if isinstance(r, dict) else {
            "ok": False, "error": "BRIDGE_READ_FAILED"}
    obs = r.get("observation") or {}
    data = obs.get("data") if isinstance(obs.get("data"), dict) else {}
    aweme = str(data.get("aweme_id") or "")
    video_url = str(data.get("video_url") or "")
    if not aweme:
        hit = re.search(r"/video/(\d+)", video_url or "")
        if hit:
            aweme = hit.group(1)
    if not aweme or not re.match(r"^\d{5,30}$", aweme):
        return {"ok": False, "error": "FEED_VIDEO_IDENTITY_MISSING"}
    if not str(data.get("has_video") or ""):
        return {"ok": False, "error": "FEED_VIDEO_ELEMENT_MISSING"}
    return {"ok": True,
            "evidence": {"url": video_url or live_origin,
                         "tab_id": str(tab_id),
                         "instance_id": str(instance_id),
                         "aweme_id": aweme,
                         "author": str(data.get("author") or ""),
                         "caption_preview": str(
                             data.get("caption_preview") or "")[:300],
                         "has_video": True,
                         "observed_at": obs.get("observed_at") or _now(),
                         "record": {"observation": data},
                         "provenance": "rea-eye",
                         "platform": "tiktok",
                         "lease": {"instance_id": str(instance_id),
                                   "tab_id": int(tab_id),
                                   "url": live_origin,
                                   "grant_epoch": obs.get("grant_epoch", 0)}},
            "observation": obs}
