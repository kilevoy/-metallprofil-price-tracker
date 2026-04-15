@echo off
setlocal EnableExtensions

chcp 65001 >nul
cd /d "%~dp0"

set "PY_CMD="
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 set "PY_CMD=python"

if not defined PY_CMD (
  where py >nul 2>nul
  if %ERRORLEVEL% EQU 0 set "PY_CMD=py -3"
)

if not defined PY_CMD (
  echo [ERROR] Python not found in PATH.
  exit /b 1
)

echo [INFO] Starting local upload server on http://127.0.0.1:8765
%PY_CMD% scripts\local_upload_server.py

