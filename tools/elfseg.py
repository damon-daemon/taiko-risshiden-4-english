"""English data segment: code and data the patches need, loaded at the end of the BSS.

Ported from TR5. The ELF has two PT_LOAD program headers; the second (at _end =
0x89BC80) is empty. Filling it makes the loader place our bytes right after the BSS.
The heap starts at _end, so crt0 is patched to start it after the segment instead:

  0x10006C/0x100074  lui/addiu a0 = _end        SetupHeap syscall (0x3D): heap start
  0x10040C/0x100410  lui v0 / addiu v1, v0 = _end   InitAlloc: start of the malloc arena
  0x3EA4A4           word = _end                libkernel sbrk's heap pointer (heap_ptr.30)

0x100008/0x100014 (BSS clear end) stays: the BSS still ends at 0x89BC80. That loop
(sq; sltu; bnez with the add in the delay slot) clears one quadword PAST _end, so the
segment starts with 16 bytes of padding (found 2026-11-08: the first 16 bytes of the
half-width code table were zero in RAM).

TR4 difference: the ELF is followed directly by TR4DATA.DAT on the disc (no free
sectors), so the file must not grow. The segment's bytes are written over the start
of the `.debug` section (12 MB of Metrowerks debug info the loader never reads; the
section header is turned into SHT_NULL so tools do not try to parse it).
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import asm

BASE = 0x89BC80
FOFF, VBASE = 0x80, 0x100000
# (lui address, addiu address, lui register, addiu destination register)
HEAP_SITES = [(0x10006C, 0x100074, 'a0', 'a0'), (0x10040C, 0x100410, 'v0', 'v1')]
HEAP_WORDS = [0x3EA4A4]
DEBUG_SECTION = '.debug'

class Segment:
    def __init__(self, base=BASE):
        self.base, self.data = base, bytearray(16)     # crt0 clears _end..+16

    @property
    def end(self):
        return self.base + len(self.data)

    def add(self, b, align=4):
        self.data.extend(bytes(-len(self.data) % align))
        addr = self.end
        self.data.extend(b)
        return addr

    def reserve(self, n, align=4):
        """Address of n zero bytes (filled later with put)."""
        return self.add(bytes(n), align)

    def put(self, addr, b):
        o = addr - self.base
        assert 0 <= o and o + len(b) <= len(self.data)
        self.data[o:o + len(b)] = b

def patch(elf, vaddr, b):
    o = vaddr - VBASE + FOFF
    elf[o:o + len(b)] = b

def sections(elf):
    """[(name, header offset, sh_type, sh_offset, sh_size)]"""
    shoff = struct.unpack_from('<I', elf, 0x20)[0]
    shentsize, shnum, shstrndx = struct.unpack_from('<HHH', elf, 0x2E)
    stroff = struct.unpack_from('<I', elf, shoff + shstrndx * shentsize + 16)[0]
    out = []
    for i in range(shnum):
        h = shoff + i * shentsize
        name, typ, _, _, off, size = struct.unpack_from('<6I', elf, h)
        n = elf[stroff + name:elf.index(0, stroff + name)].decode()
        out.append((n, h, typ, off, size))
    return out

def apply(elf, seg):
    """Write the segment into the .debug space, point PT_LOAD 2 at it, move the heap."""
    phoff = struct.unpack_from('<I', elf, 0x1C)[0]
    phnum = struct.unpack_from('<H', elf, 0x2C)[0]
    assert phnum == 2
    p = struct.unpack_from('<8I', elf, phoff + 32)
    assert p[0] == 1 and p[2] == BASE and p[4] == 0, 'PT_LOAD 2 is not the empty one at _end'
    size = len(seg.data)
    if size <= 16:
        return BASE
    name, h, typ, off, room = next(s for s in sections(elf) if s[0] == DEBUG_SECTION)
    start = (off + 0x7F) & ~0x7F
    assert size <= off + room - start, 'English segment does not fit in .debug'
    elf[start:start + size] = seg.data
    struct.pack_into('<I', elf, h + 4, 0)                       # SHT_NULL
    struct.pack_into('<8I', elf, phoff + 32, 1, start, BASE, BASE, size, size, 7, 0x10)
    end = (BASE + size + 0xFF) & ~0xFF
    for lui, addiu, r_lui, r_add in HEAP_SITES:
        o = lambda va: va - VBASE + FOFF
        assert elf[o(lui):o(lui) + 4] == asm.assemble(lui, [('lui', r_lui, asm.hi(BASE))])
        assert elf[o(addiu):o(addiu) + 4] == asm.assemble(addiu, [('addiu', r_add, r_lui, asm.lo(BASE))])
        patch(elf, lui, asm.assemble(lui, [('lui', r_lui, asm.hi(end))]))
        patch(elf, addiu, asm.assemble(addiu, [('addiu', r_add, r_lui, asm.lo(end))]))
    for va in HEAP_WORDS:
        assert elf[va - VBASE + FOFF:va - VBASE + FOFF + 4] == struct.pack('<I', BASE)
        patch(elf, va, struct.pack('<I', end))
    return end
