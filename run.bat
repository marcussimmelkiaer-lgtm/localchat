@echo off
setlocal
cd /d "%~dp0"
title LocalChat

REM LocalChat launcher for Windows. Double-click to run. First run sets up
REM everything (Python env, dependencies, config, model download); later runs
REM just start the app. After a `git pull`, changed dependencies are installed
REM automatically.

REM --- First-time setup: virtual environment ---
if exist "venv\Scripts\python.exe" goto :deps

call :find_python
if not defined PY (
  echo LocalChat needs Python 3.11 or newer, and none was found.
  echo.
  choice /c YN /m "Install Python 3.12 now (via winget, no admin needed)"
  if errorlevel 2 goto :no_python
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  call :find_python
)
if not defined PY goto :no_python

echo First-time setup: creating virtual environment...
%PY% -m venv venv
if errorlevel 1 (
  echo.
  echo Failed to create the virtual environment with %PY%.
  pause
  exit /b 1
)

REM --- Dependencies: install on first run, and again whenever requirements.txt
REM     changes (e.g. after a git pull). venv\.requirements.installed is a copy
REM     of the requirements.txt that was last installed successfully.
:deps
fc /b requirements.txt venv\.requirements.installed >nul 2>&1
if not errorlevel 1 goto :config
echo Installing dependencies ^(this can take a few minutes^)...
"venv\Scripts\python.exe" -m pip install --upgrade pip
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Dependency installation failed.
  pause
  exit /b 1
)
copy /y requirements.txt venv\.requirements.installed >nul

REM --- Config: create from template on first run ---
:config
if not exist "config.toml" (
  echo Creating config.toml from template...
  copy /y config.example.toml config.toml >nul
)

REM --- Model: download the default model on first run if none is configured ---
REM No-op once a valid model_path is set; sets it automatically after download.
"venv\Scripts\python.exe" -m backend.fetch_model

REM --- Launch the app (frameless native window) ---
REM pythonw = no console window: the setup above needs this terminal, the app
REM doesn't. `start` detaches it so this window closes. Output goes to
REM LocalChat.log (see backend/main.py _ensure_std_streams). For a console
REM with live logs, run:  venv\Scripts\python.exe -m backend.main
start "" "venv\Scripts\pythonw.exe" -m backend.main
exit /b 0

:no_python
echo.
echo Install Python 3.11+ from https://www.python.org/downloads/ and run this again.
pause
exit /b 1

REM Sets PY to a Python 3.11+ command, or leaves it undefined. config.py and
REM fetch_model.py import the stdlib tomllib, which only exists on 3.11+.
REM Also probes the per-user install folder directly, since a Python that winget
REM just installed isn't on this window's PATH yet.
:find_python
set "PY="
for %%V in (3.14 3.13 3.12 3.11) do (
  if not defined PY py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
)
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python"
)
for %%V in (314 313 312 311) do (
  if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
)
exit /b 0
