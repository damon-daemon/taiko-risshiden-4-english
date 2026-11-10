"""Redraw Japanese text baked into the FTX images (tabs, buttons, labels, banners).

Ported from TR5's gfx.py (same primitives); TR4 images come from tools/ftx.py
(uncompressed 4/8bpp with CLUT, edited in place: sizes never change).

Lettering comes from the stroke glyphs of latinfont (original drawings), rendered at
any size; colours are taken from the original image so the English keeps its look:

  banner(): big outlined lettering on a transparent image: the original's layers are
    measured (fill, dark outline, soft light outer outline) and rebuilt around the English.
  plate(): text on a background: the text area is refilled row by row from a clean sample
    area beside it (or 'inpaint'), then the English is drawn in the original's ink.
  label(): outlined text on a flat background. glyph(): light text with a dark halo on
    transparency. button(): dark text on a framed button.

Items (entry, image) -> kind + areas are listed in ITEMS; their English is in tl/gfx.txt
("entry.image<TAB>English", '|' between spots).

  python tools/gfx.py preview out.png [entry.image ...]
"""
import collections, os, sys
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))
import disc, ftx, latinfont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL = os.path.join(ROOT, 'tl', 'gfx.txt')
SS = 4
FOLD = dict((v, latinfont.MACRONS[v]) for v in latinfont.MACRONS)

def luma(c):
    return (c[0] * 299 + c[1] * 587 + c[2] * 114) // 1000

class Canvas:
    """An image being edited (ftx.Image): pixels are palette indexes."""
    def __init__(self, im):
        self.im = im
        self.w, self.h, self.pix, self.pal = im.w, im.h, im.pix, im.pal
        self.n = 256 if im.bpp == 8 else 16
        top = min(0x80, max(c[3] for c in self.pal[:self.n]))
        self.opaque = [i for i, c in enumerate(self.pal[:self.n]) if c[3] >= top - 4]
        self.cache = {}

    def get(self, x, y):
        return self.pal[self.pix[y * self.w + x]]

    def idx(self, x, y):
        return self.pix[y * self.w + x]

    def put(self, x, y, i):
        self.pix[y * self.w + x] = i

    def index(self, rgb, alpha=0x80):
        """Nearest palette entry to an RGB colour (and alpha, 0-0x80)."""
        key = tuple(int(round(v)) for v in rgb[:3]) + (int(round(alpha)),)
        if key not in self.cache:
            cands = self.opaque if alpha >= 0x80 else range(self.n)
            self.cache[key] = min(cands, key=lambda i: sum((a - b) ** 2 for a, b in zip(self.pal[i][:3], key[:3]))
                                  + 4 * (self.pal[i][3] - key[3]) ** 2)
        return self.cache[key]

    def view(self, box):
        """A Canvas on the region box (x0, y0, x1, y1 inclusive) of this one."""
        return View(self, box)

    def light(self, rgb, alpha):
        """Palette entry for a soft edge of a light outline: same colour, lower alpha."""
        key = ('light',) + tuple(rgb) + (int(alpha),)
        if key not in self.cache:
            cands = [i for i in range(self.n) if luma(self.pal[i]) >= luma(rgb) - 24] or range(self.n)
            self.cache[key] = min(cands, key=lambda i: abs(self.pal[i][3] - alpha) * 8
                                  + sum((a - b) ** 2 for a, b in zip(self.pal[i], rgb)) ** 0.5)
        return self.cache[key]

class View(Canvas):
    """A region of a Canvas (atlases hold several labels side by side)."""
    def __init__(self, cv, box):
        x0, y0, x1, y1 = box
        self.base, self.x0, self.y0 = cv, x0, y0
        self.w, self.h, self.pal, self.n = x1 - x0 + 1, y1 - y0 + 1, cv.pal, cv.n
        self.opaque, self.cache = cv.opaque, cv.cache

    def get(self, x, y):
        return self.base.get(self.x0 + x, self.y0 + y)

    def idx(self, x, y):
        return self.base.idx(self.x0 + x, self.y0 + y)

    def put(self, x, y, i):
        self.base.put(self.x0 + x, self.y0 + y, i)

# ---------------------------------------------------------------- lettering

def text_masks(text, cap, widths, condense=1.0, spacing=None, descender=None):
    """Coverage images (PIL 'L', SS times the final size) of text drawn with each
    stroke width in widths (px, final scale): wider strokes give the outline layers.
    Returns (images, (w, h), (left, top) of the cap box) at final scale."""
    stroke = widths[0]
    s = (cap - stroke) / latinfont.C
    text = ''.join(FOLD.get(c, c) for c in text)      # macron vowels: latinfont's glyph codes
    spacing = stroke * 0.45 if spacing is None else spacing
    pad = max(widths) / 2 + 2
    xs, x = [], pad
    for c in text:
        w, _ = latinfont.GLYPHS[c]
        xs.append(x)
        x += (w * s * condense + stroke + spacing) if c != ' ' else cap * 0.32
    width = x - spacing + pad
    if descender is None:
        descender = any(c in 'gjpqy,;' for c in text)
    height = cap + stroke + 2 * pad + (3 * s if descender else 0)
    base = pad + cap - stroke / 2
    out = []
    for sw in widths:
        im = Image.new('L', (int(width * SS) + 1, int(height * SS) + 1), 0)
        dr = ImageDraw.Draw(im)
        r = sw * SS / 2
        for c, x0 in zip(text, xs):
            for st in latinfont.GLYPHS[c][1]:
                pts = [((x0 + stroke / 2 + px * s * condense) * SS, (base - py * s) * SS) for px, py in st]
                # segment by segment with round joints (thick joined polylines spike)
                for a, b in zip(pts, pts[1:]):
                    dr.line([a, b], fill=255, width=max(1, round(sw * SS)))
                for px, py in pts:
                    dr.ellipse((px - r, py - r, px + r, py + r), fill=255)
        out.append(im)
    return out, (width, height), (pad, pad)

def downsample(im, size):
    return im.resize(size, Image.BOX)

# ---------------------------------------------------------------- banners

def _runs(row):
    out, x = [], 0
    while x < len(row):
        if row[x]:
            x0 = x
            while x < len(row) and row[x]:
                x += 1
            out.append((x0, x))
        x += 1
    return out

def banner_style(cv):
    """Layers of an outlined banner: (fill rows {y: [index...]}, outline index,
    outer rgb, outer width, outline width, text rows (y0, y1))."""
    w, h = cv.w, cv.h
    A = [[cv.get(x, y)[3] for x in range(w)] for y in range(h)]
    L = [[luma(cv.get(x, y)) for x in range(w)] for y in range(h)]
    light = [[A[y][x] > 0 and L[y][x] >= 235 for x in range(w)] for y in range(h)]
    inner = [[A[y][x] >= 0x78 and L[y][x] < 235 for x in range(w)] for y in range(h)]
    ys = [y for y in range(h) if any(inner[y])]
    # outer width: runs of light pixels between transparency and the inner text
    widths, dark = [], collections.Counter()
    for y in ys:
        for x0, x1 in _runs(light[y]):
            if x1 < w and inner[y][x1] and (x0 == 0 or A[y][x0 - 1] == 0 or not inner[y][x0 - 1]):
                widths.append(x1 - x0)
                for k in range(3):
                    if x1 + k < w and inner[y][x1 + k]:
                        dark[cv.idx(x1 + k, y)] += 1
    if widths:
        outer_w = sorted(widths)[len(widths) // 2]
        outline = dark.most_common(1)[0][0]
        outline_w = 2 if outer_w >= 5 else 1
        outer = collections.Counter(cv.get(x, y)[:3] for y in range(h) for x in range(w) if light[y][x])
        outer_rgb = outer.most_common(1)[0][0]
    else:
        # no light outer outline: the dark outline is the text's edge against transparency
        edge = collections.Counter(cv.idx(x, y) for y in ys for x in range(w) if inner[y][x] and any(
            A[y + dy][x + dx] < 0x78 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            if 0 <= y + dy < h and 0 <= x + dx < w))
        outer_w, outline, outline_w, outer_rgb = 0, edge.most_common(1)[0][0], 1, None
        light = [[A[y][x] < 0x78 for x in range(w)] for y in range(h)]
    # fill: inner pixels away from the light outline
    near = [[False] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if light[y][x] or A[y][x] < 0x78:
                for dy in range(-outline_w - 1, outline_w + 2):
                    for dx in range(-outline_w - 1, outline_w + 2):
                        if 0 <= y + dy < h and 0 <= x + dx < w:
                            near[y + dy][x + dx] = True
    fill = {y: [cv.idx(x, y) for x in range(w) if inner[y][x] and not near[y][x]] for y in range(h)}
    # one colour per row (the median by brightness): the originals are striped
    fill = {y: sorted(v, key=lambda i: luma(cv.pal[i]))[len(v) // 2] for y, v in fill.items() if v}
    return fill, outline, outer_rgb, outer_w, outline_w, (ys[0], ys[-1])

def banner(cv, text, cap=None):
    """Replace the lettering of an outlined banner texture with text (centred)."""
    fill, outline, outer_rgb, ow, lw, (y0, y1) = banner_style(cv)
    transparent = min(range(cv.n), key=lambda i: cv.pal[i][3])
    cap = cap or (y1 - y0 + 1) * 0.72
    condense = 1.0
    while True:
        stroke = max(2.0, cap * (0.17 if cap >= 30 else 0.12))
        o_w = min(ow, max(2.0, cap * 0.12))           # a thick glow merges small letters
        l_w = lw if cap >= 24 else 1
        widths = [stroke, stroke + 2 * l_w, stroke + 2 * (l_w + o_w)]
        masks, (tw, th), _ = text_masks(text, cap, widths, condense)
        if tw <= cv.w - 4 or cap < 6:
            break
        if condense > 0.8:
            condense *= 0.96
        else:
            cap *= 0.95
    if tw > cv.w - 1:
        raise ValueError('banner %r: %d px wide, texture %d' % (text, tw, cv.w))
    size = (int(tw) + 1, int(th) + 1)
    core, mid, out = (downsample(m, (size[0], size[1])) for m in masks)
    ox = (cv.w - size[0]) // 2
    oy = (y0 + y1) // 2 - size[1] // 2
    fy = sorted(fill)
    for y in range(cv.h):
        for x in range(cv.w):
            cv.put(x, y, transparent)
    for y in range(size[1]):
        ty = oy + y
        if not 0 <= ty < cv.h:
            continue
        row = fill[min(fy, key=lambda r: abs(r - (y0 + (y1 - y0) * y / size[1])))]
        for x in range(size[0]):
            tx = ox + x
            c, m, o = core.getpixel((x, y)) / 255, mid.getpixel((x, y)) / 255, out.getpixel((x, y)) / 255
            if c > 0.5:
                i = row
            elif m > 0.5:
                i = outline
            elif o > 0.1 and outer_rgb:
                i = cv.light(outer_rgb, o * 0x80)
            else:
                continue
            cv.put(tx, ty, i)

# ---------------------------------------------------------------- plates

def plate(cv, area, sample, text, ink, edge, cap, stroke, edge_w=1.5, align='center', text_area=None):
    """Erase area (x0, y0, x1, y1) by refilling each row with the colours of the same
    row in the sample columns (sx0, sx1), then draw text with ink inside an edge outline
    (rgb colours or None), centred in text_area (default: area) over what is there."""
    x0, y0, x1, y1 = area
    orig = sorted((cv.get(x, y) for y in range(y0, y1) for x in range(x0, x1)), key=luma)
    ink_a = orig[len(orig) // 16][3]                     # alpha of the original text
    if sample == 'inpaint':
        # replace only the text's pixels by the nearest other pixel of the row (keeps
        # brush swashes and gradients under the text)
        th = (luma(orig[len(orig) // 16]) + luma(orig[len(orig) * 3 // 4])) / 2
        for y in range(y0, y1):
            row = [cv.idx(x, y) for x in range(x0 - 1, x1 + 1)]
            keep = [luma(cv.pal[i]) > th for i in row]
            for k in range(1, len(row) - 1):
                if not keep[k]:
                    near = min((j for j in range(len(row)) if keep[j]), key=lambda j: abs(j - k), default=None)
                    if near is not None:
                        cv.put(x0 - 1 + k, y, row[near])
    else:
        for y in range(y0, y1):
            row = [cv.idx(x, y) for x in range(*sample)]
            for x in range(x0, x1):
                cv.put(x, y, row[(x - x0) % len(row)])
    if ink is None:
        ink = orig[len(orig) // 16][:3]                   # the original text colour
    if not text:
        return
    x0, y0, x1, y1 = text_area or area
    widths = [stroke] + ([stroke + 2 * edge_w] if edge else [])
    condense = 1.0
    while True:
        masks, (tw, th), (px, py) = text_masks(text, cap, widths, condense, descender=True)
        if tw <= x1 - x0 or condense < 0.6:
            break
        condense *= 0.95
    size = (int(tw) + 1, int(th) + 1)
    layers = [downsample(m, size) for m in masks]
    ox = {'center': x0 + ((x1 - x0) - size[0]) // 2, 'left': x0, 'right': x1 - size[0]}[align]
    oy = y0 + ((y1 - y0) - round(cap + widths[0])) // 2 - round(py)     # capitals centred
    for y in range(size[1]):
        for x in range(size[0]):
            tx, ty = ox + x, oy + y
            if not (0 <= tx < cv.w and 0 <= ty < cv.h):
                continue
            base = cv.get(tx, ty)
            c = layers[0].getpixel((x, y)) / 255
            e = layers[1].getpixel((x, y)) / 255 if edge else 0
            if c <= 0 and e <= 0:
                continue
            col = base[:3]
            if e > 0:
                col = tuple(p + (q - p) * e for p, q in zip(col, edge))
            if c > 0:
                col = tuple(p + (q - p) * c for p, q in zip(col, ink))
            cv.put(tx, ty, cv.index(col, base[3] + (max(ink_a, base[3]) - base[3]) * max(c, e)))

# ---------------------------------------------------------------- labels

def label(cv, box, text, cap=None, bold=0.15):
    """Outlined text on a flat background inside box (x0, y0, x1, y1 inclusive):
    background = most common colour on the box edge, outline = text pixels touching
    the background, fill = the other text pixels; then the English, centred."""
    x0, y0, x1, y1 = box
    edge = [cv.idx(x, y) for x in range(x0, x1 + 1) for y in (y0, y1)] + \
           [cv.idx(x, y) for y in range(y0, y1 + 1) for x in (x0, x1)]
    bgi = collections.Counter(edge).most_common(1)[0][0]
    bg = cv.pal[bgi]
    isfg = lambda x, y: sum(abs(a - b) for a, b in zip(cv.get(x, y)[:3], bg[:3])) > 12
    ring, core = collections.Counter(), collections.Counter()
    for y in range(y0 + 1, y1):
        for x in range(x0 + 1, x1):
            if isfg(x, y):
                if any(not isfg(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                    ring[cv.idx(x, y)] += 1
                else:
                    core[cv.idx(x, y)] += 1
    ys = [y for y in range(y0, y1 + 1) if any(isfg(x, y) for x in range(x0, x1 + 1))]
    outline_i = ring.most_common(1)[0][0]
    outline = cv.pal[outline_i][:3]
    inner = [i for i, n in core.most_common() if abs(luma(cv.pal[i]) - luma(outline)) > 20]
    fill = cv.pal[inner[0]][:3] if inner else bg[:3]       # none: hollow lettering
    text_a = cv.pal[inner[0] if inner else outline_i][3]
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            cv.put(x, y, bgi)
    cap = cap or (ys[-1] - ys[0] + 1) * 0.68
    lw = 1.0 if cap < 14 else 1.6
    condense = 1.0
    while True:
        stroke = max(1.6, cap * bold)
        masks, (tw, th), _ = text_masks(text, cap, [stroke, stroke + 2 * lw], condense)
        if tw <= x1 - x0 + 1 or cap < 6:
            break
        if condense > 0.8:
            condense *= 0.96
        else:
            cap *= 0.95
    size = (int(tw) + 1, int(th) + 1)
    c_im, o_im = (downsample(m, size) for m in masks)
    ox = x0 + (x1 - x0 + 1 - size[0]) // 2
    oy = (ys[0] + ys[-1] + 1) // 2 - size[1] // 2
    for y in range(size[1]):
        for x in range(size[0]):
            tx, ty = ox + x, oy + y
            if not (x0 <= tx <= x1 and y0 <= ty <= y1):
                continue
            c, o = c_im.getpixel((x, y)) / 255, o_im.getpixel((x, y)) / 255
            if o <= 0.05:
                continue
            col = tuple(p + (q - p) * o for p, q in zip(bg[:3], outline))
            col = tuple(p + (q - p) * c for p, q in zip(col, fill))
            a = bg[3] + (text_a - bg[3]) * o              # keeps semi-transparent plates
            cv.put(tx, ty, cv.index(col, a))

# ---------------------------------------------------------------- haloed glyphs

def glyph(cv, box, text, bold=0.2, halo_w=2.0):
    """Light lettering with a soft dark halo on a transparent background (体力 icons):
    colours measured in box, which is cleared and redrawn with text, centred."""
    x0, y0, x1, y1 = box
    px = [(cv.get(x, y), cv.idx(x, y)) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]
    solid = sorted(luma(c) for c, i in px if c[3] >= 0x50)
    hi = min(128, solid[len(solid) * 3 // 4]) if solid else 128       # brightest quarter
    light = collections.Counter(i for c, i in px if c[3] >= 0x50 and luma(c) >= hi)
    fill_a = sorted(cv.pal[i][3] for i in light.elements())[sum(light.values()) // 2]
    dark = [c for c, i in px if 0 < c[3] and luma(c) < min(80, hi // 2)]
    fill = cv.pal[light.most_common(1)[0][0]][:3]
    halo = collections.Counter(c[:3] for c in dark).most_common(1)[0][0] if dark else (0, 0, 0)
    halo_a = max(c[3] for c in dark) if dark else 0x40
    ys = [y for y in range(y0, y1 + 1) if any(cv.get(x, y)[3] >= 0x50 and luma(cv.get(x, y)) >= hi
                                               for x in range(x0, x1 + 1))]
    clear = min(range(cv.n), key=lambda i: cv.pal[i][3])
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            cv.put(x, y, clear)
    cap = (ys[-1] - ys[0] + 1) * 0.62
    condense = 1.0
    while True:
        stroke = max(1.6, cap * bold)
        masks, (tw, th), _ = text_masks(text, cap, [stroke, stroke + 2 * halo_w], condense)
        if tw <= x1 - x0 + 1 or cap < 6:
            break
        if condense > 0.75:
            condense *= 0.96
        else:
            cap *= 0.95
    size = (int(tw) + 1, int(th) + 1)
    c_im, h_im = (downsample(m, size) for m in masks)
    ox = x0 + (x1 - x0 + 1 - size[0]) // 2
    oy = (ys[0] + ys[-1] + 1) // 2 - size[1] // 2
    for y in range(size[1]):
        for x in range(size[0]):
            tx, ty = ox + x, oy + y
            if not (x0 <= tx <= x1 and y0 <= ty <= y1):
                continue
            c, h = c_im.getpixel((x, y)) / 255, h_im.getpixel((x, y)) / 255
            if c > 0.1:
                col = tuple(p + (q - p) * c for p, q in zip(halo, fill))
                cv.put(tx, ty, cv.index(col, fill_a if c > 0.5 else max(halo_a, fill_a * c)))
            elif h > 0.05:
                cv.put(tx, ty, cv.index(halo, halo_a * h))

# ---------------------------------------------------------------- buttons

def button(cv, cell, text, inset=5, bold=0.16):
    # inset: px or (left, top, right, bottom)
    """Dark text on a framed button: cell (x0, y0, x1, y1) is the whole button; the
    inside (inset px in) is refilled row by row with the row's median paper colour, then
    the English is drawn in the darkest original text colour, centred."""
    x0, y0, x1, y1 = cell
    l, t, r, b = inset if isinstance(inset, tuple) else (inset,) * 4
    ix0, iy0, ix1, iy1 = x0 + l, y0 + t, x1 - r, y1 - b
    inner = [cv.get(x, y) for y in range(iy0, iy1 + 1) for x in range(ix0, ix1 + 1)]
    lum = sorted(luma(c) for c in inner)
    dark = collections.Counter(c[:3] for c in inner if luma(c) <= lum[len(lum) // 12])
    ink = dark.most_common(1)[0][0]
    bg = {}
    for y in range(iy0, iy1 + 1):
        # the row's median colour, ignoring the text
        row = [cv.get(x, y) for x in range(ix0, ix1 + 1)]
        paper = [c for c in row if luma(c) > lum[len(lum) // 3]] or row
        col = _median(paper)[:3]
        i = cv.index(col)
        for x in range(ix0, ix1 + 1):
            bg[x, y] = col
            cv.put(x, y, i)
    h = iy1 - iy0 + 1
    cap = h * 0.62
    condense = 1.0
    while True:
        stroke = max(1.4, cap * bold)
        masks, (tw, th), _ = text_masks(text, cap, [stroke], condense)
        if tw <= ix1 - ix0 + 1 or cap < 6:
            break
        if condense > 0.78:
            condense *= 0.96
        else:
            cap *= 0.95
    size = (int(tw) + 1, int(th) + 1)
    m = downsample(masks[0], size)
    ox = ix0 + (ix1 - ix0 + 1 - size[0]) // 2
    oy = iy0 + (h - size[1]) // 2
    for y in range(size[1]):
        for x in range(size[0]):
            tx, ty = ox + x, oy + y
            c = m.getpixel((x, y)) / 255
            if c > 0.05 and (tx, ty) in bg:
                col = tuple(p + (q - p) * c for p, q in zip(bg[tx, ty], ink))
                cv.put(tx, ty, cv.index(col))

def _median(cols):
    cols = sorted(cols, key=luma)
    return cols[len(cols) // 2]

def _grid(x0, y0, w, h, cols, rows, n=None):
    cells = [(x0 + c * w, y0 + r * h, x0 + c * w + w - 1, y0 + r * h + h - 1)
             for r in range(rows) for c in range(cols)]
    return cells[:n]

# ---------------------------------------------------------------- inpainting

def inpaint(cv, mask, iters=400):
    """Fill the pixels of mask (set of (x, y)) by diffusion from their neighbours (a
    smooth patch; new lettering goes on top), mapped to the nearest palette colours."""
    import numpy as np
    if not mask:
        return
    xs = [x for x, _ in mask]; ys = [y for _, y in mask]
    x0, y0 = max(0, min(xs) - 1), max(0, min(ys) - 1)
    x1, y1 = min(cv.w - 1, max(xs) + 1), min(cv.h - 1, max(ys) + 1)
    w, h = x1 - x0 + 1, y1 - y0 + 1
    img = np.array([[cv.get(x0 + x, y0 + y) for x in range(w)] for y in range(h)], float)
    m = np.zeros((h, w), bool)
    for x, y in mask:
        m[y - y0, x - x0] = True
    known = img[~m].mean(axis=0)
    img[m] = known
    for _ in range(iters):
        p = np.pad(img, ((1, 1), (1, 1), (0, 0)), mode='edge')
        avg = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]) / 4
        img[m] = avg[m]
    for y in range(h):
        for x in range(w):
            if m[y, x]:
                c = img[y, x]
                cv.put(x0 + x, y0 + y, cv.index(c[:3], c[3]))

def text_mask(cv, box, test, grow=1):
    """Pixels in box where test(rgba) holds, grown by grow px."""
    x0, y0, x1, y1 = box
    core = {(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1) if test(cv.get(x, y))}
    out = set(core)
    for x, y in core:
        for dy in range(-grow, grow + 1):
            for dx in range(-grow, grow + 1):
                if x0 <= x + dx <= x1 and y0 <= y + dy <= y1:
                    out.add((x + dx, y + dy))
    return out

# 6x10 bitmap capitals with 2-px strokes: lettering for tiles too small for the stroke font
PIXEL = {
    'E': ['######', '######', '##....', '##....', '#####.', '#####.', '##....', '##....', '######', '######'],
    'N': ['##..##', '###.##', '###.##', '######', '######', '##.###', '##.###', '##..##', '##..##', '##..##'],
    'D': ['#####.', '######', '##..##', '##..##', '##..##', '##..##', '##..##', '##..##', '######', '#####.'],
    'G': ['.#####', '######', '##....', '##....', '##.###', '##.###', '##..##', '##..##', '######', '.#####'],
    'O': ['.####.', '######', '##..##', '##..##', '##..##', '##..##', '##..##', '##..##', '######', '.####.'],
}

def pixtext(cv, box, text, ink, gap=1):
    """Draw text with the PIXEL bitmaps in palette index ink, centred in box."""
    x0, y0, x1, y1 = box
    w = sum(len(PIXEL[c][0]) for c in text) + gap * (len(text) - 1)
    h = len(PIXEL[text[0]])
    ox = x0 + (x1 - x0 + 1 - w) // 2
    oy = y0 + (y1 - y0 + 1 - h) // 2
    for c in text:
        for y, row in enumerate(PIXEL[c]):
            for x, b in enumerate(row):
                if b == '#':
                    cv.put(ox + x, oy + y, ink)
        ox += len(PIXEL[c][0]) + gap

def fabric(cv, box, text, cap=None, stroke=None, glow_w=1.6, light=False, grow=3, align='center',
           erase=None, rotate=False, tol=None, whole=False, ink_rgb=None, pixel=False):
    """Text with a glow/outline on a patterned plate (title-menu buttons): text and glow
    inpainted away inside erase (default box), English drawn in the original ink and glow
    colours inside box. light: light text (with a darker edge) instead of dark text."""
    x0, y0, x1, y1 = box
    ex = erase or box
    px = sorted((cv.get(x, y) for y in range(ex[1], ex[3] + 1) for x in range(ex[0], ex[2] + 1)), key=luma)
    if light:
        px.reverse()
    paper = luma(px[len(px) // 2])
    ink = cv.index(px[len(px) // 100][:3])
    sign = -1 if light else 1
    glows = [c for c in px if sign * (luma(c) - paper) > 40]
    glow = cv.index(_median(glows)[:3]) if glows else None
    t = (luma(px[len(px) // 100]) + paper) / 2
    if ink_rgb:     # the text colour given (tiles with shading as dark as the text)
        ink = cv.index(ink_rgb)
        test = lambda c: sum((a - b) ** 2 for a, b in zip(c[:3], ink_rgb)) < (tol or 40) ** 2
    elif whole:     # every pixel of the erase box (plain panels: no halo left behind)
        test = lambda c: True
    elif tol:       # ink = colours near the darkest/lightest one (keeps dark brush strokes)
        ic = px[len(px) // 100]
        test = lambda c: sum((a - b) ** 2 for a, b in zip(c[:3], ic[:3])) < tol * tol
    else:
        test = lambda c: sign * (luma(c) - t) < 0
    inpaint(cv, text_mask(cv, ex, test, grow))
    if text == '~':     # tl/gfx.txt: a label the English doesn't need, only erased
        return
    cap = cap or (y1 - y0 + 1) * 0.5
    stroke = stroke or max(1.5, cap * 0.10)
    if pixel:
        pixtext(cv, box, text, ink)
        return
    if glow is None:
        glow, glow_w = ink, 0.01
    letters(cv, box, text, ink, glow, cap, stroke, glow_w, align=align, rotate=rotate)

def stamp(cv, box, text, cap=9, stroke=1.8, split=0.45, inner=None, align='right'):
    """A glyph stamped over the right part of an icon tile (season tiles): its colours =
    those much more common right of split than left of it (fill = darkest, outline =
    lightest); erased (inpainted inside inner = (x0, y0, x1, y1) relative to box, cleared
    outside), then text drawn in the same colours."""
    v = cv.view(box)
    sx = int(v.w * split)
    left = collections.Counter(v.idx(x, y) for y in range(v.h) for x in range(sx // 2))
    right = collections.Counter(v.idx(x, y) for y in range(v.h) for x in range(sx, v.w))
    own = [i for i, n in right.items() if n >= 6 and n > 4 * left.get(i, 0) and v.pal[i][3] >= 0x60]
    fill = min(own, key=lambda i: luma(v.pal[i]))
    outline = max(own, key=lambda i: luma(v.pal[i]))
    mask = text_mask(v, (sx - 3, 0, v.w - 1, v.h - 1), lambda c: c in [v.pal[i] for i in own], 2)
    ix0, iy0, ix1, iy1 = inner or (0, 0, v.w - 1, v.h - 1)
    clear = min(range(v.n), key=lambda i: v.pal[i][3])
    for x, y in [p for p in mask if not (ix0 <= p[0] <= ix1 and iy0 <= p[1] <= iy1)]:
        v.put(x, y, clear)
    inpaint(v, {p for p in mask if ix0 <= p[0] <= ix1 and iy0 <= p[1] <= iy1})
    letters(v, (0, 0, v.w - 1, v.h - 1), text, fill, outline, cap, stroke, 1.0, align=align)

def draw_cell(cv, box, text, cap=None, stroke=None, outline_w=1.0, fill=None, align='center'):
    """Small light glyph with a dark outline on transparency (numerals, tiny labels):
    the box is cleared and text drawn in its lightest (or fill: most common bright) and
    darkest opaque colours."""
    x0, y0, x1, y1 = box
    px = collections.Counter(cv.idx(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)
                             if cv.pal[cv.idx(x, y)][3] >= 0x60)
    dark = min(px, key=lambda i: luma(cv.pal[i]))
    if fill == 'common':
        light = max((i for i in px if i != dark), key=lambda i: px[i])
    else:
        light = max(px, key=lambda i: luma(cv.pal[i]))
    clear = min(range(cv.n), key=lambda i: cv.pal[i][3])
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            cv.put(x, y, clear)
    h = y1 - y0 + 1
    cap = cap or h * 0.62
    stroke = stroke or max(1.4, cap * 0.18)
    letters(cv, box, text, light, dark, cap, stroke, outline_w, align=align)

def glowtext(cv, text, cap=None, stroke=None, glow_w=3.0):
    """Opaque lettering with a soft translucent glow on transparency (title 'Press START'):
    cleared and redrawn, ink = most common opaque colour, glow = most common translucent."""
    cnt = collections.Counter(cv.idx(x, y) for y in range(cv.h) for x in range(cv.w))
    ink = max((i for i in cnt if cv.pal[i][3] >= 0x78), key=lambda i: cnt[i])
    soft = [i for i in cnt if 0 < cv.pal[i][3] < 0x78]
    glow = cv.pal[max(soft, key=lambda i: cnt[i])][:3] if soft else None
    ys = [y for y in range(cv.h) if any(cv.pal[cv.idx(x, y)][3] >= 0x78 for x in range(cv.w))]
    clear = min(range(cv.n), key=lambda i: cv.pal[i][3])
    for y in range(cv.h):
        for x in range(cv.w):
            cv.put(x, y, clear)
    cap = cap or (ys[-1] - ys[0] + 1) * 0.62
    stroke = stroke or max(1.6, cap * 0.16)
    letters(cv, (0, 0, cv.w - 1, cv.h - 1), text, ink, ink, cap, stroke, 0.3, outer=glow, outer_w=glow_w)

# ---------------------------------------------------------------- brush tabs

def letters(cv, box, text, fill, outline, cap, stroke, outline_w=1.4, align='center', condense=1.0,
            outer=None, outer_w=0, rotate=False):
    """Draw text (palette index colours: fill inside an outline, optional soft outer
    rgb) over what is in box (x0, y0, x1, y1 inclusive); shrinks to fit the box width.
    rotate: turned 90 degrees clockwise (reads top to bottom; vertical plates), centred."""
    x0, y0, x1, y1 = box
    room = (y1 - y0 + 1) if rotate else (x1 - x0 + 1)
    widths = [stroke, stroke + 2 * outline_w] + ([stroke + 2 * (outline_w + outer_w)] if outer else [])
    while True:
        masks, (tw, th), (px, py) = text_masks(text, cap, widths, condense)
        if tw <= room or condense < 0.6:
            break
        condense *= 0.95
    size = (int(tw) + 1, int(th) + 1)
    layers = [downsample(m, size) for m in masks]
    if rotate:
        layers = [l.transpose(Image.ROTATE_270) for l in layers]
        size = layers[0].size
        bx = layers[-1].getbbox() or (0, 0, size[0], size[1])
        ox = x0 + (x1 - x0 + 1 - (bx[2] - bx[0])) // 2 - bx[0]
        oy = y0 + (y1 - y0 + 1 - (bx[3] - bx[1])) // 2 - bx[1]
    else:
        ox = {'center': x0 + (x1 - x0 + 1 - size[0]) // 2, 'left': x0, 'right': x1 + 1 - size[0]}[align]
        oy = y0 + (y1 - y0 + 1 - round(cap + stroke)) // 2 - round(py)
    for y in range(size[1]):
        for x in range(size[0]):
            tx, ty = ox + x, oy + y
            if not (0 <= tx < cv.w and 0 <= ty < cv.h):
                continue
            c, o = layers[0].getpixel((x, y)) / 255, layers[1].getpixel((x, y)) / 255
            if c > 0.5:
                cv.put(tx, ty, fill)
            elif o > 0.4:
                cv.put(tx, ty, outline)
            elif outer and layers[2].getpixel((x, y)) > 25:
                cv.put(tx, ty, cv.light(outer, 0x80 * layers[2].getpixel((x, y)) / 255))

def brushtab(cv, text, cap=13, stroke=2.4):
    """Tab label: light lettering with a dark outline over a dark brush band (person-info
    tabs 基本/能力/列伝). Redrawn whole: a slanted band in the tab's mid colours, then text."""
    from PIL import ImageDraw as D
    opaque = [i for i in range(cv.n) if cv.pal[i][3] >= 0x78]
    byl = sorted(opaque, key=lambda i: luma(cv.pal[i]))
    outline, fill = byl[0], byl[-3]
    band = [i for i in byl if 50 <= luma(cv.pal[i]) <= 120] or byl[1:4]
    clear = min(range(cv.n), key=lambda i: cv.pal[i][3])
    w, h = cv.w, cv.h
    m = Image.new('L', (w * SS, h * SS), 0)
    d = D.Draw(m)
    # band: lower left to upper right, ragged ends
    pts = [(1, h * 0.62), (w * 0.15, h * 0.40), (w * 0.97, h * 0.30), (w - 1, h * 0.42),
           (w * 0.80, h * 0.80), (w * 0.10, h * 0.90)]
    d.polygon([(x * SS, y * SS) for x, y in pts], fill=255)
    m = m.resize((w, h), Image.BOX)
    ys = [y for y in range(h) if any(m.getpixel((x, y)) > 127 for x in range(w))]
    for y in range(h):
        k = (y - ys[0]) / max(1, ys[-1] - ys[0])
        row = band[[len(band) * 2 // 3, len(band) // 3, 0][min(2, int(k * 3))]]
        for x in range(w):
            cv.put(x, y, row if m.getpixel((x, y)) > 127 else clear)
    letters(cv, (1, 0, w - 2, h - 3), text, fill, outline, cap, stroke, 1.3)

# ---------------------------------------------------------------- items

def _lab(x0, y0, x1, y1, left=None, align='right', pad=2):
    """A label spot on a plain panel: the Japanese at (x0, y0, x1, y1) is erased whole
    (fabric whole=True); the English goes right-aligned to x1 (or centred / left) in a box
    reaching left to `left`."""
    box = (x0 - pad if left is None else left, y0 - pad, x1, y1 + pad)
    return (box, {'align': align, 'erase': (x0 - pad, y0 - pad, x1 + 1, y1 + pad)})

# (entry, image): ('banner',), ('plate', area, sample columns, ink, edge, cap, stroke),
# ('labels', [boxes]), ('glyphs', [boxes]), ('buttons', cells, mode, inset), ('plates', ...),
# ('mixed', [(kind, box)...])
ITEMS = {
    **{(3, k): ('fabric', [(9, 9, 244, 53)]) for k in (7, 8, 9, 10)},   # title menu
    (3, 3): ('glowtext', 17, 2.6),
    (0, 29): ('fabric', [(50, 137, 112, 165), (201, 137, 264, 165)], 13, 2.2, 1.2, True, 2),  # 最大 最小
    (0, 25): ('fabric', [(5, 5, 33, 33)], 12, 2.0, 1.0),     # 可
    (0, 26): ('fabric', [(5, 5, 33, 33)], 12, 2.0, 1.0),     # 否
    (0, 41): ('fabric', [(3, 3, 20, 20)], 9, 1.8, 0.8),      # 本                                    # スタートボタンを押してください
    # castle-town facility plates (40x96, vertical): English rotated
    **{(29, k): ('fabric', [(4, 4, 33, 90)], 13, 1.9, 0.01, False, 1, 'center', None, True) for k in range(28)},
    # scenario bars: 'Scenario N' | title (over a red brush stroke) | year
    **{(26, k): ('fabric', [(14, 6, 124, 33), ((128, 5, 298, 34), {'tol': 70, 'grow': 2}), (300, 6, 384, 33)],
                 15, 1.9, 1.2)
       for k in range(1, 7)},
    (26, 8): ('fabric', [(10, 4, 290, 55)], 26, 3.4, 1.6, True, 3),     # haiku: 鳴かぬなら
    (26, 9): ('fabric', [(10, 4, 290, 55)], 26, 3.4, 1.6, True, 3),     # ほととぎす
    # name entry labels (dark text on a patterned bar)
    (27, 1): ('fabric', [((5, 6, 56, 40), {'align': 'left', 'erase': (5, 6, 40, 40)}), (140, 6, 200, 40)], 12, 1.8, 1.0),
    (27, 2): ('fabric', [((5, 6, 56, 40), {'align': 'left', 'erase': (5, 6, 40, 40)}), (115, 6, 175, 40)], 12, 1.8, 1.0),
    (27, 3): ('fabric', [(96, 6, 130, 40)], 12, 1.8, 1.0),
    # map display filter: 表示 ; 城 町 里 (light text, dark panel)
    (20, 2): ('fabric', [(100, 10, 168, 38), (30, 45, 72, 71), (80, 45, 128, 71), (132, 45, 172, 71)],
              14, 2.3, 1.0, True, 3),
    # council panel: 大方針 戦略 方針 over brush highlights; mission table header 武将 主命 評価
    (28, 1): ('fabric', [(18, 14, 110, 43), (18, 49, 110, 76), (18, 82, 110, 109)], 15, 2.3, 1.0, False, 2,
              'left', None, False, 100),
    (28, 2): ('fabric', [((x0, 7, x1, 34), {'tol': 110, 'grow': 2, 'erase': (x0, 8, x1, 34)}) for x0, x1 in ((20, 110), (195, 265), (330, 400))], 15, 2.3, 1.2, False, 2,
              'center', None, False, 70),
    (35, 17): ('fabric', [(5, 5, 58, 27), (69, 5, 122, 27)], 13, 2.1, 0.8),                # 終了
    (35, 19): ('fabric', [((1, 20, 36, 39), {'erase': (1, 20, 36, 39)}), (125, 20, 151, 39)], 10, 1.7, 0.6),
    (50, 7): ('fabric', [(1, 2, 30, 30), (33, 2, 94, 30)], 11, 1.9, 0.8),                  # 親 振番
    **{(50, k): ('fabric', [(5, 4, w - 8, 27)], 14, 2.2, 0.8) for k, w in ((16, 108), (17, 136), (18, 136))},
    # card album: header + 7 tabs; covers; footer rows; collection rate
    (32, 0): ('fabric', [((2, 0, 195, 21), {'align': 'left', 'grow': 1})]
              + [(76 * (k % 3) + 2, 23 + 24 * (k // 3), 76 * (k % 3) + 73, 43 + 24 * (k // 3)) for k in range(7)],
              11, 1.8, 0.8),
    **{(32, k): ('fabric', [(8, 8, 96, 148)], 17, 2.6, 1.2) for k in range(2, 9)},
    (32, 16): ('fabric', [((3, 24 * r + 3, 200, 24 * r + 20), {'align': 'left'}) for r in range(7)]
               + [(425, 24 * r + 3, 535, 24 * r + 20) for r in range(7)], 12, 1.9, 0.6, False, 1),
    # the counters' '/' is in the English format strings (elfstr 405ca0-b0): texture slashes erased
    (32, 1001): ('erase', [(x, y, x + 9, y + 20) for y in (10, 198) for x in (72, 236, 396, 560)][:7]),
    (32, 1016): ('erase', [(x, 24 * r + 3, x + 11, 24 * r + 21) for r in range(7) for x in (304, 552)]),
    (32, 1): ('fabric', [(492, 259, 600, 291)], 14, 2.3, 1.2, True, 2),
    # duel announcements (gradient brush lettering)
    **{(12, k): ('banner',) for k in range(36, 61)},
    # duel skill-card pictures: name on a gold strip at the bottom
    **{(12, k): ('fabric', [(1, 75, 62, 90)], 8, 1.5, 1.0, True, 2) for k in range(19, 34)},
    # duel sheets: 連勝中 / 勝敗 (grey brush); 攻撃 防御 tags, card numerals 一-九, 体力 武力
    (12, 34): ('banners', [(66, 48, 224, 95), (0, 96, 59, 143), (60, 96, 119, 143)]),
    (12, 35): ('fabric', [(166, 2, 232, 27), (170, 31, 236, 56)], 13, 2.4, 1.2, True, 2),
    (12, 1035): ('cells', [(160 + 15 * k, 57, 174 + 15 * k + 4 * (k == 3), 73) for k in range(4)]
                 + [(224, 57 + 15 * k, 241, 71 + 15 * k + 4 * (k == 4)) for k in range(5)], 11, 2.0),
    (12, 2035): ('cells', [(48, 166, 75, 183), (76, 166, 104, 183)], 9, 1.8, 0.8, 'common'),
    # field battle (entry 23): combo words, tags, card numerals, plan banners, card strips, panel
    (23, 12): ('banners', [(0, 0, 93, 34), (94, 0, 178, 34), (0, 35, 91, 72), (92, 35, 178, 72),
                           (0, 73, 91, 110), (92, 73, 178, 110)]),
    (23, 1012): ('fabric', [(180, 2, 240, 27), (184, 33, 240, 55), ((178, 84, 214, 99), {'cap': 9, 'stroke': 1.6}),
                            (186, 232, 250, 253)], 12, 2.2, 1.1, True, 2),
    (23, 2012): ('cells', [(145 + 16 * k, 181, 159 + 16 * k, 197) for k in range(7)]
                 + [(145, 198, 159, 213), (161, 198, 175, 213)], 11, 2.0),
    (23, 16): ('banner',), (23, 17): ('banner',),
    **{(23, k): ('fabric', [(1, 75, 62, 90)], 8, 1.5, 1.0, True, 2) for k in range(18, 28)},
    **{(23, k): ('fabric', [((x0, y0, x1, y1), {'align': 'right', 'erase': (e0, y0, x1 + 1, y1)})
                            for y0, y1 in ((36, 62), (65, 90), (93, 118), (121, 146))
                            for x0, e0, x1 in ((40, 77, 138), (180, 217, 278), (322, 361, 420))],
                 12, 2.1, 1.0, True, 0, 'right', None, False, None, True) for k in (28, 29)},
    # battle setup screens (light labels on a dark panel; colons kept)
    (22, 0): ('fabric', [_lab(70, 242, 166, 267, align='center'),
                         _lab(272, 277, 317, 297, 200), _lab(250, 308, 317, 327, 200), _lab(272, 340, 317, 361, 200),
                         _lab(272, 373, 317, 392, 200), _lab(272, 404, 317, 424, 200),
                         _lab(465, 307, 533, 328, 400), _lab(489, 338, 533, 358, 400)],
              13, 2.2, 1.0, True, 0, 'right', None, False, None, True),
    (22, 1): ('fabric', [_lab(78, 49, 141, 70, align='center'), _lab(473, 32, 518, 51, align='center'),
                         _lab(546, 32, 613, 52, 525, 'center'),
                         _lab(382, 57, 453, 76, 330), _lab(405, 82, 453, 101, 330), _lab(405, 106, 453, 125, 330),
                         _lab(405, 130, 453, 150, 330), _lab(467, 172, 514, 192, 462)]
              + [_lab(x, y, x + 65, y + 20, align='center') for y in (186, 314) for x in (101, 354)],
              13, 2.2, 1.0, True, 0, 'right', None, False, None, True),
    # battle overview (blue 152 / red 153): Rice; per unit band (72 px): name, LDR, Men Morale Train Merit
    **{(22, k): ('fabric', [_lab(479, 17, 520, 37, 420)]
                 + [spot for t in range(0, 360, 72) for spot in (
                     _lab(66, 53 + t, 137, 75 + t, 15), _lab(321, 53 + t, 372, 74 + t, 260),
                     _lab(200, 81 + t, 248, 101 + t, 150), _lab(308, 81 + t, 356, 101 + t, 255),
                     _lab(409, 81 + t, 460, 101 + t, 360), _lab(510, 81 + t, 562, 101 + t, 465))],
                 13, 2.2, 1.0, True, 0, 'right', None, False, None, True) for k in (152, 153)},
    # unit markers 将 二 三 四 五 (3 colours), unit panels, merit stamps, merit window header
    (22, 142): ('cells', [(24 * c, 24 * r, 24 * c + 23, 24 * r + 23) for r in range(3) for c in range(5)], 15, 2.6, 1.0),
    **{(22, k): ('fabric', [_lab(70, 36, 122, 55, 20), _lab(190, 37, 242, 56, 140)],
                 13, 2.2, 1.0, True, 0, 'right', None, False, None, True) for k in (143, 144)},
    **{(22, k): ('fabric', [_lab(75, 42, 131, 62, 15), _lab(200, 41, 255, 61, 140), _lab(75, 70, 131, 89, 15),
                            _lab(201, 71, 255, 91, 140), _lab(76, 97, 131, 117, 15)],
                 13, 2.2, 1.0, True, 0, 'right', None, False, None, True) for k in (145, 146)},
    (22, 148): ('cells', [(3, 24 * r + 3, 92, 24 * r + 20) for r in range(3)], 13, 2.0, 0.6, 'common'),
    (22, 149): ('fabric', [((12, 16, 160, 42), {'align': 'left'}), ((280, 16, 462, 42), {'align': 'right'})],
                14, 2.2, 1.2, False, 2, 'center', None, False, 70),
    # battle header sheet: Castle Def. plate, vs, Men/Rice/Morale plates, weather, unit labels
    (22, 151): ('fabric', [((30, 44, 146, 63), {'align': 'left'}),
                           ((193, 1, 254, 22), {'light': True}), ((193, 25, 254, 46), {'light': True}),
                           ((193, 49, 254, 70), {'light': True})], 11, 1.9, 0.8),
    (22, 1151): ('cells', [(150, 39, 171, 57)] + [(2, 97, 86, 119), (89, 97, 171, 119), (174, 97, 253, 119),
                                                (2, 121, 86, 143), (88, 121, 171, 143)], 13, 2.3, 1.0, None, 'left'),
    (22, 2151): ('stamps', [((x, 70, x + 31, 90), (1, 1, 30, 19)) for x in (25, 57, 89, 121)]),
    # mini-game record: headers, footer, grade stamps
    (33, 0): ('fabric', [(6, 5, 182, 36), (188, 5, 260, 36), (266, 5, 554, 36), (560, 5, 620, 36),
                         ((12, 366, 300, 400), {'align': 'left'})], 14, 2.2, 1.2, False, 2, 'center', None, False, 70),
    **{(33, k): ('cells', [(11, 11, 36, 36)], 16, 2.8, 0.8, 'common') for k in (2, 3, 4, 5)},
    (40, 1): ('banner',),                                                  # bingo 終了
    **{(43, k): ('fabric', [(10, 66, 86, 92), (106, 66, 182, 92)], 11, 1.9, 1.0, True, 2) for k in range(1, 9)},
    **{(45, k): ('fabric', [(4, 4, 43, 43)], 11, 2.0, 1.0, True, 2) for k in (15, 16, 19)},
    (47, 6): ('fabric', [((2, 2, 21, 21), {'ink_rgb': (0, 0, 83), 'pixel': True})], 7, 1.6, 0.01, False, 1),
    (47, 7): ('fabric', [((2, 2, 21, 21), {'ink_rgb': (247, 247, 0), 'pixel': True}),
                         ((26, 2, 45, 21), {'ink_rgb': (112, 20, 0), 'pixel': True})], 7, 1.6, 0.01, False, 1),
    (50, 19): ('fabric', [(72 * c + 2, 24 * r + 2, 72 * c + 69, 24 * r + 21) for r in range(7) for c in range(2)][:13],
               11, 1.8, 0.8),
    (52, 0): ('fabric', [(14, 8, 70, 34), (74, 8, 180, 34), (270, 8, 340, 34)], 13, 2.1, 1.0, False, 2,
              'center', None, False, 70),
    (0, 42): ('banner',),                                   # 読み込み中...
    **{(0, k): ('brushtab',) for k in (47, 48, 49)},          # person info tabs 基本 能力 列伝
    (0, 27): ('banners', [(0, 96, 38, 119), (40, 96, 79, 119)]),   # 体力 病気
    (0, 1027): ('stamps', [((x, 96, x + 39, 119), (1, 1, 26, 19)) for x in (80, 120, 160, 200)]),  # 春夏秋冬
}

def load_tl():
    out = {}
    if os.path.exists(TL):
        for line in open(TL, encoding='utf-8').read().splitlines():
            if line.strip() and not line.startswith('#'):
                k, _, v = line.partition('\t')
                e, _, t = k.partition('.')
                out[int(e), int(t)] = v
    return out

def redraw(im, item, text):
    cv = Canvas(im)
    if item[0] == 'banner':
        banner(cv, text)
    elif item[0] == 'fabric':
        # boxes: (x0, y0, x1, y1) or ((x0, y0, x1, y1), {fabric keyword overrides})
        for box, t in zip(item[1], text.split('|')):
            if not t:
                continue            # empty spot: left as it is
            kw = {}
            if isinstance(box[0], tuple):
                box, kw = box
            names = ('cap', 'stroke', 'glow_w', 'light', 'grow', 'align', 'erase', 'rotate', 'tol', 'whole')
            fabric(cv, box, t, **{**dict(zip(names, item[2:])), **kw})
    elif item[0] == 'stamps':
        for (box, inner), t in zip(item[1], text.split('|')):
            stamp(cv, box, t, inner=inner)
    elif item[0] == 'cells':
        for box, t in zip(item[1], text.split('|')):
            draw_cell(cv, box, t, *item[2:])
    elif item[0] == 'glowtext':
        glowtext(cv, text, *item[1:])
    elif item[0] == 'erase':
        # boxes refilled from their surroundings (marks the English doesn't need)
        for x0, y0, x1, y1 in item[1]:
            inpaint(cv, {(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)})
    elif item[0] == 'brushtab':
        brushtab(cv, text, *item[1:])
    elif item[0] == 'banners':
        # several outlined labels in one atlas: banner() on each box
        for box, t in zip(item[1], text.split('|')):
            banner(cv.view(box), t)
    elif item[0] == 'mixed':
        for (kind, box), t in zip(item[1], text.split('|')):
            (glyph if kind == 'glyphs' else label)(cv, box, t)
    elif item[0] == 'plates':
        # several spots on one panel: (erase area, sample columns, text area, align, cap, stroke)
        for (area, sample, tarea, align, cap, stroke), t in zip(item[1], text.split('|')):
            plate(cv, area, sample, t, None, None, cap, stroke, align=align, text_area=tarea)
    elif item[0] == 'buttons':
        texts = text.split('|')
        for k, cell in enumerate(item[1]):
            t = {'cycle': lambda: texts[k % len(texts)], 'rows': lambda: texts[k // 4],
                 'list': lambda: texts[k]}[item[2]]()
            button(cv, cell, t, item[3])
    elif item[0] == 'glyphs':
        for box in item[1]:
            glyph(cv, box, text)
    elif item[0] == 'labels':
        for box, t in zip(item[1], text.split('|')):
            label(cv, box, t)
    else:
        _, area, sample, ink, edge, cap, stroke, *more = item
        plate(cv, area, sample, text, ink, edge, cap, stroke, text_area=more[0] if more else None)

def apply(entry):
    """-> {entry: new bytes}; entry(i) = clean TR4DATA entry (images edited in place)."""
    by_entry = collections.defaultdict(dict)
    for (e, t), text in load_tl().items():
        by_entry[e][t] = text
    out = {}
    for e, texts in sorted(by_entry.items()):
        blob = bytearray(entry(e))
        ims = ftx.images(blob)
        for t, text in sorted(texts.items()):
            redraw(ims[t % 1000], ITEMS[e, t], text)     # t + 1000k: more spots on image t
            ims[t % 1000].store(blob)
        out[e] = bytes(blob)
    return out

if __name__ == '__main__':
    # gfx.py preview out.png [e.t ...]: items of tl/gfx.txt, original above English
    data = open(disc.extract(disc.DATA), 'rb').read()
    elf = open(disc.extract(disc.ELF), 'rb').read()
    import datafile
    want = set(sys.argv[3:])
    pairs = []
    for (e, t), text in sorted(load_tl().items()):
        if want and '%d.%d' % (e, t) not in want:
            continue
        ims = ftx.images(datafile.entry(data, elf, e))
        before = ims[t % 1000].rgba()
        redraw(ims[t % 1000], ITEMS[e, t], text)
        pairs.append((before, ims[t % 1000].rgba()))
    W = 1100
    x = y = rowh = 0
    pos = []
    for a, b in pairs:
        w, h = max(a.width, b.width), a.height + b.height + 2
        if x + w > W:
            x, y, rowh = 0, y + rowh + 8, 0
        pos.append((x, y))
        x += w + 8
        rowh = max(rowh, h)
    sheet = Image.new('RGBA', (W, y + rowh), (60, 90, 120, 255))
    for (a, b), (x, y) in zip(pairs, pos):
        sheet.alpha_composite(a, (x, y))
        sheet.alpha_composite(b, (x, y + a.height + 2))
    sheet.save(sys.argv[2])
