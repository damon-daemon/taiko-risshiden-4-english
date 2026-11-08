"""Name tables in the ELF: fixed records with a name (and for footholds a half-width
kana reading), found by their symbols (sizes from the symbol table).

English needs no reading, so a name may run on into the reading field: it may use the
bytes from the name up to the first data byte (measured from the clean ELF over all
records: any non-zero byte that is not name or reading text), minus one for the NUL.
The foothold reading getter returns an empty string instead (apply_code).

tl/tables/<table>.txt: "index<TAB>English" lines; missing indexes keep the Japanese.

  elftables.py export   -> script/tables/<table>.json (index, Japanese, reading, English)
"""
import json, os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import elfseg, text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL = os.path.join(ROOT, 'tl', 'tables')
SCRIPT = os.path.join(ROOT, 'script', 'tables')
BASE, FOFF = 0x100000, 0x80

# name: (vaddr of record 0, stride, count, name offset, reading offset or None)  [symbol]
TABLES = {
    'goods':       (0x3F9720, 16, 60, 0, None),    # s_asTradeItemData (交易品)
    'placecards':  (0x403DB0, 20, 20, 4, None),    # gs_asPlaceCardData (名所札)
    'skillcards':  (0x403F40, 15, 37, 0, None),    # gs_asSBCardData (秘技札)
    'titlecards':  (0x404170, 15, 81, 0, None),    # gs_asTitleCardData (称号札)
    'battlecards': (0x404630, 24, 37, 0, None),    # gs_asBattleCardData (合戦札)
    'formations':  (0x4049B0, 15, 10, 0, None),    # gs_asBattleFormCardData (陣形札)
    'cards':       (0x404A50, 15, 123, 0, None),   # gs_asCommonCardData (一般札)
    'provinces':   (0x4068C2, 14, 60, 0, None),    # CCountryElement::m_asFixData (+2)
    'footholds':   (0x4081D0, 24, 253, 1, 12),     # CFootHoldElement::m_sFootHoldNameData
    'items':       (0x40F550, 18, 210, 0, None),   # CItemElement::m_sFixData
    'jobs':        (0x4104A0, 16, 33, 0, None),    # s_asJobData (仕事)
    'works':       (0x4106C0, 12, 14, 0, None),    # s_asWorkKindData
    'offices':     (0x4189D0, 12, 150, 0, None),   # COfficialRankElement::m_sFixData (官職)
    'tradeareas':  (0x41F3F0, 25, 15, 0, None),    # s_asTradeAreaData (商業圏)
}
FOOTHOLD_RUBY = 0x1D1020    # CFootHoldElement::strGetNameRuby
# tables whose names are only read through getters that return a pointer: the English
# goes to the segment (any length) and the getters read a pointer table.
# CCountryElement::strGetPureName returns the name, strGetName formats "%s国" with it.
LONG = {'provinces': [(0x1AB710, 'v0', 6, 'c0100500'),     # whole getter (sll v0,a1,3 ...)
                      (0x1AB748, 'a2', 7, 'c0100500')]}     # sll..addiu a2 before strFormat

def _f(va):
    return va - BASE + FOFF

def _cstr(elf, o):
    return bytes(elf[o:elf.index(b'\0', o)])

def text_end(elf, name):
    """Offset (in the record) of the first data byte after the name that is not part of
    the name or reading text (over all records): the name may run on up to there."""
    base, stride, count, no, ro = TABLES[name]
    end = stride
    for i in range(count):
        o = _f(base) + i * stride
        text = set(range(no, no + len(_cstr(elf, o + no)) + 1))
        if ro is not None:
            text |= set(range(ro, ro + len(_cstr(elf, o + ro)) + 1))
        nz = next((k for k in range(no, stride) if elf[o + k] and k not in text), stride)
        end = min(end, nz)
    return end

def records(elf, name):
    base, stride, count, no, ro = TABLES[name]
    o = _f(base)
    return [(i, _cstr(elf, o + i * stride + no), _cstr(elf, o + i * stride + ro) if ro is not None else b'')
            for i in range(count)]

def load_tl(name):
    path = os.path.join(TL, name + '.txt')
    out = {}
    if os.path.exists(path):
        for line in open(path, encoding='utf-8').read().splitlines():
            if line.strip() and not line.startswith('#'):
                k, _, v = line.partition('\t')
                out[int(k)] = v
    return out

def apply(elf, clean_elf, seg):
    """Write the English of every table into elf; returns {table: count}."""
    done, errors = {}, []
    for name, (base, stride, count, no, ro) in TABLES.items():
        tl = load_tl(name)
        if not tl:
            continue
        end = text_end(clean_elf, name)
        room = end - no - 1
        if name in LONG:
            _apply_long(elf, clean_elf, seg, name, tl)
            done[name] = len(tl)
            continue
        for i, en in tl.items():
            b = text.fold(en).encode('ascii')
            if len(b) > room:
                errors.append('%s %d: %r is %d bytes, room %d' % (name, i, en, len(b), room))
                continue
            o = _f(base) + i * stride + no
            elf[o:o + room + 1] = b + bytes(room + 1 - len(b))
        done[name] = len(tl)
    if errors:
        raise ValueError('\n'.join(errors))
    if load_tl('footholds'):
        import asm
        empty = seg.add(b'\0', 4)
        o = _f(FOOTHOLD_RUBY)
        assert elf[o:o + 4] == bytes.fromhex('f0ffbd27'), 'foothold reading getter moved'   # addiu sp,-0x10
        elfseg.patch(elf, FOOTHOLD_RUBY, asm.assemble(FOOTHOLD_RUBY, [
            ('lui', 'v0', asm.hi(empty)), ('jr', 'ra'), ('addiu', 'v0', 'v0', asm.lo(empty))]))
    return done

def _apply_long(elf, clean_elf, seg, name, tl):
    import asm
    for i, en in tl.items():
        text.fold(en).encode('ascii')
    ptrs = [seg.add(text.fold(tl[i]).encode('ascii') + b'\0', 1) if i in tl else
            TABLES[name][0] + i * TABLES[name][1] + TABLES[name][3] for i in range(TABLES[name][2])]
    table = seg.add(struct.pack('<%dI' % len(ptrs), *ptrs), 4)
    for va, reg, n, first in LONG[name]:
        assert clean_elf[_f(va):_f(va) + 4] == bytes.fromhex(first), '%s getter moved' % name
        code = [('lui', reg, asm.hi(table)), ('sll', 'v1', 'a1', 2), ('addu', reg, reg, 'v1'),
                ('lw', reg, asm.lo(table), reg)]
        if reg == 'v0':
            code += [('jr', 'ra'), ('nop',)]
        code += [('nop',)] * (n - len(code))
        elfseg.patch(elf, va, asm.assemble(va, code))

def export(elf):
    os.makedirs(SCRIPT, exist_ok=True)
    for name in TABLES:
        tl = load_tl(name)
        rows = [{'id': i, 'jp': jp.decode('cp932', 'replace'), 'reading': rd.decode('cp932', 'replace'),
                 'en': tl.get(i, '')} for i, jp, rd in records(elf, name)]
        json.dump({'room': text_end(elf, name) - TABLES[name][3] - 1, 'rows': rows},
                  open(os.path.join(SCRIPT, name + '.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)

if __name__ == '__main__':
    elf = open(os.path.join(ROOT, 'extract', 'SLPM_621.05'), 'rb').read()
    if sys.argv[1:] == ['export']:
        export(elf)
        for name in TABLES:
            print(name, 'room', text_end(elf, name) - TABLES[name][3] - 1)
    else:
        sys.exit(__doc__)
