@echo off
rem Starts the desktop pet with the project's own Python. Run setup.bat once first.
rem Another character: start.bat mira
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo The pet isn't set up yet: run setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py %*
if errorlevel 1 pause
