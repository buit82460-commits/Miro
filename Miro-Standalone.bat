@echo off
REM Miro Standalone: 1 cham mo BE + Bridge + FE (khong browser).
REM Launcher tu mo UI sau khi dich vu san sang. Giu cua so Chrome cua user.
cd /d "%~dp0"
python windows\miro.py start --only be,bridge,fe
if errorlevel 1 pause
