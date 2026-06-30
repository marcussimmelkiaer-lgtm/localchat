from __future__ import annotations

import os
import threading
import time
from typing import Iterator, Tuple

from . import store
from .config import Config
from .files import fold_content
from .sessions import SessionRegistry

# The engine yields a stream of events to the route's worker thread:
#   ("token", str) | ("stats", dict) | ("error", str)
# The route turns these into SSE frames and persists the result.
Event = Tuple[str, object]


def prompt_from_store(conv_id: str):
    """Rebuild (history_prefix, prompt) from SQLite — the single source of truth.

    The prompt is the last user message; the prefix is every completed message
    before it. The trailing empty assistant placeholder is naturally excluded
    (empty content), so this is identical for a fresh send and a regenerate.

    Each user message's attachment text is folded in front of its typed content
    (fold_content) so the model sees uploaded file contents on every turn."""
    msgs = store.get_messages(conv_id)
    idx = -1
    for i in range(len(msgs) - 1, -1, -1):
        if msgs[i]["role"] == "user":
            idx = i
            break
    if idx == -1:
        return [], ""
    prefix = []
    for m in msgs[:idx]:
        if m["role"] not in ("user", "assistant"):
            continue
        text = fold_content(m["content"], m.get("attachments")) if m["role"] == "user" else m["content"]
        if text:
            prefix.append({"role": m["role"], "content": text})
    last = msgs[idx]
    return prefix, fold_content(last["content"], last.get("attachments"))


class NobodyWhoEngine:
    """Real local generation via the NobodyWho bindings (llama.cpp + Vulkan).

    A single reference-counted Model holds the weights (loaded once, on the GPU
    when available); each conversation gets its own Chat sharing those weights."""

    backend = "nobodywho"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.model_error: str | None = None
        self._model = None
        self._model_lock = threading.Lock()
        self._loaded = threading.Event()
        self._warming = False
        self._sessions = SessionRegistry(self._build_chat, cfg.max_live_chats)
        self._active: dict[str, object] = {}

    def model_loaded(self) -> bool:
        return self._loaded.is_set()

    def warmup(self) -> None:
        """Load the model. Raises on failure (caller records model_error)."""
        self._ensure_model()

    def start_warmup(self) -> None:
        """Kick off a one-shot background model load (idempotent, non-blocking).

        The load is a native call that holds the GIL for ~3s, so it MUST run off
        the event loop. It runs on a daemon thread here; a concurrent first
        message blocks on the same _model_lock (no double load). The UI (a
        separate WebView2 process) stays responsive while this runs."""
        with self._model_lock:
            if self._loaded.is_set() or self._warming:
                return
            self._warming = True

        def _run():
            try:
                self._ensure_model()
            except Exception as e:  # noqa: BLE001
                self.model_error = str(e)
            finally:
                self._warming = False

        threading.Thread(target=_run, daemon=True).start()

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is None:
                if not self.cfg.model_path:
                    raise RuntimeError(
                        "No model configured. Set model_path in config.toml to a local .gguf file."
                    )
                if not os.path.isfile(self.cfg.model_path):
                    raise RuntimeError(f"Model file not found: {self.cfg.model_path}")
                import nobodywho

                model = nobodywho.Model(
                    self.cfg.model_path, use_gpu_if_available=self.cfg.use_gpu
                )
                self._model = model
                self._loaded.set()
                self.model_error = None
        return self._model

    def _build_sampler(self):
        import nobodywho

        s = self.cfg.sampler or {}
        preset = (s.get("preset") or "temperature").lower()
        try:
            if preset == "greedy":
                return nobodywho.SamplerPresets.greedy()
            if preset == "top_k":
                return nobodywho.SamplerPresets.top_k(int(s.get("top_k", 40)))
            if preset == "top_p":
                return nobodywho.SamplerPresets.top_p(float(s.get("top_p", 0.95)))
            if preset == "default":
                return nobodywho.SamplerPresets.default()
            return nobodywho.SamplerPresets.temperature(float(s.get("temperature", 0.7)))
        except Exception as e:  # noqa: BLE001
            print(f"[llm] sampler build failed, using model default: {e}")
            return None

    def _build_chat(self):
        import nobodywho

        model = self._ensure_model()
        kwargs = {
            "n_ctx": self.cfg.n_ctx,
            # Reasoning models (Qwen3) read enable_thinking from their template;
            # off by default keeps <think> blocks out of the chat.
            "template_variables": {"enable_thinking": self.cfg.allow_thinking},
        }
        if self.cfg.system_prompt:
            kwargs["system_prompt"] = self.cfg.system_prompt
        sampler = self._build_sampler()
        if sampler is not None:
            kwargs["sampler"] = sampler
        return nobodywho.Chat(model, **kwargs)

    def stop(self, conv_id: str) -> None:
        chat = self._active.get(conv_id)
        if chat is not None:
            try:
                chat.stop_generation()
            except Exception:  # noqa: BLE001
                pass

    def evict(self, conv_id: str) -> None:
        self._sessions.evict(conv_id)

    def stream(self, conv_id: str, stop_event: threading.Event) -> Iterator[Event]:
        prefix, prompt = prompt_from_store(conv_id)
        try:
            # Lazily loads the model on first use (blocks this worker thread, not
            # the event loop's request handling beyond this generation).
            sess = self._sessions.get(conv_id)
        except Exception as e:  # noqa: BLE001
            self.model_error = str(e)
            yield ("error", str(e))
            return
        with sess.lock:
            chat = sess.chat
            self._active[conv_id] = chat
            try:
                try:
                    chat.set_chat_history(prefix)
                except Exception as e:  # noqa: BLE001
                    print(f"[llm] set_chat_history failed: {e}")

                t0 = time.perf_counter()
                first = None
                count = 0
                try:
                    response = chat.ask(prompt)
                    for token in response:
                        if stop_event.is_set():
                            try:
                                chat.stop_generation()
                            except Exception:  # noqa: BLE001
                                pass
                            break
                        if first is None:
                            first = time.perf_counter()
                        count += 1
                        yield ("token", token)
                except Exception as e:  # noqa: BLE001
                    if not stop_event.is_set():
                        yield ("error", str(e))
                        return
                yield ("stats", _stats(t0, first, count))
            finally:
                self._active.pop(conv_id, None)


def _stats(t0: float, first: float | None, count: int) -> dict:
    base = first if first is not None else t0
    seconds = max(1e-3, time.perf_counter() - base)
    return {
        "tokens": count,
        "seconds": seconds,
        "tokens_per_second": count / seconds,
        "ttft_ms": (base - t0) * 1000.0,
    }


def build_engine(cfg: Config) -> NobodyWhoEngine:
    return NobodyWhoEngine(cfg)
