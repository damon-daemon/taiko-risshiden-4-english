#!/bin/bash
# headless.sh image.iso : run PCSX2 on a disc image inside a headless gamescope (no window
# on the desktop); drive it with hpress.sh (keys via tools/emu/xkeys.py on gamescope's
# private X display), screenshot with hshot.sh, inspect with tools/emu/pine.py.
# Stop: tools/emu/headless.sh stop
# Output size: HW/HH (default 640x448; e.g. HW=2560 HH=1792 with upscaling to check it).
#
# Runs side by side with other projects' headless emulators (e.g. a DuckStation
# session): input never leaves our X display, SDL pads are ignored (datapath.py
# --headless), screenshots use our own gamescope socket, stop kills only our processes.
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
MARK="$ROOT/build/pcsx2h"
if [ "$1" = stop ]; then
  pkill -f "gamescope --backend headless .*$MARK"; exit 0
fi
"$ROOT/.venv/bin/python" "$ROOT/tools/emu/datapath.py" --headless >/dev/null
(env -u WAYLAND_DISPLAY QT_QPA_PLATFORM=xcb gamescope --backend headless -W ${HW:-640} -H ${HH:-448} -- \
  ~/.local/bin/pcsx2-v2.4.0-linux-appimage-x64-Qt.AppImage -datapath "$MARK" -batch -fastboot -fullscreen \
  -- "$(realpath "$1")" > "$MARK/headless.log" 2>&1 &)
