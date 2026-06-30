@echo off
setlocal
cd /d "%~dp0"

REM --- First-time setup: virtual environment + dependencies ---
if not exist "venv\Scripts\python.exe" (
  echo First-time setup: creating virtual environment...
  py -3 -m venv venv
  if errorlevel 1 (
    echo.
    echo Failed to create the virtual environment. Is Python 3.10+ installed?
    pause
    exit /b 1
  )
  echo Installing dependencies ^(this can take a few minutes the first time^)...
  "venv\Scripts\python.exe" -m pip install --upgrade pip
  "venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo Dependency installation failed.
    pause
    exit /b 1
  )
)

REM --- Config: create from template on first run ---
if not exist "config.toml" (
  echo Creating config.toml from template - edit it and set model_path.
  copy /y config.example.toml config.toml >nul
)

REM --- Launch the app (frameless native window) ---
"venv\Scripts\python.exe" -m backend.main
