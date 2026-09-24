"""End-to-end smoke test of a packaged LocalChat build (used by CI).

    python packaging/smoke_test.py <path-to-LocalChat-binary> [args...]

Launches the frozen app headless (LOCALCHAT_NO_WINDOW=1) on a clean machine and
checks the whole first-run path a real user hits:

  1. the server comes up (/healthz),
  2. warmup triggers the first-run model download (frozen builds ship no model)
     and the model loads,
  3. a chat message streams tokens back and finishes with status "done".

The caller picks a tiny model via LOCALCHAT_DEFAULT_MODEL so CI doesn't pull
2.5 GB, and LOCALCHAT_USE_GPU=0 since runners have no usable GPU. Stdlib only.
Exits non-zero (printing the app's log) on any failure.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
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


def _wait_healthz(proc, seconds: int) -> dict:
    for _ in range(seconds):
        if proc.poll() is not None:
            raise RuntimeError(f"app exited early with code {proc.returncode}")
        try:
            return _json("GET", "/healthz")
        except OSError:
            time.sleep(1)
    raise RuntimeError("server never answered /healthz")


def _wait_model(seconds: int) -> None:
    _json("POST", "/api/warmup")
    last = None
    for _ in range(seconds):
        h = _json("GET", "/healthz")
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


def main() -> int:
    os.environ["LOCALCHAT_NO_WINDOW"] = "1"
    log_path = Path(tempfile.gettempdir()) / "smoke_app.log"
    log = open(log_path, "w", encoding="utf-8")
    cmd = [str(Path(sys.argv[1]).resolve()), *sys.argv[2:]]
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
    try:
        h = _wait_healthz(proc, 120)
        print(f"[smoke] server up: {h}")
        _wait_model(900)
        _chat()
        print("[smoke] PASS")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[smoke] FAIL: {e}")
        log.flush()
        print("----- app output -----")
        print(log_path.read_text(encoding="utf-8", errors="replace")[-8000:])
        # A windowed build has no stdout; it logs to the per-user data dir.
        for d in (Path(os.environ.get("LOCALAPPDATA", "")) / "LocalChat",
                  Path.home() / "Library" / "Application Support" / "LocalChat"):
            app_log = d / "LocalChat.log"
            if app_log.is_file():
                print(f"----- {app_log} -----")
                print(app_log.read_text(encoding="utf-8", errors="replace")[-8000:])
        return 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
