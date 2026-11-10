"""Long skill names for messages.

strGetSkill 0x304280 returns the skill name from the pointer table 0x3F7800 (16 skills,
strings 419268-4192E0, 4 bytes each in Japanese). The same getter feeds narrow UI cells
(person info, job lists, sort buttons, card labels "%s Lv.%y", the formation panel) and
messages ("Training in %s takes %u days"), so tl/elfstr.txt keeps the short forms (Cav.,
Strat, Build) and the messages read "Training in Cav.".

Patch: STR_LONG in the segment returns LONG[skill] (fallback: the original getter), and
the jal of the callers that only build messages (MESSAGE_CALLERS: dojo training
Tanren*, the training mini-game, high-level skills, castle mission reports, the drill
ground greeting) is repointed to it. UI callers keep the short names.
"""
import struct

from asm import assemble, hi, lo
import text

BASE, FOFF = 0x100000, 0x80
STR_GET_SKILL = 0x304280

# ESkill order (table 0x3F7800); glossary: notes/glossary.md (skills)
LONG = ['Infantry', 'Cavalry', 'Gunnery', 'Navy', 'Archery', 'Swordsmanship', 'Tactics',
        'Ninjutsu', 'Building', 'Farming', 'Mining', 'Accounting', 'Etiquette', 'Speech',
        'Tea Ceremony', 'Medicine']

MESSAGE_CALLERS = [
    0x19452C,                               # AcquireHighLevel
    0x1957AC, 0x195980,                     # BattleMiniGame
    0x196448, 0x196458, 0x1964F0,           # AfterTanrenMain
    0x1967BC, 0x196880, 0x196928,           # bBeforeTanrenMain
    0x196ABC, 0x196BBC, 0x196C94,           # bCheckTanrenItem
    0x2B91C8, 0x2B9230,                     # CMPCastle::ReportUserResultMes
    0x2E1704,                               # CMPTanrenjo::ChangeGreetings (strMes)
]

def _word(elf, va):
    return struct.unpack_from('<I', elf, va - BASE + FOFF)[0]

def _put(elf, va, b):
    elf[va - BASE + FOFF:va - BASE + FOFF + len(b)] = b

def apply(elf, seg):
    jal = assemble(0, [('jal', STR_GET_SKILL)])
    for va in MESSAGE_CALLERS:
        assert _word(elf, va) == struct.unpack('<I', jal)[0], 'skillnames: no jal at %x' % va
    ptrs = [seg.add(text.encode(s) + b'\0', 4) for s in LONG]
    tab = seg.add(struct.pack('<%dI' % len(ptrs), *ptrs), 4)
    body = lambda org: assemble(org, [
        ('sltiu', 'at', 'a0', len(LONG)),
        ('beqz', 'at', 'orig'),
        ('sll', 'v0', 'a0', 2),
        ('lui', 'at', hi(tab)),
        ('addu', 'at', 'at', 'v0'),
        ('lw', 'v0', lo(tab), 'at'),
        ('jr', 'ra'),
        ('nop',),
        'orig:',
        ('j', STR_GET_SKILL),
        ('nop',),
    ])
    fn = seg.reserve(len(body(0)), 8)
    seg.put(fn, body(fn))
    for va in MESSAGE_CALLERS:
        _put(elf, va, assemble(va, [('jal', fn)]))
