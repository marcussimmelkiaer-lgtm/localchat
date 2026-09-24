# CLAUDE.md — LocalChat

Project context for Claude Code. Read this first before working on the app.

## ⚠️ This is the macOS (Apple Silicon) build

This folder (`localchat-mac`) is a port of the original Windows `localchat`. **Most of the document
below describes the original Windows app and its hard-won Windows/WebView2 history — that context is
still accurate and worth reading, but the platform specifics differ here.** What changed for macOS:

- **Launcher**: `run.sh` (POSIX) replaces `run.bat`. `venv/bin/python` instead of
  `venv\Scripts\python.exe`. `chmod +x run.sh` once, then `./run.sh`.
- **First-run guards in `run.sh`** (added after two real Mac install failures — see decision #9):
  before building the venv it (1) **auto-detects a Python 3.11+ interpreter** and (2) on Apple Silicon
  verifies the venv interpreter is **arm64** (not an Intel/Rosetta `python3`). Both fail fast with an
  actionable message instead of an opaque pip/`tomllib` error mid-install. The pip-upgrade step is also
  guarded. **Interpreter detection** (`find_python`): probes `python3.14/3.13/3.12/3.11` **before** plain
  `python3`, because macOS pins `python3` to Apple's 3.9 and Homebrew installs *versioned* names
  (`python3.12`) without always shadowing Apple's on PATH — so a fresh clone works even when `python3`
  alone is 3.9. Falls back to `python3`/`python` if they're ≥3.11.
- **Python 3.11+ is REQUIRED** (not 3.10): `backend/config.py` and `backend/fetch_model.py` import the
  stdlib **`tomllib`**, which only exists on 3.11+. README + run.sh guard reflect this.
- **GPU backend**: **Metal**, not Vulkan. The NobodyWho 1.5.0 macOS wheel
  (`cp38-abi3-macosx_11_0_arm64`) is Metal-built; `pip install` resolves it automatically. `use_gpu`
  / `Model(use_gpu_if_available=True)` are unchanged. **Caveat**: this is the *only* macOS wheel —
  there is **no x86_64 wheel and no sdist**, so an Intel/Rosetta Python can't install nobodywho at all
  (hence the arm64 guard above). Apple Silicon = arm64; the wheel is correct for it.
- **CI** (`.github/workflows/macos-first-run.yml`): runs the real `run.sh` first-run path on a
  `macos-14` (Apple Silicon) runner — venv + `pip install` of the arm64 wheel + `tomllib` import +
  headless `/healthz` boot — plus a job asserting `run.sh` rejects Python 3.10. Seeds a **dummy model**
  (sets `model_path` to a touched file) so `fetch_model` is a no-op and the 2.5 GB download is skipped;
  it validates install/boot only, NOT real download or generation (the runner has no GPU). Actions
  pinned to Node-24 majors (`checkout@v5`, `setup-python@v6`); no `upload-artifact` (still Node 20).
- **Window shell** (`backend/main.py`): now **cross-platform** — it branches on `sys.platform`.
  - macOS uses `_control_loop_native` (calls pywebview's native `minimize()` / `toggle_fullscreen()`
    / `destroy()` directly) + `_initial_geometry_darwin` (sizes to `NSScreen.visibleFrame()`).
    **The WebView2 SetWindowPos workaround does NOT apply on WKWebView** — those native ops are safe
    on Cocoa, so the macOS path is simpler than the Windows one.
  - Windows still uses `_control_loop_win` / `_initial_geometry_win` (the original SetWindowPos
    dance). The "pywebview / WebView2 gotchas" section below is **Windows-only**.
- **pyobjc**: pywebview pulls the Cocoa backend (`pyobjc-*`) automatically on macOS via dependency
  markers — no `requirements.txt` change.
- **Hardware**: Apple Silicon (M5) with **unified memory** — no hard 8 GB VRAM wall, so the 8B model
  is comfortable too. Model cache lives under `~/Library/Application Support/nobodywho/...`.
- **Open verification item**: dragging the frameless window from the custom title bar on macOS — if
  it doesn't drag, add the `pywebview-drag-region` CSS class in `TitleBar.jsx` or set
  `easy_drag=True` in `create_window`.

## What this is

**LocalChat** is a polished, ChatGPT-style **desktop chat app for Windows** that runs a local LLM
entirely on the user's machine via the **NobodyWho** Python bindings (a PyO3 wrapper around
llama.cpp with a Vulkan GPU backend). Monochrome, white-dominant UI. Live token streaming with a
tokens/second readout. Native window (no browser).

Everything runs locally — no cloud, no API keys. The whole app was built in one session (June 2026).

## Hardware / environment (this user's machine)

- **GPU: NVIDIA RTX 4070 Laptop, 8 GB VRAM** (NOT AMD — an early assumption was AMD; it's NVIDIA).
  NobodyWho's **Vulkan** backend drives it fine (Vulkan is cross-vendor).
- Windows 11, **Python 3.12** (venv in `localchat/venv/`), Node 25 / npm 11.
- Model: **Qwen3-4B Q4_K_M** (current) at
  `C:\Users\marcu\AppData\Local\nobodywho\models\Qwen\Qwen3-4B-GGUF\Qwen3-4B-Q4_K_M.gguf`
  — ~50 tok/s, ~2.5 GB VRAM. The **Qwen3-8B Q4_K_M** (~30–34 tok/s, ~5.4 GB VRAM) is still cached at
  `...\Qwen\Qwen3-8B-GGUF\Qwen3-8B-Q4_K_M.gguf`; switch by editing `model_path` in `config.toml`.
  Both downloaded via `nobodywho.download_model`. Same Qwen3 family → identical chat template /
  thinking / sampler, so swapping is a pure config change (no code).

## Architecture

```
run.bat ──> python -m backend.main
                │
                ├─ uvicorn (FastAPI) in a DAEMON THREAD  ── serves SPA + /api + SSE
                │     └─ generation runs in WORKER THREADS (queue ─> SSE), never on the event loop
                └─ pywebview window on the MAIN THREAD (frameless, working-area-sized + fullscreen toggle, WebView2)
                      └─ loads http://127.0.0.1:<port>  (same origin as API → no CORS)
```

- **Frontend**: React 18 + Tailwind 3, built with **Vite 5**. Built output is committed to
  `backend/static/` and served by FastAPI. (No StrictMode; wrapped in an ErrorBoundary.)
- **Backend**: FastAPI + uvicorn; **SSE** streaming via `sse-starlette`; **SQLite (WAL)** persistence.
- **Engine**: one shared NobodyWho `Model` (loaded once on the GPU), one `Chat` per conversation
  (LRU registry). Generation streams tokens through a worker-thread → `queue.Queue` → async SSE bridge.
- **Shell**: pywebview (Edge WebView2), **frameless** window (Normal-state, snapped to the working area;
  fullscreen toggle via `SetWindowPos` — see decision #3).

## Key files

Backend (`backend/`):
- `main.py` — entry point. Picks/locks a 127.0.0.1 port, runs uvicorn in a daemon thread, waits for
  `/healthz`, then opens the pywebview window. Contains `_WindowApi` + `_control_loop` (window
  minimize/close, run on the webview worker thread — see "pywebview gotchas").
- `app.py` — FastAPI factory + lifespan (init DB, build engine; **model is NOT loaded inline at
  startup** — warmed on a background thread via `POST /api/warmup`, see decision #2). Serves `/healthz`,
  `/api/warmup`, and mounts the SPA from `static/`.
- `config.py` — loads `config.toml` + `LOCALCHAT_*` env overrides into a `Config` dataclass.
- `llm.py` — `NobodyWhoEngine` (shared `Model`, sampler, lazy load, `stream()` generator, `stop()` via
  `chat.stop_generation()`); `prompt_from_store()` rebuilds history+prompt from SQLite each turn and
  **folds each user message's attachment text in front of its typed content** (via `files.fold_content`)
  so the model sees uploaded files every turn.
- `files.py` — **file-attachment text extraction** (see decision #7). `extract_attachment({name, mime,
  data_b64}) -> {name, mime, size, text}` decodes base64 and pulls plain text out of CSV (verbatim),
  PDF (`pypdf`), `.xlsx` (`openpyxl`), `.xls` (`xlrd`), `.docx` (`python-docx`); caps each file at
  `MAX_CHARS_PER_FILE` (8000) with a truncation marker; never raises (bad/unsupported/empty → a short
  bracketed note). `fold_content(content, attachments)` builds the model-facing prompt text.
- `sessions.py` — `SessionRegistry`: LRU cache of one `Chat` per conversation, sharing the `Model`.
- `store.py` — SQLite (WAL) conversations + messages; one short-lived connection per op. Messages have
  an `attachments TEXT` column (JSON metadata incl. extracted `text`; additive `ALTER TABLE` migration
  for older DBs). The raw file bytes are NEVER stored — only metadata + the extracted text.
- `schemas.py` — Pydantic request/response models. `AttachmentIn {name, mime, data_b64}` on
  `ChatStreamRequest`; `MessageOut.attachments: list[AttachmentMeta {name, mime, size}]` (the extracted
  `text` is dropped here so it never reaches the UI).
- `routes/chat.py` — `POST /api/chat/stream` (SSE), `/api/chat/regenerate` (SSE), `/api/chat/stop`.
  `/stream` runs each attachment through `files.extract_attachment`, stores the user's **typed text** as
  `content` and the extraction as attachment metadata. Worker thread runs `engine.stream`; async
  generator drains the queue → SSE frames; persists messages.
- `routes/conversations.py` — conversation CRUD.
- `fetch_model.py` — **first-run model bootstrap** (see decision #8). `ensure_model()` is a no-op when
  `config.toml` already names an existing `.gguf`; otherwise it downloads the default
  (`Qwen3-4B-Q4_K_M`, ~2.5 GB, overridable via `LOCALCHAT_DEFAULT_MODEL`) via
  `nobodywho.download_model` into NobodyWho's cache and rewrites `model_path` in `config.toml`. Both
  launchers call `python -m backend.fetch_model` after dep install, before `backend.main`. Never fatal
  — on failure the app still starts and the UI surfaces the model error.

Frontend (`frontend/src/`):
- `App.jsx` — layout shell: `TitleBar` + `Sidebar` + `ChatPane`; owns health/model-ready state.
- `main.jsx` — mounts `<ErrorBoundary><App/></ErrorBoundary>` (no StrictMode).
- `api/llmClient.js` — **the single transport seam**: `sendMessage(...)` → POST + SSE parse. Real
  backend only (the old fake/demo stream was removed at the user's request). The `/stream` POST body
  carries `attachments: [{name, mime, data_b64}]`.
- `api/conversations.js` — REST CRUD client. `api/health.js` — `/healthz` probe.
- `hooks/useConversations.js` — conversations + per-conversation messages + persistence (in-memory
  fallback if backend unreachable). `normMsg()` preserves `attachments` metadata so chips survive reload.
- `hooks/useChatStream.js` — streaming lifecycle: optimistic messages, **RAF-batched token appends**,
  AbortController, `send(text, files)`/`regenerate`/`stop`. Reads attached files to base64 (`FileReader`)
  and sends them; keeps light `{name, mime, size}` metadata on the optimistic user message for the chip.
  Sends client-generated `user_message_id` / `assistant_message_id` so frontend and DB ids match.
- `hooks/useAutoScroll.js` — pin-to-bottom with detach + scroll-to-bottom chip.
- `components/` — `Sidebar`, `ConversationItem`, `ChatPane`, `MessageList`, `Message`, `Markdown`,
  `CodeBlock`, `ThinkingBlock`, `Composer`, `EmptyState`, `TokensPerSec`, `ScrollToBottomChip`,
  `TitleBar`, `ErrorBoundary`, `icons.jsx`. `Composer` has a paperclip file picker (hidden
  `<input type="file">`, accepts `.csv/.pdf/.xlsx/.xls/.docx`) + removable file chips; `Message`
  renders attachment chips (filename + `FileIcon`) above the user bubble.

Root: `run.bat`, `run.sh` (macOS/Linux launcher, with the arm64 + Python-3.11+ first-run guards),
`config.toml` (gitignored, real config), `config.example.toml`, `requirements.txt`, `.gitignore`,
`.gitattributes` (pins `run.sh`=LF, `run.bat`=CRLF), `README.md`, `.github/workflows/macos-first-run.yml`.

## How to run / dev workflow

- **Run the app**: double-click `run.bat` (first run creates the venv, installs `requirements.txt`,
  copies `config.example.toml` → `config.toml`). Opens a frameless window (fullscreen toggle in title bar).
- **Frontend dev**: `cd frontend && npm install && npm run dev` (Vite at :5173, proxies `/api` +
  `/healthz` to the backend at :8765). For the real app you must **`npm run build`** — it outputs to
  `../backend/static/`, which is what the app serves. **Always rebuild after frontend changes.**
- **Backend headless (for testing without the window)**: set `LOCALCHAT_NO_WINDOW=1`, then
  `venv\Scripts\python -m backend.main`. Then hit `http://127.0.0.1:8765`.
- **Config** (`config.toml`): `model_path`, `port`, `n_ctx`, `use_gpu`, `allow_thinking`,
  `system_prompt`, `max_live_chats`, `[sampler]`. Env overrides: `LOCALCHAT_MODEL_PATH`,
  `LOCALCHAT_PORT`, `LOCALCHAT_USE_GPU`, `LOCALCHAT_ALLOW_THINKING`, `LOCALCHAT_DB_PATH`,
  `LOCALCHAT_NO_WINDOW`.

## Verified NobodyWho 1.5.0 API (from introspecting the installed wheel)

Prebuilt wheel `nobodywho-1.5.0-cp38-abi3-win_amd64.whl` (bundles llama.cpp + Vulkan; no build tools).

- `from nobodywho import Chat, ChatAsync, Model, SamplerPresets, SamplerBuilder, TokenStream, tool, ...`
- `Model(model_path, use_gpu_if_available=True, projection_model_path=None, on_download_progress=None)`
  — reference-counted; **share one Model across many Chats**. GPU via Vulkan if available, else CPU.
- `Chat(model, n_ctx=4096, system_prompt=None, template_variables=..., tools=..., sampler=None,
  allow_thinking=None)` — `model` can be a `Model`, a local `.gguf` path, or a `huggingface:` URI.
- `chat.ask(prompt) -> TokenStream`; iterate `for tok in stream` (live) or `stream.completed()` (full).
- History: `get_chat_history()`, `set_chat_history(msgs)`, `reset_history()`, `reset(...)`.
- **`chat.stop_generation()`** — cancels in-flight generation (used by /stop).
- Sampler: `SamplerPresets.temperature(t) | top_k(k) | top_p(p) | greedy() | default()`, or
  `SamplerBuilder()...dist()`. Passed via `sampler=` kwarg.
- **Qwen3 thinking**: pass `template_variables={"enable_thinking": True/False}` (the `allow_thinking`
  kwarg is deprecated). Thinking output is inline `<think>...</think>` then the answer.
- `download_model("huggingface:repo/file.gguf")`, `get_cached_models()`.
- Full notes also in scratchpad `nbw_api_notes.md` (session-temp; reproduce via introspection if gone).

## Important decisions & WHY (don't undo these without reading)

1. **Real-model-only.** All fake/demo streams were removed at the user's request. If no model is
   configured/loadable, the UI shows an error; it never fabricates output.
2. **Background model warmup after the UI loads** (NOT eager-at-startup, NOT lazy-on-first-message).
   `nobodywho.Model(...)` is a native call that **holds the GIL for ~3 s** while loading to GPU
   (verified: it does NOT release the GIL, so a load anywhere blocks the event loop). Loading it
   inline at startup froze the loop before the server served and made conversations fail to appear
   ("chats disappeared"). Instead: the frontend calls **`POST /api/warmup`** once the conversation
   list has rendered (`convo.ready`), which runs `engine.start_warmup()` on a daemon thread. The
   ~3 s GIL freeze then happens after the UI is up — and the UI is a separate WebView2 process, so it
   stays responsive (only backend HTTP pauses briefly). The composer is **disabled with a
   "Preparing model…" hint** (gated on `health.model_loaded`, polled via `/healthz`) until ready, so
   the first message is instant. `engine._model_lock`/`_loaded` make a concurrent first message safe
   (it waits on the same load; no double load).
3. **Frameless + maximized-look window with a working fullscreen toggle.** The window is created in the
   **Normal** WindowState (NOT `maximized=True`) and snapped to the monitor **working area** so it
   looks maximized; the title-bar fullscreen button swaps its bounds to the **full monitor bounds +
   topmost** via `SetWindowPos` only. pywebview's `toggle_fullscreen()` is NOT used — it mutates
   `FormBorderStyle`/`WindowState`/DWM on the live window and crashes WebView2 (see pywebview gotchas).
   `SetWindowPos`-only bounds swaps (the primitive `resize`/`move` use) are safe. Esc exits fullscreen.
4. **Thinking enabled** (`allow_thinking=true`). `Message.jsx` splits `<think>...</think>` and renders
   the reasoning in a collapsible `ThinkingBlock` (code-block styling) above the answer.
5. **Client-supplied message ids.** The frontend generates `user_message_id`/`assistant_message_id`
   and sends them so optimistic UI rows and persisted rows share ids (no reconcile on reload).
6. **NobodyWho logo**: transparent, ink-tinted (#0A0A0A) PNG at `frontend/src/assets/logo-nobodywho.png`
   (made from the user's `Logo-NW-white.png` by trimming + converting white→alpha). In sidebar + empty state.
7. **File uploads = text extraction folded into the prompt** (CSV, PDF, `.xlsx`, `.xls`, `.docx`).
   Files are base64'd in the browser and sent inline in the existing JSON `/stream` body (no multipart
   endpoint — keeps `llmClient.js` the single seam). The backend (`files.py`) extracts plain text and
   `prompt_from_store` folds it in front of the typed message, so **the model path is unchanged** —
   `chat.ask(prompt)` just receives a longer string. Key UX choice: the chat bubble stores/shows **only
   the typed text** (with a filename chip); the (potentially huge) extracted text lives in attachment
   metadata and never renders. Per-file cap 8000 chars (`MAX_CHARS_PER_FILE`) vs `n_ctx=16384` — large
   files are truncated with a marker. **Images ARE now supported** (see decision #12): an uploaded image
   auto-switches to a vision GGUF (Qwen2.5-VL-3B + mmproj) for that turn via a `Prompt([Text, Image])`, then
   switches back — text files still take the fold-into-prompt path unchanged. Scanned/image-only PDFs yield
   `[no extractable text]` (OCR would be a separate addition). Legacy `.doc` (pre-2007 binary) is
   unsupported (no reliable pure-Python reader).
8. **First-run model auto-download** (`backend/fetch_model.py`). The model is NOT committed (a 4B GGUF
   is ~2.5 GB — far over GitHub's 100 MB file / LFS-quota limits), so a fresh clone has no weights.
   Instead the launcher runs `python -m backend.fetch_model` after installing deps: if `config.toml`
   already points at an existing `.gguf` it's a no-op; otherwise it downloads the default Qwen3-4B via
   `nobodywho.download_model` into the NobodyWho cache and writes the resolved path into `config.toml`
   (regex-replacing the first uncommented `model_path =` line). Override the default with the
   `LOCALCHAT_DEFAULT_MODEL` env var (any `huggingface:` / `https://` GGUF). Never fatal — on a failed
   download the app still launches and the UI shows the model error, so the user can set `model_path`
   by hand. First launch therefore needs internet; later launches are offline.
9. **macOS first-run guards in `run.sh`** (two real failures a fresh Mac clone hit). The launcher checks
   prerequisites *before* building the venv and fails fast with guidance instead of an opaque error:
   (a) **Python 3.11+** — `config.py`/`fetch_model.py` import the stdlib `tomllib` (3.11+ only); a 3.9/3.10
   Python (e.g. Apple's CLT 3.9) would install deps then crash at launch with `ModuleNotFoundError:
   tomllib`. **`find_python` auto-detects the interpreter** — it probes `python3.14/3.13/3.12/3.11` before
   plain `python3`, so a fresh clone builds the venv with a real 3.11+ even though macOS pins `python3` to
   Apple's 3.9 and Homebrew only installs versioned `python3.12`-style names (this fixed a real fresh-Mac
   failure where the hardcoded `python3` resolved to 3.9.6). (b) **arm64 interpreter on Apple Silicon** — nobodywho ships *only* an arm64 macOS wheel (no
   x86_64, no sdist), so an Intel/Rosetta `python3` can't resolve it; the guard tells the user to use an
   arm64 Python or `arch -arm64 ./run.sh`. The pip-upgrade step is guarded too. Verified end-to-end on a
   real Apple Silicon GitHub Actions runner (`.github/workflows/macos-first-run.yml`), including a
   negative test that 3.10 is rejected. NOTE: the dummy-model trick means CI does NOT exercise the real
   `download_model` / config-rewrite path or generation — install + boot only.
10. **Default system prompt = business/data-analysis assistant** (`config.example.toml`, and the user's
   local `config.toml`). Replaced the generic "You are a helpful assistant." with a concise (~150-word)
   prompt that leans into the file-upload feature (CSV/Excel/PDF/Word analysis), hard-codes "never
   fabricate numbers/facts," asks for step-by-step verified calculations, Markdown tables, and a
   professional tone — kept short to preserve the `n_ctx` budget for uploaded file text. Stored as a
   TOML triple-quoted multi-line string (`tomllib` parses it fine). Read at startup, so a relaunch picks
   it up; history rebuilt per turn means existing chats get the new prompt too.
11. **In-app model download & switching** (built — was decision-#2's deferred "Known issue"). A runtime
   model manager: curated Qwen3 catalog (1.7B/4B/8B Q4_K_M) **+** a forgiving Hugging Face download field
   (accepts a **bare repo id** — see #14 — as well as full specs/URLs), with
   download progress, runtime switch, and delete-to-reclaim-disk. **Reuses the existing load lifecycle in
   reverse**: a swap clears `engine._loaded` + the `SessionRegistry`, nulls `_model`, sets the new
   `cfg.model_path`, and re-runs `_ensure_model()` under `_model_lock` — so the existing `/healthz`
   `model_loaded` gate auto-disables the composer ("Preparing model…") during the reload, no UI special-
   casing. Engine gains `current_model()`, a polled task-state (`idle|downloading|loading|ready|error` via
   `task_status()`), `start_switch()`, `start_download()` (both daemon-threaded); `SessionRegistry.clear()`
   is safe mid-generation (a running `stream()` holds its `Chat` in a local). New `backend/models_catalog.py`
   (matches catalog specs against `nobodywho.get_cached_models()` `(path, size)` tuples by path-tail; this is
   also the authoritative delete guard — only files NobodyWho reports as cached can be deleted) and
   `backend/routes/models.py` (`GET /api/models`, `GET /api/models/status`, `POST .../download`,
   `POST .../switch`, `DELETE /api/models`). The choice is persisted by reusing `fetch_model._write_model_path`.
   **Switching is blocked while generating**: `routes/models.py` checks `app.state.stops` (registered
   synchronously when a `/chat/stream` starts → no startup race; the engine's `_active` check is defense-in-
   depth) and returns 409 → "Stop generation before switching models." Frontend: `api/models.js`,
   `hooks/useModelManager.js` (status polling + actions), `components/ModelPicker.jsx` (modal) +
   `ModelManagerButton.jsx` (sidebar footer), wired in `App.jsx`/`Sidebar.jsx`. **Cross-platform by
   construction**: never hardcodes the cache dir (Win `%LOCALAPPDATA%\nobodywho` vs mac
   `~/Library/Application Support/nobodywho`) — paths come from `get_cached_models()`/`download_model`;
   comparisons use `os.path.samefile`/normalised tails so Windows case/slash diffs don't false-mismatch;
   `_write_model_path` emits forward slashes (valid TOML on both). Verified headless on Windows: list,
   switch 4B↔8B (+ config rewrite + generation on the swapped model), all guards (delete-active 409,
   delete-bogus 400, switch-missing 409, switch-while-streaming 409 incl. the frame-0 instant). The real
   ~1 GB download path (same `download_model` as `fetch_model.py`) is left to manual one-time verification.
12. **Vision (image) uploads via a borrowed vision model** (built — was decision-#7's deferred "future step").
   A user can attach a screenshot/image and ask about it. **NobodyWho 1.5.0 already exposes the API** (verified in
   `venv/.../nobodywho/__init__.pyi`): `Model(model_path, projection_model_path=<mmproj>)`, and `chat.ask(prompt)`
   accepts a `Prompt([Text(...), Image(path)])` (`Image` takes a **file path only** — no base64/bytes). Because 8 GB
   VRAM holds one model at a time, an **image turn auto-switches** to a small vision model (**Qwen2.5-VL-3B** + its
   `mmproj-...-f16.gguf`, from `ggml-org/Qwen2.5-VL-3B-Instruct-GGUF`), generates, then **switches back** to the
   persisted text model (`llm._start_restore_default`, on a daemon thread so the ~3 s reload hides behind the answer
   and the existing `/healthz model_loaded` gate disables the composer meanwhile). The swap is **in-memory only — it
   deliberately does NOT rewrite `config.toml`** (unlike the manual switch), so the text model stays the default;
   `engine._default_model_path/_default_projection` track what to restore to (updated only by persisted switches).
   Key pieces: catalog entry gains `projection` + `vision: True` (two-file `downloaded`/resolve via
   `models_catalog.resolve_cached_paths` / `projection_for_path`); `Config.projection_model_path`
   (+`LOCALCHAT_PROJECTION_PATH`); `_ensure_model` passes it to `Model(...)`; `prompt_from_store` now returns
   `(prefix, prompt, image_paths)` (only the **current** turn can carry images — history is text-only via
   `set_chat_history`, so prior images survive as the `[Image: name]` placeholder `fold_content` emits); `stream()`
   calls `_ensure_vision_loaded()` then `_build_prompt`. **Image bytes ARE stored on disk** (departure from #7's "raw
   bytes never stored"): `files.save_image` downscales to ≤1024px and re-encodes to JPEG (Pillow) under
   `uploads/<conv>/<msg>_<idx>.jpg` — needed because `Image()` wants a path, for regenerate, and for reload
   thumbnails; deleted on conversation delete (`files.cleanup_conversation_images`). New `routes/attachments.py`
   (`GET /api/attachments/{message_id}/{idx}`, FileResponse, guarded to a message's own image attachments) re-serves
   thumbnails after reload; the live bubble uses a local object-URL preview. **Download-on-first-use**: if the vision
   model isn't cached when an image arrives, `_ensure_vision_loaded` kicks off the two-file download
   (`start_download(..., then_switch=False, extra_specs=[mmproj])`) and returns a "Downloading… resend when ready"
   message as the turn's error; it's also pre-downloadable from the ModelPicker (a vision row downloads both files, no
   switch). Frontend: `Composer` accepts images + shows chip thumbnails; `useChatStream` keeps a `previewUrl`;
   `Message`/`AttachmentChips` render `<img>` (previewUrl live, endpoint on reload); `AttachmentMeta` gained
   `is_image` (still strips `path`/`text`). Added `Pillow` to `requirements.txt`. **Verified headless on Windows** (no
   GPU/download): catalog two-file wiring, `save_image` downscale+JPEG, image tagging, `[Image:]` fold placeholder,
   `_build_prompt` (Prompt vs str), `_same_path`/borrow logic, `_ensure_vision_loaded` download-wiring (mmproj as
   extra_spec, `then_switch=False`), `prompt_from_store` 3-tuple + image_paths, the attachments endpoint + 404 guards,
   `MessageOut` stripping, and cleanup. The real ~3.3 GB download + live GPU vision generation + swap-back is left to
   **manual one-time verification** (CI has no GPU; consistent with #8/#11). Follow-ups: multimodal history (needs
   NobodyWho image-history support), OCR for scanned PDFs, surfacing vision-download progress during a chat (currently
   only visible in the Models modal).
13. **`n_ctx` raised 4096 → 16384** (`config.toml` + `config.example.toml`). 4096 was an over-conservative
   default, not a hardware/model limit — Qwen3/Qwen2.5-VL are trained for 32768 tokens. The real constraint is
   VRAM: llama.cpp allocates the **full `n_ctx` KV-cache upfront** at load, so it trades VRAM for headroom
   (system prompt + history + folded file text + image tokens + reply). On the 8 GB 4070, 16384 (~2.4 GB KV
   with a 3–4B model, total ~5.7 GB) is the sweet spot with ~2 GB spare; **32768 (~4.7 GB KV) risks OOM on a
   4B** — drop to 8192 if a bigger model fails to load. Read at startup + history rebuilt per turn, so a relaunch
   applies it to existing chats too. (NB: the local `config.toml` currently points `model_path` at a small
   `Mythos-nano.Q4_K_M` model, which leaves even more room than the Qwen3-4B the docs above assume.)
14. **Forgiving Hugging Face download field** (built on top of #11's custom-spec field). Users naturally copy
   a repo id off a HF page (`Qwen/Qwen3-0.6B`), but `download_model` wants a **concrete GGUF file**
   (`huggingface:owner/repo/file.gguf`) — and a base repo like `Qwen/Qwen3-0.6B` is safetensors-only; the GGUF
   lives in a sibling `…-GGUF` repo and still needs a quant chosen. New `models_catalog.resolve_spec(user_input)`
   bridges the gap and accepts, in order: a local file path (as-is); a full `huggingface:…` spec (as-is);
   the same without the prefix; a direct `https://…/file.gguf` URL (as-is) or a HF page/blob/resolve URL
   (reduced to a repo id, then resolved); and a **bare `owner/name`** — it queries the public HF API
   (`https://huggingface.co/api/models/{repo}`, stdlib `urllib`, no new dep) for `.gguf` siblings, trying
   `owner/name` then `owner/name-GGUF`, and picks a quant (**Q4_K_M preferred**, then fallbacks in
   `_PREFERRED_QUANTS`; single-file GGUFs preferred over `-00001-of-000NN` shards since `download_model`
   fetches one file). An optional **`:QUANT` suffix** (`Qwen/Qwen3-0.6B:Q5_K_M`) forces a specific quant —
   and if that repo doesn't ship it, resolution **fails with a clear message** rather than silently fetching a
   different (possibly much larger) file. Wired into `llm._do_download`: resolution runs on the existing
   daemon thread (it may hit the network), updates the task `target` to the resolved file, and surfaces
   `ValueError`s through the normal task-error path; catalog-supplied `extra_specs` (mmproj) are already
   concrete and left unresolved. Frontend `ModelPicker.jsx`: field relabeled "Download from Hugging Face",
   placeholder `Qwen/Qwen3-0.6B`, with a hint line. Verified: offline forms + **live** resolution of
   `Qwen/Qwen3-0.6B` → `…Qwen3-0.6B-GGUF/Qwen3-0.6B-Q8_0.gguf` (Qwen's small-model GGUF repos ship only Q8_0,
   same quirk noted for 1.7B in the catalog) + explicit-quant-not-found erroring. The actual download+switch on
   a resolved model is left to manual one-time verification (consistent with #8/#11).
15. **Downloadable installers (Windows + macOS) — ONE file per OS, no models inside** (built). Ship the app as
   double-click installers instead of git-clone-and-setup: `LocalChat-Setup-x64.exe` (~37 MB) and
   `LocalChat-arm64.dmg`. Two layers: **PyInstaller** (`packaging/localchat.spec`) freezes a small onedir app —
   Python + deps + the native `nobodywho.pyd` + `backend/static`; then a **platform installer** (Inno Setup / DMG)
   wraps it. **Why no models (user decision, Sep 2026):** an earlier version preloaded 3 models (Qwen3-4B/1.7B/0.6B,
   ~5 GB), but Windows won't run a `Setup.exe` much over ~4 GB, so Inno had to **disk-span** into `Setup.exe` +
   `-1/-2/-3.bin` — not a single file, and too big for GitHub releases. The user chose the **slim, download-on-first-
   run** variant: `NobodyWhoEngine._start_first_run_download` (called from `start_warmup`, **frozen builds only**)
   kicks off the existing download→switch task (#11) for `fetch_model.default_spec()` (Qwen3-4B,
   `LOCALCHAT_DEFAULT_MODEL` override) when `model_path` doesn't exist; `_do_switch` persists `model_path`.
   `/healthz` now includes `model_task`, and the composer shows **"Downloading model… N%"** (`App.jsx` → `ChatPane`
   `downloadPct`). A failed download with no model loaded sets `model_error` (via `_download_failed`) with a "needs
   internet once — reconnect and restart, or use Models" hint; the next launch retries. **First launch needs internet
   once**; afterward fully offline. Source checkouts unchanged (run.sh/run.bat still run `fetch_model`, and a hand-set
   bad path errors rather than triggering a 2.5 GB fetch). **Key enabler — writable paths** (`backend/paths.py`): a
   frozen bundle is read-only, so `config.toml`/DB/`uploads/` moved to a per-user data dir (`%LOCALAPPDATA%\LocalChat`
   / `~/Library/Application Support/LocalChat`) while static/template come from `bundle_dir()`. **Dev is unchanged**:
   not-frozen → `data_dir()==bundle_dir()==repo root`. `backend/bootstrap.py` runs **only when frozen** (first in
   `main.main`): seeds `config.toml` from the bundled template and adopts an already-cached Qwen3 model
   (`DEFAULT_CANDIDATES`) so a reinstall doesn't re-download. **Windows** (`packaging/windows/localchat.iss` +
   `build_win.ps1`): Inno Setup, **per-user** (`PrivilegesRequired=lowest`), app → `%LOCALAPPDATA%\Programs\LocalChat`,
   `ExtraDiskSpaceRequired` reserves room for the model, WebView2 Evergreen bootstrapper bundled; `build_win.ps1`
   falls back to `python` on PATH when there's no venv (CI). Inno Setup is installed via winget at
   `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` (probed). **macOS** (`packaging/macos/build_mac.sh`): PyInstaller
   `.app` (**arm64-only**) → `.dmg`; same first-run download as Windows (no more in-bundle seed models). **Signing
   deferred** (per user): unsigned — Windows SmartScreen "More info → Run anyway", macOS right-click→Open / `xattr`;
   hooks stubbed in `build_mac.sh` + the `.iss`/ps1. **Verified on Windows**: built the single 37 MB `Setup.exe`,
   silent-installed it **alone** (no side files) into a scratch dir, installed app booted headless → `/api/warmup`
   loaded the model on the GPU; first-run download path verified in source mode with `is_frozen` patched (download →
   switch → config persisted; bogus spec → `model_error` surfaced). NB: installer test installs share the AppId —
   uninstalling a scratch install removes the real install's uninstall entry (reinstall to restore). **CI**
   (`.github/workflows/build-installers.yml`, `workflow_dispatch` + `v*` tags): `macos-14` builds the `.dmg`,
   `windows-latest` builds the `.exe`, each uploaded as an artifact — how the **macOS `.dmg` gets produced**.
   PyInstaller is **build-only**, deliberately NOT in `requirements.txt`. **macOS build hardening (unrun)**: the
   spec's `IS_MAC` branch `collect_all`s the pyobjc frameworks (Cocoa backend imports them dynamically);
   `build_mac.sh` guards **arm64 AND Python 3.11+** (keep it **LF** — `.gitattributes` `*.sh eol=lf`). See
   `packaging/README.md` + the macOS TODO under Known issues.

## Token throughput theory (asked but NOT implemented — for future reference)

Single-user decode is **memory-bandwidth bound at batch 1**, not compute bound: each token streams the
whole weight set from VRAM once, so `tok/s ≈ bandwidth ÷ model_bytes`. "GPU utilization %" is misleading
(it's warp residency, not FLOP usage). Levers, none applied this session: smaller/more-quantized model
(biggest, = changing model); unthrottle the GPU (the laptop 4070 is power-capped ~42/95 W — already maxed
per the user); flash-attention / KV-cache quant (only help at *long* context, don't move short-chat tok/s,
and depend on NobodyWho exposing the knobs); **speculative decoding** (a tiny draft model verified in a
batched pass — the only batch-1 trick that beats the bandwidth wall *without* changing the current model's
weights, but needs NobodyWho draft-model support, unconfirmed in 1.5.0). Conclusion reached with the user:
keeping the model + maxed GPU + ruling out speculative decoding ⇒ effectively at the ceiling.

## pywebview / WebView2 gotchas (HARD-WON — this caused many crashes)

- **Calling pywebview's window STATE ops (`maximize`, `toggle_fullscreen`, setting `WindowState` /
  `FormBorderStyle`) at runtime CRASHES** this WebView2 build (exit `-805306369`) — from a js_api
  callback, a spawned thread, or the worker thread, once the real SPA is loaded. `fullscreen=True` at
  *creation* also crashes. pywebview's `toggle_fullscreen()` does invasive native surgery —
  FormBorderStyle + WindowState + SetWindowPos + DWM on the live window (see `winforms.py:550`).
- **BUT bare `SetWindowPos` bounds/z-order changes ARE SAFE** (the primitive pywebview's own
  `resize()`/`move()` use, lines 600–643 — no WindowState/FormBorderStyle/DWM). So fullscreen IS
  implemented (see decision #3 / `main.py:_control_loop`): create the window in **Normal** state (never
  `maximized=True`), snap it to the working area for the maximized look, and swap to full monitor
  bounds + `HWND_TOPMOST` for fullscreen — all via `SetWindowPos` only. Verified working on this build.
  (Confirmed WebView2 itself can fullscreen fine — Tauri/Electron do; it was purely pywebview's WinForms
  state surgery that crashed.)
- **`minimize` / `restore` / `destroy(close)` at runtime are SAFE.** Window controls go through a
  command queue drained by `_control_loop` running on the `webview.start(func, ...)` worker thread.
- **Keep js_api attributes underscore-private** (`_window`, `_cmds`). pywebview tries to serialize
  public api attributes to JS; a public `window` reference makes it walk the WinForms object graph and
  spam the console with `AccessibilityObject ... maximum recursion depth exceeded` (non-fatal but ugly).
- `run.bat` does setup in its console, then **`start "" venv\Scripts\pythonw.exe -m backend.main`** so no terminal
  stays open. The old "pythonw instant-close" was uvicorn crashing on `sys.stdout.isatty()` with no console
  (stdout/stderr are `None`); `main._ensure_std_streams()` now redirects both to `LocalChat.log` in the data dir
  (repo root in dev) — same fix makes the windowed (`console=False`) frozen build start. Live logs: run
  `venv\Scripts\python.exe -m backend.main` directly.
- Can't screenshot the pywebview window directly. To "see" the SPA, run the server headless and use
  Edge headless: `msedge --headless=new --disable-gpu --user-data-dir=<tmp> --screenshot=<png>
  --virtual-time-budget=8000 http://127.0.0.1:8765`. (The custom TitleBar only renders inside pywebview.)
- Test SSE with Python `urllib` streaming — PowerShell `Invoke-WebRequest` can't read a stream in
  non-interactive mode.

## Known issues / possible next steps

- **GPU is power-throttled**: ~42 W of a 95 W limit (laptop power policy), pinning clocks to ~960 MHz.
  Already maxed at that clock (94% GPU / 91% mem util). To go faster: set the laptop vendor app to
  Performance mode, NVIDIA Control Panel → "Prefer maximum performance", Windows "Best performance".
  `nvidia-smi -pl` is blocked on laptop GPUs. (Switching 8B→4B already bought ~1.5× — ~50 vs ~33 tok/s.)
- **In-app model switching/downloading** — **DONE** (see decisions #11 + #14): runtime model picker (curated
  Qwen3 catalog + a forgiving HF download field that accepts a bare `owner/name` repo id, `:QUANT` suffix,
  full specs, or URLs — `models_catalog.resolve_spec`), download with progress, switch, and delete, via
  `backend/routes/models.py` + the sidebar `ModelPicker`. Editing `model_path` in `config.toml` by hand
  still works as a fallback. Possible follow-ups: more catalog entries / non-Qwen families (caveat: a
  different chat template/sampler may need tuning), and surfacing the live download progress in CI.
- **Downloadable installers** — **Windows DONE, macOS needs a real build** (see decision #15). Windows single-file
  `dist/installer/LocalChat-Setup-x64.exe` built + silent-install-verified on this machine. Outstanding:
  - **macOS `.dmg` has never been built/run** — the scripts + spec exist but are unexercised. Build on an
    **Apple-Silicon, Python 3.11+** Mac: `pip install -r requirements.txt pyinstaller` →
    `./packaging/macos/build_mac.sh`. Or trigger the `macos-14` CI job (`.github/workflows/build-installers.yml`).
  - **Verify the frozen `.app` opens a window** (top risk — pyobjc dynamic imports; spec now `collect_all`s them,
    but confirm). Quick isolation: `LOCALCHAT_NO_WINDOW=1 dist/LocalChat.app/Contents/MacOS/LocalChat` + curl
    `/healthz` — if that works but the GUI doesn't, it's purely a pyobjc/window issue.
  - **Frameless-window drag on WKWebView** (also the open item under decision #12-era notes / top of this file):
    if the title bar doesn't drag, add the `pywebview-drag-region` CSS class in `TitleBar.jsx` or `easy_drag=True`.
  - **Real first-run download from a clean machine** not yet exercised in a frozen build (this machine already has
    the model cached, so bootstrap adopts it); the path itself was verified in source mode.
  - **Signing/notarization** (deferred per user): unsigned today (Win SmartScreen "Run anyway"; mac right-click →
    Open / `xattr -dr com.apple.quarantine`). Wire the stubbed `codesign`/`notarytool` block in `build_mac.sh` and
    a `signtool` step in `build_win.ps1` once the NobodyWho Apple Developer + Authenticode certs exist.
  - **Hosting**: installers are now small enough for GitHub release assets.
- **No LaTeX rendering**: Qwen3 sometimes emits `$...$` / `$$...$$`; the markdown renderer shows it raw.
  Could add `remark-math` + KaTeX.
- **Fullscreen** works (title-bar button + Esc, via `SetWindowPos` bounds swap — see gotchas/decision #3).
  There's still no free-floating *resize* toggle (the window stays at working-area or full-screen bounds).
- **History fidelity**: each turn rebuilds the Chat's history from SQLite via `set_chat_history`
  (`prompt_from_store`), so no KV-cache reuse across turns. Fine for short chats; could optimize later.
- **Image/vision uploads** — **DONE** (see decision #12): an image auto-switches to Qwen2.5-VL-3B (+mmproj)
  for that turn (borrowed, then restored) and answers via `Prompt([Text, Image(path)])`. Follow-ups:
  multimodal chat *history* (only the current turn's image is passed; prior images degrade to an
  `[Image: name]` placeholder — needs NobodyWho image-history support), surfacing vision-download progress
  during a chat (today only in the Models modal), and OCR for scanned PDFs/images (Tesseract).
- The repo also contains an unrelated `../github-dashboard` project — not part of LocalChat.

## Status (current)

Working and verified end-to-end: GPU streaming, tokens/sec readout, stop/cancel + stop→resend
integrity, regenerate, SQLite persistence across restarts, Qwen3 thinking in a collapsible box,
NobodyWho logo. The app launches via `run.bat`.

**File uploads** (decision #7) verified end-to-end: CSV + PDF tested live against the model (model
correctly answered a question about an attached CSV); `.xlsx`/`.xls`/`.docx` extraction unit-tested with
real generated files; attachment-column DB migration tested on an old-schema DB. Requires `pypdf`,
`openpyxl`, `python-docx`, `xlrd` (in `requirements.txt`). Frontend rebuilt to `backend/static/`.

**Latest session (added on top of the above):**
- **Fullscreen** (decision #3 / gotchas): title-bar button + Esc, via `SetWindowPos` bounds-swap
  (Normal-state window, working-area ↔ full-monitor+topmost). Avoids pywebview's crashing
  `toggle_fullscreen`. User-confirmed working. Files: `main.py` (`_control_loop`, `_initial_geometry`),
  `TitleBar.jsx`, `icons.jsx` (`ExitFullscreenIcon`).
- **Background model warmup** (decision #2): `engine.start_warmup()` + `POST /api/warmup`, triggered by
  the frontend after the conversation list renders; composer disabled with "Preparing model…" until
  `/healthz` reports `model_loaded`. Moves the ~3 s GIL-holding load off the first message. Verified the
  load holds the GIL (~3 s) and that the background-thread warmup loads the model without error.
- **Model swap 8B→4B**: now running **Qwen3-4B Q4_K_M** (~50 tok/s, ~2.5 GB VRAM); 8B still cached.
  Pure `config.toml` change (same Qwen3 family). Verified loading + generation on GPU.
- Researched but NOT built: in-app model picker/downloader (see Known issues).

**Most recent session (packaging + HF download UX):**
- **Forgiving Hugging Face download field** (decision #14): the model picker accepts a bare `owner/name`
  repo id (`Qwen/Qwen3-0.6B`), a `:QUANT` suffix, full specs, or URLs, resolved via
  `models_catalog.resolve_spec` (queries the HF API, prefers Q4_K_M). Verified offline + live.
- **Downloadable installers** (decision #15): one installer file per OS (`Setup.exe` ~37 MB / `.dmg`), no
  models inside — the app downloads Qwen3-4B on first launch with progress in the composer. New
  `backend/paths.py` (writable-data-dir vs read-only-bundle), `backend/bootstrap.py` (frozen-only first-run setup),
  `run_app.py`, `packaging/` (PyInstaller spec, Inno `.iss`, `build_win.ps1`, `build_mac.sh`) and
  `.github/workflows/build-installers.yml`. **Dev workflow unchanged**. **Windows single-file installer built +
  silent-install-verified on this machine**. **macOS build is written but UNRUN** — see the macOS TODO under Known
  issues. Signing deferred per user.
- CURRENT STATE: everything above works on Windows; the outstanding work is the **macOS `.dmg` build/verify**
  and (whenever ready) **signing**.
