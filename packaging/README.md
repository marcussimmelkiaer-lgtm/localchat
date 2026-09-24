# Packaging LocalChat as downloadable installers

This directory turns the source app into **one double-click installer file per
OS** — `LocalChat-Setup-x64.exe` (Windows) and `LocalChat-arm64.dmg` (macOS) —
no git clone, no venv.

## How it's put together

The app is Python (FastAPI/uvicorn + pywebview) + the native `nobodywho` wheel +
a built React SPA. Packaging has two layers:

1. **Freeze** the app with **PyInstaller** (`localchat.spec`) into a small
   self-contained folder — Python, all deps, the `nobodywho` native lib
   (llama.cpp + GPU backend), and `backend/static`.
2. **Wrap** it in a single platform installer: Inno Setup `.exe` / `.dmg`.

**No models are bundled.** Windows won't run a `Setup.exe` much over ~4 GB, and
three preloaded models were ~5 GB (that forced a multi-file `.exe` + `.bin` set).
Instead, on first launch the app downloads its default model (Qwen3-4B, ~2.5 GB)
into NobodyWho's cache in the background — the composer shows
"Downloading model… N%" and unlocks when it's loaded. **First launch needs
internet once**; after that it's fully offline. Other models download from the
in-app **Models** menu. If the download fails (offline), the UI says so; restart
or use the Models menu to retry.

### Writable paths (why the app needed changes)

A frozen bundle is **read-only**, so anything the app writes moved to a per-user
data dir (`backend/paths.py`):

| Data | Dev (source checkout) | Packaged build |
|------|----------------------|----------------|
| config.toml, DB, uploads | repo root | `%LOCALAPPDATA%\LocalChat` / `~/Library/Application Support/LocalChat` |
| static SPA, config template | repo root | inside the bundle (read-only) |
| model GGUFs | NobodyWho cache | NobodyWho cache (downloaded on first launch) |

`backend/bootstrap.py` runs on launch **only when frozen**: it seeds a default
`config.toml` and adopts an already-cached Qwen3 model if there is one (so a
reinstall doesn't re-download). If none is cached, the engine starts the
download once the UI is up (`NobodyWhoEngine._start_first_run_download`). In a
source checkout all of this is a no-op, so `run.sh` / `run.bat` behave exactly
as before.

## Prerequisites

- The project **venv** with app deps installed, **plus** `pip install pyinstaller`.
- **Windows:** [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`ISCC.exe`).
- **macOS:** an **Apple-Silicon** Mac (arm64 — there is no Intel `nobodywho`
  wheel), Xcode command-line tools; optionally `create-dmg` for a nicer DMG.

## Build — Windows

```powershell
# from the repo root, venv active
powershell -ExecutionPolicy Bypass -File packaging\build_win.ps1
```

Produces a single `dist\installer\LocalChat-Setup-x64.exe` (~40 MB). It:
- freezes the app,
- downloads the WebView2 bootstrapper if missing,
- compiles the Inno installer.

The installer is **per-user** (`PrivilegesRequired=lowest`, no admin): the app
goes to `%LOCALAPPDATA%\Programs\LocalChat` and models to
`%LOCALAPPDATA%\nobodywho\models`. Per-user is required so `{localappdata}`
resolves to the real user (an elevated Program-Files install would write models
to the admin's cache instead).

## Build — macOS (Apple Silicon)

```bash
# from the repo root, arm64 venv active
./packaging/macos/build_mac.sh
```

Produces a single `dist/LocalChat-arm64.dmg`. Same first-launch model download
as Windows.

## Signing (deferred)

Both builds currently ship **unsigned**. Until the NobodyWho signing assets are
wired in:

- **Windows:** users see a SmartScreen "unknown publisher" warning → *More info →
  Run anyway*. Fix: an Authenticode (OV/EV) certificate + `signtool` on the
  `.exe` and the installer (add to `build_win.ps1`).
- **macOS:** Gatekeeper blocks it ("unidentified developer") → users right-click →
  **Open** once, or run `xattr -dr com.apple.quarantine /Applications/LocalChat.app`.
  Fix: an **Apple Developer Program** membership → "Developer ID Application" cert
  → `codesign` + `notarytool` (stubbed near the bottom of `build_mac.sh`).

## Distribution note

Both installers are small (tens of MB), so they fit as **GitHub release assets**
(2 GB limit) or any static host.

## Files

| File | Purpose |
|------|---------|
| `localchat.spec` | PyInstaller freeze (cross-platform) |
| `build_win.ps1` | Windows end-to-end build |
| `windows/localchat.iss` | Inno Setup installer definition (single file) |
| `macos/build_mac.sh` | macOS `.app` + `.dmg` build |
| `assets/` | optional `localchat.ico` / `localchat.icns` |

CI: `.github/workflows/build-installers.yml` builds both installers on GitHub
runners (`macos-14` + `windows-latest`) on manual dispatch or a `v*` tag,
uploading each as an artifact — the standard way to get the **macOS `.dmg`**
without a local Mac.
