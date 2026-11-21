@echo off
REM Miro first-time setup (Windows): backend venv + web node_modules + dep report.
cd /d "%~dp0.."
if not exist apps\backend\.venv (
  python -m venv apps\backend\.venv
  if errorlevel 1 exit /b 1
)
apps\backend\.venv\Scripts\python.exe -m pip install -e apps\backend
if errorlevel 1 exit /b 1
where npm >nul 2>nul
if errorlevel 1 (
  echo Node.js not found - FE and node-youtube will be skipped. Install Node 18+ to enable them.
) else (
  cd apps\web
  if not exist node_modules call npm install --no-audit --no-fund
  cd ..\..
)
python windows\miro.py check
