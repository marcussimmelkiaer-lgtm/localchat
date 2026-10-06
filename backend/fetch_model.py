"""First-run model bootstrap.

Ensures a usable local GGUF chat model exists and that `config.toml` points at
it. Run once by the launcher (Start LocalChat.bat / .command) after dependencies
install, before the app starts. Idempotent: if config.toml already names a model
file that exists on disk, this is a no-op.

A `.gguf` placed next to the launcher (e.g. copied from a USB stick at a
workshop) is adopted instead of downloading.

The model is NOT committed to the repo (GGUFs are far over GitHub's file
limits). Instead it is downloaded once from Hugging Face into
NobodyWho's local cache (~/Library/Application Support/nobodywho/... on macOS,
%LOCALAPPDATA%\\nobodywho\\... on Windows) and reused forever.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

from .paths import bundle_dir, data_dir

# config.toml is WRITABLE, so it lives in the per-user data dir (repo root in a
# source checkout). The example template it's seeded from is a shipped asset, so
# it comes from the read-only bundle.
CONFIG_PATH = data_dir() / "config.toml"
_EXAMPLE_PATH = bundle_dir() / "config.example.toml"

# Default model for a fresh machine: the smallest Qwen3 (~640 MB), so a first
# launch on shared Wi-Fi is quick. Bigger Qwen3s are one click away in the Models
# picker (same family -> same chat template / thinking / sampler). The official
# 0.6B GGUF repo ships only Q8_0. Override with LOCALCHAT_DEFAULT_MODEL.
DEFAULT_MODEL = "huggingface:Qwen/Qwen3-0.6B-GGUF/Qwen3-0.6B-Q8_0.gguf"


def default_spec() -> str:
    """The model to fetch on a fresh machine (env override, else DEFAULT_MODEL)."""
    import os

    return os.environ.get("LOCALCHAT_DEFAULT_MODEL") or DEFAULT_MODEL


def _current_model_path() -> str | None:
    """Read model_path out of config.toml without importing the full app."""
    if not CONFIG_PATH.exists():
        return None
    try:
        import tomllib

        with open(CONFIG_PATH, "rb") as f:
            data = tomllib.load(f)
    except Exception as e:  # noqa: BLE001
        print(f"[fetch_model] could not parse config.toml: {e}")
        return None
    val = data.get("model_path") or None
    return str(Path(val).expanduser()) if val else None


def _write_model_path(path: str) -> None:
    """Set model_path in config.toml, preserving the rest of the file.

    Replaces the first uncommented `model_path = ...` assignment. If config.toml
    doesn't exist yet (shouldn't happen — the launcher copies the template
    first), it is created from the example template."""
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    text = CONFIG_PATH.read_text(encoding="utf-8")
    # TOML on Windows: forward slashes are safest (backslashes are escapes in
    # basic strings). Path() normalises; we emit with forward slashes.
    value = str(Path(path)).replace("\\", "/")
    line = f'model_path = "{value}"'

    pattern = re.compile(r'^\s*model_path\s*=.*$', re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(line, text, count=1)
    else:
        text = line + "\n" + text
    CONFIG_PATH.write_text(text, encoding="utf-8")
    print(f"[fetch_model] set model_path in config.toml -> {value}")


_last_print = 0.0


def _on_progress(*args) -> None:
    """Throttled download progress. NobodyWho's callback signature isn't
    contractual across versions, so accept whatever it hands us: a single
    fraction (0..1), or (downloaded, total) byte counts."""
    global _last_print
    now = time.monotonic()
    if now - _last_print < 0.5:
        return
    _last_print = now
    try:
        if len(args) == 1 and isinstance(args[0], (int, float)):
            frac = float(args[0])
            if frac <= 1.0:
                print(f"\r[fetch_model] downloading... {frac * 100:5.1f}%", end="", flush=True)
                return
        if len(args) >= 2 and all(isinstance(a, (int, float)) for a in args[:2]):
            done, total = float(args[0]), float(args[1])
            if total > 0:
                pct = done / total * 100
                gb = total / 1e9
                print(f"\r[fetch_model] downloading... {pct:5.1f}% of {gb:.2f} GB", end="", flush=True)
                return
    except Exception:  # noqa: BLE001 - progress is best-effort, never fatal
        pass
    print("\r[fetch_model] downloading...", end="", flush=True)


def _sideloaded_model() -> str | None:
    """A .gguf sitting next to the launcher (the repo root), if any.

    Lets a workshop hand out the model on a USB stick: copy the folder plus the
    .gguf and no download happens. Picks the largest file, so a stray mmproj
    projector (always much smaller) is never chosen as the chat model."""
    files = [p for p in data_dir().glob("*.gguf") if p.is_file()]
    if not files:
        return None
    return str(max(files, key=lambda p: p.stat().st_size).resolve())


def ensure_model() -> int:
    """Returns 0 if a usable model is configured (downloading one if needed),
    non-zero on failure. The launcher still starts the app on failure — the UI
    surfaces the model error and the user can set model_path by hand."""
    existing = _current_model_path()
    if existing and Path(existing).is_file():
        print(f"[fetch_model] model already present: {existing}")
        return 0

    local = _sideloaded_model()
    if local:
        _write_model_path(local)
        print(f"[fetch_model] using model next to the launcher: {local}")
        return 0

    spec = default_spec()
    print(f"[fetch_model] no local model found — downloading default ({spec}).")
    print("[fetch_model] this happens once and is cached for next time.")
    try:
        import nobodywho

        try:
            local_path = nobodywho.download_model(spec, on_download_progress=_on_progress)
        except TypeError:
            # Older/newer signature without the kwarg — fall back plainly.
            local_path = nobodywho.download_model(spec)
        print()  # end the progress line
    except Exception as e:  # noqa: BLE001
        print(f"\n[fetch_model] download failed: {e}")
        print("[fetch_model] you can set model_path in config.toml manually instead.")
        return 1

    if not local_path or not Path(local_path).is_file():
        print(f"[fetch_model] download reported '{local_path}' but the file is missing.")
        return 1

    _write_model_path(str(local_path))
    print(f"[fetch_model] ready: {local_path}")
    return 0


if __name__ == "__main__":
    sys.exit(ensure_model())
