@echo off
REM Mo Chrome dung Profile 20 + remote debugging cho Miro live-read.
REM Login giu nguyen, khong mat, khong an danh.
REM Luu y: dong het Chrome truoc khi chay file nay.
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data" --profile-directory="Profile 20" about:blank
