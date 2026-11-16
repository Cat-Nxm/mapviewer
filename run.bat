@echo off
rem ===================================================================
rem  mapviewer launcher
rem  Usage:  run.bat firmware.map
rem          run.bat firmware.map -n 30
rem  Purpose: find a real Python, bypass the fake python.exe stub
rem           in C:/Users/<you>/AppData/Local/Microsoft/WindowsApps
rem ===================================================================
setlocal

rem use UTF-8 console so the bars and Chinese render properly
chcp 65001 >nul 2>nul
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

set "PY="

rem 1) official py launcher first
where py >nul 2>nul && set "PY=py"

rem 2) real interpreter in user profile
if not defined PY if exist "%LOCALAPPDATA%\Python\bin\python.exe" set "PY=%LOCALAPPDATA%\Python\bin\python.exe"

rem 3) whatever python is on PATH
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)

if not defined PY (
  echo.
  echo   Python not found.
  echo   Install it from https://www.python.org/downloads/
  echo   and check "Add python.exe to PATH".
  echo.
  exit /b 1
)

"%PY%" "%~dp0mapviewer.py" %*
