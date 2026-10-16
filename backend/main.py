"""LocalChat backend entry point: `python -m backend.main`.

Runs the local HTTP server (FastAPI + uvicorn) and nothing else. The window is
the Flutter desktop app in desktop/, which starts this process, talks to it over
http://127.0.0.1:<port>, and asks it to stop (POST /api/shutdown) when the
window closes. The same UI is also served to a normal browser at that address.

Exiting: the process ends with os._exit() once the server has stopped. A normal
interpreter exit would run llama.cpp's native teardown (Metal on macOS) while
model and worker threads are still alive, which crashes ("Python quit
unexpectedly"). Nothing needs that teardown: SQLite commits every write, and the
OS reclaims the model's memory.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time

import uvicorn

from .app import create_app
from .bootstrap import bootstrap
from .config import load_config


def _pick_port(host: str, preferred: int) -> int:
    """Use the preferred port if free, else an OS-assigned ephemeral one."""
    for candidate in (preferred, 0):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, candidate))
            port = s.getsockname()[1]
            s.close()
            return port
        except OSError:
            continue
    return preferred


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _watch_parent(server: uvicorn.Server, pid: int) -> None:
    """Stop when the desktop app that started us is gone (e.g. it crashed or
    was force-quit and never sent /api/shutdown)."""
    while not server.should_exit:
        if not _pid_alive(pid):
            print(f"[main] desktop app (pid {pid}) is gone; shutting down")
            server.should_exit = True
            return
        time.sleep(2)


def _ensure_std_streams():
    """Give a windowless launch somewhere to write.

    Started without a console (pythonw.exe, or by a GUI app without pipes)
    sys.stdout/stderr are None, and uvicorn's log formatter crashes on
    sys.stdout.isatty() at startup. Point both at the log file in the state dir
    instead (fresh each launch) — also useful when a user reports a problem."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    from .paths import state_dir

    log = open(state_dir() / "LocalChat.log", "w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log


def main():
    _ensure_std_streams()
    # First-launch setup for packaged builds (writable config, adopt a
    # cached default model). No-op from a source checkout. Must run before load_config
    # so the config it writes is picked up.
    bootstrap()
    cfg = load_config()
    port = _pick_port(cfg.host, cfg.port)
    app = create_app(cfg)

    # timeout_keep_alive: the desktop app polls every few seconds over a reused
    # connection; uvicorn's default (5 s) closed it just as the next poll went
    # out, which showed up as random "Cannot reach the local server" flashes.
    server = uvicorn.Server(uvicorn.Config(
        app, host=cfg.host, port=port, log_level="warning",
        timeout_keep_alive=120, timeout_graceful_shutdown=5,
    ))
    app.state.server = server  # POST /api/shutdown sets server.should_exit

    parent = os.environ.get("LOCALCHAT_PARENT_PID")
    if parent and parent.isdigit():
        threading.Thread(target=_watch_parent, args=(server, int(parent)), daemon=True).start()

    # The desktop app reads this line to learn the port.
    print(f"[main] LocalChat backend listening on http://{cfg.host}:{port}", flush=True)
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    print("[main] stopped", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
