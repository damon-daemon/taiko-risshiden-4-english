"""Name entry (new officer): English letters, long names, no reading fields.

CInpNameWindow (0x3C9E10-0x3CEE80; caller MakeNewBushouName 0x1DE130) edits an SNameData
(34 B: family[9] | family reading[9] | given[7] | given reading[9]) in four input modes
(m_eNameMode +0xB8: 0 family, 1 its reading, 2 given, 3 its reading; L1/R1). The right
grid (gs_strNameList 0x3FC2E0, 6 x 10 string pointers, 8-byte strings from 0x423350;
gs_eNameCode = EListCode per cell) picks a kana row or a button (戻る かな カナ 数字 英字
記号 決定); the left panel then lists the candidates of that code (kanji by reading, or
full-width letters for 英字; ranges in gs_sjCodeKouho) and InsCode appends the pick.

English names are family 15 + given 13 bytes (names.py record layout) and readings are
not shown anywhere, so:
- SNameData becomes family[18] at +0 | given[16] at +0x12 (same 34 bytes; the copies in
  MakeNewBushouName, the constructor and bEndCheck use 16/14 bytes, reading copies are
  dropped and the person's reading record is emptied);
- modes 1 and 3 are skipped (L1/R1 step 2), their strings are no longer drawn, the
  confirmation only needs the two names;
- InsCode converts a full-width letter / digit pick to ASCII (CONV; ー -> '-') and
  allows 15 / 13 bytes; DelCode removes the last character whatever its size (DEL);
- the window opens in pick mode on the 英字 cell (the letter panel is up at once) and
  keeps the panel when the field is switched;
- the name positions move right of the "Family" / "Given" labels (points 0x423BF0.. are
  set by a static initialiser: rewritten in the constructor hook), underlines are 7 / 6
  cells of 24 px;
- the grid buttons are English (BUTTONS).
Japanese kana / kanji can still be entered. The shop-name window (CInpYagouWindow) is
unchanged.
"""
import struct

from asm import assemble
import text

BASE, FOFF = 0x100000, 0x80
ROOM_FAMILY, ROOM_GIVEN = 15, 13
STRLEN, STRCPY, STRNCPY, COPY, PUT_INP = 0x385F30, 0x385EF0, 0x385E20, 0x1009B0, 0x3CE780
CODE = (0x3C9E10, 0x3CE3C0)             # bInpEvent .. Open (PutInpString callers)
NAME_X = {0x423BF0: 72, 0x423BF8: 72, 0x423C10: 400, 0x423C18: 400}   # text + underline x
GRID_STRINGS = 0x423350                 # 60 x 8 bytes
BUTTONS = {23: ('戻る', 'Back'), 29: ('かな', 'Hira'), 35: ('カナ', 'Kata'), 41: ('数字', ' 123'),
           47: ('英字', ' ABC'), 53: ('記号', ' Sym'), 59: ('決定', '  OK')}   # spaces: centred in 48 px
ALPHA_CELL = (5, 7)                     # column, row of 英字 in the grid

# (address, original word, replacement lines)
def _sites(conv, dele, init):
    li = lambda reg, n: [('addiu', reg, 'zero', n)]
    nop = [('nop',)]
    jal = lambda f: 0x0C000000 | f >> 2
    return [
        # MakeNewBushouName: readings not loaded; names back with 16/14, readings emptied
        (0x1DE2A8, jal(STRCPY), nop), (0x1DE2C8, jal(STRCPY), nop),
        (0x1DE318, 0x24060009, li('a2', ROOM_FAMILY + 1)),
        (0x1DE330, jal(STRNCPY), [('sb', 'zero', 0, 'a0')]),
        (0x1DE344, 0x24060007, li('a2', ROOM_GIVEN + 1)),
        (0x1DE360, jal(STRNCPY), [('sb', 'zero', 0, 'a0')]),
        # constructor: copy 16 / 14, no readings; initial state
        (0x3CE504, 0x24060009, li('a2', ROOM_FAMILY + 1)), (0x3CE520, jal(COPY), nop),
        (0x3CE534, 0x24060007, li('a2', ROOM_GIVEN + 1)), (0x3CE550, jal(COPY), nop),
        (0x3CE568, 0x8FA2002C, [('jal', init)]),            # lw v0, 0x2c(sp)
        (0x3CE56C, 0xAC4000C0, [('daddu', 'a0', 'v0', 'zero')]),   # sw zero, 0xc0(v0)
        (0x3CE570, 0x70001E28, nop), (0x3CE574, 0x70002628, nop),  # v1 / a0 = cursor (from init)
        # bEndCheck: readings not required, not copied
        (0x3CDB0C, 0x1200002C, nop), (0x3CDB1C, 0x12400028, nop),
        (0x3CDC14, 0x1600000E, [('b', 0x3CDC50)]), (0x3CDC8C, 0x1640000D, [('b', 0x3CDCC4)]),
        (0x3CDB6C, 0x24060009, li('a2', ROOM_FAMILY + 1)), (0x3CDB84, jal(COPY), nop),
        (0x3CDB94, 0x24060007, li('a2', ROOM_GIVEN + 1)), (0x3CDBAC, jal(COPY), nop),
        # InsCode: convert the pick, longer fields
        (0x3CD778, jal(STRLEN), [('jal', conv)]),
        (0x3CD7D0, 0x24030008, li('v1', ROOM_FAMILY)), (0x3CD878, 0x24030006, li('v1', ROOM_GIVEN)),
        # DelCode: family / given
        (0x3CD544, jal(STRLEN), [('jal', dele)]),
        (0x3CD554, 0x00501821, nop), (0x3CD558, 0xA0600093, nop),
        (0x3CD55C, 0x00501821, nop), (0x3CD560, 0xA0600092, nop),
        (0x3CD59C, jal(STRLEN), [('jal', dele)]),
        (0x3CD5AC, 0x00501821, nop), (0x3CD5B0, 0xA06000A5, nop),
        (0x3CD5B4, 0x00501821, nop), (0x3CD5B8, 0xA06000A4, nop),
        # L1 / R1: family <-> given, the pick panel stays
        (0x3C9EF0, 0x24050001, li('a1', 2)), (0x3CA0C4, 0x24050001, li('a1', 2)),
        (0x3C9F3C, 0xAEA000C0, nop), (0x3CA110, 0xAEA000C0, nop),
        # underline cells
        (0x3CBAB0, 0x2E420004, [('sltiu', 'v0', 's2', 7)]),
        (0x3CBC50, 0x2E420003, [('sltiu', 'v0', 's2', 6)]),
    ]

def _word(elf, va):
    return struct.unpack_from('<I', elf, va - BASE + FOFF)[0]

def _put(elf, va, b):
    elf[va - BASE + FOFF:va - BASE + FOFF + len(b)] = b

def conv_code(buf):
    """a0 = picked string. A single full-width letter / digit / ー becomes one ASCII byte
    in buf and the caller's s2 (its string pointer) is set to buf; v0 = length."""
    def rng(first, n, ascii0):
        return [('addiu', 't3', 't1', -first), ('sltiu', 'at', 't3', n),
                ('bnez', 'at', 'out'), ('addiu', 't3', 't3', ascii0)]
    return lambda org: assemble(org, [
        ('lbu', 't0', 0, 'a0'),
        ('beqz', 't0', 'orig'),
        ('lbu', 't1', 1, 'a0'),
        ('lbu', 't2', 2, 'a0'),
        ('bnez', 't2', 'orig'),
        ('addiu', 'at', 'zero', 0x81),
        ('beq', 't0', 'at', 'sym'),
        ('addiu', 'at', 'zero', 0x82),
        ('bne', 't0', 'at', 'orig'),
        ('nop',),
        *rng(0x4F, 10, ord('0')), *rng(0x60, 26, ord('A')), *rng(0x81, 26, ord('a')),
        'orig:',
        ('j', STRLEN),
        ('nop',),
        'sym:',
        ('addiu', 'at', 'zero', 0x5B),
        ('bne', 't1', 'at', 'orig'),
        ('addiu', 't3', 'zero', ord('-')),
        'out:',
        ('lui', 's2', buf >> 16),
        ('ori', 's2', 's2', buf & 0xFFFF),
        ('sb', 't3', 0, 's2'),
        ('sb', 'zero', 1, 's2'),
        ('jr', 'ra'),
        ('addiu', 'v0', 'zero', 1),
    ])

def del_code(org):
    """a0 = string: cut its last character (1 or 2 bytes); v0 = 0 if it was empty."""
    return assemble(org, [
        ('daddu', 'v0', 'zero', 'zero'),
        'loop:',
        ('lbu', 't0', 0, 'a0'),
        ('beqz', 't0', 'done'),
        ('nop',),
        ('daddu', 'v0', 'a0', 'zero'),
        ('addiu', 't1', 't0', -0x81),
        ('sltiu', 't1', 't1', 0x1F),
        ('bnez', 't1', 'two'),
        ('addiu', 't1', 't0', -0xE0),
        ('sltiu', 't1', 't1', 0x1D),
        ('beqz', 't1', 'loop'),
        ('addiu', 'a0', 'a0', 1),
        ('b', 'second'),
        ('nop',),
        'two:',
        ('addiu', 'a0', 'a0', 1),
        'second:',
        ('lbu', 't0', 0, 'a0'),
        ('bnez', 't0', 'loop'),
        ('addiu', 'a0', 'a0', 1),
        'done:',
        ('beqz', 'v0', 'ret'),
        ('nop',),
        ('sb', 'zero', 0, 'v0'),
        'ret:',
        ('jr', 'ra'),
        ('nop',),
    ])

def init_code(org):
    """a0 = window (constructor): pick mode on, name positions; v1, a0 = grid cursor."""
    lines = [('addiu', 't0', 'zero', 1), ('sw', 't0', 0xC0, 'a0'), ('lui', 't1', 0x42)]
    for va, x in NAME_X.items():
        assert va >> 16 == 0x42 and va & 0x8000 == 0
        lines += [('addiu', 't0', 'zero', x), ('sw', 't0', va & 0xFFFF, 't1')]
    lines += [('addiu', 'v1', 'zero', ALPHA_CELL[0]), ('jr', 'ra'), ('addiu', 'a0', 'zero', ALPHA_CELL[1])]
    return assemble(org, lines)

def apply(elf, seg):
    buf = seg.reserve(4, 4)
    seg.put(buf, bytes(4))
    funcs = []
    for body in (conv_code(buf), del_code, init_code):
        fn = seg.reserve(len(body(0)), 8)
        seg.put(fn, body(fn))
        funcs.append(fn)
    for va, old, lines in _sites(*funcs):
        assert _word(elf, va) == old, 'nameentry: %x is %08x' % (va, _word(elf, va))
        _put(elf, va, assemble(va, lines))
    # reading strings (+0x9D, +0xAD of the window) are no longer drawn
    n, put = 0, 0x0C000000 | PUT_INP >> 2
    for va in range(CODE[0], CODE[1], 4):
        w = _word(elf, va)
        if w >> 26 == 0x09 and (w >> 16) & 31 == 5 and w & 0xFFFF in (0x9D, 0xAD):   # addiu a1, reg, 0x9d
            for at in range(va + 4, va + 40, 4):
                if _word(elf, at) == put:
                    _put(elf, at, bytes(4))
                    n += 1
                    break
    assert n == 10, n                        # bInpEvent 4, DelCode 2, InsCode 2, Open 2
    for cell, (jp, en) in BUTTONS.items():
        o = GRID_STRINGS + 8 * cell - BASE + FOFF
        assert bytes(elf[o:o + 8]).rstrip(b'\0') == jp.encode('cp932'), cell
        elf[o:o + 8] = text.encode(en).ljust(8, b'\0')
