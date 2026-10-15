"""Drive the real LocalChat window on macOS and report how the app exits (CI).

    python packaging/mac_gui_probe.py            # run every scenario, print a table
    python packaging/mac_gui_probe.py <scenario> # run one scenario in this process

Each scenario starts the app exactly like the launcher does (backend.main.main(),
real pywebview window), drives it the way a user would (the title-bar buttons
are called through the same JS bridge the buttons use, Cmd+Q via NSApp
terminate:) and then lets the process exit. The parent runs every scenario in
a subprocess and reports its exit code: 0 is a clean exit, a negative code is
the signal that killed it (-6 SIGABRT, -11 SIGSEGV = "quit unexpectedly").
Screenshots go to $PROBE_OUT (default ./probe-out). Stdlib + the app's deps.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("PROBE_OUT", ROOT / "probe-out"))
PORT = int(os.environ.setdefault("LOCALCHAT_PORT", "8777"))
BASE = f"http://127.0.0.1:{PORT}"

SCENARIOS = {
    "close_idle": "close button before the model is loaded",
    "close_loaded": "close button with the model loaded",
    "close_generating": "close button while an answer is streaming",
    "window_ops": "fullscreen on/off, minimize/restore, drag, then close",
    "cmd_q": "Cmd+Q (app menu Quit) with the model loaded",
    "cmd_q_generating": "Cmd+Q while an answer is streaming",
}


def log(msg: str) -> None:
    print(f"[probe] {msg}", flush=True)


def _req(method, path, body=None, timeout=10):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def _json(method, path, body=None, timeout=10):
    with _req(method, path, body, timeout) as r:
        return json.loads(r.read())


def screenshot(name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    subprocess.run(["screencapture", "-x", str(OUT / f"{name}.png")], check=False)


def load_model() -> None:
    try:
        _json("POST", "/api/warmup", timeout=30)
    except OSError:
        pass
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        try:
            h = _json("GET", "/healthz")
            if h["model_loaded"]:
                log("model loaded")
                return
            if h["model_error"]:
                raise RuntimeError(h["model_error"])
        except OSError:
            pass
        time.sleep(1)
    raise RuntimeError("model never loaded")


def start_generating() -> threading.Event:
    """Start a long answer in the background; returns once tokens flow."""
    first = threading.Event()

    def run():
        conv = _json("POST", "/api/conversations", {})
        body = {"conversation_id": conv["id"],
                "content": "Write a long, detailed story about a lighthouse keeper.",
                "user_message_id": str(uuid.uuid4()),
                "assistant_message_id": str(uuid.uuid4())}
        try:
            with _req("POST", "/api/chat/stream", body, timeout=600) as r:
                for raw in r:
                    if raw.startswith(b"event: token"):
                        first.set()
        except Exception as e:  # noqa: BLE001 - the app going away mid-stream is expected
            log(f"stream ended: {type(e).__name__}")

    threading.Thread(target=run, daemon=True).start()
    if not first.wait(300):
        raise RuntimeError("no tokens streamed")
    log("answer is streaming")
    return first


def js(window, code):
    return window.evaluate_js(code)


def click(window, method: str) -> None:
    """What the title-bar button does: call the js_api bridge from the page."""
    log(f"click {method}")
    js(window, f"window.pywebview.api.{method}()")


def quit_app() -> None:
    from AppKit import NSApp
    from PyObjCTools import AppHelper

    log("Cmd+Q (NSApp terminate:)")
    AppHelper.callAfter(NSApp.terminate_, None)


def scenario_thread(name: str, api) -> None:
    w = api._window
    try:
        if not w.events.loaded.wait(60):
            raise RuntimeError("page never loaded")
        for _ in range(100):
            if js(w, "!!(window.pywebview && window.pywebview.api && window.pywebview.api.close)"):
                break
            time.sleep(0.1)
        time.sleep(1)
        screenshot(f"{name}-1-open")

        if name != "close_idle":
            load_model()
        if name in ("close_generating", "cmd_q_generating"):
            start_generating()
            time.sleep(2)
            screenshot(f"{name}-2-generating")

        if name == "window_ops":
            click(w, "toggle_fullscreen"); time.sleep(3); screenshot(f"{name}-2-fullscreen")
            click(w, "toggle_fullscreen"); time.sleep(3); screenshot(f"{name}-3-normal")
            click(w, "minimize"); time.sleep(2); screenshot(f"{name}-4-minimized")
            log("restore"); w.restore(); time.sleep(2); screenshot(f"{name}-5-restored")
            log("drag (move)"); w.move(40, 60); time.sleep(1); screenshot(f"{name}-6-moved")

        if name.startswith("cmd_q"):
            quit_app()
        else:
            click(w, "close")
    except Exception as e:  # noqa: BLE001
        log(f"SCENARIO ERROR: {e!r}")
        screenshot(f"{name}-error")
        os._exit(3)


def run_one(name: str) -> None:
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    import backend.main as m

    original = m._control_loop_native

    def control_loop(api):
        threading.Thread(target=scenario_thread, args=(name, api), daemon=True).start()
        original(api)

    m._control_loop_native = control_loop
    m.main()
    log("main() returned; interpreter exiting")


def crash_reports() -> set[str]:
    d = Path.home() / "Library" / "Logs" / "DiagnosticReports"
    return {p.name for p in d.glob("*")} if d.is_dir() else set()


def run_all() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows, bad = [], 0
    for name, desc in SCENARIOS.items():
        before = crash_reports()
        t0 = time.monotonic()
        log(f"===== {name}: {desc}")
        try:
            p = subprocess.run([sys.executable, "-u", __file__, name], timeout=900,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            code, output = p.returncode, p.stdout
        except subprocess.TimeoutExpired as e:
            code, output = "TIMEOUT (hung)", (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            subprocess.run(["pkill", "-f", f"mac_gui_probe.py {name}"], check=False)
        took = time.monotonic() - t0
        (OUT / f"{name}.log").write_text(output, encoding="utf-8")
        new = sorted(crash_reports() - before)
        ok = code == 0 and not new
        bad += not ok
        rows.append((name, code, f"{took:.0f}s", ", ".join(new) or "-", "OK" if ok else "PROBLEM"))
        print(output[-6000:], flush=True)
        for r in new:
            src = Path.home() / "Library" / "Logs" / "DiagnosticReports" / r
            try:
                (OUT / r).write_bytes(src.read_bytes())
                print(f"----- crash report {r} (head) -----")
                print(src.read_text(errors="replace")[:6000])
            except OSError:
                pass
    print("\n| scenario | exit code | time | crash reports | result |")
    print("| --- | --- | --- | --- | --- |")
    for r in rows:
        print("| " + " | ".join(str(x) for x in r) + " |")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### {os.environ.get('RUNNER_LABEL', sys.platform)}\n\n")
            f.write("| scenario | exit code | time | crash reports | result |\n| --- | --- | --- | --- | --- |\n")
            for r in rows:
                f.write("| " + " | ".join(str(x) for x in r) + " |\n")
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_one(sys.argv[1])
    else:
        sys.exit(run_all())
