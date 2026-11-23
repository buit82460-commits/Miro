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
                           approval: dict | None) -> dict:
    """Gate 8 diem truoc moi WRITE (docs/security/eye-gate.md). Fail-closed.

    Tra ve record sau khi pass. Bat ky diem nao rot -> raise, khong bam.
    """
    from miro.browser.runtime import _urls_same_destination

    record = dict(getattr(acquired, "record", {}) or {})
    target = str(record.get("targetId", ""))
    instance = str(getattr(getattr(acquired, "runtime", None),
                           "instance_id", "") or "")
    ev = check_evidence(evidence or {}, tab_id=target,
                        instance_id=instance)
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
    if callable(verify):
        try:
            actor_now = await verify(page, record, acquired.lease) or ""
        except RegistryError as exc:
            if "ACCOUNT_VERIFIER_UNAVAILABLE" in str(exc):
                actor_now = ""
            else:
                raise
        if actor_now and ev.get("actor") and actor_now != ev.get("actor"):
            raise RegistryError("EVIDENCE_ACTOR_CHANGED: actor doi tu "
                                + str(ev.get("actor")) + " sang "
                                + str(actor_now) + "; mat doc lai")
        expected = str(record.get("expectedAccountId") or "")
        if expected and actor_now and actor_now != expected:
            from miro.browser.errors import WorkerStopped
            raise WorkerStopped("WORKER_STOPPED: ACCOUNT_MISMATCH")
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        raise RegistryError("WRITE_DENIED: thieu approval hop le cua dung task")
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
                            adapter_fn) -> dict:
    """WRITE duy nhất: gate 8 diem (docs/security/eye-gate.md) roi moi goi adapter.

    - evidence qua check_evidence + check_write_gate (instance/tab tuoi,
      actor, url destination, lease, approval dung task) — rot la DENY.
    - adapter_fn: async (page) -> receipt dict.
    Sau thao tac: receipt phai co (ack/toast/url), khong co -> UNKNOWN giu.
    """
    from miro.browser.session_manager import reuse_or_open_tab

    out = await reuse_or_open_tab(session, platform_id=platform_id, url=url,
                                  caller=caller)
    acquired = out["handle"]
    try:
        await check_write_gate(session, acquired, evidence, approval)
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
        "Gateway (read_via_eye/write_via_adapter) + eye collector.")
