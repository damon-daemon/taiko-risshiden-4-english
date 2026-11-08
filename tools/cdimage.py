"""Raw CD image access for the PS2 disc (single track, MODE2/2352): read files, write a
patched copy.

Every sector is Mode 2 Form 1: 12 sync bytes, a header (MSF address in BCD + mode 2),
an 8-byte subheader (submode 0x08 = data, 0x89 = last sector of a file), 2048 bytes of
user data, EDC (CRC-32 over subheader + data) and Reed-Solomon P/Q parity (ECC, computed
with the header zeroed). The disc ends with 150 zero postgap sectors.

The game opens files by name (sceCdSearchFile), so a file may change size as long as its
directory record follows. TR4DATA.DAT is the last file on the disc, so it may grow at
the end (the postgap moves along and the volume size in the PVD is updated); the other
files must fit in their original sectors. Only sectors whose content changed are
re-encoded; everything else stays byte-identical to the clean disc.
"""
import os, struct
import numpy as np

RAW = 2352
SECTOR = 2048
SYNC = b'\x00' + b'\xff' * 10 + b'\x00'
POSTGAP = 150
GROW_FILE = 'TR4DATA.DAT'

# ---------------------------------------------------------------- EDC / ECC

def _edc_table():
    t = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ (0xD8018001 if c & 1 else 0)
        t.append(c)
    return np.array(t, dtype=np.uint32)

EDC_T = _edc_table()
F_LUT = np.array([((i << 1) ^ (0x11D if i & 0x80 else 0)) & 0xFF for i in range(256)], dtype=np.uint8)
B_LUT = np.zeros(256, dtype=np.uint8)
for _i in range(256):
    B_LUT[_i ^ F_LUT[_i]] = _i

def _ecc_index(major_count, minor_count, major_mult, minor_inc):
    size = major_count * minor_count
    idx = np.zeros((major_count, minor_count), dtype=np.intp)
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        for minor in range(minor_count):
            idx[major, minor] = index
            index += minor_inc
            if index >= size:
                index -= size
    return idx

P_IDX = _ecc_index(86, 24, 2, 86)
Q_IDX = _ecc_index(52, 43, 86, 88)

def _ecc_block(src, idx):
    """src: (N, L) uint8 from sector offset 12; returns (N, 2*major) parity."""
    g = src[:, idx]                                    # (N, major, minor)
    a = np.zeros(g.shape[:2], dtype=np.uint8)
    b = np.zeros(g.shape[:2], dtype=np.uint8)
    for m in range(g.shape[2]):
        t = g[:, :, m]
        a = F_LUT[a ^ t]
        b ^= t
    a = B_LUT[F_LUT[a] ^ b]
    return np.concatenate([a, a ^ b], axis=1)

def _bcd(n):
    return (n // 10) << 4 | n % 10

def msf(lba):
    a = lba + 150
    return bytes([_bcd(a // 4500), _bcd(a // 75 % 60), _bcd(a % 75)])

def encode(lbas, subheads, datas):
    """Build raw Form 1 sectors. lbas: list of int, subheads: list of 4-byte submode
    words (file, channel, submode, coding), datas: list of 2048-byte blocks."""
    n = len(lbas)
    s = np.zeros((n, RAW), dtype=np.uint8)
    s[:, :12] = np.frombuffer(SYNC, np.uint8)
    s[:, 16:20] = np.frombuffer(b''.join(subheads), np.uint8).reshape(n, 4)
    s[:, 20:24] = s[:, 16:20]
    s[:, 24:2072] = np.frombuffer(b''.join(datas), np.uint8).reshape(n, SECTOR)
    crc = np.zeros(n, dtype=np.uint32)
    for k in range(16, 2072):
        crc = EDC_T[(crc ^ s[:, k]) & 0xFF] ^ (crc >> 8)
    s[:, 2072:2076] = crc.astype('<u4').view(np.uint8).reshape(n, 4)
    s[:, 2076:2248] = _ecc_block(s[:, 12:2076], P_IDX)       # header still zero
    s[:, 2248:2352] = _ecc_block(s[:, 12:2248], Q_IDX)
    for i, lba in enumerate(lbas):
        s[i, 12:16] = np.frombuffer(msf(lba) + b'\x02', np.uint8)
    return [r.tobytes() for r in s]

def postgap_sector(lba):
    return SYNC + msf(lba) + b'\x02' + bytes(RAW - 16)

# ---------------------------------------------------------------- ISO 9660

class Record:
    def __init__(self, path, rec_lba, rec_pos, lba, size, is_dir):
        self.path, self.rec_lba, self.rec_pos = path, rec_lba, rec_pos
        self.lba, self.size, self.is_dir = lba, size, is_dir

    @property
    def sectors(self):
        return max(1, (self.size + SECTOR - 1) // SECTOR)

class Image:
    def __init__(self, path):
        self.path = path
        self.f = open(path, 'rb')
        self.count = os.path.getsize(path) // RAW

    def raw(self, lba):
        self.f.seek(lba * RAW)
        return self.f.read(RAW)

    def data(self, lba, n=1):
        out = []
        for i in range(n):
            out.append(self.raw(lba + i)[24:24 + SECTOR])
        return b''.join(out)

    def records(self):
        pvd = self.data(16)
        assert pvd[1:6] == b'CD001', 'not an ISO 9660 image'
        ext, length = struct.unpack_from('<I4xI', pvd, 156 + 2)
        out = {}
        self._read_dir(ext, length, '', out)
        return out

    def _read_dir(self, lba, size, prefix, out):
        data = self.data(lba, (size + SECTOR - 1) // SECTOR)
        pos = 0
        while pos < len(data):
            n = data[pos]
            if n == 0:
                pos = (pos // SECTOR + 1) * SECTOR
                continue
            ext, length = struct.unpack_from('<I4xI', data, pos + 2)
            flags, nlen = data[pos + 25], data[pos + 32]
            name = data[pos + 33:pos + 33 + nlen]
            if name not in (b'\0', b'\1'):
                name = name.decode('ascii').split(';')[0]
                rec = Record(prefix + name, lba + pos // SECTOR, pos % SECTOR, ext, length, bool(flags & 2))
                out[rec.path] = rec
                if rec.is_dir:
                    self._read_dir(ext, length, rec.path + '/', out)
            pos += n

    def read_file(self, name, recs=None):
        rec = (recs or self.records())[name]
        return self.data(rec.lba, rec.sectors)[:rec.size]

def read_file(path, name):
    return Image(path).read_file(name)

# ---------------------------------------------------------------- writing

BATCH = 4096

def write_image(clean, out, files):
    """Copy clean to out with files ({iso name: bytes}) replaced. Only GROW_FILE may
    outgrow its sectors. Returns the number of re-encoded sectors."""
    img = Image(clean)
    recs = img.records()
    sectors = {}                              # lba -> (subheader, 2048-byte data)
    meta = {}                                 # lba -> patched user data of meta sectors
    new_count = img.count
    for name, data in files.items():
        rec = recs[name]
        need = max(1, (len(data) + SECTOR - 1) // SECTOR)
        if need > rec.sectors:
            if name != GROW_FILE or rec.lba + rec.sectors != img.count - POSTGAP:
                raise RuntimeError('%s: %d sectors needed, %d available' % (name, need, rec.sectors))
            new_count = rec.lba + need + POSTGAP
        span = max(need, rec.sectors)
        padded = data + bytes(span * SECTOR - len(data))
        for i in range(span):
            sub = bytes([0, 0, 0x89 if i == need - 1 else 0x08, 0])
            sectors[rec.lba + i] = (sub, padded[i * SECTOR:(i + 1) * SECTOR])
        # directory record: extent size (both byte orders)
        d = bytearray(meta.get(rec.rec_lba) or img.data(rec.rec_lba))
        struct.pack_into('<I', d, rec.rec_pos + 10, len(data))
        struct.pack_into('>I', d, rec.rec_pos + 14, len(data))
        meta[rec.rec_lba] = bytes(d)
    if new_count != img.count:
        for lba in (16,):                     # PVD volume space size
            d = bytearray(meta.get(lba) or img.data(lba))
            struct.pack_into('<I', d, 80, new_count)
            struct.pack_into('>I', d, 84, new_count)
            meta[lba] = bytes(d)
    for lba, d in meta.items():
        sectors[lba] = (img.raw(lba)[16:20], d)

    # keep only sectors that differ from the clean disc
    todo = []
    for lba in sorted(sectors):
        sub, d = sectors[lba]
        if lba < img.count - POSTGAP:
            r = img.raw(lba)
            if r[16:20] == sub and r[24:2072] == d:
                continue
        todo.append(lba)

    tmp = out + '.part'
    with open(clean, 'rb') as src, open(tmp, 'wb') as dst:
        end = min(img.count, new_count) - POSTGAP
        remaining = end * RAW
        while remaining:
            chunk = src.read(min(remaining, 64 << 20))
            dst.write(chunk)
            remaining -= len(chunk)
        for lba in range(end, new_count - POSTGAP):      # placeholders for grown data
            dst.write(bytes(RAW))
        for lba in range(new_count - POSTGAP, new_count):
            dst.write(postgap_sector(lba))
        for k in range(0, len(todo), BATCH):
            part = todo[k:k + BATCH]
            raws = encode(part, [sectors[l][0] for l in part], [sectors[l][1] for l in part])
            for lba, r in zip(part, raws):
                dst.seek(lba * RAW)
                dst.write(r)
    os.replace(tmp, out)
    return len(todo)

def write_cue(bin_path):
    cue = os.path.splitext(bin_path)[0] + '.cue'
    with open(cue, 'w', newline='\r\n') as f:
        f.write('FILE "%s" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n'
                % os.path.basename(bin_path))
    return cue
