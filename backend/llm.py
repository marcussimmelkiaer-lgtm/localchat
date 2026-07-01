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


def _same_path(a: str | None, b: str | None) -> bool:
    """True if two paths point at the same file, tolerant of slash/case diffs.

    Doesn't require the file to exist (compares normalised absolute strings), so
    it's usable while a model is mid-swap."""
    if not a or not b:
        return False
    try:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
    except Exception:  # noqa: BLE001
        return False


def _image_paths(attachments: list[dict] | None) -> list[str]:
    """On-disk paths of the image attachments that still exist (for Image parts)."""
    out = []
    for a in attachments or []:
        if a and a.get("is_image") and a.get("path") and os.path.isfile(a["path"]):
            out.append(a["path"])
    return out


def prompt_from_store(conv_id: str):
    """Rebuild (history_prefix, prompt, image_paths) from SQLite — the single
    source of truth.

    The prompt is the last user message; the prefix is every completed message
    before it. The trailing empty assistant placeholder is naturally excluded
    (empty content), so this is identical for a fresh send and a regenerate.

    Each user message's attachment text is folded in front of its typed content
    (fold_content) so the model sees uploaded file contents on every turn.
    `image_paths` are the *current* turn's image files — only the latest turn can
    carry images, because chat history is text-only (set_chat_history), so prior
    images survive only as the `[Image: name]` placeholder fold_content emits."""
    msgs = store.get_messages(conv_id)
    idx = -1
    for i in range(len(msgs) - 1, -1, -1):
        if msgs[i]["role"] == "user":
            idx = i
            break
    if idx == -1:
        return [], "", []
    prefix = []
    for m in msgs[:idx]:
        if m["role"] not in ("user", "assistant"):
            continue
        text = fold_content(m["content"], m.get("attachments")) if m["role"] == "user" else m["content"]
        if text:
            prefix.append({"role": m["role"], "content": text})
    last = msgs[idx]
    return (
        prefix,
        fold_content(last["content"], last.get("attachments")),
        _image_paths(last.get("attachments")),
    )


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
        # The persisted "default" model to fall back to after a temporary vision
        # swap. Updated on every explicit (persisted) switch; the vision
        # auto-swap deliberately does NOT touch it, so an image turn borrows the
        # vision model and then restores this one.
        self._default_model_path = cfg.model_path
        self._default_projection = cfg.projection_model_path
        # State of the current long-running model op (download or switch), polled
        # by the frontend via GET /api/models/status. status:
        #   idle | downloading | loading | ready | error
        self._task = {
            "action": None,
            "target": None,
            "status": "idle",
            "fraction": 0.0,
            "error": None,
        }
        self._task_lock = threading.Lock()

    def model_loaded(self) -> bool:
        return self._loaded.is_set()

    def current_model(self) -> dict:
        """The active model as {path, name, exists}. Cheap; doesn't touch weights."""
        path = self.cfg.model_path
        return {
            "path": path,
            "name": os.path.basename(path) if path else None,
            "exists": bool(path and os.path.isfile(path)),
        }

    # ---- model-task state (download / switch) ----------------------------

    def task_status(self) -> dict:
        with self._task_lock:
            return dict(self._task)

    def _set_task(self, **fields) -> None:
        with self._task_lock:
            self._task.update(fields)

    def _task_busy(self) -> bool:
        with self._task_lock:
            return self._task["status"] in ("downloading", "loading")

    def start_switch(self, path: str) -> dict:
        """Swap the active model to an already-downloaded GGUF (background load).

        Returns {ok: bool, error?: str}. Refuses (ok=False) if a generation is in
        flight or another model task is running — the caller turns that into 409."""
        if not path or not os.path.isfile(path):
            return {"ok": False, "error": f"Model file not found: {path}"}
        if self._active:
            return {"ok": False, "error": "Stop generation before switching models."}
        if self._task_busy():
            return {"ok": False, "error": "A model download or switch is already running."}
        self._set_task(action="switch", target=path, status="loading", fraction=0.0, error=None)
        threading.Thread(target=self._do_switch, args=(path,), daemon=True).start()
        return {"ok": True}

    def start_download(self, spec: str, then_switch: bool = True, extra_specs: list[str] | None = None) -> dict:
        """Download a GGUF by `huggingface:`/`https:` spec, then optionally switch
        to it. Runs on a daemon thread. Refuses if a task is already running.

        `extra_specs` are additional files fetched in the same task before the
        switch decision — used to pull a vision model's mmproj alongside its
        backbone (with `then_switch=False`, since vision is only borrowed)."""
        if not spec:
            return {"ok": False, "error": "No model spec given."}
        if self._task_busy():
            return {"ok": False, "error": "A model download or switch is already running."}
        self._set_task(action="download", target=spec, status="downloading", fraction=0.0, error=None)
        threading.Thread(
            target=self._do_download, args=(spec, then_switch, extra_specs), daemon=True
        ).start()
        return {"ok": True}

    def _on_download_progress(self, *args) -> None:
        """NobodyWho's callback signature isn't contractual: a single fraction
        (0..1) or (downloaded, total) byte counts. Write the fraction to task
        state for the UI to poll."""
        try:
            if len(args) == 1 and isinstance(args[0], (int, float)):
                frac = float(args[0])
                if frac <= 1.0:
                    self._set_task(fraction=max(0.0, min(1.0, frac)))
                return
            if len(args) >= 2 and all(isinstance(a, (int, float)) for a in args[:2]):
                done, total = float(args[0]), float(args[1])
                if total > 0:
                    self._set_task(fraction=max(0.0, min(1.0, done / total)))
        except Exception:  # noqa: BLE001 - progress is best-effort
            pass

    def _do_download(self, spec: str, then_switch: bool, extra_specs: list[str] | None = None) -> None:
        def _fetch(s: str):
            import nobodywho

            try:
                return nobodywho.download_model(s, on_download_progress=self._on_download_progress)
            except TypeError:
                return nobodywho.download_model(s)

        try:
            local_path = _fetch(spec)
            for s in extra_specs or []:
                if s:
                    self._set_task(fraction=0.0)  # reset the bar for the next file
                    _fetch(s)
        except Exception as e:  # noqa: BLE001
            self._set_task(status="error", error=f"Download failed: {e}")
            return
        if not local_path or not os.path.isfile(local_path):
            self._set_task(status="error", error="Download finished but the file is missing.")
            return
        self._set_task(fraction=1.0)
        if then_switch:
            self._do_switch(str(local_path))
        else:
            self._set_task(status="ready", target=str(local_path))

    def _do_switch(self, path: str) -> None:
        self._set_task(status="loading", target=path)
        try:
            from . import models_catalog

            # If the target is a vision model's backbone, pick up its mmproj so a
            # manual switch to it (via the model picker) can also see images.
            proj = models_catalog.projection_for_path(path)
            with self._model_lock:
                self._loaded.clear()
                self._sessions.clear()
                self._model = None
                self.cfg.model_path = path
                self.cfg.projection_model_path = proj
                self.model_error = None
            # Load outside the lock guard's mutation block via _ensure_model
            # (which re-acquires the lock); on failure record the error.
            self._ensure_model()
        except Exception as e:  # noqa: BLE001
            self.model_error = str(e)
            self._set_task(status="error", error=str(e))
            return
        # An explicit switch becomes the new default to restore to after vision.
        self._default_model_path = self.cfg.model_path
        self._default_projection = self.cfg.projection_model_path
        try:
            from . import fetch_model

            fetch_model._write_model_path(path)
        except Exception as e:  # noqa: BLE001 - persistence is best-effort
            print(f"[llm] could not persist model_path: {e}")
        self._set_task(status="ready", error=None)

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

                kwargs = {"use_gpu_if_available": self.cfg.use_gpu}
                # A vision model needs its mmproj; text models pass None (ignored).
                if self.cfg.projection_model_path:
                    kwargs["projection_model_path"] = self.cfg.projection_model_path
                model = nobodywho.Model(self.cfg.model_path, **kwargs)
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

    # ---- vision (image) support ------------------------------------------

    def _ensure_vision_loaded(self) -> str | None:
        """Make sure the vision model is loaded before an image turn.

        Returns None on success, or a user-facing message string if the model
        isn't ready (not downloaded yet → kicks off the download). Performs the
        model swap IN MEMORY only (no config.toml rewrite): the persisted default
        stays the text model, so `_start_restore_default` can switch back."""
        from . import models_catalog

        entry = models_catalog.vision_entry()
        if not entry:
            return "No vision model is configured."
        model_path, proj_path = models_catalog.resolve_cached_paths(entry)
        if not (model_path and proj_path):
            st = self.task_status()
            if st.get("status") == "downloading":
                pct = int((st.get("fraction") or 0) * 100)
                return (
                    f"Downloading vision model ({entry['name']}, ~{entry['size_gb']} GB)… {pct}%. "
                    "Send your image again once it finishes."
                )
            res = self.start_download(
                entry["spec"], then_switch=False, extra_specs=[entry.get("projection")]
            )
            if not res.get("ok"):
                return res.get("error") or "Could not start the vision model download."
            return (
                f"Downloading the vision model ({entry['name']}, ~{entry['size_gb']} GB). "
                "This happens once — send your image again when it's ready."
            )
        # Cached. Already the loaded model? Nothing to do.
        if self._loaded.is_set() and _same_path(model_path, self.cfg.model_path):
            return None
        try:
            with self._model_lock:
                self._loaded.clear()
                self._sessions.clear()
                self._model = None
                self.cfg.model_path = model_path
                self.cfg.projection_model_path = proj_path
                self.model_error = None
            self._set_task(action="switch", target=model_path, status="loading", fraction=0.0, error=None)
            self._ensure_model()
            self._set_task(status="ready", error=None)
        except Exception as e:  # noqa: BLE001
            self.model_error = str(e)
            return f"Failed to load the vision model: {e}"
        return None

    def _is_vision_borrowed(self) -> bool:
        """True if the loaded model differs from the persisted default (i.e. we
        temporarily swapped to vision and owe a restore)."""
        return not _same_path(self.cfg.model_path, self._default_model_path)

    def _start_restore_default(self) -> None:
        """Reload the default (text) model on a daemon thread after a vision turn.

        Runs off the request path so the ~3 s load happens while the user reads
        the answer; the /healthz model_loaded gate disables the composer until
        it's back, reusing the existing warmup UX."""
        if not self._default_model_path or _same_path(self.cfg.model_path, self._default_model_path):
            return
        self._set_task(action="switch", target=self._default_model_path, status="loading", fraction=0.0, error=None)

        def _run():
            try:
                with self._model_lock:
                    self._loaded.clear()
                    self._sessions.clear()
                    self._model = None
                    self.cfg.model_path = self._default_model_path
                    self.cfg.projection_model_path = self._default_projection
                    self.model_error = None
                self._ensure_model()
                self._set_task(status="ready", error=None)
            except Exception as e:  # noqa: BLE001
                self.model_error = str(e)
                self._set_task(status="error", error=str(e))

        threading.Thread(target=_run, daemon=True).start()

    def _build_prompt(self, prompt_text: str, image_paths: list[str]):
        """A plain string when there are no images, else a multimodal Prompt of
        the typed text + one Image part per attached image file."""
        if not image_paths:
            return prompt_text
        import nobodywho

        parts = []
        if prompt_text:
            parts.append(nobodywho.Text(prompt_text))
        for p in image_paths:
            parts.append(nobodywho.Image(p))
        return nobodywho.Prompt(parts)

    def stream(self, conv_id: str, stop_event: threading.Event) -> Iterator[Event]:
        prefix, prompt, image_paths = prompt_from_store(conv_id)

        # An image turn borrows the vision model (loaded here, before we build the
        # Chat, because the swap clears the session registry). Restored afterwards.
        restore_after = False
        if image_paths:
            err = self._ensure_vision_loaded()
            if err:
                yield ("error", err)
                return
            restore_after = self._is_vision_borrowed()

        try:
            try:
                # Lazily loads the model on first use (blocks this worker thread,
                # not the event loop's request handling beyond this generation).
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
                        response = chat.ask(self._build_prompt(prompt, image_paths))
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
        finally:
            if restore_after:
                self._start_restore_default()


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
