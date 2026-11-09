"""Event scripts (TR4DATA entry 61, 'T4ES' sub-files): parse <-> rebuild.

Derived from the interpreter (`CEventScriptPlayer::Action` 0x1BD9F0, jump table
0x407620; command enum EScriptCommand and the S*CommandHeader bit fields are in the
ELF's DWARF info, see tools/dev/dwarf1.py).

Entries 60 and 61 share one directory layout ('T4EV' container):
  'T4EV' u32 0x00130009 | u32 n (100) | u32 ? | (n + 1) x (u32 file id, u32 offset)
  (the last row: id 0xFFFFFFFF, offset = entry size).
Entry 60 holds the event data files (triggers, conditions; 'T4EV' sub-files; the whole
entry is read into CEventFileManager's 512 KB buffer at boot); entry 61 holds the
scripts of the same file ids ('T4ES' sub-files, read from the disc by offset when a
script runs: entry 61 may grow freely).

T4ES sub-file: 'T4ES' u32 0x00130009 | u32 file id | u32 count | (count + 1) x u32
offset (relative to the sub-file; the last = its size) | scripts. A script is copied
into CScriptFile::m_abyDataBuffer (0x5000 = 20,480 bytes) before it runs.

Script = a command list ended by a 00 word (SCRIPTCOMMAND_BLOCKEND). Command = u32
header (low byte = opcode) + data. Lengths (from Action / the Act* handlers):
  01 02 0E 0F       block: len = (w >> 8) * 4, body at +4
  04 05             branch / else: len = (w >> 18) * 4, body at +4
  06                switch: len = (w >> 9) * 4, body at +4 (+ a term if b1 & 1)
  08                switch on person: len = u16@2 * 4, body at +4
    inside a 06 / 08 body only 07 (len (w >> 9) * 4, body +4 [+ term if b1 & 1]) and
    09 (len (w >> 18) * 4, body +4) are cases; other words are skipped 4 at a time.
  0A 0B             inspect / substitute: len = (u16@2 >> 3) * 4
  0C 0D             inspect block: len = (u16@2 & 0x1FF) * 4, body at + (b1 >> 4) * 4
  10                update: 4 + term (+ another term if b1 & 3 == 3)
  17-1A             container: u16@4 * 4;  1D: (w >> 11) * 4
  11 12 13 14 1F 49 converse / speak / soliloquy / narration / string set / mission
                    string: one string at +4, padded with zeros to 4
  41                send event mission: 12-byte header + one string (the job name)
  16                menu: b1 strings (each padded like the above)
  3B                change name: 4 strings (family, given, family reading, given
                    reading)
  struct sizes: 28 ShowStill 8, 33 RaiseArmy 40, 37 AppointKokushu 8, 40 SendMission 12,
  47 InputNumber 16, 48 DirectArmy 8, 4C CallMessageData 8;
  the rest 4.
Expression terms (SEvDescHead, InspectData 0x1CE1D0): 4 bytes; kind = b0 & 0x7F, sub =
(u16 >> 7) & 0xFF; a term of kind k with sub in NEST[k] is followed by one nested term
(ValuatePerson/Castle/Country/Lord/District/Town/NinjaHome loops, jump tables
0x407B40-0x407DE0).

usage: evscript.py check            # parse + rebuild every sub-file (identity)
       evscript.py dump FILE [K]    # strings of sub-file FILE (index 0-99), script K
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))

ENTRY_DATA, ENTRY_SCRIPT = 60, 61
SCRIPT_BUFFER = 0x8000      # 0x5000 in the game; tools/scriptbuf.py adds 32 KB buffers

NEST = {3: {117}, 5: {4, 5}, 6: {1, 2}, 9: {4, 5, 6, 21}, 0xA: {1, 2},
        0x1C: {8, 9, 15, 16, 17, 18, 20}, 0x1D: {3, 6}}
STRUCT = {0x28: 8, 0x33: 40, 0x37: 8, 0x40: 12, 0x47: 16, 0x48: 8, 0x4C: 8}
TEXT_OPS = {0x11, 0x12, 0x13, 0x14, 0x1F, 0x41, 0x49}   # one string
STR_HEAD = {0x41: 12}                             # header bytes before the string
MULTI_OPS = {0x16: None, 0x3B: 4}                # count (None = b1)
OP_NAMES = {0x11: 'converse', 0x12: 'speak', 0x13: 'soliloquy', 0x14: 'narration',
            0x16: 'menu', 0x1F: 'string', 0x3B: 'name', 0x41: 'job', 0x49: 'mission'}

def u16(b, p): return struct.unpack_from('<H', b, p)[0]
def u32(b, p): return struct.unpack_from('<I', b, p)[0]

class ParseError(Exception):
    pass

def term_len(b, p):
    k, sub = b[p] & 0x7F, (u16(b, p) >> 7) & 0xFF
    return 4 + term_len(b, p + 4) if sub in NEST.get(k, ()) else 4

class Ins:
    """op; head = bytes before the body / strings; body = Block or None; strs = [bytes]
    or None; switch = body is a switch body."""
    __slots__ = ('op', 'head', 'body', 'strs', 'switch')
    def __init__(self, op, head, body=None, strs=None, switch=False):
        self.op, self.head, self.body, self.strs, self.switch = op, head, body, strs, switch

class Block(list):
    end = bytes(4)

def _ins_len(b, p, in_switch):
    """-> (length, body offset or None)"""
    op, w, h = b[p], u32(b, p), u16(b, p + 2)
    if in_switch:
        if op == 7:
            return (w >> 9) << 2, p + 4 + (term_len(b, p + 4) if b[p + 1] & 1 else 0)
        if op == 9:
            return (w >> 18) << 2, p + 4
        return 4, None
    if op in (1, 2, 0xE, 0xF):
        return (w >> 8) << 2, p + 4
    if op in (4, 5):
        return (w >> 18) << 2, p + 4
    if op == 6:
        return (w >> 9) << 2, p + 4 + (term_len(b, p + 4) if b[p + 1] & 1 else 0)
    if op == 8:
        return h << 2, p + 4
    if op in (0xA, 0xB):
        return (h >> 3) << 2, None
    if op in (0xC, 0xD):
        return (h & 0x1FF) << 2, p + ((b[p + 1] >> 4) << 2)
    if op == 0x10:
        q = p + 4 + term_len(b, p + 4)
        if b[p + 1] & 3 == 3:
            q += term_len(b, q)
        return q - p, None
    if 0x17 <= op <= 0x1A:
        return u16(b, p + 4) << 2, None
    if op == 0x1D:
        return (w >> 11) << 2, None
    if op > 0x55:
        raise ParseError('opcode %02x at %x' % (op, p))
    return STRUCT.get(op, 4), None

def _string(b, p):
    e = b.index(0, p)
    return b[p:e], e + 1

def parse_list(b, p, end, in_switch=False):
    """-> (Block, offset after the closing 00 word)"""
    out = Block()
    while True:
        if p + 4 > end:
            raise ParseError('block overruns its end %x' % end)
        op = b[p]
        if op == 0:
            out.end = b[p:p + 4]
            return out, p + 4
        if not in_switch and (op in TEXT_OPS or op in MULTI_OPS):
            head = b[p:p + STR_HEAD.get(op, 4)]
            q = p + len(head)
            n = 1 if op in TEXT_OPS else (MULTI_OPS[op] or b[p + 1])
            strs = []
            for _ in range(n):
                s, e = _string(b, q)
                q2 = q + ((len(s) + 4) & ~3)
                if any(b[e:q2]):
                    raise ParseError('non-zero string padding at %x' % e)
                strs.append(s)
                q = q2
            out.append(Ins(op, head, strs=strs))
            p = q
            continue
        n, body = _ins_len(b, p, in_switch)
        if n < 4 or p + n > end:
            raise ParseError('bad length %d of op %02x at %x' % (n, op, p))
        if body is None:
            out.append(Ins(op, b[p:p + n]))
        else:
            sw = op in (6, 8) and not in_switch
            kids, q = parse_list(b, body, p + n, sw)
            if q != p + n:
                raise ParseError('block %02x at %x ends at %x, not %x' % (op, p, q, p + n))
            out.append(Ins(op, b[p:body], body=kids, switch=sw))
        p += n

def _pack_len(head, n, op, in_switch):
    w = u32(head, 0)
    k = n >> 2
    if in_switch and op == 7 or not in_switch and op == 6:
        bits, shift = 23, 9
    elif op in (4, 5) and not in_switch or op == 9 and in_switch:
        bits, shift = 14, 18
    elif op == 8:
        bits, shift = 16, 16
    elif op in (0xC, 0xD):
        bits, shift = 9, 16
    else:
        bits, shift = 24, 8
    if k >= 1 << bits:
        raise ParseError('block of op %02x too long (%d bytes)' % (op, n))
    mask = ((1 << bits) - 1) << shift
    return struct.pack('<I', (w & ~mask & 0xFFFFFFFF) | k << shift) + head[4:]

def build_list(items, in_switch=False):
    out = bytearray()
    for it in items:
        if it.strs is not None:
            out += it.head
            for s in it.strs:
                out += s + bytes(((len(s) + 4) & ~3) - len(s))
        elif it.body is None:
            out += it.head
        else:
            body = build_list(it.body, it.switch)
            out += _pack_len(it.head, len(it.head) + len(body), it.op, in_switch) + body
    return bytes(out + getattr(items, 'end', bytes(4)))

class ScriptFile:
    """A T4ES sub-file: head (16 bytes), scripts = [(Block, tail zero count)]."""
    def __init__(self, data):
        if data[:4] != b'T4ES':
            raise ParseError('not a T4ES file')
        self.head = data[:16]
        n = u32(data, 12)
        off = struct.unpack_from('<%dI' % (n + 1), data, 16)
        if off[n] != len(data):
            raise ParseError('offset table does not end at the file size')
        if off[0] != 16 + 4 * (n + 1):
            raise ParseError('gap after the offset table')
        self.scripts = []
        for k in range(n):
            items, q = parse_list(data, off[k], off[k + 1])
            tail = data[q:off[k + 1]]
            if any(tail):
                raise ParseError('script %d: data after the end word' % k)
            self.scripts.append((items, len(tail)))

    def build(self):
        n = len(self.scripts)
        bodies = [build_list(items) + bytes(tail) for items, tail in self.scripts]
        off = [16 + 4 * (n + 1)]
        for s in bodies:
            off.append(off[-1] + len(s))
        return self.head + struct.pack('<%dI' % (n + 1), *off) + b''.join(bodies)

def directory(entry):
    """-> (head 16 bytes, [(file id, offset)] incl. the end row)"""
    n = u32(entry, 8)
    return entry[:16], [struct.unpack_from('<II', entry, 16 + 8 * i) for i in range(n + 1)]

def split(entry):
    """-> (head, [(file id, bytes)], end id)"""
    head, rows = directory(entry)
    files = [(rows[i][0], entry[rows[i][1]:rows[i + 1][1]]) for i in range(len(rows) - 1)]
    return head, files, rows[-1][0]

def join(head, files, end_id):
    n = len(files)
    p = 16 + 8 * (n + 1)
    rows, blobs = [], []
    for fid, data in files:
        rows.append((fid, p))
        blobs.append(data)
        p += len(data)
    rows.append((end_id, p))
    return head + b''.join(struct.pack('<II', *r) for r in rows) + b''.join(blobs)

def strings(items, path=()):
    """Yield (path, ins, index) for every string, in order."""
    for i, it in enumerate(items):
        if it.strs is not None:
            for j in range(len(it.strs)):
                yield path + (i,), it, j
        elif it.body is not None:
            yield from strings(it.body, path + (i,))

def _open():
    import datafile
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    elf = open(os.path.join(root, 'extract', 'SLPM_621.05'), 'rb').read()
    data = open(os.path.join(root, 'extract', 'TR4DATA.DAT'), 'rb').read()
    return lambda i: datafile.entry(data, elf, i)

def main():
    get = _open()
    entry = get(ENTRY_SCRIPT)
    head, files, end_id = split(entry)
    if sys.argv[1] == 'check':
        nscr = nstr = 0
        big = 0
        out = []
        for i, (fid, data) in enumerate(files):
            try:
                sf = ScriptFile(data)
            except ParseError as e:
                print('file %d (id %08x): %s' % (i, fid, e))
                out.append((fid, data))
                continue
            if sf.build() != data:
                raise SystemExit('file %d: rebuild differs' % i)
            nscr += len(sf.scripts)
            nstr += sum(1 for items, _ in sf.scripts for _ in strings(items))
            big = max(big, max(len(build_list(it)) for it, _ in sf.scripts))
            out.append((fid, data))
        if join(head, out, end_id) != entry:
            raise SystemExit('directory rebuild differs')
        print('%d files, %d scripts, %d strings: identical (largest script %d bytes)'
              % (len(files), nscr, nstr, big))
    elif sys.argv[1] == 'dump':
        import text
        sf = ScriptFile(files[int(sys.argv[2])][1])
        ks = [int(sys.argv[3])] if len(sys.argv) > 3 else range(len(sf.scripts))
        for k in ks:
            for path, it, j in strings(sf.scripts[k][0]):
                print('%d %s %s.%d %s' % (k, '.'.join(map(str, path)),
                                          OP_NAMES.get(it.op, '%02x' % it.op), j,
                                          text.decode(it.strs[j]).replace('\n', '\\n')))

if __name__ == '__main__':
    main()
