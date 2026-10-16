"""End-to-end smoke test of a running LocalChat (used by CI).

    python packaging/smoke_test.py          # app already started by a launcher
    python packaging/smoke_test.py --quit   # ...then quit the desktop app

Checks the whole first-run path a real user hits, after Start LocalChat.* has
started the desktop app:

  1. the server comes up (/healthz),
  2. the app loads the model by itself,
  3. a chat message streams tokens back and finishes with status "done",
  4. (--quit) quitting the app like a user stops the app and its backend.

Run with LOCALCHAT_USE_GPU=0 on CI, since runners have no usable GPU. Stdlib
only. Exits non-zero on any failure.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

PORT = int(os.environ.setdefault("LOCALCHAT_PORT", "8765"))
BASE = f"http://127.0.0.1:{PORT}"


def _req(method: str, path: str, body: dict | None = None, timeout: float = 10):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    return urllib.request.urlopen(req, timeout=timeout)


def _json(method: str, path: str, body: dict | None = None):
    with _req(method, path, body) as r:
        return json.loads(r.read())


def _wait_healthz(seconds: int) -> dict:
    for _ in range(seconds):
        try:
            return _json("GET", "/healthz")
        except OSError:
            time.sleep(1)
    raise RuntimeError("server never answered /healthz")


def _wait_model(seconds: int) -> None:
    """Wait until the model is loaded. The load is NOT started here: the desktop
    app must load it by itself (a real user never calls warmup)."""
    last = None
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            h = _json("GET", "/healthz")
        except OSError as e:
            # Loading the model holds the GIL, so the server can stall for a
            # while (longest on a GPU-less CI runner). Keep polling.
            print(f"[smoke] /healthz busy ({e}); retrying")
            time.sleep(2)
            continue
        if h["model_loaded"]:
            print("[smoke] model loaded")
            return
        if h["model_error"]:
            raise RuntimeError(f"model error: {h['model_error']}")
        task = h.get("model_task") or {}
        line = f"{task.get('status')} {round((task.get('fraction') or 0) * 100)}%"
        if line != last:
            print(f"[smoke] model task: {line}")
            last = line
        time.sleep(1)
    raise RuntimeError("model never loaded")


def _chat() -> None:
    conv = _json("POST", "/api/conversations", {})
    body = {
        "conversation_id": conv["id"],
        "content": "Say hello in one short sentence.",
        "user_message_id": str(uuid.uuid4()),
        "assistant_message_id": str(uuid.uuid4()),
    }
    tokens, status, event = [], None, None
    with _req("POST", "/api/chat/stream", body, timeout=300) as r:
        for raw in r:
            line = raw.decode("utf-8").strip()
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
                if event == "token":
                    tokens.append(data["text"])
                elif event == "error":
                    raise RuntimeError(f"stream error: {data['message']}")
                elif event == "done":
                    status = data["status"]
                    break
    reply = "".join(tokens)
    print(f"[smoke] reply ({len(tokens)} tokens): {reply[:200]!r}")
    if status != "done" or not tokens:
        raise RuntimeError(f"chat did not complete (status={status}, tokens={len(tokens)})")


def _crash_reports() -> set[str]:
    d = Path.home() / "Library" / "Logs" / "DiagnosticReports"
    return {p.name for p in d.glob("*")} if d.is_dir() else set()


def _app_running() -> bool:
    if sys.platform == "win32":
        out = subprocess.run(["tasklist", "/fi", "imagename eq LocalChat.exe"],
                             capture_output=True, text=True).stdout
        return "LocalChat.exe" in out
    return subprocess.run(["pgrep", "-x", "LocalChat"], capture_output=True).returncode == 0


def _quit_app() -> None:
    """Quit the desktop app the way a user does (close the window / Cmd+Q) and
    check it and its backend exit cleanly (no hang, no crash report)."""
    before = _crash_reports()
    if sys.platform == "win32":
        # Without /f, taskkill sends WM_CLOSE: the same as clicking the X.
        subprocess.run(["taskkill", "/im", "LocalChat.exe"], check=False)
    else:
        subprocess.run(["osascript", "-e", 'quit app "LocalChat"'], check=False)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        backend_up = True
        try:
            _json("GET", "/healthz")
        except OSError:
            backend_up = False
        if not backend_up and not _app_running():
            break
        time.sleep(1)
    else:
        raise RuntimeError("the app or its backend was still running 30 s after quitting")
    new = sorted(r for r in _crash_reports() - before if "LocalChat" in r or "Python" in r)
    if new:
        raise RuntimeError(f"crash report(s) after quitting: {new}")
    print("[smoke] app and backend exited cleanly")


def main() -> int:
    try:
        print(f"[smoke] server up: {_wait_healthz(600)}")
        _wait_model(300)
        _chat()
        if "--quit" in sys.argv[1:]:
            _quit_app()
        print("[smoke] PASS")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[smoke] FAIL: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
