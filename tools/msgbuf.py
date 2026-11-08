"""Message block buffer: room for English blocks.

CMessageManager (one instance, MSGMGR 0x5474C0) keeps block 0 at this+0 and loads the
current other block right after it, at this + align64(size of block 0), up to its
output buffer at this+0x10200: about 51 KB. English blocks 13 and 17-19 are 53-55 KB
and overran into the manager's fields (bios came out blank).

The five places that compute that base (lui/lw gs_uiMesOffset[1]; addiu 0x3F; and -0x40:
dwSetMsgOffset 0x25720C / 0x257308 / 0x25735C / 0x257398, ReadMsgData 0x257440) now
compute BUF - this instead, so the block goes to a 64 KB buffer in the English segment.
Read positions stay relative to `this` (u32 arithmetic wraps), as in the original.
"""
import struct

import elfseg
from asm import assemble, hi, lo

SIZE = 0x10000
SITES = [(0x25720C, 's4'), (0x257308, 's4'), (0x25735C, 's4'), (0x257398, 's4'), (0x257440, 's3')]
REG = 'zero at v0 v1 a0 a1 a2 a3'.split()

def _w(elf, va):
    return struct.unpack_from('<I', elf, va - elfseg.VBASE + elfseg.FOFF)[0]

def apply(elf, seg, largest):
    assert largest <= SIZE, 'message block of %d bytes > buffer %d' % (largest, SIZE)
    buf = seg.reserve(SIZE, 64)
    for va, this in SITES:
        assert _w(elf, va) == 0x3C010041 and _w(elf, va + 4) == 0x8C222954, hex(va)   # lui at,0x41; lw v0,0x2954(at)
        a = _w(elf, va + 16)
        assert a >> 26 == 0 and a & 0x3F == 0x24, hex(va)                            # and rd, ...
        rd = REG[(a >> 11) & 31]
        elfseg.patch(elf, va, assemble(va, [
            ('lui', rd, hi(buf)), ('addiu', rd, rd, lo(buf)), ('subu', rd, rd, this), ('nop',), ('nop',)]))
    return buf
