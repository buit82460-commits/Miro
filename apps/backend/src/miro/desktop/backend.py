"""Desktop backend: thin wrapper over the agent-desktop CLI (Miro unified).

Sources: C:/dubtool/shared/desktop_backend.py (session/ref state on disk,
CALL_LOG accounting) + D:/JARVIS-Assistant/backend/app/integrations/
agent_desktop.py (closed allowlist, secret-scrubbed env, envelope parse,
headless default).

Each call is one CLI invocation; session/ref state lives on disk under
MIRO_DESKTOP_HOME. No input is issued without the caller first passing
miro.desktop.gate.gate(). The lease inside agent-desktop only serialises
concurrent access; it does not replace the epoch check.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

BIN = os.environ.get(
    "MIRO_AGENT_DESKTOP_BIN",
    os.environ.get(
        "JARVIS_AGENT_DESKTOP_BIN",
        r"C:\nvm4w\nodejs\node_modules\agent-desktop\bin\agent-desktop-win32-x64.exe",
    ),
)
STATE_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "miro-desktop"

ALLOWED_COMMANDS = {
    "status", "permissions", "version",
    "list-windows", "list-apps", "list-displays", "list-surfaces",
    "clipboard-get", "snapshot", "find", "screenshot", "get", "is",
    "click", "type", "set-value", "clear", "focus", "select", "toggle",
    "check", "uncheck", "expand", "collapse", "scroll", "scroll-to",
    "press", "launch", "close-app", "focus-window", "resize-window",
    "move-window", "minimize", "maximize", "restore", "wait",
    "session",
}

CALL_LOG: list = []
_SESSION_ID = None


def set_session(session_id):
    global _SESSION_ID
    _SESSION_ID = session_id


def get_session():
    return _SESSION_ID


def ensure_state_dir(path=None) -> Path:
    target = Path(path) if path else STATE_DIR
    target.mkdir(parents=True, exist_ok=True)
    user = os.environ.get("USERNAME", "")
    if os.name == "nt":
        subprocess.run(
            ["icacls", str(target), "/inheritance:r",
             "/grant:r", f"{user}:(OI)(CI)F",
             "NT AUTHORITY\\SYSTEM:(OI)(CI)F",
             "BUILTIN\\Administrators:(OI)(CI)F"],
            capture_output=True, text=True, timeout=60)
    return target


def scrubbed_env(session_id=None):
    env = dict(os.environ)
    for key in list(env):
        upper = key.upper()
        if any(t in upper for t in ("API_KEY", "SECRET", "TOKEN", "PASSWORD", "COOKIE")):
            del env[key]
    env["AGENT_DESKTOP_HOME"] = str(ensure_state_dir())
    if session_id:
        env["AGENT_DESKTOP_SESSION"] = session_id
    return env


def _cmd_label(args):
    if not args:
        return "?"
    base = args[1] if args[0] == "--headed" and len(args) > 1 else args[0]
    if base == "find" and "--role" in args:
        idx = args.index("--role")
        if idx + 1 < len(args):
            return f"find:{args[idx + 1]}"
    if base == "get" and "--property" in args:
        idx = args.index("--property")
        if idx + 1 < len(args):
            return f"get:{args[idx + 1]}"
    return base


def _ok(payload):
    return isinstance(payload, dict) and payload.get("ok") is True


def run_cli(args, stdin_text=None, use_session=True, timeout=120):
    """Run one agent-desktop command after allowlist check. Returns payload."""
    if args and args[0] == "--headed":
        cmd, rest = args[1], args[2:]
    else:
        cmd, rest = (args[0], args[1:]) if args else ("", [])
    if cmd not in ALLOWED_COMMANDS:
        return {"ok": False, "error": "COMMAND_NOT_ALLOWED", "command": cmd}
    t0 = time.time()
    env = scrubbed_env(_SESSION_ID if use_session else None)
    proc = subprocess.run(
        [BIN] + args, capture_output=True, text=True, timeout=timeout,
        input=stdin_text, env=env)
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {"raw": (proc.stdout or "")[:500]}
    CALL_LOG.append({"cmd": _cmd_label(args), "dur_s": round(time.time() - t0, 3),
                     "ok": _ok(payload)})
    if proc.returncode != 0 and not _ok(payload):
        err = payload.get("error") if isinstance(payload, dict) else None
        return {"ok": False, "error": err or (proc.stderr or "")[:500] or "CLI_FAILED"}
    return payload


def take_call_log():
    calls = list(CALL_LOG)
    del CALL_LOG[:]
    return calls


def session_start(name="miro-act"):
    payload = run_cli(["session", "start", "--name", name],
                      use_session=False)
    if not _ok(payload):
        err = payload.get("error") if isinstance(payload, dict) else None
        return {"ok": False, "error": err or "SESSION_START_FAILED"}
    data = payload.get("data") or {}
    return {"ok": True, "session_id": data.get("session_id")}


def session_end(session_id):
    payload = run_cli(["session", "end", session_id], use_session=False)
    if not _ok(payload):
        err = payload.get("error") if isinstance(payload, dict) else None
        return {"ok": False, "error": err or "SESSION_END_FAILED"}
    return {"ok": True}


def list_windows(app=None):
    args = ["list-windows"]
    if app:
        args += ["--app", app]
    payload = run_cli(args)
    if not _ok(payload):
        err = payload.get("error") if isinstance(payload, dict) else None
        return {"ok": False, "error": err or "LIST_FAILED"}
    return {"ok": True, "windows": payload.get("data")}


def find(window_id, role=None, name=None, native_id=None, value=None):
    args = ["find", "--window-id", str(window_id)]
    if role:
        args += ["--role", role]
    if name:
        args += ["--name", name]
    if native_id:
        args += ["--native-id", native_id]
    if value:
        args += ["--value", value]
    payload = run_cli(args)
    if not _ok(payload):
        err = payload.get("error") if isinstance(payload, dict) else None
        return {"ok": False, "error": err or "FIND_FAILED"}
    data = payload.get("data") or {}
    return {"ok": True, "matches": data.get("matches", []),
            "snapshot_id": data.get("snapshot_id")}


def get_value(ref):
    payload = run_cli(["get", ref, "--property", "value"])
    if not _ok(payload):
        err = payload.get("error") if isinstance(payload, dict) else None
        return {"ok": False, "error": err or "GET_FAILED"}
    data = payload.get("data") or {}
    return {"ok": True, "value": data.get("value")}


def get_states(ref):
    payload = run_cli(["get", ref, "--property", "states"])
    if not _ok(payload):
        err = payload.get("error") if isinstance(payload, dict) else None
        return {"ok": False, "error": err or "GET_STATES_FAILED"}
    val = (payload.get("data") or {}).get("value")
    return {"ok": True, "states": val if isinstance(val, list) else []}


def set_value(ref, text):
    payload = run_cli(["set-value", ref, text])
    if not _ok(payload):
        err = payload.get("error") if isinstance(payload, dict) else None
        code = err.get("code") if isinstance(err, dict) else err
        return {"ok": False, "error": code or "SET_FAILED", "detail": err}
    data = payload.get("data") or {}
    post = data.get("post_state", {}) if isinstance(data, dict) else {}
    return {"ok": True, "value": post.get("value")}


def write(ref, text):
    """Alias cua set_value cho act boundary (desktop_act goi ops.write)."""
    return set_value(ref, text)


def click(ref, headed=False):
    args = (["--headed", "click", ref] if headed else ["click", ref])
    payload = run_cli(args)
    if not _ok(payload):
        err = payload.get("error") if isinstance(payload, dict) else None
        code = err.get("code") if isinstance(err, dict) else err
        return {"ok": False, "error": code or "CLICK_FAILED", "detail": err}
    return {"ok": True}
