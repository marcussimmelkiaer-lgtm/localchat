"""First-run model bootstrap.

Ensures a usable local GGUF chat model exists and that `config.toml` points at
it. Run once by the launcher (run.sh / run.bat) after dependencies install,
before the app starts. Idempotent: if config.toml already names a model file
that exists on disk, this is a no-op.

The model is NOT committed to the repo (a 4B GGUF is ~2.5 GB — far over
GitHub's limits). Instead it is downloaded once from Hugging Face into
NobodyWho's local cache (~/Library/Application Support/nobodywho/... on macOS,
%LOCALAPPDATA%\\nobodywho\\... on Windows) and reused forever.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.toml"

# Default model for a fresh machine. Same Qwen3 family the app is tuned for
# (~2.5 GB, ~50 tok/s on Apple Silicon / a modern GPU). Override with the
# LOCALCHAT_DEFAULT_MODEL env var if you want a different one.
DEFAULT_MODEL = "huggingface:Qwen/Qwen3-4B-GGUF/Qwen3-4B-Q4_K_M.gguf"


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
        example = ROOT / "config.example.toml"
        CONFIG_PATH.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")

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


def ensure_model() -> int:
    """Returns 0 if a usable model is configured (downloading one if needed),
    non-zero on failure. The launcher still starts the app on failure — the UI
    surfaces the model error and the user can set model_path by hand."""
    import os

    existing = _current_model_path()
    if existing and Path(existing).is_file():
        print(f"[fetch_model] model already present: {existing}")
        return 0

    spec = os.environ.get("LOCALCHAT_DEFAULT_MODEL") or DEFAULT_MODEL
    print(f"[fetch_model] no local model found — downloading default ({spec}).")
    print("[fetch_model] this happens once (~2.5 GB) and is cached for next time.")
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
