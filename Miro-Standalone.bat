@echo off
REM Miro Standalone: 1 cham mo BE + Bridge (khong browser).
REM FE chay rieng khi can UI (xem README). Giu cua so Chrome cua user.
cd /d "%~dp0"
python windows\miro.py start --only be,bridge --no-browser
if errorlevel 1 pause
