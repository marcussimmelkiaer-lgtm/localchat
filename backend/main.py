"""LocalChat backend entry point: `python -m backend.main`.

Runs the local HTTP server (FastAPI + uvicorn) and nothing else. The window is
the Flutter desktop app in desktop/, which starts this process, talks to it over
http://127.0.0.1:<port>, and asks it to stop (POST /api/shutdown) when the
window closes.

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


def _announce_when_listening(server: uvicorn.Server, url: str) -> None:
    """Print the line the desktop app reads to learn the port, but only once
    uvicorn accepts connections. Printed earlier, the app's first request could
    be refused (instantly on macOS), leaving the chat list empty."""
    while not server.started:
        if server.should_exit:
            return
        time.sleep(0.02)
    print(f"[main] LocalChat backend listening on {url}", flush=True)


def main():
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

    url = f"http://{cfg.host}:{port}"
    threading.Thread(target=_announce_when_listening, args=(server, url), daemon=True).start()
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
