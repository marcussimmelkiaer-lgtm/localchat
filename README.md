# LocalChat

A clean, ChatGPT-style desktop chat app that runs a local LLM entirely on your
machine via the [NobodyWho](https://github.com/nobodywho-ooo/nobodywho) Python
bindings (llama.cpp). Live token streaming, a tokens/second readout, and a
monochrome, white-dominant interface, in a native Flutter desktop app for
Windows and macOS.

Everything runs locally — no cloud, no API keys.

## Requirements

- macOS 12+ on Apple Silicon (M1 or newer), or Windows 10/11 x64.
- Git, to clone.
- Nothing else. The launcher downloads a private Python 3.12 (via
  [uv](https://docs.astral.sh/uv/)) into the folder; no admin rights needed.
- GPU acceleration is automatic: **Metal** on macOS, Vulkan on Windows. Falls
  back to CPU.

## Run

Clone once, then double-click one file:

- **Windows:** **`Start LocalChat.bat`**
- **macOS:** **`Start LocalChat.command`**

On first launch it downloads uv + Python 3.12 into `.uv/`, installs the
dependencies into `venv/`, copies `backend/config.example.toml` to `config.toml`, and
**downloads the default chat model** (Qwen3-0.6B, ~640 MB) into NobodyWho's local
cache. Bigger models are a click away in the app's **Models** picker. Later
launches start straight away, offline. Dependencies are reinstalled whenever
`backend/requirements.txt` changes. Chats, uploads and the log live in
`LocalChat data/`.

> A `.gguf` placed next to the launcher is used instead of downloading (handy for
> handing the model out on a USB stick). To pick a different download, set
> `LOCALCHAT_DEFAULT_MODEL` to another `huggingface:` / `https://` GGUF.

> Use `git clone` rather than GitHub's "Download ZIP": a downloaded ZIP is marked
> as coming from the internet, so Windows/macOS security prompts kick in; a
> clone isn't.

### Workshop repos

Workshop participants clone a slim, single-OS repo (one launcher + `backend/`)
generated from this one, so the two never drift:

```
python packaging/export_workshop.py windows <tmp>/win --repo-url <clone-url> --app-dir <dir>
python packaging/export_workshop.py mac     <tmp>/mac --repo-url <clone-url> --app-dir <dir>
```

`--app-dir` holds the desktop app built by CI (the `LocalChat-windows` /
`LocalChat-macos` artifact of `.github/workflows/desktop-app.yml`). The export
deletes everything in its target except `.git`, so export to a temporary folder
and copy the files into each slim-repo clone, then commit + push there.
`.github/workflows/workshop-first-run.yml` runs the exported launchers on clean
macOS + Windows runners (real model download, CPU generation).

## Configuration (`config.toml`)

The template (`backend/config.example.toml`) only lists the settings worth
experimenting with; the others below can be added by hand and default sensibly.

| Key | Meaning |
| --- | --- |
| `model_path` | Absolute path to a local `.gguf` chat model (required) |
| `port` | Local server port (falls back to a free one if busy) |
| `n_ctx` | Context window size |
| `use_gpu` | Use the GPU (Metal on macOS / Vulkan on Windows) if available; `false` forces CPU |
| `allow_thinking` | For reasoning models (Qwen3): think before answering (shown in a collapsible box) |
| `file_uploads` | Show the paperclip for attaching files and images |
| `system_prompt` | System prompt |
| `[sampler]` | `preset` = temperature \| top_k \| top_p \| greedy \| default |
| `[tools]` | Optional model tools: `time`, `weather`, `wikipedia`, `pandas`, `rag` (see `backend/tools.py`) |

## Architecture

- **Backend** — FastAPI with a streaming chat endpoint (SSE). Generation runs in
  a worker thread; tokens stream to the app over Server-Sent Events.
  Conversations persist in a local SQLite file.
- **Desktop app** — Flutter (`desktop/`, see its README). It starts the Python
  backend, shows the chat, and stops the backend when the window closes. CI
  builds it per OS; the workshop repos ship it as `app/LocalChat.zip`, which
  the launcher unpacks on first run.

## Develop

Run the backend on its own (it prints its address):

```
venv/bin/python -m backend.main   # Windows: venv\Scripts\python
```

See `desktop/README.md` for building and running the desktop app.
