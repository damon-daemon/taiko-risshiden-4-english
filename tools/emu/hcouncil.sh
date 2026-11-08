#!/bin/bash
# hcouncil.sh image.bin out.png : hfree.sh, then out to the town (Toshiie event), home (ninja:
# council called), the dojo duel tutorial (msg03), the first council (scenario 1, 1560/7/1)
# up to the target-castle choice; saves state slot 4 at the council hall door (before the
# council events) and slot 5 at the end. Key timing is loose: check the shot.
D=$(cd "$(dirname "$0")" && pwd); P="$D/hpress.sh"
"$D/hfree.sh" "$1" /dev/null
"$P" /dev/null Z w w X w w w
for i in $(seq 1 8); do "$P" /dev/null X w; done
"$P" /dev/null Left Left Left Left X w w w
for i in $(seq 1 130); do "$P" /dev/null X w; done
"$P" /dev/null Right Right Right Right X w w w
"$D/../../.venv/bin/python" "$D/pine.py" save 4
for i in $(seq 1 56); do "$P" /dev/null X w; done
"$D/../../.venv/bin/python" "$D/pine.py" save 5
[ "$2" = /dev/null ] || "$D/hshot.sh" "$2"
