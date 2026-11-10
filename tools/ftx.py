"""Graphics files of TR4DATA (entries 0-52, EFileID GRP_*_FTX): archives of PS2 images.

Archive: u32 count, u32 header size (16-byte units), u32 offsets of items 1..count-1
(16-byte units from the start of the file; item 0 starts at the header end).
Image: 16-byte header
  +0 u32 0x10000, +4 u32 type (0x13 = 8bpp, 0x14 = 4bpp), +8 u16 width, +0xA u16 height,
  +0xC u16 pixel qwords (VRAM, rounded), +0xE u16 CLUT qwords
then 0x60 bytes of GIF packets (BITBLTBUF/TRXPOS/TRXREG/TRXDIR + IMAGE tag at +0x60, NLOOP = pixel qwords), the pixels
(linear, 4bpp low nibble first), a 16-byte IMAGE tag and the CLUT (RGBA, alpha 0x80 =
opaque; 8bpp CLUTs in PS2 CSM1 order, index bits 3 and 4 swapped).
Nothing is compressed: an edited image keeps its size, so archives are rewritten in place.

  python tools/ftx.py dump [entries...]   -> extract/gfx/NN/KKK.png (+ contact sheets)
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import disc

GRP_ENTRIES = range(53)
NAMES = ['FIXGRP', 'SAVELOAD', 'WINBACK', 'TITLE', 'BUSTUP', 'FACE', 'TOWN', 'ROOM', 'EVENT',
         'CARD', 'ITEM', 'TRADEITEM', 'SINGLEBATTLE', 'SBUNIT', 'SBEFFECT', 'JAPAN', 'MAPFH',
         'BIRD', 'MAPCHAR', 'MAPSCN', 'SELECTFH', 'MINIMAP', 'BATTLE', 'USERWAR', 'BUUNIT',
         'BEFFECT', 'INIT', 'INPNAME', 'MPWIN', 'JOKABTN', 'FHANIME', 'HELP', 'ALBUM',
         'MGRECORD', 'MINIGAME', 'MGSTONE', 'MGTRUEHIT', 'MGNOUMIN', 'MGSHINKEI', 'MGNINJUTSU',
         'MGBINGO', 'MGAMIDA', 'MGKAIKON', 'MGKANPOU', 'MGBENZETSU', 'MGKARAKURI', 'MGSHOOTING',
         'MGGUNGAKU', 'MGJOUBA', 'MGGUNNER', 'GAMBLE', 'HANAFUDA', 'CDPLAYER']
PIX = 0x70                     # pixel data offset inside an image

def items(blob):
    """Item offsets of an archive."""
    cnt, hdr = struct.unpack_from('<II', blob)
    return [hdr * 16] + [16 * x for x in struct.unpack_from('<%dI' % (cnt - 1), blob, 8)]

def csm1(i):
    return (i & ~0x18) | ((i & 8) << 1) | ((i & 0x10) >> 1)

class Image:
    def __init__(self, blob, off):
        self.off = off
        magic, self.typ, self.w, self.h, self.pq, self.cq = struct.unpack_from('<IIHHHH', blob, off)
        if magic != 0x10000 or self.typ not in (0x13, 0x14):
            raise ValueError('not an image at 0x%x' % off)
        self.bpp = 8 if self.typ == 0x13 else 4
        self.pq = struct.unpack_from('<H', blob, off + 0x60)[0] & 0x7FFF   # IMAGE tag NLOOP
        assert self.pq == (self.w * self.h * self.bpp // 8 + 15) // 16, (hex(off), self.w, self.h)
        p = off + PIX
        raw = blob[p:p + self.w * self.h * self.bpp // 8]
        if self.bpp == 8:
            self.pix = bytearray(raw)
        else:
            self.pix = bytearray(len(raw) * 2)
            self.pix[0::2] = bytes(b & 15 for b in raw)
            self.pix[1::2] = bytes(b >> 4 for b in raw)
            del self.pix[self.w * self.h:]
        c = p + self.pq * 16 + 16
        cl = blob[c:c + self.cq * 16]
        pal = [tuple(cl[4 * i:4 * i + 4]) for i in range(len(cl) // 4)]
        self.pal = [pal[csm1(i)] for i in range(256)] if self.bpp == 8 else pal
        self.size = PIX + self.pq * 16 + 16 + self.cq * 16

    def rgba(self):
        from PIL import Image as P
        out = bytearray()
        for i in self.pix:
            r, g, b, a = self.pal[i]
            out += bytes((r, g, b, min(255, a * 2)))
        return P.frombytes('RGBA', (self.w, self.h), bytes(out))

    def store(self, blob):
        """Write pixels and palette back into blob (bytearray) at the image's offset."""
        p = self.off + PIX
        if self.bpp == 8:
            raw = bytes(self.pix)
            pal = [self.pal[csm1(i)] for i in range(256)]
        else:
            raw = bytes(a | (b << 4) for a, b in zip(self.pix[0::2], self.pix[1::2]))
            pal = self.pal
        blob[p:p + len(raw)] = raw
        c = p + self.pq * 16 + 16
        blob[c:c + len(pal) * 4] = b''.join(bytes(x) for x in pal)

def images(blob):
    out = []
    for o in items(blob):
        try:
            out.append(Image(blob, o))
        except ValueError:
            out.append(None)
    return out

def load(i, data=None, elf=None):
    import datafile
    if data is None:
        data = open(disc.extract(disc.DATA), 'rb').read()
        elf = open(disc.extract(disc.ELF), 'rb').read()
    return datafile.entry(data, elf, i)

def dump(entries):
    import datafile
    from PIL import Image as P, ImageDraw
    data = open(disc.extract(disc.DATA), 'rb').read()
    elf = open(disc.extract(disc.ELF), 'rb').read()
    for i in entries:
        blob = datafile.entry(data, elf, i)
        d = disc.extract('gfx/%02d' % i)
        os.makedirs(d, exist_ok=True)
        ims = images(blob)
        tiles = []
        for k, im in enumerate(ims):
            if im is None:
                print('%d.%d: not an image' % (i, k))
                continue
            png = im.rgba()
            png.save(os.path.join(d, '%03d.png' % k))
            tiles.append((k, png))
        # contact sheet: 1024 px wide, each tile scaled to max 256
        x = y = rowh = 0
        place = []
        for k, png in tiles:
            t = png.copy()
            t.thumbnail((256, 256))
            if x + t.width > 1024:
                x, y, rowh = 0, y + rowh + 14, 0
            place.append((k, t, x, y))
            x += t.width + 4
            rowh = max(rowh, t.height)
        sheet = P.new('RGBA', (1024, y + rowh + 14), (60, 0, 60, 255))
        dr = ImageDraw.Draw(sheet)
        for k, t, x, y in place:
            sheet.alpha_composite(t, (x, y + 12))
            dr.text((x, y), '%d' % k, fill=(255, 255, 0, 255))
        sheet.save(os.path.join(disc.extract('gfx'), 'sheet_%02d_%s.png' % (i, NAMES[i])))
        print(i, NAMES[i], len(ims), 'images')

if __name__ == '__main__':
    if sys.argv[1] == 'dump':
        dump([int(a) for a in sys.argv[2:]] or GRP_ENTRIES)
