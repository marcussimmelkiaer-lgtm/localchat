@echo off
setlocal
cd /d "%~dp0"
title LocalChat

REM LocalChat launcher for Windows. Double-click to run.
REM
REM The first run downloads everything it needs INTO THIS FOLDER: uv and a
REM private Python in .uv\, the app's packages in venv\ (uv's download cache
REM stays in %LOCALAPPDATA%\uv: its short path keeps packages that build from
REM source under Windows' 260-character path limit). Nothing is installed
REM system-wide and no admin rights are needed; deleting the folder removes
REM LocalChat (downloaded models stay in %LOCALAPPDATA%\nobodywho for reuse).
REM Later runs skip straight to starting the app.

set "UV_DIR=%~dp0.uv"
set "UV=%UV_DIR%\uv.exe"
set "UV_PYTHON_INSTALL_DIR=%UV_DIR%\python"
REM Always use uv's own Python, never whatever happens to be on the machine.
set "UV_PYTHON_PREFERENCE=only-managed"

REM --- uv: a single-file tool that downloads Python and installs packages ---
if exist "%UV%" goto :venv
echo First-time setup: downloading the Python installer (uv)...
set "UV_INSTALL_DIR=%UV_DIR%"
set "UV_NO_MODIFY_PATH=1"
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
if not exist "%UV%" goto :fail
attrib +h "%UV_DIR%" >nul 2>&1

REM --- Python + virtual environment ---
:venv
if exist "venv\Scripts\python.exe" goto :deps
echo First-time setup: downloading Python...
"%UV%" venv venv --python 3.12 --seed
if errorlevel 1 goto :fail

REM --- Packages: install on first run, and again whenever requirements.txt
REM     changes. venv\.requirements.installed is a copy of the requirements.txt
REM     that was last installed successfully.
:deps
fc /b requirements.txt venv\.requirements.installed >nul 2>&1
if not errorlevel 1 goto :config
echo Installing packages, this can take a few minutes...
"%UV%" pip install --python venv\Scripts\python.exe -r requirements.txt
if errorlevel 1 goto :fail
copy /y requirements.txt venv\.requirements.installed >nul

REM --- Config: create from template on first run ---
:config
if not exist "config.toml" copy /y config.example.toml config.toml >nul

REM --- Model: use a .gguf next to this file, else download the default once ---
"venv\Scripts\python.exe" -m backend.fetch_model

REM --- Launch the app ---
REM pythonw = no console window; `start` detaches it so this window closes.
REM Output goes to LocalChat.log. For live logs run:
REM   venv\Scripts\python.exe -m backend.main
start "" "venv\Scripts\pythonw.exe" -m backend.main
exit /b 0

:fail
echo.
echo Setup did not finish - see the messages above. Check the internet
echo connection, then double-click "Start LocalChat.bat" again.
if not defined CI pause
exit /b 1
