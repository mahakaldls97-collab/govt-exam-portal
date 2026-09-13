@echo off
chcp 65001 >nul
echo ========================================================
echo        SARKARI EXAM HUB - ADMIN PASSWORD RESET TOOL
echo ========================================================
echo.
echo Is tool se aap apna Admin Password turant badal sakte hain.
echo.

set PYTHON_PATH=C:\Program Files\Langflow\resources\python\python.exe
if not exist "%PYTHON_PATH%" (
    set PYTHON_PATH=python
)

"%PYTHON_PATH%" reset_password_cli.py

pause
