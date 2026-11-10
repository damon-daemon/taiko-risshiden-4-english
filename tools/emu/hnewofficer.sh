#!/bin/bash
# hnewofficer.sh image.bin out.png : headless run from boot to the new-officer name entry
# (new game, scenario 1, first hero, with the new-officer branch forced: PINE nop at 0x1dc510)
D=$(cd "$(dirname "$0")" && pwd)
"$D/headless.sh" stop; timeout 3 tail -f /dev/null
"$D/headless.sh" "$1" || exit 1; timeout 15 tail -f /dev/null
"$D/hpress.sh" /dev/null w w w w Return w w w w w w Return w w w w
"$D/../../.venv/bin/python" "$D/pine.py" write 0x1dc510 00000000
"$D/hpress.sh" /dev/null Up w X w w w w w              # New Game (the cursor starts on Continue once the card has saves)
"$D/hpress.sh" /dev/null X w w w X w w w X w w w w     # scenario 1, intro, hero list -> details
"$D/hpress.sh" /dev/null X w w w w X w w w w w          # OK, Yes
"$D/hpress.sh" /dev/null w w
[ "$2" = /dev/null ] || "$D/hshot.sh" "$2"
