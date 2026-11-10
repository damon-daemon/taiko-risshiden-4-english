"""Sentence case for expanded messages.

Messages insert shared phrases from msg00/msg01 ({01}C / {01}J: vocatives and references
such as "our lord", "that fellow", "you"). They are written in lower case because most uses
are mid-sentence, but about 400 units start a sentence with one ("{01}C+{00}, that's the best
course." -> "our lord, that's..."). Japanese has no case, so the game never cared.

CMessageManager::strDoMessage 0x254CD0 expands a message (inserts and variables included)
into its output buffer and returns it (this+0x10414); every message the game shows goes
through it (781 calls via CTK4MessageManager::strDoMessage). The patch passes that buffer
through CAP before returning it. CAP upper-cases an ASCII letter at a sentence start:
- after '.', '!' or '?' (not an ellipsis: a '.' after a '.' cancels it), across spaces,
  newlines, quotes and other punctuation;
- at the start of the buffer only if the message contains '.', '!' or '?' somewhere: the
  bare fragments callers paste into their own text ("the likes of", "our lord") never do;
- '%' (a printf field filled in later, e.g. "%s") and digits end the sentence start, so a
  conversion letter is never touched; ESC x y is skipped, Shift-JIS and kana end it;
- the macron glyphs in spare ASCII codes (latinfont.MACRONS) are letters: ^ ` (o/u-macron)
  become | _ (O/U-macron) at a sentence start ("ŌTani" before this).
Event text (scripts in TR4DATA 61) is expanded by CEventEnvironment::NewExtractMessage
0x1ADAD0 (its \\% escapes insert the same msg00 phrases): its epilogue passes the result
through CAP as well.

PLURAL (called at CAP's end and after Sprintf / VSprintf 0x387090 / 0x387120) drops the
's' of a counted noun after a lone 1: "1 days" -> "1 day" ("{02}$d days", "%2d days left").
The 1 must not follow a digit, ',' or '.' and must be followed by a space and one of the
stems in PLURAL_STEMS + 's' + a non-lower-case byte.
"""
import struct

from asm import assemble, hi, lo

BASE, FOFF = 0x100000, 0x80
RET = 0x254D28      # lui at,1; addu at,s0,at; lw v0,0x414(at); lq ra,16(sp); lq s0,0(sp);
                    # addiu sp,sp,0x20; jr ra; nop
ORIG = [0x3C010001, 0x02010821, 0x8C220414, 0x7BBF0010, 0x7BB00000, 0x27BD0020,
        0x03E00008, 0x00000000]

EV_RET = 0x1ADB84   # lq ra,64 / s3,48 / s2,32 / s1,16 / s0,0(sp); addiu sp,0x50; jr ra; nop
                    # then 3 nops of padding before NewExtractMessageCore 0x1ADBB0
EV_ORIG = [0x7BBF0040, 0x7BB30030, 0x7BB20020, 0x7BB10010, 0x7BB00000, 0x27BD0050,
           0x03E00008, 0, 0, 0, 0]

PLURAL_STEMS = ['day', 'night', 'gun', 'horse', 'time', 'coin', 'month', 'year', 'turn',
                'card', 'point', 'bale', 'officer', 'castle', 'troop', 'chip', 'unit', 'ship',
                'piece', 'round', 'win']

SPRINTF_VA = 0x3870B4   # Sprintf: constant va_list offset code (v1 = 6 * 8), 11 words
SPRINTF_RET = 0x387100  # lw v1,-0x7b48(gp); sb zero,0(v1); lq ra; addiu sp,0x60; jr ra; nop x3
VSPRINTF = 0x387120     # whole function, 16 words up to input_buffer 0x387160
SPRINTF_ORIG = {SPRINTF_VA: [0x24020002, 0x28420008, 0x14400004, 0, 0x70001E28, 0x10000005, 0,
                             0x24030002, 0x24020008, 0x00431023, 0x000218C0],
                SPRINTF_RET: [0x8F8384B8, 0xA0600000, 0x7BBF0000, 0x27BD0060, 0x03E00008, 0, 0, 0],
                VSPRINTF: [0x27BDFFF0, 0x7FBF0000, 0xAF8484B8, 0x3C020038, 0x24447160, 0x0C0E1C60,
                           0, 0x8F8384B8, 0xA0600000, 0x7BBF0000, 0x27BD0010, 0x03E00008, 0, 0, 0, 0]}

def _word(elf, va):
    return struct.unpack_from('<I', elf, va - BASE + FOFF)[0]

def _put(elf, va, b):
    elf[va - BASE + FOFF:va - BASE + FOFF + len(b)] = b

def cap_fn(org, plural):
    """CAP(a0 = string) -> v0 = a0. Leaf; uses t0-t4, at."""
    c = ord
    return assemble(org, [
        ('addu', 'v0', 'a0', 'zero'),
        ('addu', 't3', 'a0', 'zero'),
        ('addu', 't1', 'zero', 'zero'),        # sentence start at the top only if there is
        'scan:',                               # an end mark somewhere
        ('lbu', 't4', 0, 't3'),
        ('beqz', 't4', 'go'),
        ('addiu', 't3', 't3', 1),
        ('addiu', 'at', 'zero', c('.')),
        ('beq', 't4', 'at', 'has'),
        ('addiu', 'at', 'zero', c('!')),
        ('beq', 't4', 'at', 'has'),
        ('addiu', 'at', 'zero', c('?')),
        ('bne', 't4', 'at', 'scan'),
        ('nop',),
        'has:',
        ('addiu', 't1', 'zero', 1),
        'go:',
        ('addu', 't0', 'a0', 'zero'),
        ('addu', 't2', 'zero', 'zero'),        # previous byte
        'loop:',
        ('lbu', 't4', 0, 't0'),
        ('beqz', 't4', 'end'),
        ('nop',),
        ('addiu', 'at', 'zero', 0x1B),
        ('bne', 't4', 'at', 'notesc'),
        ('nop',),
        ('b', 'loop'),
        ('addiu', 't0', 't0', 3),
        'notesc:',
        ('sltiu', 'at', 't4', 0x80),
        ('bnez', 'at', 'ascii'),
        ('nop',),
        ('addu', 't1', 'zero', 'zero'),        # Japanese ends it
        ('sltiu', 'at', 't4', 0xA0),           # Shift-JIS lead 0x81-0x9F, 0xE0-0xFC: 2 bytes
        ('bnez', 'at', 'two'),
        ('nop',),
        ('sltiu', 'at', 't4', 0xE0),
        ('bnez', 'at', 'next'),                # half-width kana
        ('nop',),
        'two:',
        ('b', 'next'),
        ('addiu', 't0', 't0', 1),
        'ascii:',
        ('addiu', 'at', 't4', -c('a')),
        ('sltiu', 'at', 'at', 26),
        ('beqz', 'at', 'notlow'),
        ('nop',),
        ('beqz', 't1', 'clear'),
        ('nop',),
        ('addiu', 't4', 't4', -0x20),
        ('sb', 't4', 0, 't0'),
        'clear:',
        ('b', 'next'),
        ('addu', 't1', 'zero', 'zero'),
        'notlow:',                             # macron glyphs (latinfont.MACRONS) are letters:
        ('addiu', 'at', 'zero', c('^')),       # o-macron -> O-macron, u-macron -> U-macron
        ('beq', 't4', 'at', 'macron'),
        ('addiu', 't3', 'zero', c('|')),
        ('addiu', 'at', 'zero', c('`')),
        ('beq', 't4', 'at', 'macron'),
        ('addiu', 't3', 'zero', c('_')),
        ('addiu', 'at', 'zero', c('|')),
        ('beq', 't4', 'at', 'clear'),
        ('addiu', 'at', 'zero', c('_')),
        ('beq', 't4', 'at', 'clear'),
        ('addiu', 'at', 't4', -c('A')),
        ('sltiu', 'at', 'at', 26),
        ('bnez', 'at', 'clear'),
        ('addiu', 'at', 't4', -c('0')),
        ('sltiu', 'at', 'at', 10),
        ('bnez', 'at', 'clear'),
        ('addiu', 'at', 'zero', c('%')),
        ('beq', 't4', 'at', 'clear'),
        ('addiu', 'at', 'zero', c('.')),
        ('bne', 't4', 'at', 'excl'),
        ('nop',),
        ('beq', 't2', 'at', 'clear'),          # ellipsis
        ('nop',),
        ('b', 'next'),
        ('addiu', 't1', 'zero', 1),
        'excl:',
        ('addiu', 'at', 'zero', c('!')),
        ('beq', 't4', 'at', 'set'),
        ('addiu', 'at', 'zero', c('?')),
        ('bne', 't4', 'at', 'next'),
        ('nop',),
        'set:',
        ('b', 'next'),
        ('addiu', 't1', 'zero', 1),
        'macron:',                             # t3 = the capital's code
        ('beqz', 't1', 'clear'),
        ('nop',),
        ('b', 'clear'),
        ('sb', 't3', 0, 't0'),
        'next:',
        ('addu', 't2', 't4', 'zero'),
        ('b', 'loop'),
        ('addiu', 't0', 't0', 1),
        'end:',
        ('j', plural),
        ('nop',),
    ])

def plural_fn(org, table):
    """PLURAL(a0 = string): see the module docstring. Leaf; uses t0-t7, at; keeps v0."""
    c = ord
    return assemble(org, [
        ('addu', 't0', 'a0', 'zero'),
        ('addu', 't2', 'zero', 'zero'),        # previous byte
        'loop:',
        ('lbu', 't4', 0, 't0'),
        ('beqz', 't4', 'done'),
        ('addiu', 'at', 'zero', 0x1B),
        ('bne', 't4', 'at', 'notesc'),
        ('nop',),
        ('b', 'loop'),
        ('addiu', 't0', 't0', 3),
        'notesc:',
        ('addiu', 'at', 'zero', c('1')),
        ('bne', 't4', 'at', 'next'),
        ('addiu', 'at', 't2', -c('0')),
        ('sltiu', 'at', 'at', 10),
        ('bnez', 'at', 'next'),
        ('addiu', 'at', 'zero', c(',')),
        ('beq', 't2', 'at', 'next'),
        ('addiu', 'at', 'zero', c('.')),
        ('beq', 't2', 'at', 'next'),
        ('lbu', 'at', 1, 't0'),
        ('addiu', 't5', 'zero', c(' ')),
        ('bne', 'at', 't5', 'next'),
        ('lui', 't6', hi(table)),
        ('addiu', 't6', 't6', lo(table)),
        'stem:',
        ('lbu', 't7', 0, 't6'),
        ('beqz', 't7', 'next'),                # end of the table
        ('addiu', 't3', 't0', 2),
        'cmp:',
        ('lbu', 't7', 0, 't6'),
        ('beqz', 't7', 'matched'),
        ('lbu', 't5', 0, 't3'),
        ('bne', 't5', 't7', 'skip'),
        ('addiu', 't6', 't6', 1),
        ('b', 'cmp'),
        ('addiu', 't3', 't3', 1),
        'skip:',                               # to the next stem
        ('lbu', 't7', 0, 't6'),
        ('bnez', 't7', 'skip'),
        ('addiu', 't6', 't6', 1),
        ('b', 'stem'),
        ('nop',),
        'matched:',                            # t3 -> the byte after the stem
        ('addiu', 'at', 'zero', c('s')),
        ('bne', 't5', 'at', 'next'),
        ('lbu', 't5', 1, 't3'),
        ('addiu', 'at', 't5', -c('a')),
        ('sltiu', 'at', 'at', 26),
        ('bnez', 'at', 'next'),
        ('nop',),
        'shift:',                              # delete the 's' (NUL included)
        ('lbu', 't5', 1, 't3'),
        ('sb', 't5', 0, 't3'),
        ('bnez', 't5', 'shift'),
        ('addiu', 't3', 't3', 1),
        'next:',
        ('addu', 't2', 't4', 'zero'),
        ('b', 'loop'),
        ('addiu', 't0', 't0', 1),
        'done:',
        ('jr', 'ra'),
        ('nop',),
    ])

def apply(elf, seg):
    assert [_word(elf, RET + 4 * i) for i in range(8)] == ORIG, 'strDoMessage epilogue'
    for va, ws in SPRINTF_ORIG.items():
        assert [_word(elf, va + 4 * i) for i in range(len(ws))] == ws, 'Sprintf %x' % va
    tab = b''.join(w.encode() + b'\0' for w in PLURAL_STEMS) + b'\0'
    table = seg.reserve(len(tab), 4)
    seg.put(table, tab)
    n = len(plural_fn(0x100000, table))
    plural = seg.reserve(n, 8)
    seg.put(plural, plural_fn(plural, table))
    n = len(cap_fn(0x100000, plural))
    cap = seg.reserve(n, 8)
    seg.put(cap, cap_fn(cap, plural))
    _put(elf, SPRINTF_VA, assemble(SPRINTF_VA, [('addiu', 'v1', 'zero', 0x30),
                                                ('sw', 'a0', 0x10, 'sp')] + [('nop',)] * 9))
    _put(elf, SPRINTF_RET, assemble(SPRINTF_RET, [
        ('lw', 'v1', -0x7B48, 'gp'), ('sb', 'zero', 0, 'v1'), ('jal', plural),
        ('lw', 'a0', 0x10, 'sp'), ('lq', 'ra', 0, 'sp'), ('jr', 'ra'), ('addiu', 'sp', 'sp', 0x60)]))
    _put(elf, VSPRINTF, assemble(VSPRINTF, [
        ('addiu', 'sp', 'sp', -0x20), ('sq', 'ra', 0, 'sp'), ('sw', 'a0', 0x10, 'sp'),
        ('sw', 'a0', -0x7B48, 'gp'), ('lui', 'v0', 0x38), ('jal', 0x387180),
        ('addiu', 'a0', 'v0', 0x7160), ('lw', 'v1', -0x7B48, 'gp'), ('sb', 'zero', 0, 'v1'),
        ('jal', plural), ('lw', 'a0', 0x10, 'sp'), ('lq', 'ra', 0, 'sp'), ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 0x20), ('nop',), ('nop',)]))
    _put(elf, RET, assemble(RET, [
        ('lui', 'at', 1), ('addu', 'at', 's0', 'at'), ('jal', cap), ('lw', 'a0', 0x414, 'at'),
        ('lq', 'ra', 16, 'sp'), ('lq', 's0', 0, 'sp'), ('jr', 'ra'), ('addiu', 'sp', 'sp', 0x20)]))
    assert [_word(elf, EV_RET + 4 * i) for i in range(len(EV_ORIG))] == EV_ORIG, 'NewExtractMessage epilogue'
    _put(elf, EV_RET, assemble(EV_RET, [
        ('jal', cap), ('addu', 'a0', 'v0', 'zero'),
        ('lq', 'ra', 64, 'sp'), ('lq', 's3', 48, 'sp'), ('lq', 's2', 32, 'sp'),
        ('lq', 's1', 16, 'sp'), ('lq', 's0', 0, 'sp'), ('jr', 'ra'), ('addiu', 'sp', 'sp', 0x50)]))
