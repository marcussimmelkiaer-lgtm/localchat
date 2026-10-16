# CLAUDE.md — LocalChat

Project context for Claude Code. Read this first before working on the app.

## What this is

**LocalChat** is a ChatGPT-style **desktop chat app for Windows and macOS (Apple Silicon)** that runs a
local LLM entirely on the user's machine via the **NobodyWho** Python bindings (a PyO3 wrapper around
llama.cpp; **Vulkan** GPU backend on Windows, **Metal** on macOS). Monochrome, white-dominant UI, live
token streaming with a tokens/second readout. No cloud, no API keys.

It is distributed for a **professors' workshop**: participants `git clone` a slim per-OS repo and
double-click `Start LocalChat.bat` / `Start LocalChat.command` (decision #16). The goal of the workshop is
to "play with the code to see how the model behaves" (config.toml, `backend/tools.py`).

## Hardware / environment (this user's machine)

- **GPU: NVIDIA RTX 4070 Laptop, 8 GB VRAM** (NOT AMD). NobodyWho's Vulkan backend drives it.
- Windows 11, Python 3.12 (uv-managed, venv in `venv/`), Flutter SDK at `%LOCALAPPDATA%\flutter`,
  **Windows Developer Mode ON** (needed for `flutter build windows`).
- Models cached in `C:\Users\marcu\AppData\Local\nobodywho\models\...` (Qwen3-0.6B/4B/8B etc.). The
  workshop default is **Qwen3-0.6B Q8_0** (~640 MB); the 4B (~50 tok/s, ~2.5 GB VRAM) is the "balanced /
  file analysis" choice. Switch in the app's Models picker or by editing `model_path` in `config.toml`.
- macOS: Apple Silicon only (nobodywho ships only an arm64 macOS wheel). Model cache lives under
  `~/Library/Application Support/nobodywho/...`. Unified memory, so no 8 GB VRAM wall.

## Architecture

```
Start LocalChat.bat / .command
   │  (first run: uv + Python 3.12 into .uv/, venv/, pip install, config.toml, model download,
   │   unpack app/LocalChat.zip)
   └─> Flutter desktop app (desktop/)
          └─ spawns venv python -u -m backend.main  (LOCALCHAT_PARENT_PID set)
                 ├─ reads the port from the "listening on http://…" line
                 └─ uvicorn (FastAPI) on 127.0.0.1:<port>  ── REST + SSE
                       └─ generation runs in WORKER THREADS (queue ─> SSE), never on the event loop
```

- **Desktop app**: Flutter (Dart) in `desktop/`, packages `http`, `file_selector`, `url_launcher`,
  `gpt_markdown` (Markdown/LaTeX/code), `window_manager`. App-drawn title bar.
- **Backend**: FastAPI + uvicorn; **SSE** streaming via `sse-starlette`; **SQLite (WAL)** persistence.
  API only (the old React browser UI was removed Oct 16, decision #22).
- **Engine**: one shared NobodyWho `Model` (loaded once on the GPU), one `Chat` per conversation
  (LRU registry). Generation streams tokens through a worker-thread → `queue.Queue` → async SSE bridge.

## Key files

Backend (`backend/`):
- `main.py` — entry point, the HTTP server only. Prints `listening on http://…`, serves until
  `/api/shutdown` (or the parent-PID watchdog sees the app is gone), then `os._exit(0)`.
- `app.py` — FastAPI factory + lifespan (init DB, build engine; **model is NOT loaded inline at
  startup** — warmed on a background thread via `POST /api/warmup`, decision #2). Serves `/healthz`,
  `/api/warmup`, `/api/shutdown`.
- `config.py` — loads `config.toml` + `LOCALCHAT_*` env overrides into a `Config` dataclass.
- `paths.py` — `REPO_ROOT` and `state_dir()` (`LocalChat data/`, with migration of old root-level files).
- `llm.py` — `NobodyWhoEngine` (shared `Model`, sampler, lazy load, `stream()` generator, `stop()` via
  `chat.stop_generation()`, model download/switch tasks, vision borrow/restore); `prompt_from_store()`
  rebuilds history+prompt from SQLite each turn and folds attachment text in front of the typed content.
- `files.py` — attachment text extraction (CSV, PDF, `.xlsx`, `.xls`, `.docx`; decision #7) and image
  saving (decision #12).
- `tools.py` / `tool_support.py` — optional model tools (time, weather, Wikipedia, pandas, RAG), off by
  default, switched in `config.toml [tools]`; decision #17.
- `sessions.py` — `SessionRegistry`: LRU cache of one `Chat` per conversation, sharing the `Model`.
- `store.py` — SQLite (WAL) conversations + messages; one short-lived connection per op. Messages have
  `attachments` and `tool_calls` JSON columns (additive migrations). Raw file bytes are never stored
  (images are, on disk — decision #12).
- `schemas.py` — Pydantic request/response models.
- `routes/chat.py` — `POST /api/chat/stream` (SSE), `/api/chat/regenerate` (SSE), `/api/chat/stop`.
- `routes/conversations.py` — conversation CRUD. `routes/models.py` — model manager (decision #11).
  `routes/attachments.py` — re-serves stored images.
- `fetch_model.py` — first-run model bootstrap (decision #8). `models_catalog.py` — curated catalog +
  HF spec resolution (decisions #11, #14).
- `requirements.txt`, `config.example.toml` — live in `backend/` (decision #19).

Desktop app (`desktop/lib/`):
- `backend.dart` — finds the LocalChat folder (walks up to `backend/main.py`; `LOCALCHAT_ROOT`
  overrides), starts/stops the backend, writes its output to `LocalChat data/LocalChat.log`.
- `api.dart` — HTTP + SSE client. `state.dart` — conversations, streaming, health polling, model manager.
- `main.dart` — window setup, lifecycle (`AppLifecycleListener.onExitRequested` → shutdown).
- `ui/` — `chat.dart`, `sidebar.dart`, `model_picker.dart`, `title_bar.dart`, `theme.dart`.
- `text.dart` — think-block / maths helpers. Tests in `desktop/test/`.

Root and tooling:
- `Start LocalChat.bat` / `Start LocalChat.command` — the launchers (decision #16).
- `config.toml` (gitignored, real config), `data/sales_2025.csv` (pandas example), `rag/employee_handbook.md`
  (RAG example, fictional). Everything else in `rag/` is gitignored (test documents).
- `packaging/export_workshop.py` (slim-repo export), `packaging/smoke_test.py` (CI check of a running app),
  `packaging/workshop/README-<os>.md`.
- `.github/workflows/desktop-app.yml` (reusable: builds the Flutter app per OS) and
  `workshop-first-run.yml` (export + launcher + real model download + chat + quit, both OSes).
- `.gitattributes` pins `*.command`/`*.sh` = LF, `*.bat` = CRLF.

## How to run / dev workflow

- **Run the app**: double-click `Start LocalChat.bat` / `Start LocalChat.command`. In this dev repo the
  launcher falls back to `desktop/build/...` when there's no `app/LocalChat.zip`.
- **Build the desktop app**: `cd desktop && flutter build windows` (~50 s; macOS builds need CI or a Mac).
  `flutter test` for the unit/UI tests.
- **Backend alone**: `venv\Scripts\python -m backend.main` (prints its address). Test SSE with Python
  `urllib` streaming — PowerShell `Invoke-WebRequest` can't read a stream non-interactively.
- **Config** (`config.toml`): `system_prompt`, `allow_thinking`, `file_uploads`, `model_path`,
  `[sampler]`, `[tools]` (`time`/`weather`/`wikipedia`/`pandas`/`rag`); also by hand: `port`, `n_ctx`,
  `use_gpu`, `max_live_chats`, `projection_model_path`. Env overrides: `LOCALCHAT_MODEL_PATH`,
  `LOCALCHAT_PROJECTION_PATH`, `LOCALCHAT_PORT`, `LOCALCHAT_USE_GPU`, `LOCALCHAT_ALLOW_THINKING`,
  `LOCALCHAT_DB_PATH`, `LOCALCHAT_DEFAULT_MODEL` (fetch_model). The app sets `LOCALCHAT_PARENT_PID`;
  `LOCALCHAT_ROOT` overrides where the app looks for the LocalChat folder.

## Verified NobodyWho API

**Pinned to `nobodywho==3.0.0`** (Sep 2026, user asked for the newest). `requirements.txt` used to say
`>=1.5.0`, so CI silently built against 3.0.0 while everything had been tested on 1.5.0 — hence the exact
pin: bump it deliberately and re-verify. 3.0.0 keeps every call the app makes source-compatible (`Model`,
`Chat`, `SamplerPresets.*`, `set_chat_history`, `ask`, `stop_generation`, `Prompt`/`Text`/`Image`,
`download_model` with `(downloaded, total)` progress, `get_cached_models`, `Encoder`, `cosine_similarity`).
Verified on this machine: GPU text generation + a vision `Prompt([Text, Image])` on Qwen2.5-VL-3B. New in
3.0 (unused): **MTP speculative decoding** (`Model(draft_model_path=...)` + `Chat(mtp=MtpConfig())`),
`Chat(n_threads=...)`, `Model.max_ctx`, `model_path="auto"`, `Audio` prompt parts,
`SpeechToText`/`TextToSpeech`.

- `Model(model_path, use_gpu_if_available=True, projection_model_path=None, on_download_progress=None)`
  — reference-counted; **share one Model across many Chats**.
- `Chat(model, n_ctx=4096, system_prompt=None, template_variables=..., tools=..., sampler=None)`.
- `chat.ask(prompt) -> TokenStream`; iterate `for tok in stream` (live) or `stream.completed()`.
- History: `get_chat_history()`, `set_chat_history(msgs)`, `reset_history()`.
- **`chat.stop_generation()`** cancels in-flight generation (used by /stop).
- Sampler: `SamplerPresets.temperature(t) | top_k(k) | top_p(p) | greedy() | default()`.
- **Qwen3 thinking**: `template_variables={"enable_thinking": True/False}`. Output is inline
  `<think>...</think>` then the answer.
- `download_model("huggingface:repo/file.gguf")`, `get_cached_models()`.
- `nobodywho.tool` reads the function's own signature/annotations (see decision #17 gotchas).

## Important decisions & WHY (don't undo these without reading)

1. **Real-model-only.** All fake/demo streams were removed at the user's request. If no model is
   configured/loadable, the UI shows an error; it never fabricates output.
2. **Background model warmup after the UI loads** (NOT eager-at-startup, NOT lazy-on-first-message).
   `nobodywho.Model(...)` is a native call that **holds the GIL for ~3 s** while loading (verified: it does
   NOT release the GIL, so a load anywhere blocks the event loop). Loading it inline at startup froze the
   loop before the server served and made conversations fail to appear. Instead the app calls
   **`POST /api/warmup`** once the conversation list has loaded (and re-POSTs every 5 s while nothing is
   loaded/loading and there's no error, decision #21), which runs `engine.start_warmup()` on a daemon
   thread. The composer shows "Preparing model…" (gated on `/healthz model_loaded`) until ready.
   `engine._model_lock`/`_loaded` make a concurrent first message safe (no double load).
3. **(Removed)** The pywebview frameless/fullscreen window. Replaced by the Flutter app (decision #20).
   Background, in short: pywebview's runtime window-state ops crashed WebView2 on Windows, and on macOS the
   Python process hung on exit after the window closed.
4. **Thinking** (`allow_thinking`, off in the template). The app splits `<think>...</think>` and renders the
   reasoning in a collapsible box above the answer; every `<think>` block is collected (decision #17).
5. **Client-supplied message ids.** The app generates `user_message_id`/`assistant_message_id` so
   optimistic UI rows and persisted rows share ids.
6. **Branding**: the "nobodywho" wordmark (`desktop/assets/logo-nobodywho.png`) in the sidebar + empty
   state; app icon = "nw" cut from the wordmark (decision #21).
7. **File uploads = text extraction folded into the prompt** (CSV, PDF, `.xlsx`, `.xls`, `.docx`). Files
   are base64'd by the app and sent inline in the JSON `/stream` body. `files.py` extracts plain text and
   `prompt_from_store` folds it in front of the typed message, so `chat.ask(prompt)` just receives a longer
   string. The chat bubble shows **only the typed text** (with a filename chip); the extracted text lives
   in attachment metadata. Per-file cap 8000 chars (`MAX_CHARS_PER_FILE`). Images take the vision path
   (decision #12). Scanned/image-only PDFs yield `[no extractable text]` (no OCR). Legacy `.doc` unsupported.
8. **First-run model auto-download** (`backend/fetch_model.py`). The model is NOT committed (GGUFs are far
   over GitHub's limits). The launcher runs `python -m backend.fetch_model` after installing deps: if
   `config.toml` already points at an existing `.gguf` it's a no-op; otherwise it adopts the largest `*.gguf`
   next to the launcher (USB fallback), else downloads the default (`fetch_model.DEFAULT_MODEL`, Qwen3-0.6B
   Q8_0; `LOCALCHAT_DEFAULT_MODEL` overrides) into the NobodyWho cache and writes `model_path` into
   `config.toml` (regex-replacing the first uncommented `model_path =` line). Never fatal — on failure the
   app still launches and shows the model error. First launch needs internet; later launches are offline.
9. **(Superseded by #16)** The old `run.sh` Python-3.11/arm64 guards. The uv launchers install a managed
   Python 3.12, and the `.command` checks for arm64 itself. Python 3.11+ is still required (`tomllib`).
10. **Default system prompt = business/data-analysis assistant** (`config.example.toml`): concise, leans into
   the file-upload feature, "never fabricate numbers/facts", step-by-step calculations, Markdown tables. A
   single-line string since decision #18. Read at startup; history is rebuilt per turn so existing chats
   get a changed prompt too.
11. **In-app model download & switching.** Curated catalog (`models_catalog.CATALOG`) + a forgiving HF field
   (#14), download progress, runtime switch, delete-to-reclaim-disk. A swap clears `engine._loaded` + the
   `SessionRegistry`, nulls `_model`, sets `cfg.model_path`, and re-runs `_ensure_model()` under
   `_model_lock`, so the `/healthz model_loaded` gate disables the composer during the reload. Engine:
   `current_model()`, task state (`idle|downloading|loading|ready|error` via `task_status()`),
   `start_switch()`, `start_download()` (daemon threads). `models_catalog` matches catalog specs against
   `nobodywho.get_cached_models()` by path tail — also the authoritative delete guard. `routes/models.py`:
   `GET /api/models`, `GET /api/models/status`, `POST .../download`, `POST .../switch`, `DELETE /api/models`.
   The choice is persisted via `fetch_model._write_model_path`. **Switching is blocked while generating**
   (`app.state.stops` → 409). Never hardcodes the cache dir; comparisons tolerate Windows case/slash diffs.
12. **Vision (image) uploads via a borrowed vision model.** An image turn auto-switches to
   **Qwen2.5-VL-3B** + its `mmproj-...-f16.gguf` (`ggml-org/Qwen2.5-VL-3B-Instruct-GGUF`), answers via
   `Prompt([Text, Image(path)])` (`Image` takes a file path only), then **switches back** to the persisted
   text model on a daemon thread (`llm._start_restore_default`). In-memory only — does NOT rewrite
   `config.toml`; `engine._default_model_path/_default_projection` track what to restore. `prompt_from_store`
   returns `(prefix, prompt, image_paths)`; only the **current** turn carries images (history is text-only,
   prior images become `[Image: name]`). **Image bytes ARE stored**: `files.save_image` downscales to ≤1024 px
   JPEG under `LocalChat data/uploads/<conv>/<msg>_<idx>.jpg` (needed for `Image()`, regenerate, reload
   thumbnails); deleted with the conversation. If the vision model isn't cached, the first image turn starts
   the two-file download and returns "Downloading… resend when ready". The real download + GPU vision
   generation + swap-back was left to manual verification.
13. **`n_ctx` = 16384** (default in `Config` too). llama.cpp allocates the full KV cache upfront at load; on
   the 8 GB 4070, 16384 with a 3–4B model is the sweet spot; 32768 risks OOM.
14. **Forgiving Hugging Face download field.** `models_catalog.resolve_spec(user_input)` accepts a local path,
   a full `huggingface:` spec (with or without prefix), a direct `https://…/file.gguf`, an HF page URL, or a
   **bare `owner/name`** — it queries the HF API for `.gguf` siblings in `owner/name` then `owner/name-GGUF`,
   prefers Q4_K_M (then `_PREFERRED_QUANTS`), single files over shards. Optional `:QUANT` suffix forces a
   quant and fails clearly if missing. Runs on the download thread (`llm._do_download`).
15. **(Removed Oct 16)** PyInstaller/Inno Setup/DMG installers and the MSIX experiment. They froze the
   pywebview-era app; after decision #20 they started a windowless backend. If installers come back they
   must bundle the Flutter app (plus Python + venv) instead.
16. **Workshop distribution: clone + double-click, uv-bootstrapped launchers** (Oct 2026). Participants
   `git clone` a **slim single-OS repo** and double-click one file — cloned files carry no Mark-of-the-Web /
   quarantine flag, so no SmartScreen/Gatekeeper prompt (a browser "Download ZIP" would). The launchers
   install **uv** into `.uv/` (`UV_INSTALL_DIR`, `UV_NO_MODIFY_PATH`), uv downloads a managed **Python 3.12**
   into `.uv/python` (`UV_PYTHON_PREFERENCE=only-managed`); venv is `venv/` (`--seed`). uv's **download cache
   is deliberately NOT in-folder** (a deep path blew Windows' 260-char MAX_PATH building the `proxy-tools`
   sdist). The `.command` checks `hw.optional.arm64` (Intel Mac → clear error) and re-execs under
   `arch -arm64` under Rosetta. **No auto-update** (user decision: a bad push mustn't break a workshop) —
   the launchers never `git pull`. **Slim repos** come from `packaging/export_workshop.py <windows|mac> <out>
   --repo-url <url> --app-dir <dir>` (launcher + app zip + `git ls-files backend` + example data/rag +
   `packaging/workshop/README-<os>.md`; stages with `--chmod=+x` for the `.command`). They are private repos
   on the user's account (https://github.com/marcussimmelkiaer-lgtm/localchat-windows and .../localchat-mac),
   cloned locally as sibling folders `../localchat-windows`, `../localchat-mac`, and move to the company org
   once verified. Verified on this Windows machine, in CI on both OSes, and on a colleague's real Apple
   Silicon Mac. CI gotcha: the **Windows runner kills processes a step leaves behind**, so the launcher and
   the smoke check run in the SAME step. Local-testing gotchas: test from a SHORT path, and PowerShell 5.1
   `Set-Content -Encoding utf8` writes a BOM that breaks `tomllib`.
   **Workflow for changes**: edit THIS repo → export → commit + push in each sibling clone; never edit the slim
   repos directly. **⚠️ Never export straight into the clones**: `export_workshop.py` deletes EVERYTHING except
   `.git` in its target (the clone's `venv/`, `config.toml`, chat DB). Export to a temp dir, then in each clone
   `git rm` tracked files missing from the export, copy the export over, `git add` exactly the exported file
   list (`--chmod=+x` for the mac `Start LocalChat.command`), commit with `git -c core.autocrlf=false`, push.
   For a one-file change, copying that file + commit is enough. Dev work lives on branch `workshop-launchers`
   (pushed to the PUBLIC `origin`; `origin/main` is far behind).
17. **Optional tools (function calling), all OFF by default.** `backend/tools.py` is the learner-facing file:
   plain functions decorated with `@tool(description, params=...)` + a `TOOLS = {switch_name: [functions]}`
   registry; switches in `config.toml [tools]`. Tools: local/city time (Open-Meteo geocoding → IANA tz →
   `zoneinfo`; `tzdata` because Windows has no tz database), weather (Open-Meteo), Wikipedia intro (MediaWiki
   API, needs a User-Agent), pandas (`list_data_files` / `describe_table` / `calculate` over CSV/Excel in
   `data/`, path-confined via `Path(name).name`), and RAG (`rag = false`): read (`pypdf`/`python-docx`/text) →
   200-word chunks, 40 overlap → `nobodywho.Encoder` with `bge-small-en-v1.5` q8 → in-memory index keyed by
   path + mtime → `cosine_similarity`, top 3. `tool_support.py`'s `tool` wraps `nobodywho.tool` to report
   each call to a module-global listener and turn exceptions into `"Error: ..."` results. **Gotchas
   (verified on 3.0.0)**: a plain `functools.wraps` wrapper exposes *no* params, so the wrapper sets
   `__signature__` and real-type `__annotations__` (`eval_str=True`); tools run on a **NobodyWho thread**, not
   the token-loop thread — hence the global listener set/cleared in `llm.stream(on_tool=...)`, fed into the
   SSE queue as `event: tool`. Raw tool-call markup is never streamed. Calls persist in `messages.tool_calls`.
   The "Using tool…" state is held ≥1.2 s so fast tools are visible; the route inserts a blank line when a
   tool starts after some text. Tool descriptions/errors are prompt engineering (`max` vs `sum` fixed by
   describing operations; a wrong-column error listing valid columns makes the 4B self-correct). A concrete
   example in a `params` description gets copied verbatim by small models — keep params generic.
   `file_uploads` switch hides the paperclip and makes `/stream` reject attachments (400). With thinking on,
   Qwen3 can emit a second `<think>` block after a tool call; all blocks are shown in one box.
   `search_documents` names files that yielded no text ("Scanned documents need OCR first").
18. **Learner-facing `config.toml`**: `config.example.toml` in plain language — SYSTEM PROMPT (single-line
   `"..."` string; use `'` for inner quotes), THINKING, FILE UPLOADS, model_path, TEMPERATURE (`[sampler]`,
   with an "ask at 0.0 and 1.5" experiment), TOOLS (`[tools]`, each with a try-this question). TOML tables
   come last. The launcher only copies the template when `config.toml` is missing, so existing installs keep
   their old file. The workshop READMEs have an "Experiment" section.
19. **Tidy repo root**: `requirements.txt` and `config.example.toml` live in `backend/`. The app's own files
   (chat DB, `uploads/`, `LocalChat.log`) live in **`LocalChat data/`** (`paths.state_dir()`; older
   root-level files are moved in on first use). Slim repos ship **no `.gitignore`/`.gitattributes`**: the
   launchers append ignore rules to `.git/info/exclude` once, and the export stages with
   `core.autocrlf=false` so the `.bat` stays CRLF.
20. **Flutter desktop app replaced the pywebview window** (Oct 15 2026). Root cause first: a CI probe showed
   pywebview on macOS 14/15/26 closed the window but the Python process **never exited** (hung in interpreter
   shutdown). Now the Flutter app starts `venv/.../python(w) -u -m backend.main` with `LOCALCHAT_PARENT_PID`,
   reads the port from the `listening on http://…` line, and on exit (window close, Alt+F4, Cmd+Q) POSTs
   `/api/shutdown`, waits 8 s, else kills. `backend/main.py` ends with `os._exit(0)` (skips llama.cpp/Metal
   teardown); a parent-PID watchdog stops the backend if the app dies. macOS: App Sandbox **off** (must spawn
   Python), ad-hoc signed, min macOS 12. Windows: VC++ runtime DLLs copied next to the exe in CI.
   **Distribution**: `.github/workflows/desktop-app.yml` builds `LocalChat-windows.zip` /
   `LocalChat-macos.zip` (`ditto`, keeps symlinks + signature) + `version.txt` (no trailing newline). The
   export ships them as `app/LocalChat.zip` + `app/version.txt`; the launchers unpack on first run and
   whenever `app/version.txt` changes. `workshop-first-run.yml` builds the app, exports, runs the launcher,
   chats, then **quits the app like a user** (`taskkill` WM_CLOSE / `osascript quit`) and fails unless app +
   backend exit within 30 s with no crash report. **Sync procedure**: `gh run download <green run> -n
   LocalChat-windows -D <dir>` (or `-macos`), then export with `--app-dir <dir>`.
21. **Desktop app polish + fixes** (Oct 16 2026).
   - **Title bar** (`ui/title_bar.dart`): app-drawn, white. Windows: native caption hidden via
     `window_manager`, 44 px bar with drag + min/max/close (close = WM_CLOSE so the backend still stops).
     macOS: transparent title bar + empty unified `NSToolbar` (traffic lights centred) in
     `MainFlutterWindow.swift`; the toolbar is removed in full screen (NotificationCenter, since
     window_manager owns the window delegate) and the Flutter bar hides.
   - **Model sometimes never loaded on macOS**: `/api/models` (`get_cached_models`) during the startup load
     (holds the GIL) — likely a native deadlock. Fixes: the app fetches the model list only after load; the
     backend takes `engine.native_lock` around cache listing; the app re-POSTs `/api/warmup` every 5 s; the
     backend logs `[llm] loading model…` / `model loaded in Ns` / `model load failed`. The CI smoke test no
     longer calls `/api/warmup` — the app must load the model itself.
   - **Random "Cannot reach the local server"**: uvicorn's 5 s keep-alive equalled the 5 s health poll.
     Fixes: `timeout_keep_alive=120`; the app retries a GET once; "server down" only after 3 failed checks.
   - **Users update with `git pull`** in their LocalChat folder, then restart via the launcher. Close
     LocalChat first, or the unpack can't replace the running app's files.
22. **Cleanup after an audit** (Oct 16 2026, user decision). Removed: the React frontend (`frontend/`,
   `backend/static/`, the SPA mount — the backend is API-only now), the PyInstaller/Inno/DMG installer layer
   (`packaging/localchat.spec`, `build_win.ps1`, `localchat.iss`, `build_mac.sh`, `packaging/README.md`,
   `build-installers.yml`, `run_app.py`, `backend/bootstrap.py`, the frozen-build branches in `paths.py`,
   `llm._start_first_run_download`), the untracked MSIX experiment, dead backend code (`engine.warmup`,
   `build_engine`, the `backend` field in `/healthz`, `store.delete_message`/`delete_last_assistant`,
   `_ensure_std_streams`, an ineffective `PRAGMA synchronous`), the smoke test's frozen-binary mode (it now
   only checks a running app; `--quit` quits it), and Flutter leftovers (`loadError`, `Api.shutdown`,
   template `pubspec.yaml` comments, the `network.server` entitlement).

23. **Audit bug fixes** (Oct 16 2026; each was reproduced headless first, then re-tested):
   - **Mac "no chat history after reopening"**: `main.py` printed `listening on …` ~60 ms before uvicorn
     bound the port; macOS refuses a connection instantly, so the app's first `listConversations` (and its one
     retry) failed and the sidebar stayed empty. Windows hid it (a refused loopback connect takes ~2 s and
     retries meanwhile). Now `_announce_when_listening` prints only once `server.started`.
   - Backend: delete returns 404 for unknown ids (`DELETE /api/conversations/..` used to wipe
     `LocalChat data/`) and stops a streaming answer first (`routes/chat.stop_generation`, shared with /stop and
     /shutdown); a failed vision load restores the text model; a finished download waits for generations to end
     before switching; `model_error` is only set when no model is loaded; regenerate clears old stats
     (`update_message(stats={})` writes NULL); `config.toml` is read as `utf-8-sig`, a parse error is shown in the
     app (`Config.config_error`) and `fetch_model` won't download on top of it, bad numbers fall back to defaults;
     `tools.py` is imported only when a tool is on (a typo can't break chat); tool argument errors go back to the
     model; pandas/RAG edge cases; mmproj + the RAG embedding model are hidden from "Other downloaded"; HF
     `/tree/main` + `hf.co` links; offline is reported as offline; EXIF rotation for photos.
   - App: a failed chat load isn't cached; Stop ends the stream locally after 5 s without `done`; deleting the
     streaming chat finishes it; poll loops can't double up; the log is appended per start; links open only
     http/https/mailto. Tests for the first two are in `desktop/test/app_test.dart`.
   - Launchers refuse to run while LocalChat is running, a failed unpack can't look up to date, the ignore rules
     cover `*.bak` and `rag/*` (marker changed so old clones get them), and the Rosetta re-exec uses an absolute
     path. `export_workshop.py` refuses a target with `venv/`, `.uv/`, `config.toml` or `LocalChat data/`.

## Token throughput theory (asked but NOT implemented — for future reference)

Single-user decode is **memory-bandwidth bound at batch 1**: each token streams the whole weight set from
VRAM once, so `tok/s ≈ bandwidth ÷ model_bytes`. Levers: smaller/more-quantized model (biggest); unthrottle
the GPU (the laptop 4070 is power-capped ~42/95 W — already maxed per the user); flash-attention / KV-cache
quant (only help at long context); **speculative decoding** — now available in nobodywho 3.0 as MTP
(`draft_model_path` + `MtpConfig`), untested.

## Known issues / possible next steps

- **GPU is power-throttled** (~42 W of 95 W). Laptop vendor app → Performance mode, NVIDIA Control Panel →
  "Prefer maximum performance". `nvidia-smi -pl` is blocked on laptop GPUs.
- **GPU OOM with 4B + 3 cached chats**: Qwen3-4B, `n_ctx=16384`, `max_live_chats=3` → the third
  conversation fails "Could not create context" on the 8 GB 4070 (each cached Chat reserves its own KV
  cache). `max_live_chats = 1` or `n_ctx = 8192` avoids it.
- **Tool/RAG reliability is model-bound**: the 0.6B rarely calls tools (never RAG); the 4B is good but not
  deterministic at temperature 0.7 and under-triggers RAG when all 5 tools are on.
- **RAG**: in-memory index (rebuilt per restart); no OCR for scanned PDFs; `.xlsx`/`.csv` aren't RAG types.
- **CI scope**: `workshop-first-run.yml` proves install + model load + one chat reply + clean quit only.
  Tools, RAG, maths, uploads and thinking UI are verified by hand on Windows only, never on a Mac.
- **History fidelity**: each turn rebuilds history from SQLite (`set_chat_history`), so no KV-cache reuse.
- **Vision follow-ups**: multimodal history, vision-download progress during a chat, OCR.
- Only nobodywho is version-pinned in `requirements.txt`; the uv installer isn't pinned either.
- Not done: a vector/large logo for a sharper icon; a real hand test of the Flutter app on a Mac.
- Untracked local test files: `rag/Cooper.pdf`, `rag/Schumpeter.pdf` (gitignored now).
- The parent folder also contains an unrelated `../github-dashboard` project — not part of LocalChat.

## Status (current)

Working and verified end-to-end on Windows (and in CI on both OSes): Flutter app ↔ backend lifecycle,
GPU streaming with tokens/sec, stop/regenerate, SQLite persistence, thinking box, file uploads, vision
borrow (code paths), model manager, optional tools + RAG, KaTeX maths. Distributed via the slim workshop
repos (`localchat-windows` / `localchat-mac`, private, user's account).

**Next steps:**
1. Try the features on a **real Mac** (only Windows was tested by hand).
2. Decide on the 4B OOM defaults and whether to add OCR for scanned PDFs.
3. Move the slim repos to the company org as **public**, re-export with the new `--repo-url`; email
   professors to install Git; prepare USB sticks (exFAT, folder + `Qwen3-0.6B-Q8_0.gguf`).
4. Ideas not built: "also add uploads to the rag folder" switch; saving the RAG index to disk; an SQLite
   FTS5 keyword-search fallback; extending CI to exercise a tool.
