"""pinescan.py START END VALUE [VALUE..] : scan EE memory (u32 steps of 2 bytes are not
tried: aligned u32 and u16 halves) for values, through batched PINE reads.
Prints 'addr: width value'."""
import socket, struct, sys
import pine

def dump(start, end, batch=2048):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(pine.SOCK)
    out = bytearray()
    for a in range(start, end, 4 * batch):
        n = min(batch, (end - a) // 4)
        body = b''.join(struct.pack('<BI', 2, a + 4 * k) for k in range(n))
        s.sendall(struct.pack('<I', 4 + len(body)) + body)
        need = 5 + 4 * n
        d = b''
        while len(d) < need:
            d += s.recv(need - len(d))
        if d[4]:
            raise IOError('PINE error')
        out += d[5:]
    s.close()
    return bytes(out)

if __name__ == '__main__':
    start, end = int(sys.argv[1], 0), int(sys.argv[2], 0)
    vals = [int(v, 0) for v in sys.argv[3:]]
    mem = dump(start, end)
    if not vals:
        sys.stdout.buffer.write(mem)
    for off in range(0, len(mem) - 3, 2):
        h = struct.unpack_from('<H', mem, off)[0]
        if h in vals:
            w = struct.unpack_from('<I', mem, off)[0] if off % 4 == 0 else None
            print('%08x: %s %d' % (start + off, 'u32' if w == h else 'u16', h))
