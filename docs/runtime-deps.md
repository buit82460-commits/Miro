# Miro runtime dependencies (Windows)

Launcher: `windows\miro.py` (`miro.bat` wrapper, `setup.bat` first-time setup).
Ports (override via env; clash-free vs legacy): BE `MIRO_BE_PORT` (8770),
FE `MIRO_FE_PORT` (3100), browser-worker `MIRO_BROWSER_WORKER_PORT` (8771),
media-worker `MIRO_MEDIA_WORKER_PORT` (8772), node-youtube `MIRO_YOUTUBE_PORT` (3457).

## Dependency probe

`miro.py check` reports (no hard-coded `C:\Users\...` or `D:\` paths —
lookup is PATH-first plus `%NVM_HOME%` / `%ProgramFiles%` roots):

| Tool | Required by | Missing behaviour |
|---|---|---|
| Python 3.12 + fastapi + uvicorn | BE, browser-worker, media-worker | `start` refuses; install then re-run |
| Node 18+ + npm | FE (`apps/web` dev), node-youtube | those services are skipped with a note |
| ffmpeg + ffprobe | media-worker render jobs | media-worker skipped; BE still runs |
| `apps/web/node_modules` | FE only | FE skipped until `npm install` in `apps/web` |

Current machine (2026-11-21): Python 3.12.6 + fastapi/uvicorn OK,
Node v24 reachable via nvm shim (not on `where` PATH — launcher checks
`%NVM_HOME%` too), **ffmpeg/ffprobe NOT found**, `apps/web/node_modules` absent.
So today: BE starts; FE/node-youtube/media-worker report "skipped" until their
toolchains are installed. That is by design — partial stack, clear message.

## Independent from Miro vs still needs legacy env

**Runs independently from Miro today (no `C:\dubtool`, no `D:\JARVIS-*` needed):**
- `windows\miro.py` itself — stdlib only (restart budget + taskkill supervision
  re-implemented locally instead of importing legacy modules).
- BE FastAPI sample (`apps/backend/src/miro` + `/health`) — verified below.
- FE scaffold (`apps/web`) — needs only Node/npm, no legacy code.
- `workers/browser|media`, `services/youtube` — interface skeletons only
  (`worker.py`/`service.py` raise `NotImplementedError`); their future
  `server.py` HTTP entrypoints will be Miro-native. No `server.py` exists yet,
  so the launcher correctly skips them for now.

**Still needs the legacy environment (explicit opt-in, never implicit):**
- Full dub/render/STT/TTS pipeline → needs `C:\dubtool` models, voices,
  `.venv`, ffmpeg — set `MIRO_LEGACY_DUBTOOL_DIR` once the merge branch lands.
- Browser automation with real profiles → needs Chrome + Playwright browsers
  from the dubtool/JARVIS setup — set `MIRO_LEGACY_BROWSER_PROFILE`.
- YouTube upload/status → needs `integrations/youtube-agent` OAuth tokens —
  set `MIRO_LEGACY_YOUTUBE_DIR`.
- JARVIS agents/jobs/planner semantics → `D:\JARVIS-Assistant` research repos
  stay read-only references until the corresponding `merge/jarvis-*` branch lands.

Rule: Miro never reads legacy paths unless the matching `MIRO_LEGACY_*` env var
is set. Unset = fully independent sample stack.

## Verification (2026-11-21)

- `python windows\miro.py check` → required deps OK; ffmpeg/ffprobe + node_modules
  reported missing (expected, see table).
- `python windows\miro.py start --only be --no-browser` → BE up at
  `http://127.0.0.1:8770`, `GET /health` → `{"status":"ok"}` (see log excerpt
  in session notes). `stop` shuts it down and removes the manifest.
