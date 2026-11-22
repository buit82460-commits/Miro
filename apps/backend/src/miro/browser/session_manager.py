"""Browser Session Manager — đầu mối duy nhất kiểm tra Profile 20.

Khong hardcode cong 9222: cong doc tu DevToolsActivePort (co the dong).
Xac minh that: process + command-line + user-data-dir + Profile 20 +
/json/version dung instance. Khong taskkill, khong dong Chrome user,
khong tu chuyen profile, khong bat remote-debugging tren session
khong duoc cau hinh, khong restart Chrome.
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import time
import urllib.request

from miro.browser.errors import RegistryError
from miro.browser.runtime import chrome_endpoint, default_user_data_dir


def _port_open(port: int) -> bool:
    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=2)
        sock.close()
        return True
    except OSError:
        return False


def _read_port_file(user_data_dir: str) -> dict:
    path = os.path.join(user_data_dir, "DevToolsActivePort")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return {"ok": False, "reason": "NO_PORT_FILE"}
    try:
        port = int((lines[0] if lines else "").strip())
        route = (lines[1] if len(lines) else "").strip()
        valid = 1 <= port <= 65535 and re.fullmatch(
            r"/devtools/browser/[A-Za-z0-9-]+", route) is not None
    except (ValueError, IndexError):
        valid = False
        port, route = 0, ""
    if not valid:
        return {"ok": False, "reason": "BAD_PORT_FILE"}
    return {"ok": True, "port": port, "route": route}


def check_process(profile_directory: str = "Profile 20") -> dict:
    """Kiem tra chrome.exe dang chay voi --profile-directory dung.

    Khong kill, chi quan sat via tasklist (Windows). Tra ve
    {running, cmdline_hit, detail}. Khong co tasklist -> UNKNOWN (khong
    suy doan chay/khong chay).
    """
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/FO", "LIST"],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"running": None, "cmdline_hit": None,
                "detail": f"UNKNOWN: khong doc duoc process ({exc})"}
    txt = out.stdout or ""
    running = "chrome.exe" in txt.lower()
    if not running:
        return {"running": False, "cmdline_hit": False,
                "detail": "Chrome khong chay (tasklist khong thay chrome.exe)."}
    try:
        wmi = subprocess.run(
            ["wmic", "process", "where",
             "name='chrome.exe'", "get", "CommandLine", "/format:list"],
            capture_output=True, text=True, timeout=15)
        hit = (profile_directory.lower() in (wmi.stdout or "").lower()
               and "--remote-debugging-port" in (wmi.stdout or ""))
    except (OSError, subprocess.SubprocessError):
        hit = None
    if hit is True:
        detail = (f"chrome.exe chay + cmdline co {profile_directory} + "
                  "remote-debugging-port.")
    elif hit is False:
        detail = (f"chrome.exe chay nhung cmdline KHONG thay "
                  f"{profile_directory} + remote-debugging-port cung luc.")
    else:
        detail = "chrome.exe chay; khong xac minh duoc cmdline (wmic loi)."
    return {"running": True, "cmdline_hit": hit, "detail": detail}


def check_profile_dir(user_data_dir: str = "",
                      profile_directory: str = "Profile 20") -> dict:
    """Thu muc Profile 20 co ton tai duoi user-data-dir khong."""
    directory = (user_data_dir or "").strip() or default_user_data_dir()
    path = os.path.join(directory, profile_directory)
    if os.path.isdir(path):
        return {"ok": True, "path": path}
    return {"ok": False, "path": path,
            "detail": f"Khong thay thu muc profile: {path}"}


def verify_cdp_instance(port: int, timeout: float = 5.0) -> dict:
    """GET /json/version tren cong dong (khong hardcode 9222).

    Tra ve {ok, browser, webSocketDebuggerUrl, ...} hoac {ok False, reason}.
    Day la buoc 'dung instance' truoc khi connect_over_cdp.
    """
    url = f"http://127.0.0.1:{int(port)}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            import json
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:
        return {"ok": False,
                "reason": f"CDP_VERIFY_FAILED: {type(exc).__name__}: {exc}"}
    ws = str(data.get("webSocketDebuggerUrl") or "")
    if not ws:
        return {"ok": False,
                "reason": "CDP_VERIFY_FAILED: thieu webSocketDebuggerUrl"}
    return {"ok": True, "browser": str(data.get("Browser") or ""),
            "userAgent": str(data.get("User-Agent") or "")[:200],
            "webSocketDebuggerUrl": ws}


def inspect_session(user_data_dir: str = "",
                    profile_directory: str = "Profile 20",
                    verify_http: bool = True) -> dict:
    """Kiem tra trang thai Profile 20, khong side-effect.

    Thu tu: port-file (cong dong) -> port mo -> /json/version dung
    instance -> profile dir ton tai -> process/cmdline (tham khao).
    """
    directory = (user_data_dir or "").strip() or default_user_data_dir()
    info = _read_port_file(directory)
    if not info.get("ok"):
        reason = info.get("reason", "NO_PORT_FILE")
        if reason == "NO_PORT_FILE":
            return {"status": "BLOCKED_NO_CDP",
                    "endpoint": "",
                    "port": 0,
                    "detail": "DevToolsActivePort missing: Chrome dang chay "
                              "nhung khong bat remote-debugging; can restart "
                              "1 lan voi --remote-debugging-port + user-data-dir "
                              "rieng (Chrome 136+). Khong tu mo thay the."}
        return {"status": "BLOCKED_BAD_FILE",
                "endpoint": "",
                "port": 0,
                "detail": "DevToolsActivePort sai dinh dang; mo "
                          "chrome://inspect/#remote-debugging de kiem tra."}
    port = int(info["port"])
    endpoint = f"ws://127.0.0.1:{port}{info['route']}"
    if not _port_open(port):
        return {"status": "BLOCKED_NO_CDP", "endpoint": endpoint,
                "port": port,
                "detail": "Port file co nhung port khong mo duoc: Chrome co "
                          "the da tat hoac port bi chiem."}
    cdp: dict = {"ok": None}
    if verify_http:
        cdp = verify_cdp_instance(port)
        if not cdp.get("ok"):
            return {"status": "BLOCKED_WRONG_INSTANCE",
                    "endpoint": endpoint, "port": port,
                    "detail": str(cdp.get("reason") or "CDP verify fail") +
                              "; khong connect nham instance."}
    prof = check_profile_dir(directory, profile_directory)
    if not prof.get("ok"):
        return {"status": "BLOCKED_NO_PROFILE", "endpoint": endpoint,
                "port": port,
                "detail": str(prof.get("detail"))}
    proc = check_process(profile_directory)
    return {"status": "CONNECTED", "endpoint": endpoint, "port": port,
            "cdp": cdp, "profile": prof.get("path"),
            "process": proc,
            "detail": f"Profile {profile_directory} port {port}: CDP verify "
                      f"OK; {proc.get('detail')}"}


def diagnose_connection(user_data_dir: str = "") -> dict:
    """Chẩn đoán chi tiết cho agent: phân biệt chạy-không-CDP vs tắt hẳn."""
    directory = (user_data_dir or "").strip() or default_user_data_dir()
    info = _read_port_file(directory)
    if not info.get("ok"):
        return {"verdict": "NOT_CONNECTED",
                "cause": info.get("reason"),
                "action": "Nguoi dung mo Chrome Profile 20 voi remote-debugging "
                          "truoc (xem Miro-Chrome-Profile20.bat); agent KHONG "
                          "tu mo thay the, KHONG taskkill."}
    if not _port_open(int(info["port"])):
        return {"verdict": "NOT_CONNECTED",
                "cause": "PORT_CLOSED",
                "action": "Chrome co the da tat; mo lai dung file bat, "
                          "khong bao ket noi thanh cong gia."}
    cdp = verify_cdp_instance(int(info["port"]))
    if not cdp.get("ok"):
        return {"verdict": "NOT_CONNECTED",
                "cause": "WRONG_INSTANCE",
                "action": str(cdp.get("reason"))}
    return {"verdict": "CONNECTABLE",
            "cause": "",
            "endpoint": f"ws://127.0.0.1:{info['port']}{info['route']}",
            "port": int(info["port"]),
            "cdp_browser": cdp.get("browser", ""),
            "action": "Dung endpoint nay cho ManagedChromeSession.open "
                      "(1 connect/batch); khong tao tab trung."}


async def ensure_session(connect, user_data_dir: str, database,
                         profile_directory: str = "Profile 20",
                         **kwargs):
    """Đảm bảo session CDP thật, hoặc BLOCKED rõ lý do.

    Khong coi lenh mo Chrome thanh cong = da ket noi: bat buoc
    inspect CONNECTED (port dong + /json/version + profile dir) +
    `connect(endpoint)` that. That bai -> RegistryError BLOCKED_* kem
    hanh dong toi thieu, khong tu phuc hoi nguy hiem, khong restart.
    """
    from miro.browser.runtime import ManagedChromeSession

    report = inspect_session(user_data_dir, profile_directory)
    if report["status"] != "CONNECTED":
        raise RegistryError("BLOCKED_" + report["status"] + ": "
                            + report["detail"])
    # Chong TOCTOU: khoa endpoint da verify, truyen thang vao open thay vi
    # doc lai port-file (co the doi giua inspect va connect).
    endpoint = report.get("endpoint", "")
    if not endpoint:
        raise RegistryError("BLOCKED_CDP_UNAVAILABLE: thieu endpoint "
                            "da verify") from None
    session = await ManagedChromeSession.open(
        connect, user_data_dir or default_user_data_dir(), database,
        endpoint=endpoint, **kwargs)
    if session.endpoint != endpoint:
        await session.close()
        raise RegistryError("BLOCKED_WRONG_INSTANCE: endpoint sau connect "
                            "lech endpoint da verify; khong dung session nay")
    return session


def list_registered_tabs(session) -> list[dict]:
    """Liệt kê tab đã đăng ký trong store (không chạm browser)."""
    try:
        return list(session.runtime.store.list("tab"))
    except Exception:
        return []


async def reuse_or_open_tab(session, *, platform_id: str, url: str,
                            caller: str, **extra) -> dict:
    """Tái dùng tab hợp lệ; thiếu -> TAB_REQUIRED_OPEN_FIRST (không tự tạo).

    Không mở tab trùng: 1 platform đã có tab open thì acquire đúng tab đó.
    """
    acquired = await session.acquire_managed_tab(
        platform_id=platform_id, url=url, caller=caller, **extra)
    return {"reused": bool(getattr(acquired, "reused", True)),
            "record": dict(getattr(acquired, "record", {})),
            "handle": acquired}
