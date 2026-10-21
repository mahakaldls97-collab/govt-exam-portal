@echo off
title Sarkari Exam Portal 2026 - Server Launcher
cd /d "%~dp0"
echo ==========================================================
echo        STARTING GOVERNMENT EXAM INFORMATION PORTAL
echo ==========================================================
echo.
echo Public Website:     http://127.0.0.1:8000/
echo Secret Admin Panel: http://127.0.0.1:8000/portal-boss-secure-2026/login
echo Admin Username:     admin
echo Admin Password:     admin@examportal2026
echo ==========================================================
echo.
echo Opening browser in 2 seconds...
start http://127.0.0.1:8000/
"C:\Users\dlsma\AppData\Local\Programs\Python\Python312\python.exe" run_server.py
if errorlevel 1 (
    python run_server.py
)
pause
