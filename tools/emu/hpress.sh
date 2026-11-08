#!/bin/bash
# hpress.sh out.png key ... : press keys in the headless PCSX2 (tools/emu/headless.sh)
#   keys: X=Circle(confirm) Z=Cross(cancel) S=Triangle A=Square Return=Start BackSpace=Select
#   Q/W=L1/R1 Up/Down/Left/Right; 'w' alone = wait 1s; out.png = /dev/null for no screenshot
# Keys go to gamescope's private X display only (tools/emu/xkeys.py), never the desktop
# or another emulator.
D=$(cd "$(dirname "$0")" && pwd); PY="$D/../../.venv/bin/python"
for k in "${@:2}"; do
  case "$k" in
    w) timeout 1 tail -f /dev/null; continue;;
    X|Z|S|A|Q|W) k=${k,,};;
  esac
  "$PY" "$D/xkeys.py" hold "$k" 250 || exit 1; timeout 0.3 tail -f /dev/null
done
timeout 0.5 tail -f /dev/null
[ "$1" = /dev/null ] || "$D/hshot.sh" "$1"
