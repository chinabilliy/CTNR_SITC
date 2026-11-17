@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
if "%PORT%"=="" set PORT=8888

set "PY="

rem 1) Explicit interpreter via PYTHON env var
if not "%PYTHON%"=="" (
  "%PYTHON%" -c "import sys" >nul 2>&1
  if not errorlevel 1 set "PY=%PYTHON%"
)

rem 2) Windows py launcher
if not defined PY (
  py -3 -c "import sys" >nul 2>&1
  if not errorlevel 1 set "PY=py -3"
)

rem 3) python on PATH, skipping the Microsoft Store stub
if not defined PY (
  for /f "delims=" %%i in ('where python 2^>nul') do (
    if not defined PY (
      echo %%i | findstr /i "WindowsApps" >nul
      if errorlevel 1 (
        "%%i" -c "import sys" >nul 2>&1
        if not errorlevel 1 set "PY=%%i"
      )
    )
  )
)

rem 4) Common install locations
if not defined PY (
  for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Program Files\Python313\python.exe"
    "C:\Program Files\Python312\python.exe"
    "C:\Program Files\Python311\python.exe"
    "%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
  ) do (
    if not defined PY (
      if exist %%p (
        %%p -c "import sys" >nul 2>&1
        if not errorlevel 1 set "PY=%%p"
      )
    )
  )
)

if not defined PY (
  echo.
  echo ============================================================
  echo  ERROR: Python 3.9+ was not found on this computer.
  echo.
  echo  1^) Download Python from: https://www.python.org/downloads/
  echo  2^) During setup, tick "Add python.exe to PATH"
  echo  3^) Close this window and run start.bat again
  echo ============================================================
  echo.
  pause
  exit /b 1
)

echo Using Python: %PY%
echo [1/2] Checking dependencies...
%PY% -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo WARN: dependency install failed ^(no network?^).
  echo       Run manually: %PY% -m pip install flask waitress openpyxl python-docx
)

echo [2/2] Starting server on http://0.0.0.0:%PORT%
echo        Open http://localhost:%PORT% or http://THIS-PC-IP:%PORT%
echo        Press Ctrl+C to stop.
%PY% run.py --serve --port=%PORT%
pause
