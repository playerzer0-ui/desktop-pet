@echo off
rem Sets up the desktop pet: Python, its packages, llama-server and the model (see setup.ps1).
rem Double-click it, or run it from a terminal. Safe to run again.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
pause
