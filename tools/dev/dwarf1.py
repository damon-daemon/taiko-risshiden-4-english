"""Minimal DWARF version 1 reader for the ELF's .debug section (Metrowerks).

usage: dwarf1.py struct NAME...     # members (offset, bit field, type) of a struct
       dwarf1.py enum NAME...       # enumerators of an enum
       dwarf1.py grep REGEX         # names of structs/enums matching REGEX
"""
import re, struct, sys

ELF = 'extract/SLPM_621.05'
FORM_LEN = {1: 4, 2: 4, 5: 2, 6: 4, 7: 8}
TAG_CLASS, TAG_STRUCT, TAG_UNION, TAG_ENUM, TAG_MEMBER, TAG_TYPEDEF = 0x02, 0x13, 0x17, 0x04, 0x0D, 0x16
AT_NAME, AT_BYTE_SIZE, AT_BIT_OFFSET, AT_BIT_SIZE = 0x03, 0x0B, 0x0C, 0x0D
AT_LOCATION, AT_FUND, AT_UDT, AT_MOD_FUND, AT_MOD_UDT = 0x02, 0x05, 0x07, 0x06, 0x08
AT_ELEMENTS, AT_SIBLING, AT_SUBSCR = 0x0F, 0x01, 0x0A
FUND = {1: 'char', 2: 'schar', 3: 'uchar', 4: 'short', 5: 'sshort', 6: 'ushort', 7: 'int',
        8: 'sint', 9: 'uint', 0xA: 'long', 0xC: 'ulong', 0xD: 'ptr', 0xE: 'float',
        0xF: 'double', 0x14: 'void', 0x15: 'bool', 0x8008: 'longlong', 0x8208: 'ulonglong'}

def section(elf):
    shoff, = struct.unpack_from('<I', elf, 0x20)
    shnum, shstrndx = struct.unpack_from('<HH', elf, 0x30)
    sh = [struct.unpack_from('<10I', elf, shoff + 40 * i) for i in range(shnum)]
    names = sh[shstrndx]
    for s in sh:
        n = elf[names[4] + s[0]:elf.index(0, names[4] + s[0])]
        if n == b'.debug':
            return elf[s[4]:s[4] + s[5]], s[4]
    raise SystemExit('no .debug')

def dies(dbg):
    """-> {offset: (tag, {attr: value}, end)}"""
    out, p = {}, 0
    while p + 4 <= len(dbg):
        n, = struct.unpack_from('<I', dbg, p)
        if n < 8:
            p += max(n, 4)
            continue
        tag, = struct.unpack_from('<H', dbg, p + 4)
        q, end, at = p + 6, p + n, {}
        while q < end:
            a, = struct.unpack_from('<H', dbg, q)
            q += 2
            form, name = a & 0xF, a >> 4
            if form == 8:
                e = dbg.index(0, q)
                v, q = dbg[q:e].decode('latin1'), e + 1
            elif form == 3:
                ln, = struct.unpack_from('<H', dbg, q)
                v, q = dbg[q + 2:q + 2 + ln], q + 2 + ln
            elif form == 4:
                ln, = struct.unpack_from('<I', dbg, q)
                v, q = dbg[q + 4:q + 4 + ln], q + 4 + ln
            elif form in FORM_LEN:
                k = FORM_LEN[form]
                v = int.from_bytes(dbg[q:q + k], 'little')
                q += k
            else:
                break
            at[name] = v
        out[p] = (tag, at, end)
        p = end
    return out

def type_name(at, D):
    if AT_FUND in at:
        return FUND.get(at[AT_FUND], 'fund%x' % at[AT_FUND])
    if AT_UDT in at:
        t = D.get(at[AT_UDT])
        return t[1].get(AT_NAME, '?%x' % at[AT_UDT]) if t else '?'
    if AT_MOD_FUND in at:
        b = at[AT_MOD_FUND]
        f = int.from_bytes(b[-2:], 'little')
        return FUND.get(f, '?') + '*' * sum(1 for c in b[:-2] if c == 1)
    if AT_MOD_UDT in at:
        b = at[AT_MOD_UDT]
        r = int.from_bytes(b[-4:], 'little')
        t = D.get(r)
        return (t[1].get(AT_NAME, '?') if t else '?') + '*' * sum(1 for c in b[:-4] if c == 1)
    if AT_SUBSCR in at:
        return 'array'
    return '?'

def location(b):
    # OP_CONST (4) u32, OP_ADD (7)
    if b and b[0] == 4:
        return int.from_bytes(b[1:5], 'little')
    return None

def members(D, off):
    tag, at, end = D[off]
    keys = sorted(k for k in D if end <= k < at.get(AT_SIBLING, end))
    out = []
    for k in keys:
        t, a, e = D[k]
        if t == TAG_MEMBER:
            out.append((location(a.get(AT_LOCATION, b'')), a.get(AT_BIT_OFFSET),
                        a.get(AT_BIT_SIZE), a.get(AT_BYTE_SIZE), a.get(AT_NAME, ''),
                        type_name(a, D)))
    return out

def enum_items(b):
    out, p = [], 0
    while p < len(b):
        v = int.from_bytes(b[p:p + 4], 'little', signed=True)
        e = b.index(0, p + 4)
        out.append((v, b[p + 4:e].decode('latin1')))
        p = e + 1
    return out

def main():
    dbg, _ = section(open(ELF, 'rb').read())
    D = dies(dbg)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == 'grep':
        rx = re.compile(args[0])
        seen = set()
        for k, (t, a, e) in D.items():
            n = a.get(AT_NAME)
            if t in (TAG_CLASS, TAG_STRUCT, TAG_UNION, TAG_ENUM) and n and rx.search(n) and n not in seen:
                seen.add(n)
                print({TAG_CLASS: 'struct', TAG_STRUCT: 'struct', TAG_UNION: 'union', TAG_ENUM: 'enum'}[t], n,
                      a.get(AT_BYTE_SIZE))
        return
    for name in args:
        hits = [k for k, (t, a, e) in D.items() if a.get(AT_NAME) == name and
                (t == TAG_ENUM if cmd == 'enum' else t in (TAG_CLASS, TAG_STRUCT)) and AT_BYTE_SIZE in a]
        if not hits:
            print(name, 'not found')
            continue
        k = hits[0]
        t, a, e = D[k]
        print('%s %s (%s bytes)' % (cmd, name, a.get(AT_BYTE_SIZE)))
        if cmd == 'enum':
            for v, n in enum_items(a.get(AT_ELEMENTS, b'')):
                print('  %5d %s' % (v, n))
        else:
            for loc, bo, bs, bsz, n, ty in members(D, k):
                bits = '' if bs is None else ' bitoff %d size %d' % (bo, bs)
                print('  +%-4s %-24s %s%s' % ('?' if loc is None else hex(loc), n, ty, bits))

if __name__ == '__main__':
    main()
