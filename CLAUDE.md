# CLAUDE.md — LocalChat

Project context for Claude Code. Read this first before working on the app.

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

Root: `run.bat`, `config.toml` (gitignored, real config), `config.example.toml`, `requirements.txt`,
`.gitignore`, `README.md`.

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
   metadata and never renders. Per-file cap 8000 chars (`MAX_CHARS_PER_FILE`) vs `n_ctx=4096` — large
   files are truncated with a marker. **Images are deliberately NOT supported**: Qwen3-8B is text-only;
   true vision would need a vision GGUF + `projection_model_path` (mmproj) and a reworked engine path
   that passes `ImagePart`s — documented as a future step. Scanned/image-only PDFs yield
   `[no extractable text]` (OCR would be a separate addition). Legacy `.doc` (pre-2007 binary) is
   unsupported (no reliable pure-Python reader).

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
- `run.bat` uses **`python.exe`** (not `pythonw` via `start` — that caused an instant-close).
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
- **In-app model switching/downloading** (researched, not built): a runtime model picker + HF download
  manager is ~1–2 days and reuses the warmup lock/poll/disabled-composer infra. Free path today is just
  editing `model_path` in `config.toml` (both 4B and 8B are cached). See the session log / decision #2.
- **No LaTeX rendering**: Qwen3 sometimes emits `$...$` / `$$...$$`; the markdown renderer shows it raw.
  Could add `remark-math` + KaTeX.
- **Fullscreen** works (title-bar button + Esc, via `SetWindowPos` bounds swap — see gotchas/decision #3).
  There's still no free-floating *resize* toggle (the window stays at working-area or full-screen bounds).
- **History fidelity**: each turn rebuilds the Chat's history from SQLite via `set_chat_history`
  (`prompt_from_store`), so no KV-cache reuse across turns. Fine for short chats; could optimize later.
- **Image/vision uploads** (next step for file uploads, decision #7): needs a vision-capable GGUF +
  `projection_model_path` (mmproj) and an engine path using NobodyWho's `Prompt`/`ImagePart` API —
  likely a small VL model loaded on demand to respect the 8 GB VRAM budget. OCR for scanned PDFs/images
  (Tesseract) is a related future addition.
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
