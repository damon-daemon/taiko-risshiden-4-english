#!/bin/bash
# hload.sh image.bin "KEYS" out.png : headless boot, title "Continue" (the default once the
# card has saves), move the load-list cursor with KEYS ("" = file 1, "Down Down" = 3rd file;
# empty slots are skipped, Up from file 1 wraps to the last file), load; screenshot.
# Headless card: 1 = 1560/6/30 castle, 2 = 1560/7/2 rice shop, 3 = 1560/9/1 Kiyosu town on
# council day, 4 = copy of 2 (saved by g3: full name in the header), 5 = 1560/11/1 S. General (rank set in RAM) with a Train mission (the drill
# ground's Train = Mock Battle: the battle engine). Key timing is loose: check the shot.
D=$(cd "$(dirname "$0")" && pwd); P="$D/hpress.sh"
"$D/headless.sh" stop; timeout 2 tail -f /dev/null
"$D/headless.sh" "$1" || exit 1; timeout 15 tail -f /dev/null
"$P" /dev/null w w w w Return w w w w Return w w w w Return w w w X w w w w w
for k in $2; do "$P" /dev/null "$k" w; done
"$P" /dev/null X w w X w w w w X w w w
[ "$3" = /dev/null ] || "$D/hshot.sh" "$3"
