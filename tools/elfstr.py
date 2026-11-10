"""String literals of the ELF (menu labels, prompts, format strings ...), repointed exactly
with the ELF's own relocation section.

The ELF still has its `.relmain` relocations (151,980 entries) and its symbol table:
every string literal is a local symbol `@NNN` with a size, and every reference to it
is a relocation against that symbol: R_MIPS_32 (pointer word in data), R_MIPS_HI16 /
R_MIPS_LO16 (lui + addiu/load pair in code) or R_MIPS_GPREL16 (gp-relative access).

tl/elfstr.txt: "vaddr<TAB>English" lines (vaddr hex, \\n = newline, UTF-8: ASCII and the
font's symbols). English that fits the symbol (size - 1 bytes) is written in place;
longer English goes into the English segment and every HI16/LO16/32 reference is
repointed (a GPREL16 reference cannot be: such strings must fit). printf conversions
must match the Japanese.

  elfstr.py export   -> script/elfstr.json (va, symbol, size, references, Japanese, English)
"""
import collections, json, os, re, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import elfseg, text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL = os.path.join(ROOT, 'tl', 'elfstr.txt')
SCRIPT = os.path.join(ROOT, 'script', 'elfstr.json')
CLEAN = os.path.join(ROOT, 'extract', 'SLPM_621.05')
BASE, FOFF = 0x100000, 0x80
DATA_LO, DATA_HI = 0x3E2F90, 0x462980          # end of code .. end of the loaded image
R_32, R_HI16, R_LO16, R_GPREL16 = 2, 5, 6, 7
# ASCII-only literals that still need English (not found by _is_text)
ASCII_LITERALS = {
    0x40F418,          # "%d00" status-bar money remainder (x 100 mon), followed by a fixed "文"
    # "%s(%s)" formats (province(region), ...): a space before the parenthesis
    0x40CE08, 0x40CE10, 0x40CE18, 0x40CE20, 0x40CE28, 0x40CE30, 0x40CE38, 0x40CE60,
    0x40E880, 0x40E888, 0x40E890, 0x41DEC8, 0x41DEF0,
    0x405CA0, 0x405CA8, 0x405CB0,   # card album "%2d %d" / "%3d %d" (collected / total, page)
    0x4051B8,          # skill card label "%sLv.%y" (negotiation, duel...): space before Lv.
    0x4126D8,          # map balloon "%s\n%s\n%s %s": castle, clan, person + Seat/Direct label
}
# strings whose conversions change with a code patch (elftl skips the conversion check)
CODE_FORMATS = {
    0x40F418: '%6d.%d kan',   # statusbar.MONEY: printed instead of "%6d kan" when mon != 0
    0x423CB0: '"%s %s"\nIs this all right?',   # nameentry: readings dropped (extra arguments ignored)
}
FMT = re.compile(rb'%[-+ #0]*\d*(?:\.\d+)?[a-zA-Z]')

def _f(va):
    return va - BASE + FOFF

class Elf:
    """Symbols and relocations of the clean ELF."""
    def __init__(self, data):
        self.data = data
        shoff = struct.unpack_from('<I', data, 0x20)[0]
        n = struct.unpack_from('<H', data, 0x30)[0]
        sh = [struct.unpack_from('<10I', data, shoff + 40 * i) for i in range(n)]
        names = sh[struct.unpack_from('<H', data, 0x32)[0]]
        def sname(s):
            o = names[4] + s[0]
            return data[o:data.index(b'\0', o)].decode()
        secs = {sname(s): s for s in sh}
        symtab, strtab, rel = secs['.symtab'], secs['.strtab'], secs['.relmain']
        self.syms = []
        for i in range(symtab[5] // 16):
            st_name, value, size, info, other, shndx = struct.unpack_from('<IIIBBH', data, symtab[4] + 16 * i)
            o = strtab[4] + st_name
            self.syms.append((data[o:data.index(b'\0', o)].decode('latin-1'), value, size))
        self.refs = collections.defaultdict(list)          # symbol index -> [(type, offset)]
        for i in range(rel[5] // 8):
            off, info = struct.unpack_from('<II', data, rel[4] + 8 * i)
            self.refs[info >> 8].append((info & 0xFF, off))

    def literals(self):
        """[(symbol index, va, size, bytes)] of the string literals in the data."""
        out = []
        for i, (name, va, size) in enumerate(self.syms):
            if name.startswith('@') and DATA_LO <= va < DATA_HI and size:
                b = self.data[_f(va):_f(va) + size]
                s = b.split(b'\0')[0]
                if _is_text(s) or va in ASCII_LITERALS:
                    out.append((i, va, size, s))
        return out

def _is_text(b):
    i, jp = 0, 0
    while i < len(b):
        c = b[i]
        if 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC:
            if i + 1 >= len(b) or not (0x40 <= b[i + 1] <= 0xFC and b[i + 1] != 0x7F):
                return False
            jp += 1
            i += 2
            continue
        if 0xA1 <= c <= 0xDF:
            jp += 1
        elif not (0x20 <= c < 0x7F or c in (0x0A, 0x1B)):
            return False
        i += 1
    return jp > 0

def load_tl():
    out = {}
    if os.path.exists(TL):
        for line in open(TL, encoding='utf-8').read().splitlines():
            if line.strip() and not line.startswith('#'):
                k, _, v = line.partition('\t')
                out[int(k, 16)] = v.replace('\\n', '\n')
    return out

def _word(elf, va):
    return struct.unpack_from('<I', elf, _f(va))[0]

def _hi(a):
    return ((a + 0x8000) >> 16) & 0xFFFF

def _lo(a):
    return a & 0xFFFF

def apply(elf, seg, clean=None):
    """Write tl/elfstr.txt into elf (bytearray); -> (strings, moved)."""
    tl = load_tl()
    if not tl:
        return 0, 0
    E = Elf(clean or open(CLEAN, 'rb').read())
    lits = {va: (i, size, s) for i, va, size, s in E.literals()}
    errors, moved = [], 0
    for va, en in sorted(tl.items()):
        if va not in lits:
            errors.append('elfstr %x: not a string literal' % va)
            continue
        i, size, jp = lits[va]
        b = text.fold(en).encode('cp932')
        if va not in CODE_FORMATS and FMT.findall(b) != FMT.findall(jp):
            errors.append('elfstr %x: conversions %s, Japanese has %s' % (va, FMT.findall(b), FMT.findall(jp)))
            continue
        if len(b) < size:
            elf[_f(va):_f(va) + size] = b.ljust(size, b'\0')
            continue
        refs = E.refs.get(i, [])
        if not refs or any(t not in (R_32, R_HI16, R_LO16) for t, _ in refs):
            errors.append('elfstr %x: %d bytes > room %d and references %s cannot be repointed'
                          % (va, len(b), size - 1, sorted({t for t, _ in refs}) or 'none'))
            continue
        new = seg.add(b + b'\0', 4)
        for t, off in refs:
            w = _word(E.data, off)
            if t == R_32:
                assert w == va, 'elfstr %x: word at %x = %x' % (va, off, w)
                elfseg.patch(elf, off, struct.pack('<I', new))
            elif t == R_HI16:
                assert w & 0xFFFF == _hi(va), 'elfstr %x: HI16 at %x' % (va, off)
                elfseg.patch(elf, off, struct.pack('<I', (w & 0xFFFF0000) | _hi(new)))
            else:
                assert w & 0xFFFF == _lo(va), 'elfstr %x: LO16 at %x' % (va, off)
                elfseg.patch(elf, off, struct.pack('<I', (w & 0xFFFF0000) | _lo(new)))
        moved += 1
    if errors:
        raise ValueError('\n'.join(errors))
    return len(tl), moved

def export():
    import bisect
    E = Elf(open(CLEAN, 'rb').read())
    tl = load_tl()
    named = sorted((va, n, size) for n, va, size in E.syms if va and not n.startswith('@') and not n.startswith('.'))
    keys = [va for va, _, _ in named]
    def owner(off):     # the named symbol holding the reference; '~name' = past its end (unnamed data)
        k = bisect.bisect(keys, off) - 1
        if k < 0:
            return '?'
        va, n, size = named[k]
        return n if not size or off < va + size else '~' + n
    rows = []
    for i, va, size, s in E.literals():
        refs = E.refs.get(i, [])
        kinds = collections.Counter(t for t, _ in refs)
        rows.append({'va': '%x' % va, 'room': size - 1, 'refs': {str(k): v for k, v in sorted(kinds.items())},
                     'used': sorted({owner(off) for t, off in refs})[:4],
                     'jp': s.decode('cp932', 'replace'), 'en': tl.get(va, '')})
    os.makedirs(os.path.dirname(SCRIPT), exist_ok=True)
    json.dump(rows, open(SCRIPT, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    return rows

if __name__ == '__main__':
    if sys.argv[1:] == ['export']:
        rows = export()
        print(len(rows), 'strings,', sum(len(r['jp']) for r in rows), 'chars ->', SCRIPT)
    else:
        sys.exit(__doc__)
