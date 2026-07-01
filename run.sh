#!/usr/bin/env bash
# LocalChat launcher for macOS / Linux. Mirrors run.bat.
set -e
cd "$(dirname "$0")"

# Find a Python 3.11+ interpreter. config.py / fetch_model.py import the stdlib
# `tomllib` (added in 3.11); without a new-enough Python the app installs deps
# fine then crashes at launch with an opaque "No module named 'tomllib'".
# macOS ships /usr/bin/python3 = 3.9 (Apple's), and Homebrew installs VERSIONED
# names like python3.12 without always creating an unversioned `python3` ahead of
# Apple's on PATH — so probe specific versions first, then fall back to python3.
find_python() {
  local c
  for c in python3.14 python3.13 python3.12 python3.11 python3 python; do
    if command -v "$c" >/dev/null 2>&1 \
       && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
      command -v "$c"
      return 0
    fi
  done
  return 1
}

# --- First-time setup: virtual environment + dependencies ---
if [ ! -x "venv/bin/python" ]; then
  echo "First-time setup: creating virtual environment..."

  PYTHON="$(find_python || true)"
  if [ -z "$PYTHON" ]; then
    echo
    echo "LocalChat needs Python 3.11+ (the app uses the standard-library 'tomllib',"
    echo "added in 3.11). None was found on your PATH — macOS's built-in python3 is 3.9."
    echo "Install a newer Python (e.g. 'brew install python@3.12') and re-run."
    exit 1
  fi
  echo "Using $("$PYTHON" -V 2>&1) at $PYTHON"

  if ! "$PYTHON" -m venv venv; then
    echo
    echo "Failed to create the virtual environment with $PYTHON."
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
