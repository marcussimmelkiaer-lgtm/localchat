#!/bin/bash
# LocalChat launcher for macOS. Double-click in Finder (it opens in Terminal).
#
# The first run downloads everything it needs INTO THIS FOLDER: uv and a private
# Python in .uv/, the app's packages in venv/. Nothing is installed system-wide
# and no admin rights are needed; deleting the folder removes LocalChat
# (downloaded models stay in ~/Library/Application Support/nobodywho for reuse).
# Later runs skip straight to starting the app.
set -u
cd "$(dirname "$0")" || exit 1

fail() {
  echo
  echo "$1"
  echo
  echo "Setup did not finish. Fix the problem above, then double-click"
  echo "\"Start LocalChat.command\" again."
  exit 1
}

# nobodywho only ships an Apple Silicon (arm64) macOS wheel.
if [ "$(uname -s)" = "Darwin" ]; then
  if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" != "1" ]; then
    fail "LocalChat needs a Mac with Apple Silicon (M1 or newer); this Mac has an Intel processor."
  fi
  # A Terminal running under Rosetta reports x86_64, which would make uv fetch
  # an Intel Python. Re-run natively instead.
  if [ "$(uname -m)" != "arm64" ]; then
    exec arch -arm64 /bin/bash "$0" "$@"
  fi
fi

UV_DIR="$PWD/.uv"
UV="$UV_DIR/uv"
export UV_PYTHON_INSTALL_DIR="$UV_DIR/python"
# Always use uv's own Python, never whatever happens to be on the machine
# (macOS's built-in python3 is 3.9, too old for the app).
export UV_PYTHON_PREFERENCE=only-managed

# --- uv: a single-file tool that downloads Python and installs packages ---
if [ ! -x "$UV" ]; then
  echo "First-time setup: downloading the Python installer (uv)..."
  curl -LsSf https://astral.sh/uv/install.sh \
    | env UV_INSTALL_DIR="$UV_DIR" UV_NO_MODIFY_PATH=1 sh \
    || fail "Could not download uv. Check the internet connection."
  [ -x "$UV" ] || fail "uv did not install into $UV_DIR."
fi

# --- Python + virtual environment ---
if [ ! -x "venv/bin/python" ]; then
  echo "First-time setup: downloading Python..."
  "$UV" venv venv --python 3.12 --seed || fail "Could not set up Python."
fi

# --- Packages: install on first run, and again whenever requirements.txt
#     changes. venv/.requirements.installed is a copy of the requirements.txt
#     that was last installed successfully.
if ! cmp -s requirements.txt venv/.requirements.installed; then
  echo "Installing packages (this can take a few minutes)..."
  "$UV" pip install --python venv/bin/python -r requirements.txt \
    || fail "Package installation failed. Check the internet connection."
  cp requirements.txt venv/.requirements.installed
fi

# --- Config: create from template on first run ---
[ -f config.toml ] || cp config.example.toml config.toml

# --- Model: use a .gguf next to this file, else download the default once ---
venv/bin/python -m backend.fetch_model

# --- Launch the app, detached from this Terminal window so closing the window
#     doesn't quit LocalChat. Output goes to LocalChat.log.
venv/bin/python - <<'PY' || fail "Could not start LocalChat."
import subprocess, sys
log = open("LocalChat.log", "w")
subprocess.Popen([sys.executable, "-u", "-m", "backend.main"],
                 stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                 start_new_session=True)
PY
echo
echo "LocalChat is starting. You can close this Terminal window."
