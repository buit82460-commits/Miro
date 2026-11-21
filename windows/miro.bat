@echo off
REM Miro Windows launcher. Usage: miro.bat [check|start|stop|status] [--only be,fe,...] [--no-browser]
cd /d "%~dp0.."
python "%~dp0miro.py" %*
if errorlevel 1 pause
