"""Status bar (date, money, location, top left of the map screens): room for 64 glyphs.

gs_cInfoSprite 0x51B2F0 (CTR4InfoSprite, the only instance: built by the static
initialisers, no other caller of its constructor 0x22B0B0) draws PutStatus 0x22A6D0
(date "%4d/%2d/%2d", money "%6d kan", "%d00 mon", the location name) into its
CStatusFontList at +0x50. That list (CInfoFontListBase) keeps its links in an array
it points to (+0x40), with the capacity at +0x44 (s16) and the count at +0x46:
the constructor sets the array to the inline one at +0x4C, capacity 32, and builds
the 32 links (0x2C bytes) with __construct_array. Every character, spaces included,
takes a link, and bAddChar refuses the 33rd: "1560/ 6/30" + "    50 kan" + " " +
"Kiyosu Castle" lost its last two letters.

Patch: the array, its construction and the capacity move to a 64-link buffer in the
English segment. (The 32 inline links are no longer constructed; only the static
destructor would touch them, and it never runs.)

Money (MONEY 0x22A7E4): the game prints "%6d" kan at x 288, then "%d00" mon at x 384 when
the remainder isn't 0, then a fixed 文 at x 420: "475 kan 800 mon" ran past the bar. Now one
bPrintf at x 288: "%6d kan" (40F410) or "%6d.%d kan" (40F418, elfstr.CODE_FORMATS) with
the remainder in tenths of a kan ("475.8 kan", as printfnum prints money in messages).
"""
import struct

from asm import assemble, hi, lo

BASE, FOFF = 0x100000, 0x80
LINK, OLD_N, NEW_N = 0x2C, 32, 64
SET_ARRAY = 0x22B12C      # lw v0,0x2c(sp); addiu v0,v0,0x4c; sw v0,0x40(s0); addiu v0,zero,0x20; sh v0,0x44(s0)
CT_ARRAY = 0x22B17C       # lw v0,0x2c(sp); addiu a0,v0,0x4c   (__construct_array: a0 = array)
CT_COUNT = 0x22B198       # addiu t0,zero,0x20                 (__construct_array: t0 = count)

def _word(elf, va):
    return struct.unpack_from('<I', elf, va - BASE + FOFF)[0]

def _put(elf, va, b):
    elf[va - BASE + FOFF:va - BASE + FOFF + len(b)] = b

MONEY = 0x22A7E4         # kan printf (x 288) .. the remainder's divu test 0x22A830
REMAINDER = 0x22A874     # lui/addiu "%d00" (relocation sites, kept), jal bPrintf, nop

def apply(elf, seg):
    w = lambda va: _word(elf, va)
    hi16 = lambda va: w(va) >> 16              # opcode + registers (elfstr repoints the immediates later)
    assert [w(MONEY), w(MONEY + 4), hi16(0x22A808), hi16(0x22A80C), w(0x22A810)] == \
        [0x3C02CCCC, 0x3442CCCD, 0x3C02, 0x2446, 0x0C0E0BA4], 'status money'
    assert [hi16(REMAINDER), hi16(REMAINDER + 4), w(REMAINDER + 8)] == [0x3C02, 0x2446, 0x0C0E0BA4]
    # 0x22A7E4-0x22A80C stay (a3 = kan, a0/a1, a2 = "%6d kan" via the relocated lui/addiu)
    _put(elf, 0x22A810, assemble(0x22A810, [
        ('sll', 't0', 'a3', 2), ('addu', 't0', 't0', 'a3'), ('sll', 't0', 't0', 1),
        ('subu', 't0', 's0', 't0'),               # remainder (x 100 mon) = 2nd argument
        ('beqz', 't0', REMAINDER + 8),            # -> jal bPrintf with "%6d kan"
        ('nop',),
        ('b', REMAINDER),                         # a2 = "%6d.%d kan", jal bPrintf
        ('nop',)]))

    assert [_word(elf, SET_ARRAY + 4 * i) for i in range(5)] == \
        [0x8FA2002C, 0x2442004C, 0xAE020040, 0x24020020, 0xA6020044], 'status list setup'
    assert [_word(elf, CT_ARRAY + 4 * i) for i in range(2)] == [0x8FA2002C, 0x2444004C]
    assert _word(elf, CT_COUNT) == 0x24080000 | OLD_N
    buf = seg.reserve(NEW_N * LINK, 16)
    _put(elf, SET_ARRAY, assemble(SET_ARRAY, [
        ('lui', 'v0', hi(buf)), ('addiu', 'v0', 'v0', lo(buf)), ('sw', 'v0', 0x40, 's0'),
        ('addiu', 'v0', 'zero', NEW_N), ('sh', 'v0', 0x44, 's0')]))
    _put(elf, CT_ARRAY, assemble(CT_ARRAY, [('lui', 'a0', hi(buf)), ('addiu', 'a0', 'a0', lo(buf))]))
    _put(elf, CT_COUNT, assemble(CT_COUNT, [('addiu', 't0', 'zero', NEW_N)]))
