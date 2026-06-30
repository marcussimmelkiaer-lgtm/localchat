#!/usr/bin/env bash
# LocalChat launcher for macOS / Linux. Mirrors run.bat.
set -e
cd "$(dirname "$0")"

# --- First-time setup: virtual environment + dependencies ---
if [ ! -x "venv/bin/python" ]; then
  echo "First-time setup: creating virtual environment..."
  if ! python3 -m venv venv; then
    echo
    echo "Failed to create the virtual environment. Is Python 3.10+ installed?"
    exit 1
  fi
  echo "Installing dependencies (this can take a few minutes the first time)..."
  venv/bin/python -m pip install --upgrade pip
  if ! venv/bin/python -m pip install -r requirements.txt; then
    echo
    echo "Dependency installation failed."
    exit 1
  fi
fi

# --- Config: create from template on first run ---
if [ ! -f "config.toml" ]; then
  echo "Creating config.toml from template..."
  cp config.example.toml config.toml
fi

# --- Model: download the default model on first run if none is configured ---
# No-op once a valid model_path is set; sets it automatically after download.
venv/bin/python -m backend.fetch_model || true

# --- Launch the app (frameless native window) ---
exec venv/bin/python -m backend.main
