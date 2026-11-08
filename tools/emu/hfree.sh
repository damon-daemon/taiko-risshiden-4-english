#!/bin/bash
# hfree.sh image.bin out.png : hcastle.sh, then X through the opening events (Nobunaga's
# audience, Person Info) and out to the Kiyosu castle room (free play, scenario 1, 1560/6/30);
# saves state slot 1 there (Triangle = info menu, Start = system menu). Slots are per ELF CRC.
D=$(cd "$(dirname "$0")" && pwd)
"$D/hcastle.sh" "$1" /dev/null
for i in $(seq 1 55); do "$D/hpress.sh" /dev/null X; done
"$D/hpress.sh" /dev/null w w Z w w Z w w
"$D/../../.venv/bin/python" "$D/pine.py" save 1
[ "$2" = /dev/null ] || "$D/hshot.sh" "$2"
