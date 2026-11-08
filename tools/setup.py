"""Create the working folder script/ from your own disc image and the English in tl/.

script/ holds the Japanese text extracted from the disc next to the English, so it
is generated on each machine and never distributed. Run this once after cloning
(and again after editing tl/), then tools/build.py.

usage: .venv/bin/python tools/setup.py [clean.bin]
"""
import hashlib, json, os, sys

sys.path.insert(0, os.path.dirname(__file__))
import cdimage, datafile, disc, msgfile, text

ROOT = disc.ROOT
SCRIPT = os.path.join(ROOT, 'script')
TL = os.path.join(ROOT, 'tl')

def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        while chunk := f.read(1 << 24):
            h.update(chunk)
    return h.hexdigest()

def check_clean(path):
    digest = sha1(path)
    if digest != disc.CLEAN_SHA1:
        sys.exit('%s: SHA-1 %s does not match the clean dump (%s)' % (path, digest, disc.CLEAN_SHA1))

MSG_ENTRY = 57

def msg_json(n):
    return os.path.join(SCRIPT, 'msg', 'msg%02d.json' % n)

def clean_messages(img):
    recs = img.records()
    elf = img.read_file(disc.ELF, recs)
    data = img.read_file(disc.DATA, recs)
    return msgfile.blocks(datafile.entry(data, elf, MSG_ENTRY), elf)

def export_messages(img):
    os.makedirs(os.path.join(SCRIPT, 'msg'), exist_ok=True)
    for n, strings in enumerate(clean_messages(img)):
        rows = [{'id': i, 'jp': text.decode(s), 'en': ''} for i, s in enumerate(strings)]
        json.dump(rows, open(msg_json(n), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return n + 1

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else disc.CLEAN
    check_clean(path)
    n = export_messages(cdimage.Image(path))
    print('script/msg: %d message blocks' % n)
    print('script/ ready; now run tools/build.py')

if __name__ == '__main__':
    main()
