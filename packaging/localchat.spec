# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — freeze LocalChat into a small onedir app (NO models inside).

Build (from the repo root, in the project venv, with `pip install pyinstaller`):

    pyinstaller packaging/localchat.spec --noconfirm

Produces `dist/LocalChat/` — a self-contained app folder (Python + all deps +
the native nobodywho wheel + the built SPA). Models are NOT bundled anywhere;
the app downloads its default model on first launch. Run the whole thing
through the platform build scripts in packaging/{windows,macos}/.
"""

import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = os.path.dirname(SPECPATH)  # packaging/ -> repo root  # noqa: F821
IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# --- Shipped data (read-only in the bundle) ---------------------------------
datas = [
    (os.path.join(ROOT, "backend", "static"), os.path.join("backend", "static")),
    (os.path.join(ROOT, "config.example.toml"), "."),
]
binaries = []
hiddenimports = [
    "clr",                      # pythonnet, used by pywebview's winforms backend
    "websockets",               # uvicorn[standard] ws
    "websockets.legacy",
    "httptools",                # uvicorn[standard] http parser
    "watchfiles",
]

# The native nobodywho wheel (bundles llama.cpp + the GPU backend) is a single
# .pyd/.so — collect it wholesale so the binary and metadata come along.
for pkg in ("nobodywho", "webview", "clr_loader", "sse_starlette"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# uvicorn/starlette/fastapi: pull every submodule (protocol/loop implementations
# are imported by string name, so PyInstaller can't see them statically).
for pkg in ("uvicorn", "starlette", "fastapi", "anyio"):
    hiddenimports += collect_submodules(pkg)

# python-docx ships a default.docx template as package data; Pillow/openpyxl too.
for pkg in ("docx", "openpyxl", "xlrd", "pypdf", "PIL"):
    datas += collect_data_files(pkg)
    hiddenimports += collect_submodules(pkg)

# macOS: pywebview's Cocoa backend + our _initial_geometry_darwin import pyobjc
# frameworks dynamically, which PyInstaller can't see statically. Collect them so
# the frozen .app actually opens a window (the most common Mac freeze failure).
if IS_MAC:
    for pkg in ("objc", "Foundation", "AppKit", "WebKit", "Cocoa", "Quartz"):
        try:
            d, b, h = collect_all(pkg)
            datas += d
            binaries += b
            hiddenimports += h
        except Exception:
            hiddenimports.append(pkg)

block_cipher = None

a = Analysis(
    [os.path.join(ROOT, "run_app.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Trim heavy, unused stdlib/third-party to keep the bundle small.
    excludes=["tkinter", "test", "unittest", "pydoc_data"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Optional platform icon (drop files in packaging/assets/ to use them).
_icon_win = os.path.join(ROOT, "packaging", "assets", "localchat.ico")
_icon_mac = os.path.join(ROOT, "packaging", "assets", "localchat.icns")
icon = _icon_win if (IS_WIN and os.path.exists(_icon_win)) else (
    _icon_mac if (IS_MAC and os.path.exists(_icon_mac)) else None
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LocalChat",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,       # native arch (arm64 on Apple Silicon)
    codesign_identity=None,  # signing wired in later, in the build scripts
    entitlements_file=None,
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LocalChat",
)

# macOS: wrap the collected app into a proper .app bundle.
if IS_MAC:
    app = BUNDLE(
        coll,
        name="LocalChat.app",
        icon=icon,
        bundle_identifier="ooo.nobodywho.localchat",
        info_plist={
            "CFBundleName": "LocalChat",
            "CFBundleDisplayName": "LocalChat",
            "NSHighResolutionCapable": True,
            # No network entitlement needed at runtime for local inference; the
            # in-app model downloader uses outbound HTTPS which is allowed by
            # default for a non-sandboxed Developer ID app.
        },
    )
