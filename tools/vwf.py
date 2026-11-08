"""Latin text: a new half-width font with all of ASCII, and the ELF changes that use it.

TR4's text engine (CFont, 0x3849E0-0x384CA0):
- full-width glyphs: TR4DATA entry 58 (24x24 4bpp, 3,777 glyphs) loaded into
  CFont::ms_abyImageBuff 0x586480, looked up by binary search of g_aushKanjiTable;
- half-width glyphs: entry 59 (12x24 4bpp, low nibble first, levels 0-15, 141 glyphs,
  0x4F50 bytes) loaded into CFont::ms_abyHalfBuff 0x68FDA0 (BSS, exactly 141 glyphs
  long), looked up by SearchHalfNumber 0x3849E0: binary search of the 141 sorted codes
  g_abyHalfCodeTable 0x3FBAB0 (83 ASCII + 58 kana ｦ-ﾟ). Missing ASCII: " # $ % & ' ; @
  \\ ^ ` ~ (no apostrophe!).

Stage 2, proportional advance: WIDTH(a0 = byte, a1 = half cell) in the segment
returns the advance (ASCII 0x20-0x7E: tools/latinfont.py advance, scaled by half/12
when a list draws at another size; Shift-JIS lead byte: 2 x half; else half). It
uses only v0/v1/at/a0, so callers can keep state in t registers. Sites:
- CTextAreaBase::strDrawText: the wrap test (0x38C834, x + advance > right edge; word
  wrap: at a word start the whole word's width is tested, see text_wrap) and
  the horizontal advance (0x38CC80; s0 = kanji flag, s4 already past the char);
- CFontPrimContainer::bPuts: the half-width advance (0x3831D0, sp+0x48 = half cell);
- ptGetTextSize (box sizing): uiStrLen2 (longest line in bytes) is replaced by a
  pixel measure (sum of advance + spacing per char, kanji = 2 columns as before),
  and the multiply by (half + spacing) at 0x38CDC0 by a move;
- CPersonInfoWin::DrawWindow (officer bio, 22x24 cells): half-width x += 11 at
  0x21EF1C (it still wraps per character at x >= 242: bios are wrapped at build time);
- strlen x 12 pixel measures (STRLEN12: speaker nameplates CMesWin::PersonMes & co, person
  info name, help titles, save-file buttons, name entry, list pages...): `jal uiStrLen; ds;
  sll v1,v0,1; addu x,v1,v0; sll R,x,2` -> `jal STR_PX; ds; addu R,v0,zero; nop; nop`
  (STR_PX = pixel width at half cell 12, kanji 24: identical for Japanese text). Not
  patched (other arithmetic): CPersonButton 0x1CF884.. (10-px cells), DrawCheckMessage
  0x3D54D0, CEnvironmentWin 0x3E1730/0x3E1B78;
- DrawHelpMessage (help window): half-width x += 12 at 0x3D59F8; the original also
  advanced the string a second time there, skipping the byte after every half-width
  character (Japanese help text has none), which is dropped.

Changes (stage 1, still monospaced):
- entry 59 is rebuilt with 153 glyphs: codes 0x20-0x7E drawn by tools/latinfont.py
  (original font), 0xA6-0xDF copied from the disc;
- the new sorted code table and a 153-glyph buffer live in the English segment
  (tools/elfseg.py); SearchHalfNumber's table address and last index (0x8C -> 152),
  InitializeFont's read size and the five references to the old buffer are repointed.
"""
import struct

import latinfont
from asm import assemble, hi, lo

BASE, FOFF = 0x100000, 0x80
FONT_ENTRY = 59
GLYPH = 12 * 24 // 2                      # 144 bytes
OLD_TABLE, OLD_COUNT = 0x3FBAB0, 141
OLD_BUFF = 0x68FDA0                       # CFont::ms_abyHalfBuff
SEARCH_LAST = 0x3849F4                    # addiu a1, zero, 0x8C (last index of the search)
SEARCH_TABLE = [(0x384A10, 0x384A14, 'v1', 'v1'), (0x384A28, 0x384A2C, 'v1', 'v1')]
READ_SIZE = 0x384C44                      # addiu a2, zero, 0x4F50 (bRead length)
# lui/addiu pairs loading OLD_BUFF: (lui address, addiu address, lui reg, addiu rt)
BUFF_SITES = [(0x381468, 0x38146C), (0x382124, 0x382128), (0x383A04, 0x383A08),
              (0x383F00, 0x383F04), (0x384C38, 0x384C3C)]

CODES = list(range(0x20, 0x7F)) + list(range(0xA6, 0xE0))

def _off(va):
    return va - BASE + FOFF

def _word(elf, va):
    return struct.unpack_from('<I', elf, _off(va))[0]

def _put(elf, va, b):
    elf[_off(va):_off(va) + len(b)] = b

def _repoint(elf, lui, addiu, old, new):
    """Change a lui/addiu pair that loads old into one that loads new (same registers)."""
    wl, wa = _word(elf, lui), _word(elf, addiu)
    assert wl >> 26 == 0x0F and (wl & 0xFFFF) == hi(old), hex(lui)
    assert wa >> 26 == 0x09 and (wa & 0xFFFF) == lo(old) & 0xFFFF, hex(addiu)
    _put(elf, lui, struct.pack('<I', (wl & 0xFFFF0000) | hi(new)))
    _put(elf, addiu, struct.pack('<I', (wa & 0xFFFF0000) | (lo(new) & 0xFFFF)))

def old_codes(elf):
    return list(elf[_off(OLD_TABLE):_off(OLD_TABLE) + OLD_COUNT])

def build_font(old, elf):
    """old entry 59 -> new entry (one glyph per CODES entry)."""
    codes = old_codes(elf)
    assert len(old) == OLD_COUNT * GLYPH and codes == sorted(codes)
    glyphs = latinfont.render('large')
    out = bytearray()
    for code in CODES:
        if code < 0x80:
            rows = glyphs[chr(code)][0]
            g = bytearray(GLYPH)
            for y in range(24):
                for x in range(0, 12, 2):
                    g[(y * 12 + x) // 2] = rows[y][x] | rows[y][x + 1] << 4
        else:
            k = codes.index(code)
            g = old[k * GLYPH:(k + 1) * GLYPH]
        out += g
    return bytes(out)

def apply(elf, seg):
    """Patch the ELF; the table and buffer go into seg (elfseg.Segment)."""
    table = seg.add(bytes(CODES))
    buff = seg.reserve(len(CODES) * GLYPH, 16)
    assert _word(elf, SEARCH_LAST) == 0x2405008C
    _put(elf, SEARCH_LAST, assemble(SEARCH_LAST, [('addiu', 'a1', 'zero', len(CODES) - 1)]))
    for lui, addiu, _, _ in SEARCH_TABLE:
        _repoint(elf, lui, addiu, OLD_TABLE, table)
    assert _word(elf, READ_SIZE) == 0x24064F50
    _put(elf, READ_SIZE, assemble(READ_SIZE, [('addiu', 'a2', 'zero', len(CODES) * GLYPH)]))
    for lui, addiu in BUFF_SITES:
        _repoint(elf, lui, addiu, OLD_BUFF, buff)

# --- stage 2: proportional advance ----------------------------------------------
TEXT_WRAP = 0x38C834          # lbu a0,(s4); jal isKanji; nop; move a0,s1; movn a0,s2,v0
TEXT_ADV = 0x38CC80           # move v1,s1; movn v1,s2,s0
PUTS_ADV = 0x3831D0           # lw v1, 0x48(sp)
SIZE_LEN = 0x38CD90           # jal uiStrLen2
SIZE_MUL = 0x38CDC0           # mult a1, v1, a0
IS_KANJI, STRLEN2 = 0x385F80, 0x385C40
BIO_ADV = 0x21EF1C            # lw v1,0x438(sp); addiu v1,v1,11; sw v1,0x438(sp)
HELP_ADV = 0x3D59F8           # addiu s0,s0,1; lw v1,0x90(sp); addiu v1,v1,12; sw v1,0x90(sp)
STRLEN12 = [0x1A5E4C, 0x1E17E0, 0x1EB710, 0x1EB798, 0x1EB820, 0x21C840, 0x23D32C, 0x2579E4,
            0x257DB8, 0x258474, 0x258858, 0x258EAC, 0x2591AC, 0x2594CC, 0x259714, 0x2599BC,
            0x25A0B4, 0x25A3A4, 0x25A5DC, 0x25A7E4, 0x25AD1C, 0x25AF54, 0x25B14C, 0x25B5FC,
            0x2F0684, 0x3C8874, 0x3C9008, 0x3CBDA4, 0x3CC0B0, 0x3CC6B8, 0x3CCEB8, 0x3D27C8,
            0x3D379C, 0x3D3B48, 0x3D4634]
STRLEN = 0x385F30

def widths():
    adv = latinfont.render('large')
    return bytes(adv[chr(c)][1] for c in range(0x20, 0x7F))

def width_fn(org, table):
    return assemble(org, [
        ('andi', 'a0', 'a0', 0xFF),
        ('addiu', 'v1', 'a0', -0x20),
        ('sltiu', 'at', 'v1', 0x5F),
        ('beqz', 'at', 'other'),
        ('lui', 'v0', hi(table)),
        ('addu', 'v0', 'v0', 'v1'),
        ('lbu', 'v0', lo(table), 'v0'),
        ('addiu', 'at', 'zero', 12),
        ('beq', 'a1', 'at', 'ret'),
        ('nop',),
        ('mult', 'v0', 'v0', 'a1'),            # scaled: (w * half * 2731 + 0x4000) >> 15
        ('addiu', 'at', 'zero', 2731),
        ('mult', 'v0', 'v0', 'at'),
        ('addiu', 'v0', 'v0', 0x4000),
        ('sra', 'v0', 'v0', 15),
        'ret:',
        ('jr', 'ra'),
        ('nop',),
        'other:',                              # as isKanji: 0x81-0x9F, 0xE0-0xFC
        ('sltiu', 'at', 'a0', 0x81),
        ('bnez', 'at', 'half'),
        ('sltiu', 'at', 'a0', 0xA0),
        ('bnez', 'at', 'full'),
        ('sltiu', 'at', 'a0', 0xE0),
        ('bnez', 'at', 'half'),
        ('sltiu', 'at', 'a0', 0xFD),
        ('beqz', 'at', 'half'),
        ('nop',),
        'full:',
        ('jr', 'ra'),
        ('sll', 'v0', 'a1', 1),
        'half:',
        ('jr', 'ra'),
        ('addu', 'v0', 'a1', 'zero'),
    ])

def text_wrap(org, w):
    """strDrawText wrap test width (v0; the caller tests x + v0 > right edge and breaks
    the line there). Word wrap: a space never breaks (it may hang past the edge); the
    first character after a space returns the width of the whole word (up to a space,
    newline, end or kanji; ESC x y skipped; + positive area spacing per character), so a
    word that does not fit moves to the next line. A word wider than the area, and any
    other character, returns its own advance (as before: mid-word breaks)."""
    return assemble(org, [
        ('addu', 't9', 'ra', 'zero'),
        ('lbu', 'a0', 0, 's4'),
        ('jal', w),
        ('addu', 'a1', 's1', 'zero'),
        ('addu', 't5', 'v0', 'zero'),          # own advance
        ('addiu', 'at', 'zero', 0x20),
        ('lbu', 't8', 0, 's4'),
        ('beq', 't8', 'at', 'space'),
        ('lbu', 't8', -1, 's4'),
        ('bne', 't8', 'at', 'own'),            # not the start of a word
        ('addu', 't7', 's4', 'zero'),
        ('addu', 't6', 'zero', 'zero'),
        'loop:',
        ('lbu', 'a0', 0, 't7'),
        ('beqz', 'a0', 'done'),
        ('addiu', 'at', 'zero', 0x20),
        ('beq', 'a0', 'at', 'done'),
        ('addiu', 'at', 'zero', 0x0A),
        ('beq', 'a0', 'at', 'done'),
        ('addiu', 'at', 'zero', 0x1B),
        ('bne', 'a0', 'at', 'char'),
        ('nop',),
        ('b', 'loop'),
        ('addiu', 't7', 't7', 3),
        'char:',
        ('jal', w),
        ('addu', 'a1', 's1', 'zero'),
        ('sll', 'at', 's1', 1),
        ('beq', 'v0', 'at', 'done'),           # kanji: Japanese has no word spaces
        ('addu', 't6', 't6', 'v0'),
        ('lw', 'at', 0x18, 's5'),
        ('bgez', 'at', 'pos'),
        ('nop',),
        ('addu', 'at', 'zero', 'zero'),
        'pos:',
        ('addu', 't6', 't6', 'at'),
        ('b', 'loop'),
        ('addiu', 't7', 't7', 1),
        'done:',
        ('lw', 'at', 8, 's5'),                 # area width
        ('slt', 'at', 'at', 't6'),
        ('bnez', 'at', 'own'),                 # longer than a line: break inside it
        ('nop',),
        ('jr', 't9'),
        ('addu', 'v0', 't6', 'zero'),
        'space:',
        ('jr', 't9'),
        ('addu', 'v0', 'zero', 'zero'),
        'own:',
        ('jr', 't9'),
        ('addu', 'v0', 't5', 'zero'),
    ])

def text_adv(org, w):
    """strDrawText advance: v1 = s0 ? s2 : WIDTH(s4[-1], s1) - min(spacing, 0)."""
    return assemble(org, [
        ('bnez', 's0', 'kanji'),
        ('addu', 'v1', 's2', 'zero'),
        ('addu', 't9', 'ra', 'zero'),
        ('lbu', 'a0', -1, 's4'),
        ('jal', w),
        ('addu', 'a1', 's1', 'zero'),
        ('lw', 'at', 0x18, 's5'),              # the caller adds the area's spacing: a negative
        ('bgez', 'at', 'done'),                # one (edged labels: -1) is cancelled, the
        ('addu', 'v1', 'v0', 'zero'),          # proportional advance has its own gap
        ('subu', 'v1', 'v1', 'at'),
        'done:',
        ('jr', 't9'),
        ('nop',),
        'kanji:',
        ('jr', 'ra'),
        ('nop',),
    ])

def puts_adv(org, w):
    """bPuts: v1 = WIDTH(s0[-1], sp+0x48), + 1 for a single-byte glyph when the list (s2) is
    edged (CFontPrimList+0x3C mode 3/4: the outline closes 1-px gaps, 'Build' read 'Buld');
    v0 (loaded in the jal delay slot) kept."""
    return assemble(org, [
        ('addu', 't9', 'ra', 'zero'),
        ('addu', 't8', 'v0', 'zero'),
        ('lbu', 'a0', -1, 's0'),
        ('jal', w),
        ('lw', 'a1', 0x48, 'sp'),
        ('addu', 'v1', 'v0', 'zero'),
        ('lw', 'at', 0x48, 'sp'),
        ('sll', 'at', 'at', 1),
        ('beq', 'v1', 'at', 'done'),           # kanji
        ('lw', 'at', 0x3C, 's2'),
        ('sltu', 'at', 'zero', 'at'),
        ('addu', 'v1', 'v1', 'at'),
        'done:',
        ('jr', 't9'),
        ('addu', 'v0', 't8', 'zero'),
    ])

def text_size(org, w):
    """uiStrLen2 replacement inside ptGetTextSize (s1 = cell size, s0 = spacing):
    *a0 = line count, v0 = widest line in pixels including one spacing per column."""
    return assemble(org, [
        ('addiu', 'sp', 'sp', -0x10),
        ('sq', 'ra', 0, 'sp'),
        ('lw', 't2', 0, 's1'),
        ('sra', 't2', 't2', 1),                # half cell
        ('lw', 't3', 0, 's0'),                 # spacing
        ('sw', 'zero', 0, 'a0'),
        ('addu', 't1', 'a0', 'zero'),          # &lines
        ('addu', 't7', 'a1', 'zero'),          # string
        ('addu', 't4', 'zero', 'zero'),        # current line
        ('addu', 't5', 'zero', 'zero'),        # widest
        'loop:',
        ('lbu', 't0', 0, 't7'),
        ('beqz', 't0', 'end'),
        ('addiu', 't7', 't7', 1),
        ('addiu', 'at', 'zero', 0x0A),
        ('beq', 't0', 'at', 'newline'),
        ('addiu', 'at', 'zero', 0x1B),
        ('beq', 't0', 'at', 'loop'),
        ('addiu', 't7', 't7', 2),              # (only kept for ESC)
        ('addiu', 't7', 't7', -2),
        ('addiu', 'at', 'zero', 0x0D),
        ('bne', 't0', 'at', 'char'),
        ('lbu', 't0', 0, 't7'),
        ('addiu', 'at', 'zero', 0x0A),         # CR LF counts once
        ('bne', 't0', 'at', 'newline'),
        ('nop',),
        ('b', 'newline'),
        ('addiu', 't7', 't7', 1),
        'char:',
        ('lbu', 'a0', -1, 't7'),
        ('jal', w),
        ('addu', 'a1', 't2', 'zero'),
        ('addu', 't4', 't4', 'v0'),
        ('sll', 'at', 't2', 1),
        ('bne', 'v0', 'at', 'half'),
        ('addu', 't4', 't4', 't3'),
        ('lbu', 'at', 0, 't7'),                # kanji: skip the trail byte, 2 columns
        ('beqz', 'at', 'loop'),
        ('addu', 't4', 't4', 't3'),
        ('b', 'loop'),
        ('addiu', 't7', 't7', 1),
        'half:',                               # single byte: negative spacing cancelled
        ('bgez', 't3', 'loop'),                # (as in text_adv)
        ('nop',),
        ('b', 'loop'),
        ('subu', 't4', 't4', 't3'),
        'newline:',
        ('slt', 'at', 't5', 't4'),
        ('movn', 't5', 't4', 'at'),
        ('lw', 'at', 0, 't1'),
        ('addiu', 'at', 'at', 1),
        ('sw', 'at', 0, 't1'),
        ('b', 'loop'),
        ('addu', 't4', 'zero', 'zero'),
        'end:',
        ('slt', 'at', 't5', 't4'),
        ('movn', 't5', 't4', 'at'),
        ('beqz', 't4', 'out'),
        ('lw', 'at', 0, 't1'),
        ('addiu', 'at', 'at', 1),
        ('sw', 'at', 0, 't1'),
        'out:',
        ('addu', 'v0', 't5', 'zero'),
        ('lq', 'ra', 0, 'sp'),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 0x10),
    ])

def str_px(org, w):
    """v0 = pixel width of the string a0 at half cell 12 (one line, no spacing)."""
    return assemble(org, [
        ('addu', 't9', 'ra', 'zero'),
        ('addu', 't7', 'a0', 'zero'),
        ('addu', 't4', 'zero', 'zero'),
        'loop:',
        ('lbu', 'a0', 0, 't7'),
        ('beqz', 'a0', 'end'),
        ('addiu', 't7', 't7', 1),
        ('jal', w),
        ('addiu', 'a1', 'zero', 12),
        ('addu', 't4', 't4', 'v0'),
        ('addiu', 'at', 'zero', 24),
        ('bne', 'v0', 'at', 'loop'),
        ('lbu', 'at', 0, 't7'),                # kanji: skip the trail byte
        ('beqz', 'at', 'loop'),
        ('nop',),
        ('b', 'loop'),
        ('addiu', 't7', 't7', 1),
        'end:',
        ('jr', 't9'),
        ('addu', 'v0', 't4', 'zero'),
    ])

def slot_adv(org, w, ptr, half, slot):
    """x at slot(sp) of the caller += WIDTH(ptr[-1], half)."""
    return assemble(org, [
        ('addu', 't9', 'ra', 'zero'),
        ('lbu', 'a0', -1, ptr),
        ('jal', w),
        ('addiu', 'a1', 'zero', half),
        ('lw', 'v1', slot, 'sp'),
        ('addu', 'v1', 'v1', 'v0'),
        ('jr', 't9'),
        ('sw', 'v1', slot, 'sp'),
    ])

def _fn(seg, make, *args):
    n = len(make(0x100000, *args))
    addr = seg.reserve(n, 8)
    seg.put(addr, make(addr, *args))
    return addr

def apply_vwf(elf, seg):
    table = seg.add(widths())
    w = _fn(seg, width_fn, table)
    assert _word(elf, TEXT_WRAP + 4) == 0x0C000000 | IS_KANJI >> 2
    _put(elf, TEXT_WRAP, assemble(TEXT_WRAP, [
        ('jal', _fn(seg, text_wrap, w)), ('nop',),
        ('addu', 'a0', 'v0', 'zero'), ('nop',), ('nop',)]))
    assert _word(elf, TEXT_ADV + 4) == 0x0250180B, 'movn v1, s2, s0'
    _put(elf, TEXT_ADV, assemble(TEXT_ADV, [('jal', _fn(seg, text_adv, w)), ('nop',)]))
    assert _word(elf, PUTS_ADV) == 0x8FA30048
    _put(elf, PUTS_ADV, assemble(PUTS_ADV, [('jal', _fn(seg, puts_adv, w))]))
    assert _word(elf, SIZE_LEN) == 0x0C000000 | STRLEN2 >> 2
    _put(elf, SIZE_LEN, assemble(SIZE_LEN, [('jal', _fn(seg, text_size, w))]))
    assert _word(elf, SIZE_MUL) == 0x00642818, 'mult a1, v1, a0'
    _put(elf, SIZE_MUL, assemble(SIZE_MUL, [('addu', 'a1', 'v1', 'zero')]))
    assert _word(elf, BIO_ADV) == 0x8FA30438 and _word(elf, BIO_ADV + 4) == 0x2463000B
    _put(elf, BIO_ADV, assemble(BIO_ADV, [
        ('jal', _fn(seg, slot_adv, w, 's0', 11, 0x438)), ('nop',), ('nop',)]))
    px = _fn(seg, str_px, w)
    for va in STRLEN12:
        j, ds, a, b, c = (_word(elf, va + 4 * k) for k in range(5))
        assert j == 0x0C000000 | STRLEN >> 2 and a == 0x00021840, hex(va)        # sll v1,v0,1
        assert b in (0x00621021, 0x00621821), hex(va)                             # addu x,v1,v0
        x = (b >> 11) & 31
        assert (c & 0xFFFF07FF) == (x << 16 | 0x80), hex(va)                    # sll R,x,2
        r = (c >> 11) & 31
        _put(elf, va, assemble(va, [('jal', px), ('nop',)]))
        _put(elf, va + 4, struct.pack('<I', ds))
        _put(elf, va + 8, struct.pack('<III', 0x00400021 | r << 11, 0, 0))       # addu R,v0,zero
    assert _word(elf, HELP_ADV) == 0x26100001 and _word(elf, HELP_ADV + 8) == 0x2463000C
    _put(elf, HELP_ADV, assemble(HELP_ADV, [
        ('jal', _fn(seg, slot_adv, w, 's0', 12, 0x90)), ('nop',), ('nop',), ('nop',)]))
