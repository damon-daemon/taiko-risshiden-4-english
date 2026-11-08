"""TR4DATA.DAT: 117 entries addressed by a table of contents inside the ELF.

TOC at ELF file offset 0x2FBDE0 (vaddr 0x3FBD60): 117 x (u32 sector, u32 size, u32 0),
sectors relative to the start of TR4DATA.DAT. Known entries:
  57     message file (74 blocks)
  60-61  T4EV event scripts
  62-68  ILNK scenario files
"""
import struct

SECTOR = 2048
TOC = 0x2FBDE0
COUNT = 117

def toc(elf):
    return [struct.unpack_from('<II', elf, TOC + 12 * i) for i in range(COUNT)]

def entry(data, elf, i):
    sector, size = toc(elf)[i]
    return bytes(data[sector * SECTOR:sector * SECTOR + size])

def apply(data, elf, changes):
    """Write changed entries ({index: bytes}) into data (bytearray) and their TOC rows
    into elf (bytearray). An entry that outgrows the sectors up to the next entry is
    appended at the end of the file (TR4DATA is the last file on the disc, so it may
    grow). Returns the indices that were appended."""
    moved = []
    for i, new in sorted(changes.items()):
        rows = toc(elf)
        sector, size = rows[i]
        if entry(data, elf, i) == new:
            continue
        nxt = min((s for s, _ in rows if s > sector), default=len(data) // SECTOR)
        need = (len(new) + SECTOR - 1) // SECTOR
        if sector + need > nxt:
            sector = (len(data) + SECTOR - 1) // SECTOR
            data.extend(bytes(sector * SECTOR - len(data)))
            data.extend(bytes(need * SECTOR))
            moved.append(i)
        else:
            data[sector * SECTOR:nxt * SECTOR] = bytes((nxt - sector) * SECTOR)
        data[sector * SECTOR:sector * SECTOR + len(new)] = new
        struct.pack_into('<II', elf, TOC + 12 * i, sector, len(new))
    return moved
