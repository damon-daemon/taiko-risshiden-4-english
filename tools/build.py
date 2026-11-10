"""Rebuild the disc image with the translated text and produce a patch.

usage: .venv/bin/python tools/build.py [clean.bin] [out.bin]
"""
import json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(__file__))
import cdimage, datafile, disc, elfseg, elfstr, elftables, evtl, meswin, msgbuf, msgfile, names, printfnum, scenhdr, scriptbuf, sentcase, setup, skillnames, statusbar, text, vwf

ROOT = disc.ROOT
SKIP = set(filter(None, os.environ.get('TR4_SKIP', '').split(',')))   # bisecting: names,tables,elfstr,events

def build_messages(data, elf):
    blocks = msgfile.blocks(datafile.entry(data, elf, setup.MSG_ENTRY), elf)
    changed = 0
    for n in range(len(blocks)):
        for row in json.load(open(setup.msg_json(n), encoding='utf-8')):
            new = text.encode(row['en'] or row['jp'])
            if new != blocks[n][row['id']]:
                blocks[n][row['id']] = new
                changed += 1
    return msgfile.pack(blocks, elf), changed

def main():
    clean = sys.argv[1] if len(sys.argv) > 1 else disc.CLEAN
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'build', 'taiko_risshiden_4_en.bin')
    img = cdimage.Image(clean)
    recs = img.records()
    elf = bytearray(img.read_file(disc.ELF, recs))
    data = bytearray(img.read_file(disc.DATA, recs))
    msg, changed = build_messages(data, elf)
    print('messages: %d strings changed' % changed)
    seg = elfseg.Segment()
    vwf.apply(elf, seg)
    meswin.apply(elf, seg)
    statusbar.apply(elf, seg)
    sentcase.apply(elf, seg)
    scriptbuf.apply(elf, seg)
    printfnum.apply(elf, seg)
    skillnames.apply(elf, seg)
    offs = msgfile.offsets(elf)
    msgbuf.apply(elf, seg, max(b - a for a, b in zip(offs[1:], offs[2:])))
    vwf.apply_vwf(elf, seg)
    changes = {setup.MSG_ENTRY: msg,
               vwf.FONT_ENTRY: vwf.build_font(datafile.entry(data, elf, vwf.FONT_ENTRY), elf)}
    if 'names' not in SKIP:
        changes.update(names.apply(elf, data, seg))
    if 'scenarios' not in SKIP:
        print('scenario headers: %d' % scenhdr.apply(data, elf, changes))
    if 'events' not in SKIP:
        ev, n = evtl.apply_all()
        if ev is not None:
            changes[61] = ev
        print('event scripts: %d files changed' % n)
    clean_elf = img.read_file(disc.ELF, recs)
    if 'tables' not in SKIP:
        print('tables:', elftables.apply(elf, clean_elf, seg))
    if 'elfstr' not in SKIP:
        print('ELF strings: %d (%d moved)' % elfstr.apply(elf, seg, clean_elf))
    heap = elfseg.apply(elf, seg)
    print('English segment: %d bytes, heap from 0x%X' % (len(seg.data), heap))
    datafile.apply(data, elf, changes)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    n = cdimage.write_image(clean, out, {disc.ELF: bytes(elf), disc.DATA: bytes(data)})
    cdimage.write_cue(out)
    print('rebuilt %s (%d sectors re-encoded)' % (out, n))
    patch = os.path.splitext(out)[0] + '.xdelta'
    try:
        subprocess.run(['xdelta3', '-e', '-f', '-9', '-S', 'djw', '-B', str(1 << 30),
                        '-s', clean, out, patch], check=True)
        print('patch %s (%d bytes)' % (patch, os.path.getsize(patch)))
    except FileNotFoundError:
        print('xdelta3 not installed; skipped patch')

if __name__ == '__main__':
    main()
