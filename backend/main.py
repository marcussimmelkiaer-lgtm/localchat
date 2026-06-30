from __future__ import annotations

import os
import queue
import socket
import threading
import time
import urllib.request

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


class _WindowApi:
    """Exposed to the frameless window's custom title bar via pywebview js_api.

    Calling window ops (minimize / fullscreen / destroy) directly from a js_api
    callback crashes this WebView2 build. So the bridge methods only ENQUEUE a
    command; the actual window calls run in the webview worker thread (see
    _control_loop), which is the safe context for them."""

    def __init__(self):
        # Underscore-prefixed so pywebview doesn't try to serialize these (the
        # Window object graph) when exposing the api to JS — that serialization
        # spams the console with AccessibilityObject recursion errors.
        self._window = None
        self._cmds: "queue.Queue[str]" = queue.Queue()
        self._fullscreen = False  # owned by the control-loop thread

    def minimize(self):
        self._cmds.put("minimize")

    def close(self):
        self._cmds.put("close")

    def toggle_fullscreen(self):
        self._cmds.put("toggle_fullscreen")


def _control_loop(api: _WindowApi):
    """Runs window operations on the webview worker thread (the safe context).

    Fullscreen is done WITHOUT pywebview's toggle_fullscreen(): that mutates
    FormBorderStyle + WindowState + DWM attributes on the live window, which
    crashes this WebView2 build (exit -805306369). Instead we only call
    SetWindowPos to swap the window's bounds between the monitor's working area
    (normal) and its full bounds + topmost (fullscreen). SetWindowPos is the same
    non-invasive primitive pywebview's own resize()/move() use, and it is safe to
    call cross-thread. The window is created in the Normal WindowState (never
    maximized), so its bounds are honored and WindowState is never touched."""
    import ctypes
    from ctypes import wintypes

    import webview.platforms.winforms as wf

    set_window_pos = wf.windll.user32.SetWindowPos
    set_window_pos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    set_window_pos.restype = wintypes.BOOL

    HWND_TOPMOST = -1
    HWND_NOTOPMOST = -2
    SWP_SHOWWINDOW = 0x0040

    def _inst():
        w = api._window
        return wf.BrowserView.instances.get(w.uid) if w is not None else None

    def _apply(fullscreen: bool):
        inst = _inst()
        if inst is None:
            return
        screen = wf.WinForms.Screen.FromControl(inst)
        rect = screen.Bounds if fullscreen else screen.WorkingArea
        set_window_pos(
            int(inst.Handle.ToInt64()),
            HWND_TOPMOST if fullscreen else HWND_NOTOPMOST,
            rect.X,
            rect.Y,
            rect.Width,
            rect.Height,
            SWP_SHOWWINDOW,
        )
        api._fullscreen = fullscreen

    # Wait for the native form to come up, then snap the frameless window to the
    # working area so it covers the screen (minus taskbar) like a maximized window.
    for _ in range(200):  # up to ~10s
        inst = _inst()
        if inst is not None and inst.Handle.ToInt64() != 0:
            break
        time.sleep(0.05)
    _apply(False)

    while True:
        cmd = api._cmds.get()
        if cmd == "__stop__":
            break
        w = api._window
        if w is None:
            continue
        try:
            if cmd == "minimize":
                w.minimize()
            elif cmd == "close":
                w.destroy()
                break
            elif cmd == "toggle_fullscreen":
                _apply(not api._fullscreen)
        except Exception:  # noqa: BLE001
            pass


def _wait_ready(url: str, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.1)
    return False


def _initial_geometry():
    """Primary-monitor working area in logical pixels: (x, y, width, height).

    Used only for the window's initial size/position so it opens already filling
    the screen; the control loop re-snaps it to exact physical bounds once the
    native form exists. Falls back to a centered default if anything fails."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        rect = wintypes.RECT()
        SPI_GETWORKAREA = 0x0030
        user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
        try:
            dpi = user32.GetDpiForSystem()
        except Exception:  # noqa: BLE001
            dpi = 96
        scale = (dpi / 96.0) or 1.0
        return (
            int(rect.left / scale),
            int(rect.top / scale),
            int((rect.right - rect.left) / scale),
            int((rect.bottom - rect.top) / scale),
        )
    except Exception:  # noqa: BLE001
        return (None, None, 1100, 760)


def main():
    cfg = load_config()
    port = _pick_port(cfg.host, cfg.port)
    app = create_app(cfg)

    server = uvicorn.Server(
        uvicorn.Config(app, host=cfg.host, port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    url = f"http://{cfg.host}:{port}"
    if not _wait_ready(url + "/healthz"):
        print("[main] server did not become ready in time")

    # Headless mode for automated testing (no GUI window).
    if os.environ.get("LOCALCHAT_NO_WINDOW"):
        print(f"[main] running headless at {url} (no window). Ctrl+C to stop.")
        try:
            while thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        server.should_exit = True
        return

    import webview

    # Initial geometry ≈ primary monitor working area, so the frameless window
    # comes up covering the screen (the control loop then snaps it pixel-exact).
    # The window is created in the Normal WindowState (NOT maximized) so its
    # bounds can be swapped for the fullscreen toggle — see _control_loop.
    gx, gy, gw, gh = _initial_geometry()

    api = _WindowApi()
    window = webview.create_window(
        "LocalChat",
        url,
        x=gx,
        y=gy,
        width=gw,
        height=gh,
        min_size=(720, 520),
        frameless=True,
        easy_drag=False,
        js_api=api,
    )
    api._window = window
    # Run the control loop on the webview worker thread (window ops are only
    # safe there). start() blocks until the window closes.
    webview.start(_control_loop, api)

    # Window closed — unblock the control loop (if still waiting) and shut down.
    api._cmds.put("__stop__")
    server.should_exit = True
    thread.join(timeout=5)


if __name__ == "__main__":
    main()
