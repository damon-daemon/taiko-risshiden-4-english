#!/bin/bash
# hcastle.sh image.bin out.png : new game (hnewgame.sh) = the first line at Kiyosu castle
# (scenario 1, 1560/6/30: Kinoshita Tokichiro's portrait and nameplate). hnewgame.sh's presses
# already reach it (retuned 2026-11-10: the opening has fewer pages since the line joins).
D=$(cd "$(dirname "$0")" && pwd)
"$D/hnewgame.sh" "$1" "$2"
