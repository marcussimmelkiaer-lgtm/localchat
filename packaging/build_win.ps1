# Build the Windows LocalChat installer end-to-end.
#
# From the repo root, in the project venv (with `pip install pyinstaller`):
#     powershell -ExecutionPolicy Bypass -File packaging\build_win.ps1
#
# Steps:
#   1. (optional) rebuild the frontend into backend\static
#   2. PyInstaller freeze  -> dist\LocalChat
#   3. fetch the WebView2 Evergreen bootstrapper (if absent)
#   4. compile the Inno Setup installer -> dist\installer\LocalChat-Setup-x64.exe
#      (ONE file; no models inside — the app downloads its model on first launch)
#
# Prereqs: Python (the repo venv, or `python` on PATH as in CI) with the app deps
# + PyInstaller, and Inno Setup 6 (ISCC.exe) on PATH or at the default install
# location. Node/npm only for step 1.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Py = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = (Get-Command python -ErrorAction SilentlyContinue).Source }  # CI: no venv
if (-not $Py) { throw "python not found (no venv\Scripts\python.exe and none on PATH)" }

# --- 1. frontend (optional; skip with -SkipFrontend) ------------------------
if ($args -notcontains "-SkipFrontend" -and (Test-Path (Join-Path $Root "frontend\package.json"))) {
  Write-Host "==> building frontend"
  Push-Location (Join-Path $Root "frontend")
  npm run build
  Pop-Location
}

# --- 2. freeze --------------------------------------------------------------
Write-Host "==> PyInstaller freeze"
Remove-Item -Recurse -Force (Join-Path $Root "dist\LocalChat") -ErrorAction SilentlyContinue
& $Py -m PyInstaller "packaging\localchat.spec" --noconfirm --distpath "dist" --workpath "build\pyi"
if (-not (Test-Path (Join-Path $Root "dist\LocalChat\LocalChat.exe"))) { throw "freeze failed" }

# --- 3. WebView2 bootstrapper ----------------------------------------------
$Wv2 = Join-Path $Root "packaging\windows\MicrosoftEdgeWebview2Setup.exe"
if (-not (Test-Path $Wv2)) {
  Write-Host "==> downloading WebView2 bootstrapper"
  Invoke-WebRequest -Uri "https://go.microsoft.com/fwlink/p/?LinkId=2124703" -OutFile $Wv2
}

# --- 4. Inno Setup ----------------------------------------------------------
Write-Host "==> compiling installer"
$Iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $Iscc) {
  $candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"  # winget per-user install
  )
  foreach ($c in $candidates) {
    if (Test-Path $c) { $Iscc = $c; break }
  }
}
if (-not $Iscc) { throw "ISCC.exe (Inno Setup 6) not found. Install from https://jrsoftware.org/isinfo.php" }
& $Iscc "packaging\windows\localchat.iss"
if ($LASTEXITCODE -ne 0) { throw "ISCC failed ($LASTEXITCODE)" }

Write-Host "==> done: dist\installer\LocalChat-Setup-x64.exe"
