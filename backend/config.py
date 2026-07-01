from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# Project root = parent of the backend/ package.
ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"


@dataclass
class Config:
    model_path: str | None = None
    # Multimodal projector (mmproj) for vision models. Normally None: it is set
    # automatically when the app loads a vision model (see the auto-switch in
    # llm.py), not something the user hand-configures.
    projection_model_path: str | None = None
    host: str = "127.0.0.1"
    port: int = 8765
    system_prompt: str | None = None
    n_ctx: int = 4096
    use_gpu: bool = True
    # For reasoning models (e.g. Qwen3): keep <think> blocks out of the chat.
    allow_thinking: bool = False
    sampler: dict = field(default_factory=lambda: {"preset": "temperature", "temperature": 0.7})
    max_live_chats: int = 3
    db_path: str = str((ROOT / "localchat.db").resolve())


def _as_bool(v, default: bool) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return default


def load_config() -> Config:
    cfg = Config()
    toml_path = ROOT / "config.toml"
    data: dict = {}
    if toml_path.exists():
        try:
            with open(toml_path, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:  # noqa: BLE001 - never let a bad config crash startup
            print(f"[config] failed to parse config.toml: {e}")

    cfg.model_path = data.get("model_path") or None
    cfg.projection_model_path = data.get("projection_model_path") or None
    cfg.host = data.get("host", cfg.host)
    cfg.port = int(data.get("port", cfg.port))
    cfg.system_prompt = data.get("system_prompt") or None
    cfg.n_ctx = int(data.get("n_ctx", cfg.n_ctx))
    cfg.use_gpu = _as_bool(data.get("use_gpu", cfg.use_gpu), True)
    cfg.allow_thinking = _as_bool(data.get("allow_thinking", cfg.allow_thinking), False)
    cfg.max_live_chats = max(1, int(data.get("max_live_chats", cfg.max_live_chats)))
    if data.get("db_path"):
        cfg.db_path = data["db_path"]
    if isinstance(data.get("sampler"), dict):
        cfg.sampler = data["sampler"]

    env = os.environ
    if env.get("LOCALCHAT_MODEL_PATH"):
        cfg.model_path = env["LOCALCHAT_MODEL_PATH"]
    if env.get("LOCALCHAT_PROJECTION_PATH"):
        cfg.projection_model_path = env["LOCALCHAT_PROJECTION_PATH"]
    if env.get("LOCALCHAT_PORT"):
        cfg.port = int(env["LOCALCHAT_PORT"])
    if env.get("LOCALCHAT_USE_GPU"):
        cfg.use_gpu = _as_bool(env["LOCALCHAT_USE_GPU"], cfg.use_gpu)
    if env.get("LOCALCHAT_ALLOW_THINKING"):
        cfg.allow_thinking = _as_bool(env["LOCALCHAT_ALLOW_THINKING"], cfg.allow_thinking)
    if env.get("LOCALCHAT_DB_PATH"):
        cfg.db_path = env["LOCALCHAT_DB_PATH"]

    if cfg.model_path:
        cfg.model_path = str(Path(cfg.model_path).expanduser())
    if cfg.projection_model_path:
        cfg.projection_model_path = str(Path(cfg.projection_model_path).expanduser())
    cfg.db_path = str(Path(cfg.db_path).expanduser().resolve())
    return cfg
