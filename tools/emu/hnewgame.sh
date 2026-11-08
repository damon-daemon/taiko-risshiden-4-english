#!/bin/bash
# hnewgame.sh image.bin out.png : headless run from boot to msg21 #30 "ｿﾚﾃﾞﾊ、ｹﾞｰﾑｦ始ﾒﾏｽ"
# (new game, scenario 1, first hero, default abilities and settings); screenshot of it
D=$(cd "$(dirname "$0")" && pwd)
"$D/headless.sh" stop; timeout 2 tail -f /dev/null
"$D/headless.sh" "$1" || exit 1; timeout 15 tail -f /dev/null
"$D/hpress.sh" /dev/null Return w w X w w Return w w w X w w w      # title, はじめから, scenario 1
"$D/hpress.sh" /dev/null X w w X w w X w w w w X w w w              # intro, 可, hero list, details
"$D/hpress.sh" /dev/null X w w X w w w w w X w w w         # abilities, confirm 可
"$D/hpress.sh" /dev/null X w w w w X w w w X w w w w w w w w w w w w   # settings, OK, 可
"$D/hshot.sh" "$2"
