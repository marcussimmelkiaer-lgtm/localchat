# LocalChat

A clean, ChatGPT-style desktop chat app that runs a local LLM entirely on your
machine via the [NobodyWho](https://github.com/nobodywho-ooo/nobodywho) Python
bindings (llama.cpp). Live token streaming, a tokens/second readout, and a
monochrome, white-dominant interface. Native window (WKWebView on macOS,
WebView2 on Windows).

**Cross-platform**: the same codebase runs on both Windows and macOS (Apple
Silicon) — `backend/main.py` selects the platform window path at runtime.

Everything runs locally — no cloud, no API keys.

## Requirements

- macOS 11+ on Apple Silicon (M1–M5). (Also runs on Windows 10/11 x64.)
- Python 3.10+ (`python3`)
- GPU acceleration is automatic: **Metal** on macOS, Vulkan on Windows. Falls
  back to CPU.
- A local GGUF chat model (see Configuration)

## Run

- **macOS / Linux**: `chmod +x run.sh` (first time only), then `./run.sh`
- **Windows**: double-click `run.bat`

On first launch it creates a virtual environment, installs dependencies, and
copies `config.example.toml` to `config.toml`. Set `model_path` in `config.toml`,
then launch again.

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
LOCALCHAT_NO_WINDOW=1 venv/bin/python -m backend.main
```
