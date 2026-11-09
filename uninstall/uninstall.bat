@echo off
rem Uninstall.bat, in the game's folder (build.ps1 puts it there): removes Desktop Pet from this computer.
rem   1. the game: this folder
rem   2. everything it saved: %LOCALAPPDATA%\DesktopPet (the characters' saves and memories, logs, the prompt cache,
rem      and the AI model it downloaded on its first launch, several GB). See config.py.
rem It asks first, stops the game if it's running, and only ever deletes a folder that has DesktopPet.exe in it, so
rem a copy run from somewhere else (the Desktop, say) can't delete the wrong folder.
setlocal
title Uninstall Desktop Pet
set "GAME=%~dp0"
set "GAME=%GAME:~0,-1%"
set "DATA=%LOCALAPPDATA%\DesktopPet"

if not exist "%GAME%\DesktopPet.exe" goto not_the_game
if not exist "%GAME%\_internal\" goto not_the_game

echo.
echo   This removes Desktop Pet from your computer:
echo.
echo     - the game:      %GAME%
if exist "%DATA%\" echo     - what it saved: %DATA%
if exist "%DATA%\" echo       (the characters' memories of you, your trust with them, and the AI model it downloaded)
echo.
echo   This can't be undone.
echo.
set "ANSWER="
set /p "ANSWER=  Type Y and press Enter to uninstall (just Enter cancels): "
if /i not "%ANSWER%"=="Y" goto cancelled

echo.
echo   Closing Desktop Pet if it's running...
rem (only programs from this folder: the game and its llama-server, not another llama-server of yours)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Process | Where-Object { $_.Path -and $_.Path.StartsWith($env:GAME + '\', 'OrdinalIgnoreCase') } | Stop-Process -Force -ErrorAction SilentlyContinue"
rem (a moment for Windows to let go of their files)
ping -n 3 127.0.0.1 >nul

cd /d "%TEMP%"
if exist "%DATA%\" (
    echo   Removing what it saved...
    rmdir /s /q "%DATA%"
)
if exist "%DATA%\" goto data_stuck

echo   Removing the game...
rem (everything but this file first, so a file Windows still holds shows up here; this file goes last, below)
rmdir /s /q "%GAME%\_internal"
if exist "%GAME%\_internal\" goto game_stuck
for %%F in ("%GAME%\*") do if /i not "%%~nxF"=="%~nx0" del /f /q "%%F"
for /d %%D in ("%GAME%\*") do rmdir /s /q "%%D"

echo.
echo   Desktop Pet has been removed. Thanks for playing!
echo.
pause
rem (this file and its folder: "(goto)" ends the script first, so Windows isn't still reading a file that's gone)
(goto) 2>nul & rmdir /s /q "%GAME%"

:cancelled
echo.
echo   Nothing was removed.
echo.
pause
exit /b 0

:not_the_game
echo.
echo   This uninstaller only works from inside the Desktop Pet folder (next to DesktopPet.exe).
echo   Nothing was removed.
echo.
pause
exit /b 1

:data_stuck
echo.
echo   Couldn't remove %DATA%
echo   Close Desktop Pet if it's still open, then run this again. Nothing else was removed.
echo.
pause
exit /b 1

:game_stuck
echo.
echo   Its saved data is gone, but some of the game's files are still in use.
echo   Close Desktop Pet if it's still open (or restart your computer), then run this again.
echo.
pause
exit /b 1
