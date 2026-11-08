#!/bin/bash
# hshot.sh out.png : screenshot of the headless PCSX2 (tools/emu/headless.sh)
# The gamescope socket is taken from our PCSX2's environment (gamescope sets
# GAMESCOPE_WAYLAND_DISPLAY for its child), never "the newest socket": another
# project's headless gamescope may be running.
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
out=$(realpath -m "$1"); rm -f "$out"
sock=$("$ROOT/.venv/bin/python" "$ROOT/tools/emu/xkeys.py" wayland) || exit 1
GAMESCOPE_WAYLAND_DISPLAY=$sock gamescopectl screenshot "$out" >/dev/null 2>&1
for i in $(seq 1 20); do [ -s "$out" ] && break; timeout 0.25 tail -f /dev/null; done
[ -s "$out" ] || { echo "no screenshot"; exit 1; }
