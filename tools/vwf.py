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
  (STR_PX = pixel width at half cell 12, kanji 24: identical for Japanese text). Also
  patched the same way (other arithmetic, STRLEN12_OTHER): DrawCheckMessage 0x3D54D0,
  CEnvironmentWin 0x3E1730/0x3E1B78;
- CPersonButton::DrawName (castle-room nameplate, top right, font 20; the visible box is
  x 2-138 of its area): x was (14 - strlen) x 10 + 6 -> right-aligned at 138; names wider
  than 136 px (Hatakeyama Yoshitsugu...) get a narrower font width; the glyph array
  (15) holds 24; DrawName and the inline copy in Create both patched (NAMEPLATE);
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
HELP_CELL = 0x3D59CC          # addiu v0,zero,24: cell width of a half-width glyph (-> 12)
STRLEN12 = [0x1A5E4C, 0x1E17E0, 0x1EB710, 0x1EB798, 0x1EB820, 0x21C840, 0x23D32C, 0x2579E4,
            0x257DB8, 0x258474, 0x258858, 0x258EAC, 0x2591AC, 0x2594CC, 0x259714, 0x2599BC,
            0x25A0B4, 0x25A3A4, 0x25A5DC, 0x25A7E4, 0x25AD1C, 0x25AF54, 0x25B14C, 0x25B5FC,
            0x2F0684, 0x3C8874, 0x3C9008, 0x3CBDA4, 0x3CC0B0, 0x3CC6B8, 0x3CCEB8, 0x3D27C8,
            0x3D379C, 0x3D3B48, 0x3D4634]
STRLEN = 0x385F30
# (jal uiStrLen .. addiu v0,v0,6 (8 words, then sw v0,0x98(sp)), addiu v0,zero,0x14 (font
# width, sw v0,0x7c(s1)), free stack slot) in DrawName and in Create's inline copy
# other strlen x 12 measures: (jal uiStrLen, [(address, old word, new word)]) -> x = STR_PX
STRLEN12_OTHER = [
    (0x3D54D0, [(0x3D54DC, 0x00021840, 0), (0x3D54E0, 0x00621021, 0),      # DrawCheckMessage:
                (0x3D54E4, 0x00021080, 0)]),                              # centred at 640
    (0x3E1730, [(0x3E1748, 0x00021840, 0), (0x3E174C, 0x00621021, 0),      # CEnvironmentWin::
                (0x3E1750, 0x00023880, 0x00403821)]),                     # CreateTitleButton
    (0x3E1B78, [(0x3E1B90, 0x00021840, 0), (0x3E1B94, 0x00621021, 0),      # CEnvironmentWin::Open
                (0x3E1B98, 0x00023880, 0x00403821)]),
]
NAMEPLATE = [(0x1CF884, 0x1CF920, 0x60), (0x1CFB70, 0x1CFC0C, 0xD0)]
NAMEPLATE_GLYPHS = 0x1CFA7C   # addiu a1,zero,15: bCreateFontArray (heap) -> 24

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
    word that does not fit moves to the next line. A word that starts with a digit takes
    the following lower-case word with it (number + unit: "9.4 kan", "15 days"). A word
    wider than the area, and any other character, returns its own advance (as before:
    mid-word breaks)."""
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
        ('lbu', 't8', 0, 's4'),                # t8 = 1: the word is a number, glue the
        ('addiu', 't8', 't8', -0x30),          # next word if it is lower case ("9.4 kan")
        ('sltiu', 't8', 't8', 10),
        ('addu', 't6', 'zero', 'zero'),
        'loop:',
        ('lbu', 'a0', 0, 't7'),
        ('beqz', 'a0', 'done'),
        ('addiu', 'at', 'zero', 0x20),
        ('beq', 'a0', 'at', 'sp'),
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
        'sp:',
        ('beqz', 't8', 'done'),
        ('lbu', 'at', 1, 't7'),
        ('addiu', 'at', 'at', -0x61),
        ('sltiu', 'at', 'at', 26),
        ('beqz', 'at', 'done'),
        ('addu', 't8', 'zero', 'zero'),        # once
        ('b', 'char'),
        ('nop',),
        'done:',
        ('lw', 'at', 8, 's5'),                 # area width
        ('slt', 'at', 'at', 't6'),
        ('bnez', 'at', 'own'),                 # longer than a line: break inside it
        ('nop',),
        ('jr', 't9'),
        ('addu', 'v0', 't6', 'zero'),
        'space:',                              # never breaks: the advance adds the area
        ('jr', 't9'),                          # spacing the test leaves out, so x can sit
        ('addiu', 'v0', 'zero', -0x4000),      # 1 px past the edge (" much" on a new line)
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

def nameplate_x(org, px, slot):
    """v0 = x of the right-aligned name a0 in CPersonButton::DrawName (visible box x 2-138);
    font width -> slot(sp) of the caller (an unused slot of its frame): 20, or
    2720 / width20 for names wider than 136 px (17 for the widest)."""
    return assemble(org, [
        ('addu', 't8', 'ra', 'zero'),
        ('jal', px),
        ('nop',),
        ('addiu', 'at', 'zero', 10),             # w = p x 10/12 (width at font 20)
        ('mult', 'v0', 'v0', 'at'),
        ('addiu', 'at', 'zero', 2731),
        ('mult', 'v0', 'v0', 'at'),
        ('addiu', 'v0', 'v0', 0x4000),
        ('sra', 'v0', 'v0', 15),
        ('slti', 'at', 'v0', 137),
        ('bnez', 'at', 'out'),
        ('addiu', 'v1', 'zero', 20),
        ('addiu', 'at', 'zero', 2720),           # size = 2720 / w, width = w x size / 20
        ('div', 'at', 'v0'),
        ('mflo', 'v1'),
        ('mult', 'v0', 'v0', 'v1'),
        ('addiu', 'at', 'zero', 20),
        ('div', 'v0', 'at'),
        ('mflo', 'v0'),
        'out:',
        ('sw', 'v1', slot, 'sp'),
        ('addiu', 'at', 'zero', 138),
        ('subu', 'v0', 'at', 'v0'),
        ('slti', 'at', 'v0', 2),
        ('addiu', 'v1', 'zero', 2),
        ('jr', 't8'),
        ('movn', 'v0', 'v1', 'at'),
    ])

CARD_PUTS = 0x191068    # CCardSprList::Create: jal bPuts (card name, list mode 6: +1 px/glyph)
PUTS = 0x382FD0
CARD_W, CARD_NAME_Y = 0x405210, 0x405254   # SIZE_CARD_GRP.w, POS_CARD_NAME.y (set at runtime)

def card_name(org, px):
    """Card name under the picture (card album, card lists): bPuts(a0 list, a1 name, a2 pt)
    replaced. The game centred strlen x size/2 (size 20, 16 from 11 bytes). Now: one line
    at size 20 if it fits the card width - 4; else two lines split at the most balanced
    space (family / given name) at size min(14, fit), centred on the old line; no space:
    one line shrunk to fit. Width = pixels at half 12 x size / 12 + 1 per byte (mode 6)."""
    def width(p_slot, n_slot, out):          # out = p * s4 / 12 + n
        return [('lw', out, p_slot, 'sp'), ('mult', out, out, 's4'), ('addiu', 'at', 'zero', 12),
                ('div', out, 'at'), ('mflo', out), ('lw', 't0', n_slot, 'sp'), ('addu', out, out, 't0')]
    def fit(p_slot, n_slot):                 # s4 = min(s4, (W - 4 - n) * 12 / p)
        return [('lw', 't0', n_slot, 'sp'), ('addiu', 't2', 's3', -4), ('subu', 't2', 't2', 't0'),
                ('addiu', 'at', 'zero', 12), ('mult', 't2', 't2', 'at'), ('lw', 't4', p_slot, 'sp'),
                ('div', 't2', 't4'), ('mflo', 't2'), ('slt', 'at', 't2', 's4'), ('movn', 's4', 't2', 'at')]
    def centre(reg):                         # pt.x = (W - reg) / 2
        return [('subu', reg, 's3', reg), ('sra', reg, reg, 1), ('sw', reg, 0, 's2')]
    def puts(name):
        return [('sw', 's4', 0x34, 's0'), ('sw', 's4', 0x38, 's0'), ('addu', 'a0', 's0', 'zero'),
                name, ('jal', PUTS), ('addu', 'a2', 's2', 'zero')]
    return assemble(org, [
        ('addiu', 'sp', 'sp', -0x80),
        ('sq', 'ra', 0x50, 'sp'), ('sq', 's0', 0, 'sp'), ('sq', 's1', 0x10, 'sp'),
        ('sq', 's2', 0x20, 'sp'), ('sq', 's3', 0x30, 'sp'), ('sq', 's4', 0x40, 'sp'),
        ('addu', 's0', 'a0', 'zero'), ('addu', 's1', 'a1', 'zero'), ('addu', 's2', 'a2', 'zero'),
        ('jal', STRLEN), ('addu', 'a0', 's1', 'zero'),
        ('sw', 'v0', 0x60, 'sp'),                                    # n
        ('jal', px), ('addu', 'a0', 's1', 'zero'),
        ('sw', 'v0', 0x68, 'sp'),                                    # p
        ('lui', 'at', 0x40), ('lw', 's3', CARD_W & 0xFFFF, 'at'),     # W
        ('addiu', 's4', 'zero', 20)]
        + width(0x68, 0x60, 't1') + [
        ('addiu', 't2', 's3', -4),
        ('slt', 'at', 't2', 't1'),
        ('bnez', 'at', 'long'),
        ('nop',)]
        + centre('t1') + [
        ('lui', 'at', 0x40), ('lw', 't1', CARD_NAME_Y & 0xFFFF, 'at'), ('sw', 't1', 4, 's2')]
        + puts(('addu', 'a1', 's1', 'zero')) + [
        ('b', 'out'),
        ('nop',),
        'long:',                                                     # most balanced space
        ('lw', 'v0', 0x60, 'sp'),
        ('addiu', 't5', 'zero', 0x7FFF),
        ('addu', 't3', 'zero', 'zero'),
        ('addu', 't7', 's1', 'zero'),
        'scan:',
        ('lbu', 't6', 0, 't7'),
        ('beqz', 't6', 'scanned'),
        ('addiu', 'at', 'zero', 0x20),
        ('bne', 't6', 'at', 'next'),
        ('subu', 't8', 't7', 's1'),                                  # |2 i - (n - 1)|
        ('sll', 't8', 't8', 1),
        ('subu', 't8', 't8', 'v0'),
        ('addiu', 't8', 't8', 1),
        ('bgez', 't8', 'abs'),
        ('nop',),
        ('subu', 't8', 'zero', 't8'),
        'abs:',
        ('slt', 'at', 't8', 't5'),
        ('beqz', 'at', 'next'),
        ('nop',),
        ('addu', 't5', 't8', 'zero'),
        ('addu', 't3', 't7', 'zero'),
        'next:',
        ('b', 'scan'),
        ('addiu', 't7', 't7', 1),
        'scanned:',
        ('bnez', 't3', 'split'),
        ('sw', 't3', 0x64, 'sp')]
        + fit(0x68, 0x60) + width(0x68, 0x60, 't1') + centre('t1') + [   # one word: shrink
        ('lui', 'at', 0x40), ('lw', 't1', CARD_NAME_Y & 0xFFFF, 'at'),
        ('addiu', 't2', 'zero', 20), ('subu', 't2', 't2', 's4'), ('sra', 't2', 't2', 1),
        ('addu', 't1', 't1', 't2'), ('sw', 't1', 4, 's2')]
        + puts(('addu', 'a1', 's1', 'zero')) + [
        ('b', 'out'),
        ('nop',),
        'split:',
        ('sb', 'zero', 0, 't3'),
        ('jal', px), ('addu', 'a0', 's1', 'zero'),
        ('sw', 'v0', 0x6C, 'sp'),                                    # p1
        ('lw', 'a0', 0x64, 'sp'),
        ('jal', px), ('addiu', 'a0', 'a0', 1),
        ('sw', 'v0', 0x70, 'sp'),                                    # p2
        ('lw', 't3', 0x64, 'sp'), ('subu', 't0', 't3', 's1'), ('sw', 't0', 0x74, 'sp'),   # n1
        ('lw', 't1', 0x60, 'sp'), ('subu', 't1', 't1', 't0'), ('addiu', 't1', 't1', -1),
        ('sw', 't1', 0x78, 'sp'),                                    # n2
        ('addiu', 's4', 'zero', 14)]
        + fit(0x6C, 0x74) + fit(0x70, 0x78)
        + width(0x6C, 0x74, 't1') + centre('t1') + [
        ('lui', 'at', 0x40), ('lw', 't1', CARD_NAME_Y & 0xFFFF, 'at'),
        ('addiu', 't1', 't1', 10), ('subu', 't1', 't1', 's4'), ('sw', 't1', 4, 's2')]
        + puts(('addu', 'a1', 's1', 'zero'))
        + width(0x70, 0x78, 't1') + centre('t1') + [
        ('lw', 't1', 4, 's2'), ('addu', 't1', 't1', 's4'), ('sw', 't1', 4, 's2'),
        ('lw', 'a1', 0x64, 'sp')]
        + puts(('addiu', 'a1', 'a1', 1)) + [
        ('lw', 't3', 0x64, 'sp'), ('addiu', 'at', 'zero', 0x20), ('sb', 'at', 0, 't3'),
        'out:',
        ('lq', 'ra', 0x50, 'sp'), ('lq', 's0', 0, 'sp'), ('lq', 's1', 0x10, 'sp'),
        ('lq', 's2', 0x20, 'sp'), ('lq', 's3', 0x30, 'sp'), ('lq', 's4', 0x40, 'sp'),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 0x80),
    ])

# save/load file list (CFileButtonSpr::DrawView): the hero's name box drew "%s%s" of the save
# header's family[12] (+0x28) and given[8] (+0x34) at x = (14 - strlen) x 6 + 24 (unsigned:
# English names over 14 bytes went off-screen; the given name also overflowed into the lord
# name at +0x3C). SetScenarioData now writes "Family Given" into the zeroed header reserve
# at +0x60 (no given copy at +0x34); DrawView centres that by pixels (older saves: family).
SAVE_GIVEN = 0x1EBB4C          # addiu a0,s1,0x34; jal szStrCpy (a1 = person record + 18)
SAVE_DRAW = 0x1EB69C           # lw v0,8(s0) .. x for DrawFormatTextXY 0x1EB700
SAVE_NAME = 0x60

def save_name(org):
    """a0 = save header, a1 = given name (person record + 18): header+0x60 = family + ' ' + given."""
    return assemble(org, [
        ('addiu', 'a0', 'a0', SAVE_NAME),
        ('addiu', 't0', 'a1', -18),
        'fam:',
        ('lbu', 'at', 0, 't0'),
        ('beqz', 'at', 'sep'),
        ('addiu', 't0', 't0', 1),
        ('sb', 'at', 0, 'a0'),
        ('b', 'fam'),
        ('addiu', 'a0', 'a0', 1),
        'sep:',
        ('addiu', 'at', 'zero', 0x20),
        ('sb', 'at', 0, 'a0'),
        ('addiu', 'a0', 'a0', 1),
        'giv:',
        ('lbu', 'at', 0, 'a1'),
        ('sb', 'at', 0, 'a0'),
        ('addiu', 'a1', 'a1', 1),
        ('bnez', 'at', 'giv'),
        ('addiu', 'a0', 'a0', 1),
        ('jr', 'ra'),
        ('nop',),
    ])

def save_name_x(org, px):
    """a0 = save header: v1 = name (+0x60, or family +0x28 in older saves), v0 = x centred
    in the 168-px box at 24."""
    return assemble(org, [
        ('addiu', 'sp', 'sp', -0x20),
        ('sw', 'ra', 0x10, 'sp'),
        ('addiu', 't8', 'a0', SAVE_NAME),
        ('lbu', 'at', 0, 't8'),
        ('bnez', 'at', 'ok'),
        ('nop',),
        ('addiu', 't8', 'a0', 0x28),
        'ok:',
        ('sw', 't8', 0x14, 'sp'),
        ('jal', px),
        ('addu', 'a0', 't8', 'zero'),
        ('addiu', 'at', 'zero', 168),
        ('subu', 'v0', 'at', 'v0'),
        ('sra', 'v0', 'v0', 1),
        ('addiu', 'v0', 'v0', 24),
        ('lw', 'v1', 0x14, 'sp'),
        ('lw', 'ra', 0x10, 'sp'),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 0x20),
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
    for va, words in STRLEN12_OTHER:
        assert _word(elf, va) == 0x0C000000 | STRLEN >> 2, hex(va)
        _put(elf, va, assemble(va, [('jal', px)]))
        for a, old, new in words:
            assert _word(elf, a) == old, hex(a)
            _put(elf, a, struct.pack('<I', new))
    for va, size, slot in NAMEPLATE:
        assert _word(elf, va) == 0x0C000000 | STRLEN >> 2
        assert _word(elf, va + 28) == 0x24420006 and _word(elf, va + 32) == 0xAFA20098
        _put(elf, va, assemble(va, [('jal', _fn(seg, nameplate_x, px, slot)), ('nop',)]
                               + [('nop',)] * 6))
        assert _word(elf, size) == 0x24020014
        _put(elf, size, assemble(size, [('lw', 'v0', slot, 'sp')]))
    assert _word(elf, CARD_PUTS) == 0x0C000000 | PUTS >> 2
    _put(elf, CARD_PUTS, assemble(CARD_PUTS, [('jal', _fn(seg, card_name, px))]))
    assert _word(elf, SAVE_GIVEN) == 0x26240034 and _word(elf, SAVE_GIVEN + 4) == 0x0C000000 | 0x385EF0 >> 2
    _put(elf, SAVE_GIVEN, assemble(SAVE_GIVEN, [('addu', 'a0', 's1', 'zero'), ('jal', _fn(seg, save_name))]))
    assert _word(elf, SAVE_DRAW) == 0x8E020008 and _word(elf, SAVE_DRAW + 0x4C) == 0x27A40050
    assert _word(elf, SAVE_DRAW + 0x5C) == 0x25080028 and _word(elf, SAVE_DRAW + 0x60) == 0x24690034
    _put(elf, SAVE_DRAW, assemble(SAVE_DRAW, [
        ('lw', 'a0', 8, 's0'), ('jal', _fn(seg, save_name_x, px)), ('nop',),
        ('addu', 'a1', 'v0', 'zero'), ('addu', 't0', 'v1', 'zero'),
        ('lw', 't1', 8, 's0'), ('addiu', 't1', 't1', 0x9F)]          # a zero byte: "%s%s" second %s
        + [('nop',)] * 12))
    _put(elf, SAVE_DRAW + 0x5C, assemble(SAVE_DRAW + 0x5C, [('nop',), ('nop',)]))
    assert _word(elf, NAMEPLATE_GLYPHS) == 0x2405000F
    _put(elf, NAMEPLATE_GLYPHS, assemble(NAMEPLATE_GLYPHS, [('addiu', 'a1', 'zero', 24)]))
    assert _word(elf, HELP_ADV) == 0x26100001 and _word(elf, HELP_ADV + 8) == 0x2463000C
    _put(elf, HELP_ADV, assemble(HELP_ADV, [
        ('jal', _fn(seg, slot_adv, w, 's0', 12, 0x90)), ('nop',), ('nop',), ('nop',)]))
    assert _word(elf, HELP_CELL) == 0x24020018
    _put(elf, HELP_CELL, assemble(HELP_CELL, [('addiu', 'v0', 'zero', 12)]))
