"""Filesystem locations.

Everything lives under the LocalChat folder (the repo root): config.toml next to
the launcher, and the app's own files in `LocalChat data/`. Model weights are
NOT stored here — they live in NobodyWho's own cache.
"""

from __future__ import annotations

from pathlib import Path

# Repo root = parent of the backend/ package.
REPO_ROOT = Path(__file__).resolve().parent.parent

# Files the app writes for itself (not meant to be edited by hand). They get
# their own folder so the repo root stays tidy: just the launcher, config.toml
# and the learner-facing folders.
_STATE_DIR_NAME = "LocalChat data"
_STATE_FILES = ("localchat.db", "localchat.db-wal", "localchat.db-shm", "uploads", "LocalChat.log")


def state_dir() -> Path:
    """WRITABLE directory for the chat DB, uploaded images and the log:
    `<repo>/LocalChat data/`. Older versions kept these in the repo root; they
    are moved in on first use so chat history survives."""
    d = REPO_ROOT / _STATE_DIR_NAME
    d.mkdir(exist_ok=True)
    for name in _STATE_FILES:
        old, new = REPO_ROOT / name, d / name
        if old.exists() and not new.exists():
            try:
                old.rename(new)
            except OSError:
                pass  # e.g. still open elsewhere; the app just starts fresh there
    return d
