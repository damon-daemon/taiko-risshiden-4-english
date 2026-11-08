"""Numbers in the game's printf (Sprintf/VSprintf -> PrintfMain 0x387180): ASCII only.

Besides the usual conversions, PrintfMain has Japanese ones, used by ELF strings and
messages alike:
- %w: full-width digits (nPrintWDec), %y: the same with a flag set (gp-0x7B4C);
  "Save to file %w." showed "file １".
- %k: kanji numerals (nPrintKanjiNumber), e.g. "%k years, a single dream".
- %m / %M: money (nPrintMoneySub 0x387E70: value in units of 100 mon, printed as
  "N貫M00文" with ASCII / full-width digits, padded on the left to the field width).

Patch: the dispatch branches for 'w', 'y' and 'k' jump to the %d code (0x3875EC,
same registers: v1 = 'l' flag, s2 flags, s5/v0 width), and nPrintMoneySub jumps to
MONEY in the English segment, which prints "N kan", "N.M kan" or "M00 mon" (under
one kan), '-' first if negative, left-padded with spaces to the width, and returns
the number of bytes written like the original.
"""
import struct

from asm import assemble

BASE, FOFF = 0x100000, 0x80
DEC = 0x3875EC
BRANCHES = {0x387414: (0x10A40054, 0x387568),   # beq a1,a0 : 'w'
            0x387420: (0x10A4004F, 0x387560),   # 'y'
            0x38742C: (0x10A20037, 0x38750C)}   # beq a1,v0 : 'k'
MONEY_SUB = 0x387E70

def _word(elf, va):
    return struct.unpack_from('<I', elf, va - BASE + FOFF)[0]

def _put(elf, va, b):
    elf[va - BASE + FOFF:va - BASE + FOFF + len(b)] = b

def _push(chars):
    """store chars (in print order) backwards before s1"""
    out = []
    for ch in reversed(chars):
        out += [('addiu', 's1', 's1', -1), ('addiu', 't4', 'zero', ord(ch)), ('sb', 't4', 0, 's1')]
    return out

def money_fn(org):
    """MONEY(a0 = output fn(char), a1 = value, a2 = width, a3 = wide: ignored) -> v0 = bytes"""
    return assemble(org, [
        ('addiu', 'sp', 'sp', -0x80),
        ('sq', 's0', 0x30, 'sp'), ('sq', 's1', 0x40, 'sp'), ('sq', 's2', 0x50, 'sp'),
        ('sq', 's3', 0x60, 'sp'), ('sq', 'ra', 0x70, 'sp'),
        ('addu', 's0', 'a0', 'zero'),
        ('sll', 't0', 'a1', 0),                 # low 32 bits, signed
        ('addu', 's3', 'a2', 'zero'),
        ('addiu', 's2', 'sp', 0x30),            # buffer sp+0x08..0x2F, filled backwards
        ('addu', 's1', 's2', 'zero'),
        ('addu', 't5', 'zero', 'zero'),
        ('bgez', 't0', 'pos'),
        ('nop',),
        ('subu', 't0', 'zero', 't0'),
        ('addiu', 't5', 'zero', 1),
        'pos:',
        ('addiu', 't1', 'zero', 10),
        ('div', 't0', 't1'),
        ('mflo', 't2'),                         # kan
        ('mfhi', 't3'),                         # hundreds of mon
        ('bnez', 't2', 'kan'),
        ('nop',)] + _push(' mon') + _push('00') + [
        ('addiu', 's1', 's1', -1),
        ('addiu', 't4', 't3', ord('0')),
        ('b', 'sign'),
        ('sb', 't4', 0, 's1'),
        'kan:'] + _push(' kan') + [
        ('beqz', 't3', 'digits'),
        ('nop',),
        ('addiu', 's1', 's1', -1),
        ('addiu', 't4', 't3', ord('0')),
        ('sb', 't4', 0, 's1')] + _push('.') + [
        'digits:',
        ('div', 't2', 't1'),
        ('mflo', 't2'),
        ('mfhi', 't3'),
        ('addiu', 's1', 's1', -1),
        ('addiu', 't4', 't3', ord('0')),
        ('bnez', 't2', 'digits'),
        ('sb', 't4', 0, 's1'),
        'sign:',
        ('beqz', 't5', 'len'),
        ('nop',)] + _push('-') + [
        'len:',
        ('subu', 't0', 's2', 's1'),             # length
        ('subu', 's3', 's3', 't0'),             # padding
        ('slt', 'at', 's3', 'zero'),
        ('movn', 's3', 'zero', 'at'),
        ('addu', 't0', 't0', 's3'),
        ('sw', 't0', 0, 'sp'),                  # total
        'pad:',
        ('beqz', 's3', 'chars'),
        ('nop',),
        ('jalr', 's0'),
        ('addiu', 'a0', 'zero', 0x20),
        ('b', 'pad'),
        ('addiu', 's3', 's3', -1),
        'chars:',
        ('beq', 's1', 's2', 'done'),
        ('nop',),
        ('lbu', 'a0', 0, 's1'),
        ('jalr', 's0'),
        ('addiu', 's1', 's1', 1),
        ('b', 'chars'),
        ('nop',),
        'done:',
        ('lw', 'v0', 0, 'sp'),
        ('lq', 's0', 0x30, 'sp'), ('lq', 's1', 0x40, 'sp'), ('lq', 's2', 0x50, 'sp'),
        ('lq', 's3', 0x60, 'sp'), ('lq', 'ra', 0x70, 'sp'),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 0x80),
    ])

def apply(elf, seg):
    for va, (w, tgt) in BRANCHES.items():
        assert _word(elf, va) == w and va + 4 + ((w & 0xFFFF) << 2) == tgt, hex(va)
        _put(elf, va, struct.pack('<I', (w & 0xFFFF0000) | ((DEC - va - 4) >> 2 & 0xFFFF)))
    assert _word(elf, MONEY_SUB) == 0x27BDFF40, 'nPrintMoneySub prologue'
    n = len(money_fn(0x100000))
    fn = seg.reserve(n, 8)
    seg.put(fn, money_fn(fn))
    _put(elf, MONEY_SUB, assemble(MONEY_SUB, [('j', fn), ('nop',)]))
