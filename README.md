# LocalChat

A clean, ChatGPT-style desktop chat app that runs a local LLM entirely on your
machine via the [NobodyWho](https://github.com/nobodywho-ooo/nobodywho) Python
bindings (llama.cpp). Live token streaming, a tokens/second readout, and a
monochrome, white-dominant interface. Native window (WKWebView on macOS,
WebView2 on Windows).

This is the **macOS (Apple Silicon)** build. The same codebase still runs on
Windows — `backend/main.py` selects the platform path at runtime.

Everything runs locally — no cloud, no API keys.

## Requirements

- macOS 11+ on Apple Silicon (M1 or newer), or Windows 10/11 x64.
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
dependencies into `venv/`, copies `config.example.toml` to `config.toml`, and
**downloads the default chat model** (Qwen3-0.6B, ~640 MB) into NobodyWho's local
cache. Bigger models are a click away in the app's **Models** picker. Later
launches start straight away, offline. Dependencies are reinstalled whenever
`requirements.txt` changes.

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
python packaging/export_workshop.py windows ../localchat-windows --repo-url <clone-url>
python packaging/export_workshop.py mac     ../localchat-mac     --repo-url <clone-url>
```

Then commit + push in each target. `.github/workflows/workshop-first-run.yml`
runs the exported launchers on clean macOS + Windows runners (real model
download, CPU generation).

## Configuration (`config.toml`)

| Key | Meaning |
| --- | --- |
| `model_path` | Absolute path to a local `.gguf` chat model (required) |
| `port` | Local server port (falls back to a free one if busy) |
| `n_ctx` | Context window size |
| `use_gpu` | Use the GPU (Metal on macOS / Vulkan on Windows) if available; `false` forces CPU |
| `allow_thinking` | For reasoning models (Qwen3): keep `<think>` blocks out of chat |
| `system_prompt` | System prompt |
| `[sampler]` | `preset` = temperature \| top_k \| top_p \| greedy \| default |

## Architecture

- **Frontend** — React + Tailwind (Vite), prebuilt into `backend/static/`.
- **Backend** — FastAPI serving the SPA + a streaming chat endpoint (SSE).
  Generation runs in a worker thread; tokens stream to the UI over Server-Sent
  Events. Conversations persist in a local SQLite file.
- **Launcher** — `backend/main.py` runs the server in a daemon thread and opens
  a native pywebview window (WKWebView on macOS, WebView2 on Windows).

## Develop

```
cd frontend
npm install
npm run dev        # Vite dev server with API proxy to the backend
npm run build      # rebuild backend/static (commit the result)
```

Run the backend (without the window) for API testing:

```
LOCALCHAT_NO_WINDOW=1 venv/bin/python -m backend.main   # Windows: venv\Scripts\python
```
