"""Scenario headers: title + description on the scenario select screen.

ILNK subfile 0 of the scenario entries 62-67 is an SScenarioHeader (546 B, DWARF):
  +0 u16 no-war days, +2 year, +3 month, +4 day, +5 m_strTitle[17], +0x16 m_strScript[441],
  +0x1CF m_abyEnableBushou. CScenarioWindow::DrawWindow 0x1DFE60 draws the description with
  strDrawText in a 576 x 280 area (runtime word wrap); entry 68 (scenario 7) has an empty header.
English in tl/scenarios.txt ("@N title" line, then the description).

usage: .venv/bin/python tools/scenhdr.py show   (Japanese + current English)
"""
import os, re, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import datafile, disc, names, text

TL = os.path.join(disc.ROOT, 'tl', 'scenarios.txt')
ENTRIES = list(range(62, 68))
TITLE, TITLE_ROOM = 0x05, 17
SCRIPT, SCRIPT_ROOM = 0x16, 441

def load_tl():
    out, cur = {}, None
    for line in open(TL, encoding='utf-8'):
        line = line.rstrip('\n')
        if line.startswith('#') or not line.strip():
            continue
        m = re.match(r'@(\d+) (.*)$', line)
        if m:
            cur = int(m.group(1))
            out[cur] = [m.group(2), '']
        else:
            out[cur][1] += (' ' if out[cur][1] else '') + line.strip()
    return out

def _field(s, room, what, errors):
    b = text.encode(s)
    if len(b) >= room:
        errors.append('%s: %d bytes, room %d' % (what, len(b), room - 1))
    return b[:room - 1].ljust(room, b'\0')

def apply(data, elf, changes):
    """Write the English headers into changes[62..67] (or the clean entries)."""
    tl, errors = load_tl(), []
    for s, ent in enumerate(ENTRIES, 1):
        if s not in tl:
            continue
        e = bytearray(changes.get(ent) or datafile.entry(data, elf, ent))
        a, b = names.ilnk_sub(e, 0)
        assert b - a == 546, (ent, b - a)
        title, script = tl[s]
        e[a + TITLE:a + TITLE + TITLE_ROOM] = _field(title, TITLE_ROOM, 'scenario %d title' % s, errors)
        e[a + SCRIPT:a + SCRIPT + SCRIPT_ROOM] = _field(script, SCRIPT_ROOM, 'scenario %d text' % s, errors)
        changes[ent] = bytes(e)
    if errors:
        sys.exit('scenhdr:\n' + '\n'.join(errors))
    return len(tl)

if __name__ == '__main__':
    import cdimage
    img = cdimage.Image(disc.CLEAN)
    recs = img.records()
    elf, data = img.read_file(disc.ELF, recs), img.read_file(disc.DATA, recs)
    tl = load_tl()
    for s, ent in enumerate(ENTRIES, 1):
        e = datafile.entry(data, elf, ent)
        a, _ = names.ilnk_sub(e, 0)
        print('@%d %s' % (s, names.field(e[a + TITLE:a + TITLE + TITLE_ROOM])))
        print(names.field(e[a + SCRIPT:a + SCRIPT + SCRIPT_ROOM]))
        if s in tl:
            print('  -> %s (%d B)\n  -> %s (%d B)' % (tl[s][0], len(text.encode(tl[s][0])),
                                                   tl[s][1], len(text.encode(tl[s][1]))))
        print()
