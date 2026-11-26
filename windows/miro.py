"""Miro Windows launcher: manages FE / BE / browser-worker / media-worker / node-youtube.

Usage (from C:\\Miro):
    python windows\\miro.py check              # dependency report, exit 1 if required bits missing
    python windows\\miro.py start [--only be] [--no-browser]
    python windows\\miro.py stop
    python windows\\miro.py status

Design notes (deliberately independent from legacy launchers):
- No dependency on C:\\dubtool or D:\\JARVIS-Assistant code. Restart-budget logic
  is re-implemented here in ~20 lines instead of importing legacy modules, so a
  legacy checkout is never required to run Miro.
- No hard-coded user paths: home dir via pathlib, tool lookup via PATH plus
  well-known install roots derived from environment variables. Legacy roots are
  only honoured through explicit MIRO_LEGACY_* env overrides (see docs/runtime-deps.md).
- Every port is configurable via MIRO_* env vars with clash-free defaults that
  differ from the legacy stack (dubtool 7860/3456, JARVIS 8765), so Miro and
  legacy can run side by side during migration.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".miro-runtime"
LOGS_DIR = STATE_DIR / "logs"
MANIFEST = STATE_DIR / "processes.json"
CONTROL = STATE_DIR / "control.json"
BRIDGE_KEY_FILE = STATE_DIR / "bridge-backend-key"


def _bridge_backend_key() -> str:
    """Trusted-parent key management (Slice 02 §8).

    - Env MIRO_BRIDGE_BACKEND_KEY uu tien (van hanh thu cong).
    - Con lai: doc file local BRIDGE_KEY_FILE; chua co -> sinh moi
      (secrets, 128-bit), persist xuong dia, chi launcher + service
      con duoc thua huong qua env. Khong log, khong in ra console.
    - Xoay key cu: xoa file + restart service (launcher sinh key moi).
    """
    env_key = str(os.environ.get("MIRO_BRIDGE_BACKEND_KEY") or "")
    if env_key:
        return env_key
    try:
        saved = BRIDGE_KEY_FILE.read_text(encoding="utf-8").strip()
        if len(saved) >= 16:
            return saved
    except OSError:
        pass
    import secrets as _secrets
    fresh = "miro-" + _secrets.token_hex(16)
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = BRIDGE_KEY_FILE.with_suffix(".tmp")
        tmp.write_text(fresh, encoding="utf-8")
        tmp.replace(BRIDGE_KEY_FILE)
    except OSError:
        pass
    return fresh

SERVICES = ("be", "fe", "browser-worker", "media-worker", "node-youtube", "bridge")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


PORTS = {
    "be": _env_int("MIRO_BE_PORT", 8770),
    "fe": _env_int("MIRO_FE_PORT", 3100),
    "browser-worker": _env_int("MIRO_BROWSER_WORKER_PORT", 8771),
    "media-worker": _env_int("MIRO_MEDIA_WORKER_PORT", 8772),
    "node-youtube": _env_int("MIRO_YOUTUBE_PORT", 3457),
    "bridge": _env_int("MIRO_BRIDGE_PORT", 18767),
}

HEALTH_PATHS = {
    "be": "/health",
    "fe": "/",
    "browser-worker": "/health",
    "media-worker": "/health",
    "node-youtube": "/health",
    "bridge": "/health",
}


class RestartBudget:
    """Bounded crash-restart decisions (stdlib only; no legacy imports).

    L2: history persist xuong STATE_DIR (restart-budget-<name>.json) de
    crash-loop xuyen-launcher van bi chan — launcher restart khong reset budget.
    Doc chiu duoc file hong (bo qua, bat dau lich su moi).
    """

    def __init__(self, maximum: int = 3, window: float = 600.0,
                 name: str = "worker", state_dir=None) -> None:
        self.maximum = maximum
        self.window = window
        self.name = name
        self.state_dir = Path(state_dir) if state_dir else STATE_DIR
        self.history: deque[float] = deque()
        self._load()

    def _file(self) -> Path:
        safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in self.name)
        return self.state_dir / f"restart-budget-{safe}.json"

    def _load(self) -> None:
        try:
            raw = self._file().read_text(encoding="utf-8-sig")
        except OSError:
            return
        try:
            data = json.loads(raw)
        except ValueError:
            return
        if isinstance(data, list):
            now_wall = time.time()
            self.history = deque(float(t) for t in data
                                 if isinstance(t, (int, float))
                                 and 0 < now_wall - float(t) < self.window + 3600)

    def _save(self) -> None:
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            tmp = self._file().with_suffix(".tmp")
            tmp.write_text(json.dumps(list(self.history)), encoding="utf-8")
            tmp.replace(self._file())
        except OSError:
            pass

    def next_delay(self) -> float:
        now_mono = time.monotonic()
        now_wall = time.time()
        while self.history and now_wall - self.history[0] >= self.window:
            self.history.popleft()
        if len(self.history) >= self.maximum:
            raise RuntimeError("WORKER_RESTART_EXHAUSTED: fix the worker before restarting")
        self.history.append(now_wall)
        self._save()
        _ = now_mono
        return min(30.0, 2.0 ** (len(self.history) - 1))


def _control_stop_requested() -> bool:
    """L1: stop co hieu luc ngay ca giua backoff — sleep theo nhip ngan 0.2s,
    moi nhip kiem tra CONTROL thay vi sleep block ca delay."""
    if not CONTROL.exists():
        return False
    try:
        return json.loads(CONTROL.read_text(encoding="utf-8")).get("action") == "stop"
    except (OSError, ValueError):
        return False


def _sleep_interruptible(seconds: float) -> bool:
    """Sleep co the bi stop cat ngang. Tra True neu bi stop giua chung."""
    deadline = time.monotonic() + max(float(seconds), 0.0)
    while time.monotonic() < deadline:
        if _control_stop_requested():
            return True
        time.sleep(min(0.2, max(deadline - time.monotonic(), 0.0)))
    return _control_stop_requested()


def terminate_owned(proc: subprocess.Popen, timeout: float = 15) -> None:
    """Stop a still-live Popen child. Only raises if the process survives kill."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=15,
        )
    else:
        proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
    if proc.poll() is None:
        raise RuntimeError("OWNED_WORKER_STOP_FAILED")


def _which_or_known(name: str, *known: Path) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for candidate in known:
        if candidate.is_file():
            return str(candidate)
    return None


def find_node() -> str | None:
    """Resolve node without hard-coding a user profile: PATH first, then
    well-known install roots derived from env (nvm4w, Program Files)."""
    candidates: list[Path] = []
    for root_env in ("NVM_HOME", "NVM_SYMLINK", "ProgramFiles", "ProgramW6432"):
        root = os.environ.get(root_env)
        if root:
            candidates.append(Path(root) / "nodejs" / "node.exe")
            candidates.append(Path(root) / "node.exe")
    pf86 = os.environ.get("ProgramFiles(x86)")
    if pf86:
        candidates.append(Path(pf86) / "nodejs" / "node.exe")
    return _which_or_known("node", *candidates)


def check_deps() -> dict:
    """Probe required/optional runtime dependencies. Never raises for missing optional tools."""
    node = find_node()
    report = {
        "python": sys.executable,
        "python_version": sys.version.split()[0],
        "fastapi": _importable("fastapi"),
        "uvicorn": _importable("uvicorn"),
        "node": node,
        "npm": shutil.which("npm"),
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
    }
    return report


def _importable(module: str) -> str | None:
    try:
        mod = __import__(module)
        return getattr(mod, "__version__", "installed")
    except ImportError:
        return None


def print_check() -> bool:
    deps = check_deps()
    print("Miro runtime dependencies (required: python/fastapi/uvicorn):")
    ok = True
    for key in ("python", "python_version", "fastapi", "uvicorn"):
        print(f"  [OK] {key}: {deps[key]}" if deps[key] else f"  [MISSING] {key}")
        if not deps[key]:
            ok = False
    for key in ("node", "npm", "ffmpeg", "ffprobe"):
        print(f"  [{'OK' if deps[key] else 'OPTIONAL-MISSING'}] {key}: {deps[key] or 'not found'}")
    if not deps["ffmpeg"] or not deps["ffprobe"]:
        print("  note: ffmpeg/ffprobe needed only for media-worker render jobs.")
    if not deps["node"]:
        print("  note: node needed only for fe (Next.js dev) and node-youtube service.")
    if not (ROOT / "apps" / "web" / "node_modules").is_dir():
        print("  note: apps/web/node_modules missing — run `npm install` in apps/web for FE.")
    return ok


def service_command(name: str) -> tuple[list[str], Path, dict] | None:
    """Return (cmd, cwd, extra_env) or None when the service is not scaffolded yet."""
    env: dict = {}
    if name == "be":
        app_dir = ROOT / "apps" / "backend"
        if not (app_dir / "src" / "miro" / "main.py").is_file():
            return None
        env["PYTHONPATH"] = str(app_dir / "src") + os.pathsep + env.get("PYTHONPATH", "")
        # Production wiring: BE nhan backend-key tu launcher (trusted parent),
        # khong doc truc tiep tu user, khong hardcode. TaskService truyen tiep
        # vao bridge_transport khi tao production request.
        env["MIRO_BRIDGE_BACKEND_KEY"] = _bridge_backend_key()
        return (
            [sys.executable, "-m", "uvicorn", "miro.main:app",
             "--host", "127.0.0.1", "--port", str(PORTS["be"])],
            app_dir, env,
        )
    if name == "fe":
        web_dir = ROOT / "apps" / "web"
        if not (web_dir / "package.json").is_file():
            return None
        node = find_node()
        npm = shutil.which("npm")
        if not node or not npm or not (web_dir / "node_modules").is_dir():
            return None
        env["PORT"] = str(PORTS["fe"])
        # Standalone production UI (Slice 04): FE proxy /api/tasks/* sang BE
        # that qua rewrite. Ton trong env co san; mac dinh tro ve BE launcher.
        env["NEXT_PUBLIC_API_BASE"] = os.environ.get(
            "NEXT_PUBLIC_API_BASE",
            f"http://127.0.0.1:{PORTS['be']}")
        return ([npm, "run", "dev", "--", "-p", str(PORTS["fe"])], web_dir, env)
    if name == "browser-worker":
        entry = ROOT / "workers" / "browser" / "server.py"
        if not entry.is_file():
            return None
        return ([sys.executable, str(entry), "--port", str(PORTS["browser-worker"])],
                entry.parent, env)
    if name == "media-worker":
        entry = ROOT / "workers" / "media" / "server.py"
        if not entry.is_file():
            return None
        return ([sys.executable, str(entry), "--port", str(PORTS["media-worker"])],
                entry.parent, env)
    if name == "node-youtube":
        entry = ROOT / "services" / "youtube" / "server.js"
        if not entry.is_file():
            return None
        node = find_node()
        if not node:
            return None
        env["MIRO_YOUTUBE_PORT"] = str(PORTS["node-youtube"])
        return ([node, str(entry)], entry.parent, env)
    if name == "bridge":
        entry = ROOT / "experiments" / "extension-bridge" / "bridge" / "server.py"
        if not entry.is_file():
            return None
        # Backend role auth: launcher (trusted parent) cap key cho bridge
        # process. Khong hard-code key; tu sinh + persist neu chua co.
        env["MIRO_BRIDGE_BACKEND_KEY"] = _bridge_backend_key()
        return ([sys.executable, str(entry), str(PORTS["bridge"])],
                entry.parent, env)
    raise ValueError(f"unknown service: {name}")


def wait_ready(url: str, proc: subprocess.Popen, seconds: int = 90) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"service exited with code {proc.returncode}; see .miro-runtime/logs/")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    raise RuntimeError(f"service startup timed out: {url}")


def _port_in_use(port: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _write_manifest(specs: list, processes: list) -> None:
    MANIFEST.write_text(json.dumps({
        "root": str(ROOT),
        "launcher": os.getpid(),
        "services": {spec[0]: proc.pid for spec, proc in zip(specs, processes)},
        "ports": {spec[0]: PORTS[spec[0]] for spec in specs},
    }, indent=2), encoding="utf-8")


def cmd_start(only: list[str] | None = None, open_browser: bool = True) -> int:
    deps_ok = print_check()
    if not deps_ok:
        print("Missing required dependencies — install fastapi/uvicorn first.", file=sys.stderr)
        return 1
    wanted = only or list(SERVICES)
    specs: list[tuple] = []
    for name in wanted:
        built = service_command(name)
        if built is None:
            print(f"skip {name}: not scaffolded or toolchain missing (see check above).")
            continue
        cmd, cwd, extra = built
        port = PORTS[name]
        if _port_in_use(port):
            print(f"Port {port} ({name}) is busy — close the old instance or set MIRO_*_PORT.", file=sys.stderr)
            return 1
        specs.append((name, cmd, cwd, extra))
    if not specs:
        print("Nothing to start: no scaffolded services with satisfied toolchains.")
        return 0
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    if CONTROL.exists():
        CONTROL.unlink()
    base_env = os.environ.copy()
    base_env["PYTHONUTF8"] = "1"
    processes: list[subprocess.Popen] = []
    handles = []
    budgets = [RestartBudget(name=name, state_dir=STATE_DIR)
               for name, _cmd, _cwd, _extra in specs]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        for name, cmd, cwd, extra in specs:
            merged = dict(base_env)
            merged.update(extra)
            log = (LOGS_DIR / f"{name}.log").open("w", encoding="utf-8")
            handles.append(log)
            processes.append(subprocess.Popen(cmd, cwd=str(cwd), env=merged,
                                              stdout=log, stderr=subprocess.STDOUT,
                                              creationflags=flags))
        _write_manifest(specs, processes)
        for (name, _cmd, _cwd, _extra), proc in zip(specs, processes):
            wait_ready(f"http://127.0.0.1:{PORTS[name]}{HEALTH_PATHS[name]}", proc)
            print(f"  [up] {name} -> http://127.0.0.1:{PORTS[name]}")
        names = [s[0] for s in specs]
        print(f"Miro up ({', '.join(names)}). Ctrl+C to stop all.", flush=True)
        if open_browser and "be" in names:
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{PORTS['be']}/docs")
        while True:
            if CONTROL.exists():
                try:
                    if json.loads(CONTROL.read_text(encoding="utf-8")).get("action") == "stop":
                        return 0
                except (OSError, ValueError):
                    pass
            for index, proc in enumerate(processes):
                if proc.poll() is None:
                    continue
                name, cmd, cwd, extra = specs[index]
                delay = budgets[index].next_delay()
                print(f"{name} stopped ({proc.returncode}); restarting in {delay:.0f}s", flush=True)
                if _sleep_interruptible(delay):
                    return 0
                if CONTROL.exists():
                    return 0
                merged = dict(base_env)
                merged.update(extra)
                processes[index] = subprocess.Popen(cmd, cwd=str(cwd), env=merged,
                                                    stdout=handles[index],
                                                    stderr=subprocess.STDOUT,
                                                    creationflags=flags)
                _write_manifest(specs, processes)
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for proc in processes:
            if proc.poll() is None:
                terminate_owned(proc)
        for proc in processes:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        for log in handles:
            log.close()
        for state in (CONTROL, MANIFEST):
            if state.exists():
                state.unlink()
    return 0


def cmd_stop() -> int:
    if not MANIFEST.exists():
        print("No Miro launcher running (no manifest).")
        return 1
    record = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if record.get("root") != str(ROOT):
        print("Manifest belongs to another workspace; refusing.", file=sys.stderr)
        return 1
    CONTROL.write_text(json.dumps({"action": "stop", "at": time.time()}), encoding="utf-8")
    print("Stop requested — the launcher will shut services down.")
    return 0


def cmd_status() -> int:
    if not MANIFEST.exists():
        print("Miro launcher: not running.")
        return 0
    try:
        import psutil as _psutil
    except ImportError:
        _psutil = None
    record = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for name, pid in record.get("services", {}).items():
        if _psutil is not None:
            alive = _psutil.pid_exists(pid)
        else:
            alive = _pid_alive(pid)
        port = (record.get("ports") or {}).get(name, PORTS.get(name))
        health = "unknown"
        if port:
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}{HEALTH_PATHS.get(name, '/health')}",
                        timeout=2) as r:
                    health = f"http-{r.status}"
            except (OSError, ValueError):
                health = "down"
        print(f"  {name}: pid={pid} alive={alive} health={health}")
    return 0


def _pid_alive(pid: int) -> bool:
    # NOTE: os.kill(pid, 0) is NOT a read-only probe on Windows (it can signal
    # the target), so use OpenProcess there. POSIX keeps the classic kill-0 probe.
    if os.name == "nt":
        try:
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    action = argv[1]
    if action == "check":
        return 0 if print_check() else 1
    if action == "start":
        only = None
        if "--only" in argv:
            only = argv[argv.index("--only") + 1].split(",")
            unknown = [n for n in only if n not in SERVICES]
            if unknown:
                print(f"Unknown service(s): {unknown}. Choose from {SERVICES}.", file=sys.stderr)
                return 1
        return cmd_start(only, open_browser="--no-browser" not in argv)
    if action == "stop":
        return cmd_stop()
    if action == "status":
        return cmd_status()
    print(f"Unknown command: {action}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        raise SystemExit(main(sys.argv))
    except Exception as exc:  # keep the failure one line, like dubtool's run.py
        print(f"Launcher error: {exc}", file=sys.stderr)
        raise SystemExit(1)
