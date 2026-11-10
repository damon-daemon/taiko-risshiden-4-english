"""Print boxes of bright (or dark) text clusters in an FTX image: gfxfind.py entry.image [thr] [gap]
(dev aid for tools/gfx.py ITEMS coordinates; thr < 0 = dark text below -thr)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import ftx, gfx

e, i = map(int, sys.argv[1].split('.'))
thr = int(sys.argv[2]) if len(sys.argv) > 2 else 170
gap = int(sys.argv[3]) if len(sys.argv) > 3 else 8
im = ftx.images(ftx.load(e))[i]
L = lambda x, y: gfx.luma(im.pal[im.pix[y * im.w + x]]) if im.pal[im.pix[y * im.w + x]][3] >= 0x40 else (999 if thr < 0 else -1)
on = lambda x, y: L(x, y) < -thr if thr < 0 else L(x, y) > thr
pts = {(x, y) for y in range(im.h) for x in range(im.w) if on(x, y)}
# union-find of points within gap (chebyshev) -> boxes
boxes = []
for x, y in sorted(pts, key=lambda p: (p[1], p[0])):
    for b in boxes:
        if b[0] - gap <= x <= b[2] + gap and b[1] - gap // 2 <= y <= b[3] + gap // 2:
            b[0], b[1], b[2], b[3] = min(b[0], x), min(b[1], y), max(b[2], x), max(b[3], y)
            break
    else:
        boxes.append([x, y, x, y])
merged = True
while merged:
    merged = False
    for a in boxes:
        for b in boxes:
            if a is not b and a[0] - gap <= b[2] and b[0] - gap <= a[2] and a[1] - gap // 2 <= b[3] and b[1] - gap // 2 <= a[3]:
                a[:] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                boxes.remove(b); merged = True; break
        if merged:
            break
for b in sorted(boxes, key=lambda b: (b[1], b[0])):
    if (b[2] - b[0]) * (b[3] - b[1]) >= 12:
        print(tuple(b), b[2] - b[0] + 1, 'x', b[3] - b[1] + 1)
