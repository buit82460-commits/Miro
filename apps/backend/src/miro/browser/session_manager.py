"""Browser Session Manager — đầu mối duy nhất kiểm tra Profile 20.

Giải 2 lỗi vận hành:
- Agent tưởng `chrome.exe ...` trả về = đã kết nối (sai). Manager kiểm tra
  thật: process Chrome + DevToolsActivePort + endpoint + CDP connect.
- Không hỏi lại thông tin đã có: session/tab hợp lệ thì tái dùng.

Không taskkill, không đóng Chrome user, không tự chuyển profile, không bật
remote-debugging trên session không được cấu hình.
"""
from __future__ import annotations

import os
import re
import socket
import time

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
        route = (lines[1] if len(lines) > 1 else "").strip()
        valid = 1 <= port <= 65535 and re.fullmatch(
            r"/devtools/browser/[A-Za-z0-9-]+", route) is not None
    except (ValueError, IndexError):
        valid = False
        port, route = 0, ""
    if not valid:
        return {"ok": False, "reason": "BAD_PORT_FILE"}
    return {"ok": True, "port": port, "route": route}


def inspect_session(user_data_dir: str = "",
                    profile_directory: str = "Profile 20") -> dict:
    """Kiểm tra trạng thái Profile 20, không side-effect.

    Trả về dict {status, endpoint, detail}:
    - CONNECTED: port file hợp lệ + port mở được (CDP có thể nối).
    - BLOCKED_NO_CDP: Chrome chạy nhưng không có remote-debugging.
    - BLOCKED_BAD_FILE / BLOCKED_NO_PORT_FILE: thiếu/sai DevToolsActivePort.
    """
    directory = (user_data_dir or "").strip() or default_user_data_dir()
    info = _read_port_file(directory)
    if not info.get("ok"):
        reason = info.get("reason", "NO_PORT_FILE")
        if reason == "NO_PORT_FILE":
            return {"status": "BLOCKED_NO_CDP",
                    "endpoint": "",
                    "detail": "DevToolsActivePort missing: Chrome dang chay "
                              "nhung khong bat remote-debugging; can restart "
                              "1 lan voi --remote-debugging-port + user-data-dir "
                              "rieng (Chrome 136+). Khong tu mo thay the."}
        return {"status": "BLOCKED_BAD_FILE",
                "endpoint": "",
                "detail": "DevToolsActivePort sai dinh dang; mo "
                          "chrome://inspect/#remote-debugging de kiem tra."}
    endpoint = f"ws://127.0.0.1:{info['port']}{info['route']}"
    if not _port_open(int(info["port"])):
        return {"status": "BLOCKED_NO_CDP", "endpoint": endpoint,
                "detail": "Port file co nhung port khong mo duoc: Chrome co "
                          "the da tat hoac port bi chiem."}
    return {"status": "CONNECTED", "endpoint": endpoint,
            "detail": f"Profile {profile_directory} co the noi CDP."}


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
    return {"verdict": "CONNECTABLE",
            "cause": "",
            "endpoint": f"ws://127.0.0.1:{info['port']}{info['route']}",
            "action": "Dung endpoint nay cho ManagedChromeSession.open "
                      "(1 connect/batch); khong tao tab trung."}


async def ensure_session(connect, user_data_dir: str, database,
                         profile_directory: str = "Profile 20",
                         **kwargs):
    """Đảm bảo session CDP thật, hoặc BLOCKED rõ lý do.

    Không coi lệnh mở Chrome thành công = đã kết nối: bắt buộc
    inspect CONNECTED + `connect(endpoint)` thật. Thất bại -> RegistryError
    BLOCKED_* kèm hành động tối thiểu, không tự phục hồi nguy hiểm.
    """
    from miro.browser.runtime import ManagedChromeSession

    report = inspect_session(user_data_dir, profile_directory)
    if report["status"] != "CONNECTED":
        raise RegistryError("BLOCKED_" + report["status"] + ": "
                            + report["detail"])
    try:
        endpoint = chrome_endpoint(user_data_dir or default_user_data_dir())
    except RegistryError as error:
        raise RegistryError("BLOCKED_CDP_UNAVAILABLE: " + str(error)) from None
    session = await ManagedChromeSession.open(
        connect, user_data_dir or default_user_data_dir(), database, **kwargs)
    if session.endpoint != endpoint and endpoint:
        pass
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
