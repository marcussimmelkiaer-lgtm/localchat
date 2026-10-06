"""Export a slim, single-OS copy of LocalChat for the workshop repos.

This repo holds everything (frontend source, packaging, CI). Workshop
participants instead clone a slim repo with just the runtime: one launcher,
backend/ (incl. the prebuilt SPA in backend/static), requirements and the config
template. Both slim repos come from here, so they never drift apart.

    python packaging/export_workshop.py windows ../localchat-windows --repo-url https://github.com/<owner>/localchat-windows.git
    python packaging/export_workshop.py mac     ../localchat-mac     --repo-url https://github.com/<owner>/localchat-mac.git

--repo-url fills the `git clone` line in the README; re-export with the new URL
when the repos move.

The target is synced to match the export exactly (everything except .git is
replaced). If the target is a git repo, the result is staged (with the macOS
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

# Shared runtime files (repo-relative). backend/ is added from `git ls-files`
# so caches and local junk never leak into the export.
COMMON = ["requirements.txt", "config.example.toml", ".gitattributes"]


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def file_list(target_os: str) -> dict[str, Path]:
    """Map of export-relative path -> source file."""
    files = {p: ROOT / p for p in COMMON}
    for line in _git("ls-files", "backend", cwd=ROOT).splitlines():
        if (ROOT / line).is_file():  # skip tracked-but-deleted files
            files[line] = ROOT / line
    files[LAUNCHERS[target_os]] = ROOT / LAUNCHERS[target_os]
    files["README.md"] = WORKSHOP / f"README-{target_os}.md"
    files[".gitignore"] = WORKSHOP / "gitignore"
    return files


def export(target_os: str, out: Path, repo_url: str) -> None:
    files = file_list(target_os)
    missing = [str(src) for src in files.values() if not src.is_file()]
    if missing:
        sys.exit("missing source files:\n  " + "\n  ".join(missing))

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
        else:
            shutil.copyfile(src, dst)
    print(f"exported {len(files)} files for {target_os} -> {out}")

    if (out / ".git").exists():
        _git("add", "-A", cwd=out)
        if target_os == "mac":
            # Finder only runs a .command that is executable; git keeps the bit.
            _git("add", "--chmod=+x", LAUNCHERS["mac"], cwd=out)
        print("staged in", out, "- review with `git status`, then commit + push")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("os", choices=sorted(LAUNCHERS))
    ap.add_argument("out", type=Path, help="target directory (ideally a clone of the slim repo)")
    ap.add_argument("--repo-url", required=True, help="clone URL shown in the README")
    args = ap.parse_args()
    if args.out.resolve() == ROOT:
        sys.exit("refusing to export over the source repo")
    export(args.os, args.out.resolve(), args.repo_url)


if __name__ == "__main__":
    main()
