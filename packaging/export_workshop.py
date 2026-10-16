"""Export a slim, single-OS copy of LocalChat for the workshop repos.

This repo holds everything (desktop app source, packaging, CI). Workshop
participants instead clone a slim repo with just the runtime: one launcher,
the prebuilt desktop app, backend/ (incl. requirements and the config template) and
the example data/ + rag/ folders. No .gitignore / .gitattributes: the launcher
adds its own ignore rules to .git/info/exclude, and line endings are committed
as-is (CRLF .bat, LF .command), so the root shows only what learners need. Both slim repos come from here, so they never drift apart.

    python packaging/export_workshop.py windows <tmp>/win --repo-url https://github.com/<owner>/localchat-windows.git --app-dir <dir>
    python packaging/export_workshop.py mac     <tmp>/mac --repo-url https://github.com/<owner>/localchat-mac.git --app-dir <dir>

--app-dir is a folder holding the desktop app built by CI (the
"LocalChat-windows" / "LocalChat-macos" artifact of .github/workflows/desktop-app.yml:
LocalChat-<os>.zip + version.txt). It is exported as app/LocalChat.zip and
app/version.txt; the launcher unpacks it on first run.

--repo-url fills the `git clone` line in the README; re-export with the new URL
when the repos move.

The target is synced to match the export exactly: EVERYTHING except .git is
deleted first, including a venv/, config.toml or "LocalChat data/" (chats).
So export to a temporary folder, not into a clone you run LocalChat from, and
copy the files over (see CLAUDE.md decision #16). If the target is a git repo, the result is staged (with the macOS
launcher marked executable) but NOT committed: review, commit and push by hand.
Stdlib only.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKSHOP = Path(__file__).resolve().parent / "workshop"

LAUNCHERS = {"windows": "Start LocalChat.bat", "mac": "Start LocalChat.command"}
APP_ZIPS = {"windows": "LocalChat-windows.zip", "mac": "LocalChat-macos.zip"}

# Text files written with LF endings (the slim repos have no .gitattributes).
LF_TEXT = {".py", ".toml", ".txt", ".md", ".csv", ".command", ".html", ".js", ".css", ".json", ".svg"}

# Shared runtime files (repo-relative). backend/ is added from `git ls-files`
# so caches and local junk never leak into the export.
COMMON = ["data/sales_2025.csv", "rag/employee_handbook.md"]


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def file_list(target_os: str, app_dir: Path) -> dict[str, Path]:
    """Map of export-relative path -> source file."""
    files = {p: ROOT / p for p in COMMON}
    files["app/LocalChat.zip"] = app_dir / APP_ZIPS[target_os]
    files["app/version.txt"] = app_dir / "version.txt"
    for line in _git("ls-files", "backend", cwd=ROOT).splitlines():
        if (ROOT / line).is_file():  # skip tracked-but-deleted files
            files[line] = ROOT / line
    files[LAUNCHERS[target_os]] = ROOT / LAUNCHERS[target_os]
    files["README.md"] = WORKSHOP / f"README-{target_os}.md"
    return files


def export(target_os: str, out: Path, repo_url: str, app_dir: Path) -> None:
    files = file_list(target_os, app_dir)
    missing = [str(src) for src in files.values() if not src.is_file()]
    if missing:
        sys.exit("missing source files:\n  " + "\n  ".join(missing))

    # The sync below deletes everything but .git: never run it on a folder
    # someone uses LocalChat from (venv, settings, chats).
    in_use = [n for n in ("venv", ".uv", "config.toml", "LocalChat data") if (out / n).exists()]
    if in_use:
        sys.exit(f"{out} is a LocalChat folder in use ({', '.join(in_use)}): export to an "
                 "empty folder and copy the files over instead.")

    out.mkdir(parents=True, exist_ok=True)
    for child in out.iterdir():
        if child.name == ".git":
            continue
        shutil.rmtree(child) if child.is_dir() else child.unlink()

    for rel, src in files.items():
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if rel == "README.md":
            text = src.read_text(encoding="utf-8").replace("REPO_URL", repo_url)
            dst.write_text(text, encoding="utf-8", newline="\n")
        elif src.suffix in LF_TEXT:
            # Line endings as on a Mac/Linux checkout, whatever this machine's
            # git settings made of the working copy (only the .bat keeps CRLF).
            dst.write_bytes(src.read_bytes().replace(b"\r\n", b"\n"))
        else:
            shutil.copyfile(src, dst)
    print(f"exported {len(files)} files for {target_os} -> {out}")

    if (out / ".git").exists():
        # autocrlf=false: with no .gitattributes in the slim repo, commit the
        # launchers byte-for-byte (CRLF .bat, LF .command) so every clone gets
        # working line endings whatever the cloner's own git settings.
        _git("-c", "core.autocrlf=false", "add", "-A", cwd=out)
        if target_os == "mac":
            # Finder only runs a .command that is executable; git keeps the bit.
            _git("-c", "core.autocrlf=false", "add", "--chmod=+x", LAUNCHERS["mac"], cwd=out)
        print("staged in", out, "- review with `git status`, then commit + push")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("os", choices=sorted(LAUNCHERS))
    ap.add_argument("out", type=Path, help="target directory (ideally a clone of the slim repo)")
    ap.add_argument("--repo-url", required=True, help="clone URL shown in the README")
    ap.add_argument("--app-dir", type=Path, required=True,
                    help="folder with the CI-built desktop app (LocalChat-<os>.zip + version.txt)")
    args = ap.parse_args()
    if args.out.resolve() == ROOT:
        sys.exit("refusing to export over the source repo")
    export(args.os, args.out.resolve(), args.repo_url, args.app_dir.resolve())


if __name__ == "__main__":
    main()
