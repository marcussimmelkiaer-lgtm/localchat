"""Curated model catalog + cache introspection.

A small hand-picked list of Qwen3 GGUFs (same family the app is tuned for, so
swapping between them is a pure config change — identical chat template, thinking
behaviour and sampler). The user can also download any other GGUF by pasting a
`huggingface:` spec; those simply don't appear in the curated catalog but are
listed under "cached" once downloaded.

Cross-platform note: model files live in NobodyWho's per-OS cache
(`%LOCALAPPDATA%\\nobodywho\\models\\...` on Windows,
`~/Library/Application Support/nobodywho/models/...` on macOS). We never hardcode
that location — `nobodywho.get_cached_models()` reports the real absolute paths,
and a download spec's tail maps onto `.../models/<tail>`, so we match a catalog
entry to a cached file by comparing path tails. All comparisons normalise slashes
and case so Windows paths don't produce false mismatches.
"""

from __future__ import annotations

from pathlib import PurePath

# Curated, one-click models. `spec` is the `huggingface:` download spec; its tail
# (everything after the colon) also determines the on-disk cache sub-path.
CATALOG = [
    {
        # NOTE: the official Qwen/Qwen3-1.7B-GGUF repo ships ONLY Q8_0 — it has no
        # Q4_K_M (unlike the 4B/8B repos). Pointing at a Q4_K_M here 404s and
        # NobodyWho raises "check that the owner repo and filename is correct".
        # Q8_0 is still the smallest/fastest option and stays in the official Qwen
        # org (same chat template as the others).
        "id": "qwen3-1.7b",
        "name": "Qwen3 1.7B",
        "quant": "Q8_0",
        "spec": "huggingface:Qwen/Qwen3-1.7B-GGUF/Qwen3-1.7B-Q8_0.gguf",
        "size_gb": 1.8,
        "note": "fastest",
    },
    {
        "id": "qwen3-4b",
        "name": "Qwen3 4B",
        "quant": "Q4_K_M",
        "spec": "huggingface:Qwen/Qwen3-4B-GGUF/Qwen3-4B-Q4_K_M.gguf",
        "size_gb": 2.5,
        "note": "default / balanced",
    },
    {
        "id": "qwen3-8b",
        "name": "Qwen3 8B",
        "quant": "Q4_K_M",
        "spec": "huggingface:Qwen/Qwen3-8B-GGUF/Qwen3-8B-Q4_K_M.gguf",
        "size_gb": 5.4,
        "note": "most capable",
    },
    {
        # Vision-capable model (image understanding). Unlike the Qwen3 text
        # entries this needs TWO files: the text backbone (`spec`) and the
        # multimodal projector / mmproj (`projection`), passed to
        # Model(projection_model_path=...). The app auto-switches to this only
        # for the turn(s) that carry an image, then switches back — see llm.py.
        "id": "qwen2.5-vl-3b",
        "name": "Qwen2.5-VL 3B",
        "quant": "Q4_K_M",
        "spec": "huggingface:ggml-org/Qwen2.5-VL-3B-Instruct-GGUF/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf",
        "projection": "huggingface:ggml-org/Qwen2.5-VL-3B-Instruct-GGUF/mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf",
        "size_gb": 3.3,
        "vision": True,
        "note": "images / screenshots",
    },
]


def vision_entry() -> dict | None:
    """The curated vision model entry (the one carrying a `projection` spec)."""
    for item in CATALOG:
        if item.get("vision"):
            return item
    return None


def _norm(path: str) -> str:
    """Normalise a path for comparison: forward slashes, lowercase.

    Used only for tail/equality matching, never for filesystem access — keep the
    original string for that. Lowercasing is safe here because we only compare
    against other model paths (Windows is case-insensitive; on macOS the cache
    paths we emit and the ones NobodyWho reports are byte-identical anyway)."""
    return str(PurePath(path)).replace("\\", "/").lower()


def _spec_tail(spec: str) -> str:
    """The part of a download spec that becomes the cache sub-path.

    `huggingface:Qwen/Qwen3-4B-GGUF/Qwen3-4B-Q4_K_M.gguf`
        -> `qwen/qwen3-4b-gguf/qwen3-4b-q4_k_m.gguf`
    Also tolerates `https://.../file.gguf` specs (falls back to the basename)."""
    tail = spec.split(":", 1)[1] if ":" in spec else spec
    tail = tail.split("?", 1)[0].rstrip("/")
    return _norm(tail)


def cached_models() -> list[dict]:
    """All GGUFs in NobodyWho's cache as `{path, size_bytes, name}`.

    Returns [] if the binding can't be queried for any reason (best-effort)."""
    try:
        import nobodywho

        raw = nobodywho.get_cached_models()
    except Exception:  # noqa: BLE001 - listing is best-effort
        return []
    out = []
    for entry in raw:
        try:
            path, size = entry[0], int(entry[1])
        except Exception:  # noqa: BLE001
            continue
        out.append({"path": str(path), "size_bytes": size, "name": PurePath(path).name})
    return out


def _match_cached(spec: str, cached: list[dict]) -> dict | None:
    """Find the cached file a catalog spec resolves to, by path-tail match."""
    tail = _spec_tail(spec)
    for c in cached:
        if _norm(c["path"]).endswith(tail):
            return c
    return None


def resolve_cached_paths(entry: dict) -> tuple[str | None, str | None]:
    """Local cached paths for a catalog entry as (model_path, projection_path).

    Each is the on-disk path if that file is cached, else None. Non-vision
    entries always return None for the projection. Used by the vision
    auto-switch to load from cache (or detect that a download is still needed)."""
    cached = cached_models()
    mh = _match_cached(entry["spec"], cached)
    model_path = mh["path"] if mh else None
    proj_path = None
    if entry.get("projection"):
        ph = _match_cached(entry["projection"], cached)
        proj_path = ph["path"] if ph else None
    return model_path, proj_path


def projection_for_path(model_path: str | None) -> str | None:
    """If `model_path` is a catalog vision model's backbone file, return its
    cached mmproj path (else None). Lets a manual switch to the vision model
    also pick up its projector so images work without a special code path."""
    if not model_path:
        return None
    target = _norm(model_path)
    cached = cached_models()
    for item in CATALOG:
        if not item.get("vision"):
            continue
        mh = _match_cached(item["spec"], cached)
        if mh and _norm(mh["path"]) == target:
            ph = _match_cached(item["projection"], cached)
            return ph["path"] if ph else None
    return None


def build_catalog(active_path: str | None) -> dict:
    """Assemble the model list the API returns.

    Shape: {active: {path, name}, catalog: [...], cached: [...]}
      - catalog entries gain `downloaded` (bool), `path` (str|None), `active` (bool)
      - cached lists every cached GGUF (incl. custom downloads not in the catalog)
    """
    cached = cached_models()
    active_norm = _norm(active_path) if active_path else None

    catalog = []
    for item in CATALOG:
        hit = _match_cached(item["spec"], cached)
        path = hit["path"] if hit else None
        entry = {
            **item,
            "downloaded": hit is not None,
            "path": path,
            "active": bool(path and active_norm and _norm(path) == active_norm),
        }
        if item.get("projection"):
            # A vision entry needs BOTH files present to count as downloaded.
            phit = _match_cached(item["projection"], cached)
            entry["projection_path"] = phit["path"] if phit else None
            entry["downloaded"] = bool(hit and phit)
        catalog.append(entry)

    for c in cached:
        c["active"] = bool(active_norm and _norm(c["path"]) == active_norm)
        c["in_catalog"] = any(_norm(c["path"]).endswith(_spec_tail(i["spec"])) for i in CATALOG)

    return {"catalog": catalog, "cached": cached}


def is_cached_path(path: str) -> bool:
    """True iff `path` is one of NobodyWho's cached model files.

    This is the authoritative delete guard — we only ever remove files NobodyWho
    itself reports as cached models, never an arbitrary path the client sends."""
    target = _norm(path)
    return any(_norm(c["path"]) == target for c in cached_models())
