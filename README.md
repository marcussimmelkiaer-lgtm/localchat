# LocalChat

A clean, ChatGPT-style desktop chat app that runs a local LLM entirely on your
machine via the [NobodyWho](https://github.com/nobodywho-ooo/nobodywho) Python
bindings (llama.cpp + Vulkan). Live token streaming, a tokens/second readout,
and a monochrome, white-dominant interface. Native window via WebView2.

Everything runs locally — no cloud, no API keys.

## Requirements

- Windows 10/11 (x64)
- Python 3.10+ (the `py` launcher)
- A Vulkan-capable GPU for acceleration (NVIDIA / AMD / Intel). Falls back to CPU.
- A local GGUF chat model (see Configuration)

## Run

Double-click **`run.bat`**. On first launch it creates a virtual environment,
installs dependencies, and copies `config.example.toml` to `config.toml`. Set
`model_path` in `config.toml`, then launch again.

## Configuration (`config.toml`)

| Key | Meaning |
| --- | --- |
| `model_path` | Absolute path to a local `.gguf` chat model (required) |
| `port` | Local server port (falls back to a free one if busy) |
| `n_ctx` | Context window size |
| `use_gpu` | Use the GPU via Vulkan if available; `false` forces CPU |
| `allow_thinking` | For reasoning models (Qwen3): keep `<think>` blocks out of chat |
| `system_prompt` | System prompt |
| `[sampler]` | `preset` = temperature \| top_k \| top_p \| greedy \| default |

## Architecture

- **Frontend** — React + Tailwind (Vite), prebuilt into `backend/static/`.
- **Backend** — FastAPI serving the SPA + a streaming chat endpoint (SSE).
  Generation runs in a worker thread; tokens stream to the UI over Server-Sent
  Events. Conversations persist in a local SQLite file.
- **Launcher** — `backend/main.py` runs the server in a daemon thread and opens
  a native WebView2 window (pywebview).

## Develop

```
cd frontend
npm install
npm run dev        # Vite dev server with API proxy to the backend
npm run build      # rebuild backend/static (commit the result)
```

Run the backend (without the window) for API testing:

```
set LOCALCHAT_NO_WINDOW=1
venv\Scripts\python -m backend.main
```
