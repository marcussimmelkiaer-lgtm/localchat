#!/usr/bin/env bash
# Double-click launcher for macOS: Finder runs .command files in Terminal
# (a .sh file would just open in an editor). Everything happens in run.sh.
cd "$(dirname "$0")" && exec ./run.sh
