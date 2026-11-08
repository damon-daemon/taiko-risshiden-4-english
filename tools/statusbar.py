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

def apply(elf, seg):
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
