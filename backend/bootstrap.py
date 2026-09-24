"""First-run setup for a packaged (frozen) build.

A source checkout needs none of this — `run.sh` / `run.bat` copy config.toml and
`fetch_model` downloads a model. But a double-click install has no launcher
script and a read-only bundle. `bootstrap()` makes that first launch work:

  1. Ensure a writable config.toml exists (seed it from the bundled template).
  2. Point model_path at a known default model if one is already in the
     NobodyWho cache (e.g. a reinstall, or a user who had it before) — so no
     re-download.

The installers are slim single files with NO models inside; if no model is
cached, the engine downloads the default in the background once the UI is up
(`NobodyWhoEngine._start_first_run_download`), with progress in the composer.

It is a no-op when not frozen, and every step is best-effort: a failure here must
never stop the app from starting (the UI still surfaces a missing-model error).
"""

from __future__ import annotations

from pathlib import Path

from . import paths

# Already-cached models to adopt as the default, in preference order. Specs match
# the curated catalog in models_catalog.CATALOG (same repos/quants).
DEFAULT_CANDIDATES = [
    "huggingface:Qwen/Qwen3-4B-GGUF/Qwen3-4B-Q4_K_M.gguf",   # default / balanced
    "huggingface:Qwen/Qwen3-1.7B-GGUF/Qwen3-1.7B-Q8_0.gguf",
    "huggingface:Qwen/Qwen3-0.6B-GGUF/Qwen3-0.6B-Q8_0.gguf",  # fastest
]


def _config_has_usable_model() -> bool:
    """True if config.toml already names a model file that exists on disk."""
    from . import fetch_model

    existing = fetch_model._current_model_path()
    return bool(existing and Path(existing).is_file())


def _find_cached_default() -> str | None:
    """Cache path of the first DEFAULT_CANDIDATES entry that is actually present."""
    from . import models_catalog

    cached = models_catalog.cached_models()
    for spec in DEFAULT_CANDIDATES:
        hit = models_catalog._match_cached(spec, cached)
        if hit:
            return hit["path"]
    return None


def bootstrap() -> None:
    """Run first-launch setup for packaged builds. Safe/idempotent; never raises."""
    if not paths.is_frozen():
        return
    try:
        _bootstrap_frozen()
    except Exception as e:  # noqa: BLE001 - never block startup
        print(f"[bootstrap] non-fatal setup error: {e}")


def _bootstrap_frozen() -> None:
    from . import fetch_model

    # 1. Seed config.toml into the writable data dir from the shipped template.
    cfg_path = fetch_model.CONFIG_PATH
    if not cfg_path.exists():
        example = fetch_model._EXAMPLE_PATH
        if example.exists():
            cfg_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"[bootstrap] wrote default config -> {cfg_path}")

    # 2. If config doesn't already point at a real model, adopt a cached one.
    if not _config_has_usable_model():
        default_path = _find_cached_default()
        if default_path:
            fetch_model._write_model_path(default_path)
            print(f"[bootstrap] default model -> {default_path}")
        else:
            print("[bootstrap] no cached model; it will download after the UI loads")
