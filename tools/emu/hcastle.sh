#!/bin/bash
# hcastle.sh image.bin out.png : new game (hnewgame.sh), then X through the opening events to
# the first line at Kiyosu castle (scenario 1, 1560/6/30), where the Japanese game shows
# Kinoshita Tokichiro's portrait and nameplate. Used to bisect the missing event portraits.
D=$(cd "$(dirname "$0")" && pwd)
"$D/hnewgame.sh" "$1" /dev/null
"$D/hpress.sh" /dev/null X w w w w w w w w w w
"$D/hpress.sh" /dev/null X w w w w w w w w
for i in $(seq 1 81); do "$D/hpress.sh" /dev/null X; done
"$D/hpress.sh" "$2" w
