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
  conversion letter is never touched; ESC x y is skipped, Shift-JIS and kana end it.
"""
import struct

from asm import assemble, hi, lo

BASE, FOFF = 0x100000, 0x80
RET = 0x254D28      # lui at,1; addu at,s0,at; lw v0,0x414(at); lq ra,16(sp); lq s0,0(sp);
                    # addiu sp,sp,0x20; jr ra; nop
ORIG = [0x3C010001, 0x02010821, 0x8C220414, 0x7BBF0010, 0x7BB00000, 0x27BD0020,
        0x03E00008, 0x00000000]

def _word(elf, va):
    return struct.unpack_from('<I', elf, va - BASE + FOFF)[0]

def _put(elf, va, b):
    elf[va - BASE + FOFF:va - BASE + FOFF + len(b)] = b

def cap_fn(org):
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
        'notlow:',
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
        ('addiu', 't1', 'zero', 1),
        'next:',
        ('addu', 't2', 't4', 'zero'),
        ('b', 'loop'),
        ('addiu', 't0', 't0', 1),
        'end:',
        ('jr', 'ra'),
        ('nop',),
    ])

def apply(elf, seg):
    assert [_word(elf, RET + 4 * i) for i in range(8)] == ORIG, 'strDoMessage epilogue'
    n = len(cap_fn(0x100000))
    cap = seg.reserve(n, 8)
    seg.put(cap, cap_fn(cap))
    _put(elf, RET, assemble(RET, [
        ('lui', 'at', 1), ('addu', 'at', 's0', 'at'), ('jal', cap), ('lw', 'a0', 0x414, 'at'),
        ('lq', 'ra', 16, 'sp'), ('lq', 's0', 0, 'sp'), ('jr', 'ra'), ('addiu', 'sp', 'sp', 0x20)]))
