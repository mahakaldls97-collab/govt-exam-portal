@echo off
title Sarkari Exam Portal 2026 - Server Launcher
cd /d "%~dp0"
echo ==========================================================
echo        STARTING GOVERNMENT EXAM INFORMATION PORTAL
echo ==========================================================
echo.
echo Website will run at: http://127.0.0.1:8000/
echo Secret Admin Panel: http://127.0.0.1:8000/portal-boss-secure-2026/login
echo Admin Login:        admin / admin@examportal2026
echo.
"C:\Program Files\Langflow\resources\python\python.exe" run_server.py
pause
