"""Filesystem locations, aware of whether we run from source or a frozen bundle.

In development (running from a git clone) everything lives under the repo root,
exactly as it always has — `data_dir()` and `bundle_dir()` both return the repo
root, so nothing changes.

In a packaged build (PyInstaller — `sys.frozen` is set) the application code and
its shipped assets live inside a **read-only** bundle, so anything the app needs
to *write* (config.toml, the SQLite DB, uploaded images) must go to a per-user
writable directory instead:

  - Windows: %LOCALAPPDATA%\\LocalChat
  - macOS:   ~/Library/Application Support/LocalChat
  - Linux:   $XDG_DATA_HOME/localchat (or ~/.local/share/localchat)

Model weights are NOT stored here — they live in NobodyWho's own cache
(filled by the first-run download).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Repo root in a source checkout = parent of the backend/ package.
_REPO_ROOT = Path(__file__).resolve().parent.parent

# App name used for the per-user data directory in a packaged build.
_APP_NAME = "LocalChat"


def is_frozen() -> bool:
    """True when running from a PyInstaller (or similar) frozen bundle."""
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    """Read-only directory holding shipped assets (static SPA, config template).

    PyInstaller unpacks a onefile build to `sys._MEIPASS`; a onedir build sets it
    to the app directory. In a source checkout this is the repo root, so paths
    built from it (e.g. `bundle_dir()/'backend'/'static'`) resolve unchanged."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return _REPO_ROOT


def data_dir() -> Path:
    """Per-user WRITABLE directory for config.toml, the DB and uploads.

    In a source checkout this is the repo root (unchanged legacy behavior). In a
    frozen build it's the OS-appropriate app-data location, created on demand."""
    if not is_frozen():
        return _REPO_ROOT

    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / _APP_NAME
    elif os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        base = Path(local) / _APP_NAME
    else:
        xdg = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
        base = Path(xdg) / _APP_NAME.lower()

    base.mkdir(parents=True, exist_ok=True)
    return base
