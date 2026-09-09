@echo off
chcp 65001 >nul
title Isaac Helper
cd /d "%~dp0"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
set "ISAAC_EXIT=%ERRORLEVEL%"

if not "%ISAAC_EXIT%"=="0" (
    echo.
    echo Startup failed. Check the error message above.
    pause
)

exit /b %ISAAC_EXIT%
