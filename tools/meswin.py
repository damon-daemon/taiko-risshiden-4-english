"""Message window: draw more than 72 characters per page.

CMesWin (the dialogue/narration window) lays a page out with
CTextAreaBase::strDrawText (48 half-width columns x 3 lines, wrapping by pixel
width) and hands every character to its CMesTextFontList at CMesWin+0xEC. That list
owns a fixed array of 72 CMesTextFontLink objects (0x28 bytes each, list+0x40 ..
list+0xB80, count at list+0xB80): bAddChar__16CMesTextFontList 0x25C3E0 returns 0
once 72 are used, so characters 73-144 of a page are silently not drawn while the
layout goes on (verified 2026-11-08: a 160-character ASCII line showed 72, then the
page break, then characters 144-159). Japanese pages never exceed 72 full-width
characters (3 x 24); English with half-width letters needs up to 144.

Patch (both functions live in the English segment; the class vtable 0x45BF60 is
repointed, the original code is untouched):
- bAddChar: below 72 calls the original; otherwise allocates a new
  CMesTextFontLink (operator new + its constructor, as CFontPrimList::bAddChar does
  for its links), SetData()s it and appends it to the list.
- Clear: the original only unlinks (count = 0). The new one unlinks every link and
  deletes (virtual destructor, flag 1) those outside the inline array: the extra
  character links and the colour links bAddColor allocates (which the original
  leaked). A window destroyed with links still listed is fine: the base
  CFontPrimList destructor deletes listed links itself.
"""
import struct

from asm import assemble

BASE, FOFF = 0x100000, 0x80
VTABLE = 0x45BF60                       # __vt__16CMesTextFontList
VT_ADDCHAR, VT_CLEAR = VTABLE + 8, VTABLE + 0xC
ADDCHAR, CLEAR = 0x25C3E0, 0x25C360
NEW, LINK_CT, SET_DATA = 0x100510, 0x25C1E0, 0x383E80
ADD_LINK_END, REMOVE_LINK = 0x389940, 0x389880
LINK_SIZE, INLINE, ARRAY, COUNT = 0x28, 72, 0x40, 0xB80

def add_char(org):
    return assemble(org, [
        ('addiu', 'sp', 'sp', -0x60),
        ('sq', 'ra', 0x40, 'sp'),
        ('sq', 's0', 0x00, 'sp'),
        ('sq', 's1', 0x10, 'sp'),
        ('sq', 's2', 0x20, 'sp'),
        ('sq', 's3', 0x30, 'sp'),
        ('addu', 's0', 'a0', 'zero'),
        ('addu', 's1', 'a1', 'zero'),
        ('addu', 's2', 'a2', 'zero'),
        ('addu', 's3', 'a3', 'zero'),
        ('lh', 'v0', COUNT, 'a0'),
        ('slti', 'at', 'v0', INLINE),
        ('beqz', 'at', 'heap'),
        ('nop',),
        ('jal', ADDCHAR),                      # inline slot (a0-a3 unchanged)
        ('nop',),
        ('b', 'out'),
        ('nop',),
        'heap:',
        ('jal', NEW),
        ('addiu', 'a0', 'zero', LINK_SIZE),
        ('beqz', 'v0', 'out'),
        ('nop',),
        ('jal', LINK_CT),
        ('addu', 'a0', 'v0', 'zero'),
        ('sw', 'v0', 0x50, 'sp'),
        ('addu', 'a0', 'v0', 'zero'),
        ('addu', 'a1', 's1', 'zero'),
        ('addu', 'a2', 's2', 'zero'),
        ('jal', SET_DATA),
        ('addu', 'a3', 's3', 'zero'),
        ('lw', 'a1', 0x50, 'sp'),
        ('addiu', 'a1', 'a1', 4),              # the CSimpleLink part
        ('jal', ADD_LINK_END),
        ('addiu', 'a0', 's0', 8),
        'out:',
        ('lq', 'ra', 0x40, 'sp'),
        ('lq', 's0', 0x00, 'sp'),
        ('lq', 's1', 0x10, 'sp'),
        ('lq', 's2', 0x20, 'sp'),
        ('lq', 's3', 0x30, 'sp'),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 0x60),
    ])

def clear(org):
    return assemble(org, [
        ('addiu', 'sp', 'sp', -0x30),
        ('sq', 'ra', 0x20, 'sp'),
        ('sq', 's0', 0x00, 'sp'),
        ('sq', 's1', 0x10, 'sp'),
        ('addu', 's0', 'a0', 'zero'),
        ('sh', 'zero', COUNT, 'a0'),
        'loop:',
        ('lw', 's1', 8, 's0'),                 # head link (object + 4)
        ('beqz', 's1', 'done'),
        ('addiu', 'a0', 's0', 8),
        ('jal', REMOVE_LINK),
        ('addu', 'a1', 's1', 'zero'),
        ('addiu', 's1', 's1', -4),             # the object
        ('subu', 'v0', 's1', 's0'),
        ('sltiu', 'at', 'v0', ARRAY),
        ('bnez', 'at', 'delete'),
        ('sltiu', 'at', 'v0', ARRAY + INLINE * LINK_SIZE),
        ('bnez', 'at', 'loop'),                # inline link: keep
        ('nop',),
        'delete:',
        ('lw', 't9', 0, 's1'),
        ('lw', 't9', 0x1C, 't9'),              # virtual destructor
        ('addu', 'a0', 's1', 'zero'),
        ('jalr', 't9'),
        ('addiu', 'a1', 'zero', 1),            # and delete
        ('b', 'loop'),
        ('nop',),
        'done:',
        ('lq', 'ra', 0x20, 'sp'),
        ('lq', 's0', 0x00, 'sp'),
        ('lq', 's1', 0x10, 'sp'),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 0x30),
    ])

def _code(seg, fn):
    n = len(fn(0))
    addr = seg.reserve(n, 16)
    seg.put(addr, fn(addr))
    return addr

def apply(elf, seg):
    def word(va):
        return struct.unpack_from('<I', elf, va - BASE + FOFF)[0]
    assert word(VT_ADDCHAR) == ADDCHAR and word(VT_CLEAR) == CLEAR
    assert word(ADDCHAR + 0x14) == 0x84820B80, 'bAddChar: lh v0, 0xB80(a0)'
    assert word(ADDCHAR + 0x18) == 0x28410048, 'bAddChar: slti at, v0, 72'
    struct.pack_into('<I', elf, VT_ADDCHAR - BASE + FOFF, _code(seg, add_char))
    struct.pack_into('<I', elf, VT_CLEAR - BASE + FOFF, _code(seg, clear))
