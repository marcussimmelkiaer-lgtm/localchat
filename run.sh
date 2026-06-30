#!/usr/bin/env bash
# LocalChat launcher for macOS / Linux. Mirrors run.bat.
set -e
cd "$(dirname "$0")"

# --- First-time setup: virtual environment + dependencies ---
if [ ! -x "venv/bin/python" ]; then
  echo "First-time setup: creating virtual environment..."

  # Require Python 3.11+: config.py and fetch_model.py import the stdlib
  # `tomllib`, which only exists on 3.11+. Without this guard a 3.9/3.10 Python
  # installs deps fine, then the app crashes at launch with an opaque
  # "ModuleNotFoundError: No module named 'tomllib'". Fail fast instead.
  if ! command -v python3 >/dev/null 2>&1; then
    echo
    echo "python3 was not found. Install Python 3.11+ (e.g. 'brew install python@3.12')."
    exit 1
  fi
  if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo
    echo "LocalChat needs Python 3.11+ (found $(python3 -V 2>&1)). The app uses the"
    echo "standard-library 'tomllib', which was added in 3.11. Install a newer Python"
    echo "(e.g. 'brew install python@3.12') and re-run."
    exit 1
  fi

  if ! python3 -m venv venv; then
    echo
    echo "Failed to create the virtual environment. Is Python 3.11+ installed?"
    exit 1
  fi
  # On Apple Silicon, nobodywho only ships an arm64 wheel (no x86_64 wheel, no
  # sdist). If python3 was an Intel/Rosetta build, the venv is x86_64 and the
  # install fails with an opaque "no matching distribution" resolver error.
  # Catch that here with an actionable message instead.
  if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
    venv_arch="$(venv/bin/python -c 'import platform; print(platform.machine())')"
    if [ "$venv_arch" != "arm64" ]; then
      echo
      echo "Your venv Python is '$venv_arch', but this is an Apple Silicon Mac and"
      echo "nobodywho only ships an arm64 macOS wheel. You are likely using an"
      echo "Intel/Rosetta python3. Install an Apple Silicon Python (e.g."
      echo "'brew install python@3.12' on arm64 Homebrew, or python.org's universal2"
      echo "build) and re-run, or force arm64 with:  arch -arm64 ./run.sh"
      rm -rf venv
      exit 1
    fi
  fi

  echo "Installing dependencies (this can take a few minutes the first time)..."
  if ! venv/bin/python -m pip install --upgrade pip; then
    echo
    echo "Failed to upgrade pip."
    exit 1
  fi
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
