"""TR4DATA entry 57: the message file (33 blocks).

The block offsets are not in the file but in the ELF: gs_uiMesOffset (vaddr 0x412950,
file 0x3129D0), 34 u32 = start of each block + end of file. Blocks start at 0x40-aligned
offsets, zero padding between them. Block: u16 count, u32 offsets[count] (from block
start), then the strings (no obfuscation, unlike TR5's TAI5MSG). A string is the byte
range up to the next string (normally ending 05 05 05).
"""
import struct

TABLE = 0x3129D0
COUNT = 33
ALIGN = 0x40

def offsets(elf):
    return list(struct.unpack_from('<%dI' % (COUNT + 1), elf, TABLE))

def blocks(data, elf):
    """-> list of blocks, each a list of string byte strings."""
    offs = offsets(elf)
    out = []
    for k, (a, c) in enumerate(zip(offs, offs[1:])):
        b = data[a:c]
        n = struct.unpack_from('<H', b)[0]
        ptrs = list(struct.unpack_from('<%dI' % n, b, 2))
        # zero padding up to the next block (the last block runs to the end of file;
        # its last string ends in a 00 byte)
        end = len(b) if k == COUNT - 1 else len(b.rstrip(b'\0'))
        out.append([bytes(b[p:q]) for p, q in zip(ptrs, ptrs[1:] + [end])])
    return out

def pack_block(strings):
    n = len(strings)
    body, ptrs = bytearray(), []
    for s in strings:
        ptrs.append(2 + 4 * n + len(body))
        body += s
    return struct.pack('<H%dI' % n, n, *ptrs) + bytes(body)

def pack(block_list, elf):
    """-> new entry bytes; writes the block offsets into elf (bytearray)."""
    out, offs = bytearray(), []
    for k, strings in enumerate(block_list):
        if k:
            out += bytes(-len(out) % ALIGN)
        offs.append(len(out))
        out += pack_block(strings)
    offs.append(len(out))
    struct.pack_into('<%dI' % (COUNT + 1), elf, TABLE, *offs)
    return bytes(out)
