"""Event scripts larger than CScriptFile's 20 KB buffer.

CScriptFile (DWARF: 22,576 bytes) keeps a script in m_abyDataBuffer (+0x82C, 0x5000 bytes)
and its size in m_nDataByteSize (+0x582C, right after the buffer). Two instances exist:
CEventManager::m_cScriptFile (s_cEventManager 0x46B100 + 0x823C8 = 0x4ED4C8) and a stack
copy in CEventManager::bCallSubroutine (subroutine scripts); m_pScriptFile (+0x87BF8)
points to the one in use. Only three places touch the buffer:
  CScriptFile::bRead 0x1B240C  addiu a0, s0, 0x82C   (MovMem from the memory image)
                     0x1B2458  addiu a1, s0, 0x82C   (CFile::bRead from the disc)
  CEventManager::ExecuteScript 0x1B4D60  addiu s0, v0, 0x82C ; lbu v1, 0x82C(v0)
bRead stores m_nDataByteSize before copying. The patch sends a script larger than 0x5000
bytes to a 32 KB buffer in the English segment instead (one for the main instance, one
for subroutine copies), so English scripts may grow up to MAX bytes.
"""
import struct

from asm import assemble, hi, lo

BASE, FOFF = 0x100000, 0x80
MEMBER = 0x46B100 + 0x823C8
OWN, OWN_SIZE, SIZE_FIELD = 0x82C, 0x5000, 0x582C
MAX = 0x8000
SITES = {0x1B240C: 0x2604082C, 0x1B2458: 0x2605082C, 0x1B4D60: 0x2450082C, 0x1B4D64: 0x9043082C}

def _word(elf, va):
    return struct.unpack_from('<I', elf, va - BASE + FOFF)[0]

def _put(elf, va, b):
    elf[va - BASE + FOFF:va - BASE + FOFF + len(b)] = b

def helper(org, src, dst, main, sub, load_v1=False):
    """dst = data buffer of the CScriptFile in src (uses t0, t1; dst may be a0/a1/s0)."""
    body = [
        ('lw', 't0', SIZE_FIELD, src),
        ('sltiu', 't0', 't0', OWN_SIZE + 1),
        ('bnez', 't0', 'own'),
        ('lui', 't1', hi(MEMBER)),
        ('addiu', 't1', 't1', lo(MEMBER)),
        ('lui', dst, hi(main)),
        ('beq', src, 't1', 'done'),
        ('addiu', dst, dst, lo(main)),
        ('lui', dst, hi(sub)),
        ('b', 'done'),
        ('addiu', dst, dst, lo(sub)),
        'own:',
        ('addiu', dst, src, OWN),
        'done:',
    ]
    if load_v1:
        body += [('jr', 'ra'), ('lbu', 'v1', 0, dst)]
    else:
        body += [('jr', 'ra'), ('nop',)]
    return assemble(org, body)

def apply(elf, seg):
    for va, w in SITES.items():
        assert _word(elf, va) == w, 'scriptbuf site %X' % va
    main = seg.reserve(MAX, 64)
    sub = seg.reserve(MAX, 64)
    fns = {}
    for name, src, dst, v1 in (('a0', 's0', 'a0', False), ('a1', 's0', 'a1', False),
                               ('ex', 'v0', 's0', True)):
        n = len(helper(0x100000, src, dst, main, sub, v1))
        a = seg.reserve(n, 8)
        seg.put(a, helper(a, src, dst, main, sub, v1))
        fns[name] = a
    # the instruction after each site runs in the jal's delay slot (see the docstring):
    # 0x1B2410 move a2, s1 / 0x1B245C lui at, 8 - neither reads the helper's registers.
    _put(elf, 0x1B240C, assemble(0x1B240C, [('jal', fns['a0'])]))
    _put(elf, 0x1B2458, assemble(0x1B2458, [('jal', fns['a1'])]))
    _put(elf, 0x1B4D60, assemble(0x1B4D60, [('jal', fns['ex']), ('nop',)]))
