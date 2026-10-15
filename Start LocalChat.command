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

# --- Packages: install on first run, and again whenever backend/requirements.txt
#     changes. venv/.requirements.installed is a copy of the requirements.txt
#     that was last installed successfully.
if ! cmp -s backend/requirements.txt venv/.requirements.installed; then
  echo "Installing packages (this can take a few minutes)..."
  "$UV" pip install --python venv/bin/python -r backend/requirements.txt \
    || fail "Package installation failed. Check the internet connection."
  cp backend/requirements.txt venv/.requirements.installed
fi

# --- Config: create from template on first run ---
[ -f config.toml ] || cp backend/config.example.toml config.toml

# --- Git: hide the files created above from `git status` (local to this
#     clone, so the repo needs no .gitignore). Added once.
if [ -d .git/info ] && ! grep -qs "app/LocalChat.app/" .git/info/exclude; then
  cat >> .git/info/exclude <<'EOF'
# Added by the LocalChat launcher: files created on first run.
.uv/
venv/
config.toml
LocalChat data/
app/LocalChat.app/
*.gguf
__pycache__/
EOF
fi

# --- Model: use a .gguf next to this file, else download the default once ---
venv/bin/python -m backend.fetch_model

# --- The app window: unpack it on first run, and again after an update
#     (app/version.txt differs from the unpacked copy's) ---
APP=app/LocalChat.app
if [ -f app/LocalChat.zip ] && ! cmp -s app/version.txt "$APP/Contents/Resources/version.txt"; then
  echo "Unpacking the LocalChat app..."
  rm -rf "$APP"
  ditto -x -k app/LocalChat.zip app || fail "Could not unpack the LocalChat app."
fi
# In the source repo (no app/), use the app built from desktop/.
[ -d "$APP" ] || APP=desktop/build/macos/Build/Products/Release/LocalChat.app
[ -d "$APP" ] || fail "The LocalChat app is missing (app/LocalChat.zip). Download LocalChat again."

# --- Launch, detached from this Terminal window so closing the window doesn't
#     quit LocalChat. The app starts the Python backend itself and stops it when
#     it quits; backend output goes to "LocalChat data/LocalChat.log".
venv/bin/python - "$APP/Contents/MacOS/LocalChat" <<'PY' || fail "Could not start LocalChat."
import subprocess, sys
subprocess.Popen([sys.argv[1]], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL, start_new_session=True)
PY
echo
echo "LocalChat is starting. You can close this Terminal window."
