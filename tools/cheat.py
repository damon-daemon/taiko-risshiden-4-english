"""PCSX2 cheat for the extras: every card collected (Card Album, playable heroes).

usage: .venv/bin/python tools/cheat.py doc                    -> docs/cheats.md
       .venv/bin/python tools/cheat.py pnach [image.bin] [dir]  -> <dir>/SLPM-62105_<CRC>.pnach

How the game stores it (CTK4SystemData SYSTEMDATA at 0x4F2DC0, BSS: the addresses are the
same in the Japanese and the English build; saved to the memory card's system file):
- hero cards 0-649 (card = person id): one byte each at 0x4F2DD0 + i; the card is owned
  when the byte equals key(i) = rand(255) + 1 with the game's LCG seeded with i
  (isUserGainCardFlag 0x1E8250, ushRnd 0x386240: seed = seed * 0x6C078965 + 12345,
  value = (seed >> 16) & 0xFFFF). The hero list of a new game shows the owned hero
  cards (isSystemPlayerCard 0x1E9070).
- other cards 650-1005 (places, duel, titles, battle, formations, common, skills): bits
  at 0x4F305A. Six of them are not album cards (SCardBaseData.m_byAlbumType == 0, table
  0x402610) and are left alone; the album holds 1,000 cards.
The values are written continuously (patch=1), so the system data saved to the memory
card keeps them: a player can save once and remove the cheat.

PCSX2 names a cheat file after the serial and the CRC of the main program, which changes
with every build; the codes themselves do not, so docs/cheats.md lists them once.
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import cdimage, disc

ROOT = disc.ROOT
SERIAL = disc.SERIAL
HEROES, HERO_BASE = 650, 0x4F2DD0
CARDS, CARD_BASE = 1006, 0x4F305A
CHEATS = [
    ('All cards', 'Collects every card of the Card Album (1000), which also makes every hero '
     'selectable in a new game. Save once in the game and it stays on the memory card.'),
]

def key(i):
    seed = (i * 0x6C078965 + 12345) & 0xFFFFFFFFFFFFFFFF
    return ((seed >> 16) & 0xFFFF) % 255 + 1

# album type per card, from the clean ELF's card table (1 hero, 5 place, 3 duel, 2 title,
# 4 battle/formation, 7 common, 6 skill; 0 = not shown in the album)
ALBUM_RUNS = [(650, 56), (707, 113), (825, 181)]      # not in the album: 706, 820-824

def card_bits():
    out = bytearray((CARDS - HEROES + 7) // 8)
    for first, n in ALBUM_RUNS:
        for c in range(first, first + n):
            out[(c - HEROES) >> 3] |= 1 << ((c - HEROES) & 7)
    return bytes(out)

def blocks():
    """(cheat index, base address, bytes)."""
    return [(0, HERO_BASE, bytes(key(i) for i in range(HEROES))),
            (0, CARD_BASE, card_bits())]

def crc(elf):
    """PCSX2's game CRC: XOR of the ELF's 32-bit words."""
    c = 0
    for (w,) in struct.iter_unpack('<I', elf[:len(elf) // 4 * 4]):
        c ^= w
    return c

def writes(cheat):
    """(address, size, value) of one cheat: aligned words, single bytes around them."""
    out = []
    for c, base, data in blocks():
        k = 0
        while c == cheat and k < len(data):
            if (base + k) % 4 == 0 and k + 4 <= len(data):
                out.append((base + k, 4, struct.unpack_from('<I', data, k)[0]))
                k += 4
            else:
                out.append((base + k, 1, data[k]))
                k += 1
    return out

def pnach_lines(cheat):
    name, desc = CHEATS[cheat]
    return ['[%s]' % name, 'author=damon-daemon', 'description=' + desc] + \
           ['patch=1,EE,%08X,%s,%0*X' % (a, 'word' if n == 4 else 'byte', 2 * n, v) for a, n, v in writes(cheat)]

def raw_lines(cheat):
    """Unencrypted raw codes (2aaaaaaa = 32-bit write, 0aaaaaaa = 8-bit write)."""
    return ['%d%07X %08X' % (2 if n == 4 else 0, a, v) for a, n, v in writes(cheat)]

def pnach(elf_crc):
    lines = ['gametitle=Taiko Risshiden IV [%s] (%08X)' % (SERIAL, elf_crc)]
    for c in range(len(CHEATS)):
        lines += [''] + pnach_lines(c)
    return '\n'.join(lines) + '\n'

DOC = """# Cheat: all cards

An optional cheat for Taiko Risshiden IV ({serial}), English patch or Japanese disc:

- **All cards**: collects every card of the Card Album (1,000: heroes, titles, duel,
  battle, skills, places, other). Hero cards are also what makes an officer selectable
  as the hero of a new game, so every hero becomes playable.

You only need it once: with the cheat on, load any save and **save again in the game**
(or start a new game and save). The cards are then stored on the memory card and the
cheat can be turned off. After that save the game congratulates you on each card
milestone at once (300 cards, 700 cards, ...; with the extras they open, such as the mode
for playing any mini-game): press through the messages. The cheat doesn't change
anything inside a playthrough (money, stats, items, the cards your hero holds).

## PCSX2

1. Find the game's CRC: in PCSX2 it is shown in the game's Properties (Summary) and in
   the log when the game starts. For the English patch v{version} it is `{crc_en}`; every
   release of the patch has a different CRC, the Japanese disc is `{crc_jp}`.
2. In PCSX2's `cheats` folder (Settings > Folders) create `{serial}_<CRC>.pnach`
   (e.g. `{serial}_{crc_en}.pnach`) and paste the block below into it.
3. Enable cheats for the game (PCSX2 2.x: the game's Properties > Cheats, tick
   "All cards") and start it.

Tested in PCSX2 2.4 with the English patch v0.9.1 (the addresses are the same in every release): the Card Album shows 1000 cards
(100%), and it still does after saving and starting again without the cheat.

{pnach}

## Raw codes

The same writes as unencrypted raw codes (`2aaaaaaa vvvvvvvv` = 32-bit write,
`0aaaaaaa 000000vv` = 8-bit write), for cheat tools that take raw codes. A cheat device
on a real PS2 may also need a master code for this game, which is not provided.

{raw}

Generated by `tools/cheat.py doc`.
"""

def details(title, lines):
    return '<details>\n<summary>%s (%d lines)</summary>\n\n```\n%s\n```\n</details>' % (title, len(lines), '\n'.join(lines))

def doc(version, crc_en):
    pn = '\n\n'.join(details('.pnach: ' + CHEATS[c][0], pnach_lines(c)) for c in range(len(CHEATS)))
    raw = '\n\n'.join(details(CHEATS[c][0], raw_lines(c)) for c in range(len(CHEATS)))
    return DOC.format(serial=SERIAL, pnach=pn, raw=raw, version=version, crc_en='%08X' % crc_en,
                      crc_jp='%08X' % crc(cdimage.read_file(disc.CLEAN, disc.ELF)))

def make(image, out_dir):
    c = crc(cdimage.read_file(image, disc.ELF))
    path = os.path.join(out_dir, '%s_%08X.pnach' % (SERIAL, c))
    with open(path, 'w', newline='\r\n') as f:
        f.write(pnach(c))
    return path

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'doc'
    built = os.path.join(ROOT, 'build', 'taiko_risshiden_4_en.bin')
    if cmd == 'doc':
        # doc [version] [image]: the release the example CRC is quoted for
        version = sys.argv[2] if len(sys.argv) > 2 else '0.9.2'
        image = sys.argv[3] if len(sys.argv) > 3 else built
        path = os.path.join(ROOT, 'docs', 'cheats.md')
        with open(path, 'w') as f:
            f.write(doc(version, crc(cdimage.read_file(image, disc.ELF))))
        print(path)
    elif cmd == 'pnach':
        image = sys.argv[2] if len(sys.argv) > 2 else built
        print(make(image, sys.argv[3] if len(sys.argv) > 3 else os.path.join(ROOT, 'build')))
    else:
        sys.exit(__doc__)
