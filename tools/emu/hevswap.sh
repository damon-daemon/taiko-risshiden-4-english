#!/bin/bash
# hevswap.sh FILE.SCRIPT N outdir : build build/evswap.bin with TR4_EVSWAP=88.37=FILE.SCRIPT,
# load card file 1 (Nobunaga's audience at Kiyosu, before the first town visit), go outside (the swapped
# scene plays) and press X N times with a screenshot after each; contact sheets of 16 in outdir.
# NOBUILD=1 reuses build/evswap.bin. Variables the real trigger would set are unset (odd names/places): ignore those.
D=$(cd "$(dirname "$0")" && pwd); R="$D/../.."; P="$D/hpress.sh"; PY="$R/.venv/bin/python"
mkdir -p "$3"
[ -n "$NOBUILD" ] || TR4_EVSWAP="88.37=$1" "$PY" "$R/tools/build.py" "$R/taiko_risshiden_4.bin" "$R/build/evswap.bin" | tail -1
"$D/hload.sh" "$R/build/evswap.bin" "" "$3/000.png"
"$P" /dev/null X w w Z w w Z w w X w w w w   # file 1 = Nobunaga's audience: his menu, close, room, Go outside? Yes
"$D/hshot.sh" "$3/001.png"
same=0; prev="$3/001.png"
for i in $(seq 2 "$2"); do          # stops once X changes nothing (the scene is over: a static panel)
  f="$3/$(printf %03d $i).png"; "$P" "$f" X w
  if "$PY" -c 'import sys,numpy as n;from PIL import Image as I;a,b=[n.asarray(I.open(f).convert("L"),dtype=float) for f in sys.argv[1:]];sys.exit(int(abs(a-b).mean()>0.4))' "$prev" "$f"; then same=$((same+1)); rm "$f"; [ $same -ge 3 ] && break; else same=0; prev="$f"; fi
done
"$PY" - "$3" <<'PYEOF'
import glob, sys
from PIL import Image
d = sys.argv[1]; shots = sorted(glob.glob(d + '/[0-9][0-9][0-9].png'))
for s in range(0, len(shots), 16):
    sheet = Image.new('RGB', (1280, 896))
    for i, f in enumerate(shots[s:s + 16]):
        sheet.paste(Image.open(f).convert('RGB').resize((320, 224)), (i % 4 * 320, i // 4 * 224))
    sheet.save('%s/sheet%02d.png' % (d, s // 16))
PYEOF
