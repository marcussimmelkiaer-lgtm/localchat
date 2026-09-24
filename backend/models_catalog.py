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

import json
import os
import re
import urllib.request
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


# --- Forgiving download-spec resolution -------------------------------------
#
# NobodyWho's download_model() wants a concrete GGUF file:
# `huggingface:owner/repo/file.gguf`. Users, though, naturally copy a repo id off
# a Hugging Face page ("Qwen/Qwen3-0.6B") — which is usually the *base* repo with
# no GGUF at all; the GGUF lives in a sibling "…-GGUF" repo and still needs a
# quant picked. `resolve_spec` bridges that gap so the download field accepts the
# short form as well as the full spec / URL forms.

# Quant preference when the user doesn't name one — mirrors the app's Q4_K_M
# default (best size/quality trade-off), then reasonable fallbacks.
_PREFERRED_QUANTS = ["Q4_K_M", "Q4_K_S", "Q5_K_M", "Q4_0", "Q6_K", "Q5_K_S", "Q8_0", "Q3_K_M", "Q2_K"]


def _hf_gguf_files(repo: str) -> list[str]:
    """`.gguf` filenames in a Hugging Face repo via its public API.

    Returns [] on 404/network error (best-effort — the caller tries the next
    candidate repo, then raises a helpful message if all come up empty)."""
    url = f"https://huggingface.co/api/models/{repo}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "localchat"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - any failure just means "no files here"
        return []
    files = []
    for sib in data.get("siblings") or []:
        name = sib.get("rfilename") if isinstance(sib, dict) else None
        if name and name.lower().endswith(".gguf"):
            files.append(name)
    return files


def _is_shard(fname: str) -> bool:
    """A multi-part GGUF (…-00001-of-00003.gguf). download_model fetches one file,
    so we avoid picking a shard unless nothing else is available."""
    return re.search(r"-\d{5}-of-\d{5}\.gguf$", fname, re.IGNORECASE) is not None


def _pick_gguf(files: list[str], want_quant: str | None) -> str | None:
    """Choose one GGUF: an explicitly-requested quant if present, else the first
    preferred quant, else the first single-file GGUF."""
    if not files:
        return None
    singles = [f for f in files if not _is_shard(f)] or files
    if want_quant:
        # An explicit quant is a hard request — match it or give up (so the
        # caller can say "no such quant" rather than silently fetch a different,
        # possibly much larger, file).
        wq = want_quant.lower()
        for f in singles:
            if wq in f.lower():
                return f
        return None
    for q in _PREFERRED_QUANTS:
        for f in singles:
            if q.lower() in f.lower():
                return f
    return singles[0]


def resolve_spec(user_input: str) -> str:
    """Turn forgiving user input into a concrete download spec.

    Accepts, in order of increasing help:
      - a local file path (returned as-is);
      - a full `huggingface:owner/repo/file.gguf` spec (returned as-is);
      - the same without the prefix (`owner/repo/file.gguf` -> prefixed);
      - a direct `https://.../file.gguf` URL (returned as-is) or a Hugging Face
        page / blob / resolve URL (reduced to a repo id, then resolved);
      - a bare repo id `owner/name` — the GGUF repo is discovered (trying
        `owner/name` then the conventional `owner/name-GGUF`) and a quant chosen
        automatically (Q4_K_M preferred). An optional `:QUANT` suffix forces one,
        e.g. `Qwen/Qwen3-0.6B:Q5_K_M`.

    Raises ValueError with an actionable message when nothing resolves."""
    s = (user_input or "").strip()
    if not s:
        raise ValueError("No model given.")

    if os.path.isfile(s):
        return s

    if s.lower().startswith(("http://", "https://")):
        low = s.lower()
        if "huggingface.co/" in low:
            after = s.split("huggingface.co/", 1)[1]
            # Strip /resolve/<rev>/, /blob/<rev>/, /tree/<rev>/ markers so a link
            # copied from the file browser collapses to owner/repo[/file].
            after = re.sub(r"/(resolve|blob|tree)/[^/]+/", "/", after)
            s = after.split("?", 1)[0].rstrip("/")
            # fall through to the huggingface-path handling below
        elif low.endswith(".gguf"):
            return s  # arbitrary direct GGUF URL — nobodywho fetches it directly
        else:
            raise ValueError("Give a Hugging Face repo (owner/name) or a direct .gguf URL.")

    if s.lower().startswith("huggingface:"):
        s = s.split(":", 1)[1].strip()

    # Optional :QUANT selector on a bare repo (e.g. Qwen/Qwen3-0.6B:Q5_K_M).
    want_quant = None
    m = re.match(r"^([^/\s]+/[^/\s:]+):([A-Za-z0-9_]+)$", s)
    if m:
        s, want_quant = m.group(1), m.group(2)

    if s.lower().endswith(".gguf"):
        return f"huggingface:{s}"

    parts = [p for p in s.split("/") if p]
    if len(parts) != 2:
        raise ValueError(
            f"Couldn't understand '{user_input}'. Use owner/name "
            "(e.g. Qwen/Qwen3-0.6B) or a full owner/repo/file.gguf spec."
        )
    owner, name = parts

    candidates = [f"{owner}/{name}"]
    if not name.lower().endswith("-gguf"):
        candidates.append(f"{owner}/{name}-GGUF")

    for repo in candidates:
        chosen = _pick_gguf(_hf_gguf_files(repo), want_quant)
        if chosen:
            return f"huggingface:{repo}/{chosen}"

    hint = f" with quant '{want_quant}'" if want_quant else ""
    raise ValueError(
        f"No GGUF{hint} found for '{user_input}'. Tried: {', '.join(candidates)}. "
        "Paste the exact owner/repo/file.gguf if the model lives elsewhere."
    )
