@echo off
:: Simple launcher: run main.py (use pythonw if available to avoid console)
cd /d "%~dp0"
where pythonw >nul 2>&1
if %errorlevel%==0 (
    start "" pythonw "%~dp0main.py"
) else (
    start "" python "%~dp0main.py"
)
exit /b 0
