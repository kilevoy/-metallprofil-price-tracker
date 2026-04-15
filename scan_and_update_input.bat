@echo off
setlocal EnableExtensions

chcp 65001 >nul

set "REPO_DIR=%~dp0"
set "INPUT_DIR=%REPO_DIR%input"

if "%~1"=="" (
  set "SOURCE_DIR=%USERPROFILE%\Downloads"
) else (
  set "SOURCE_DIR=%~1"
)

echo [INFO] Repository: "%REPO_DIR%"
echo [INFO] Input folder: "%INPUT_DIR%"
echo [INFO] Source folder: "%SOURCE_DIR%"

if not exist "%INPUT_DIR%" (
  echo [ERROR] Folder not found: "%INPUT_DIR%"
  exit /b 1
)

if not exist "%SOURCE_DIR%" (
  echo [ERROR] Source folder not found: "%SOURCE_DIR%"
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$src=$env:SOURCE_DIR; $dst=$env:INPUT_DIR; $copied=0; " ^
  "Get-ChildItem -LiteralPath $src -Filter *.pdf -File -ErrorAction SilentlyContinue | ForEach-Object { " ^
  "  $target=Join-Path $dst $_.Name; " ^
  "  if(-not (Test-Path -LiteralPath $target)) { Copy-Item -LiteralPath $_.FullName -Destination $target; $copied++; Write-Host ('[ADD] ' + $_.Name) } " ^
  "}; " ^
  "if($copied -eq 0){ Write-Host '[INFO] No new PDF files found.' } else { Write-Host ('[INFO] Copied ' + $copied + ' new PDF file(s).') }"
if %ERRORLEVEL% NEQ 0 (
  echo [ERROR] Failed while scanning/copying PDF files.
  exit /b 1
)

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

echo [INFO] Running parser...
cd /d "%REPO_DIR%"
%PY_CMD% scripts\update_sandwich_panels.py
if %ERRORLEVEL% NEQ 0 (
  echo [ERROR] Parser failed.
  exit /b 1
)

echo [DONE] Updated:
echo        data\sandwich-panels.json
echo        site\index.html
exit /b 0
