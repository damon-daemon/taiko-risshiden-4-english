"""Translation helper for the event scripts (TR4DATA entry 61, see tools/evscript.py).

tl/ev/NN.txt holds the English of script file NN (00-99, the index in entry 61; no
Japanese), one block per string:

    # comment
    @<script>.<n>     string n (0, 1, ... in script order) of script <script>
    English text, possibly over several physical lines (joined with spaces).

  \\n or ||  forced line break        \\_  a space that line stripping would eat
  =          (whole block) keep the Japanese
  Escapes are copied from `show` as printed and may move:
    \\#XXX  person name (XXX & 0x3FF = event person id; +0x400 given name only,
           +0x800 family name only)
    \\%NN   word from msg00 through the table at 0x406ED0 (PCT_UNIT; English already):
           00 "I", 01 "you", 02XXX "that lord/fellow" (person XXX), 03 how the speaker
           addresses the listener ("my lord", "Father", else the bare family name),
           04XXX / 20XXX how he refers to person XXX ("Lord X", "my brother", "X");
           05-1F Japanese verb endings (empty in English: never in English) - may be dropped
    \\&NN, \\Xnnn (X = one of 0-9 : ; < = > ? @ A-Z: places, numbers, items, string
           slots set by a [1F] string...) - must stay.
  A '%' becomes full-width ％.

Kinds: dialogue (11 converse, 12 speak, 13 soliloquy, 14 narration) is shown in the
message window, which wraps words at 576 px and pages itself (3 lines a page): write it
as running text, `\\n` only where the Japanese breaks a thought; a blank line (`|| ||`)
starts a new page. choice (16 menu items) and label (1F string slot, 41 job name,
49 mission text) are not wrapped: keep them about as wide as the Japanese.
Names (3B change name: family, given, readings) are not translated per string: a pair
known from the scenario records gets the English of tl/names_persons.json; others are
listed once in tl/ev/names.txt (`evtl.py names`):
    @<file>.<script>.<n>   n = the string number of the family part
    Family|Given

usage:
    evtl.py show  NN [A[-B]] [--todo]    # Japanese strings of scripts A-B (--todo: only those without
                                         # English that this file owns: a string repeated
                                         # in several files is translated in the lowest one)
    evtl.py apply NN [batch.txt]         # merge a batch into tl/ev/NN.txt and validate
    evtl.py stats                        # progress per file
    evtl.py names                        # name pairs (3B) still without English
TR4_EVTAG=1 tools/build.py ...: debug build, every dialogue/choice string starts with its
"file.script.n " key (to find which script runs where).
TR4_EVSWAP=88.37=00.5[,...] tools/build.py ...: debug build, script 00.5 plays in place of
88.37 (the first visit to the castle town: new game -> Go outside) to view any scene.
"""
import fcntl, functools, json, os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
import evscript, setup, text, tl

ROOT = setup.ROOT
TL_EV = os.path.join(setup.TL, 'ev')

DIALOGUE = {0x11, 0x12, 0x13, 0x14}
CHOICE = {0x16}
NAME_OPS = {0x3B}
WINDOW_PX, PAGE = 576, 3
CHOICE_PX = 240            # menu items: at least this wide (MakeNormalMenuData; verify)
UNIT_BYTES = 500           # warn above (expander szBuff$1239 is 0x800 bytes)
NAME_ROOM = (15, 13)       # family / given bytes (names.py ROOM_FAMILY / ROOM_GIVEN)

ESC = re.compile(rb'\\(#[0-9A-Fa-f]{3}|%(?:02|04|20)[0-9A-Fa-f]{3}|%[0-9A-Fa-f]{2}'
                 rb'|&[0-9A-Fa-f]{2}|[0-9:;<=>?@A-Z][0-9A-Fa-f]{3})')
# \\%NN -> msg00 unit (NewExtractMessageCore jump table 0x406ED0)
PCT_UNIT = dict(enumerate([0x1C, 0x21, 0x22, 0x2A, 0x2B] + list(range(0x2E, 0x31))
                          + list(range(0x32, 0x4A)) + [0x2D]))
FULL_LATIN = re.compile('[０-９Ａ-Ｚａ-ｚ]')

# ---------------------------------------------------------------- data access

@functools.lru_cache(None)
def _clean():
    """-> (entry 61 bytes, elf bytes, TR4DATA reader)"""
    import datafile
    ext = os.path.join(ROOT, 'extract')
    elf = open(os.path.join(ext, 'SLPM_621.05'), 'rb').read()
    data = open(os.path.join(ext, 'TR4DATA.DAT'), 'rb').read()
    return datafile.entry(data, elf, evscript.ENTRY_SCRIPT), elf, data

@functools.lru_cache(None)
def _files():
    return evscript.split(_clean()[0])

def file_count():
    return len(_files()[1])

def units(f):
    """-> (ScriptFile, [(script, n, ins, j)]) of script file f (fresh objects)."""
    sf = evscript.ScriptFile(_files()[1][f][1])
    out = []
    for k, (items, _) in enumerate(sf.scripts):
        for n, (path, ins, j) in enumerate(evscript.strings(items)):
            out.append((k, n, ins, j))
    return sf, out

@functools.lru_cache(None)
def _units_ro(f):
    return units(f)[1]

def kind(ins, j):
    if ins.op in DIALOGUE:
        return 'dialogue'
    if ins.op in NAME_OPS:
        return 'name'
    if ins.op in CHOICE:
        return 'choice'
    return 'label'

@functools.lru_cache(None)
def person_names():
    """person id -> English 'Family Given' (scenario 1 form)."""
    out = {}
    for r in json.load(open(os.path.join(setup.TL, 'names_persons.json'), encoding='utf-8')):
        out[r['id']] = ' '.join(p for p in r['en'] if p)
    return out

PERSONS = 0x2DF            # GetPersonIndex 0x1B1340: ids below are person ids
SPECIAL = {0x3FF: 'none', 0x3FE: 'HERO', 0x3FD: "HERO's lord", 0x3EF: 'master of this place'}

def speaker(ins):
    """'speaker' / 'speaker -> listener' of a dialogue command, for show."""
    w = int.from_bytes(ins.head[:4], 'little')
    def who(p):
        if p < PERSONS:
            return person_names().get(p, 'person %X' % p)
        return SPECIAL.get(p, 'var-person %X' % p)
    kind = (w >> 8) & 3                 # 2 = yes/no question (the window asks after it)
    yn = ' (yes/no)' if kind == 2 and ins.op in DIALOGUE else ''
    if ins.op == 0x11:
        return '%s -> %s%s' % (who((w >> 10) & 0x3FF), who((w >> 20) & 0x3FF), yn)
    if ins.op == 0x12:                  # ActSpeak: kind 3 = the hero speaks to the person
        p = who((w >> 10) & 0x3FF)
        return ('HERO -> %s' if kind == 3 else '%s -> HERO') % p + yn
    if ins.op == 0x13:
        return 'HERO (thinks)' + yn
    return yn.strip()

# ---------------------------------------------------------------- names (3B)

NAMES_TL = os.path.join(TL_EV, 'names.txt')
NAME_KEY = re.compile(r'@(\d+)\.(\d+)\.(\d+)\s*')

def parse_names(path=NAMES_TL):
    out, key = {}, None
    if not os.path.exists(path):
        return out
    for raw in open(path, encoding='utf-8'):
        line = raw.strip()
        m = NAME_KEY.fullmatch(line)
        if m:
            key = tuple(map(int, m.groups()))
        elif line and not line.startswith('#') and key:
            fa, _, gi = line.partition('|')
            out[key] = (fa.strip(), gi.strip())
            key = None
    return out

@functools.lru_cache(None)
def record_names():
    """Japanese (family, given) bytes -> English (family, given) bytes: every pair of the
    scenario records with English in tl/names_persons.json, then tl/ev/names.txt."""
    import names
    _, elf, data = _clean()
    jp, _ = names.disc_names(data, elf)
    tlp = names.load_tl()
    out = {}
    for scen, rows in jp.items():
        for i, (f, g) in enumerate(rows):
            if i in tlp:
                ef, eg = names.english(tlp[i], scen)
                key = (f.encode('cp932'), g.encode('cp932'))
                out.setdefault(key, (text.fold(ef).encode('ascii'), text.fold(eg).encode('ascii')))
    for (f, k, n), (ef, eg) in parse_names().items():
        for kk, nn, ins, j in _units_ro(f):
            if (kk, nn) == (k, n) and ins.op in NAME_OPS:
                out[(ins.strs[0], ins.strs[1])] = (text.fold(ef).encode('ascii'),
                                                   text.fold(eg).encode('ascii'))
    return out

# ---------------------------------------------------------------- tl files

def tl_path(f):
    return os.path.join(TL_EV, '%02d.txt' % f)

KEY = re.compile(r'@(\d+)\.(\d+)\s*')

def parse_tl(path):
    """-> {(script, n): text}"""
    out, key, buf = {}, None, []
    def flush():
        if key is not None:
            out[key] = ' '.join(buf)
    if not os.path.exists(path):
        return out
    for raw in open(path, encoding='utf-8'):
        line = raw.rstrip('\n')
        m = KEY.fullmatch(line)
        if m:
            flush()
            key, buf = (int(m.group(1)), int(m.group(2))), []
        elif line.lstrip().startswith('#'):
            continue
        elif key is not None and line.strip():
            buf.append(line.strip())
    flush()
    return out

def write_tl(path, new):
    """Merge {(script, n): text} into a tl file (blocks replaced in place, new ones appended)."""
    lines = open(path, encoding='utf-8').read().split('\n') if os.path.exists(path) else []
    out, i, done = [], 0, set()
    while i < len(lines):
        m = KEY.fullmatch(lines[i])
        key = (int(m.group(1)), int(m.group(2))) if m else None
        if key in new:
            out += [lines[i], new[key]]
            done.add(key)
            i += 1
            while i < len(lines) and lines[i].strip() and not KEY.fullmatch(lines[i]) \
                    and not lines[i].lstrip().startswith('#'):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    while out and out[-1] == '':
        out.pop()
    for k in sorted(set(new) - done):
        out += ['@%d.%d' % k, new[k]]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(out) + '\n')

def tl_files():
    out = []
    for name in sorted(os.listdir(TL_EV)) if os.path.isdir(TL_EV) else []:
        m = re.fullmatch(r'(\d{2})\.txt', name)
        if m:
            out.append(int(m.group(1)))
    return out

@functools.lru_cache(None)
def memory():
    """(kind, Japanese) -> English source from every tl/ev file (lowest file first)."""
    mem = {}
    for f in tl_files():
        en = parse_tl(tl_path(f))
        for k, n, ins, j in _units_ro(f):
            src = en.get((k, n))
            if src is not None and src.strip() != '=':
                mem.setdefault((kind(ins, j), ins.strs[j]), src)
    return mem

# ---------------------------------------------------------------- validation

def english_bytes(src):
    s = src.replace(' || ', '\n').replace('||', '\n').replace('\\n ', '\n').replace('\\n', '\n')
    s = s.replace('\\_', ' ').replace(' \n', '\n').replace('\n ', '\n')
    return text.encode(re.sub(r'(?<!\\)%', '％', s))

def escapes(b):
    return sorted(m.group(1).upper() for m in ESC.finditer(b))

def measure(line):
    """Pixel width of one line, escapes counted as nothing (only for labels/choices)."""
    W = tl.widths()
    b = ESC.sub(b'', line)
    px = i = 0
    while i < len(b):
        c = b[i]
        if (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC) and i + 1 < len(b):
            px += 24; i += 2
        else:
            px += W.get(chr(c), 12) if c < 0x80 else 12
            i += 1
    return px

def check(jp, en, k):
    """-> (errors, warnings, final bytes)"""
    errs, warns = [], []
    if FULL_LATIN.search(en.decode('cp932', 'replace')):
        errs.append('full-width Latin/digits in English')
    if b'\\' in ESC.sub(b'', en):
        errs.append('backslash that is not an escape')
    je, ee = escapes(jp), escapes(en)
    for x in ee:
        if x in je:
            je.remove(x)
        else:
            errs.append('escape not in the Japanese: \\%s' % x.decode())
    for x in ee:
        if x[:1] == b'%' and 0x05 <= int(x[1:3], 16) <= 0x1F:
            errs.append('\\%s is a Japanese verb ending (empty in English)' % x.decode())
    for x in je:
        if x[:1] != b'%':
            errs.append('missing escape \\%s' % x.decode())
    if any(c < 0x20 and c != 0x0A for c in en):
        errs.append('control byte in English')
    if k == 'name':
        errs.append('names are translated in tl/ev/names.txt')
    elif k == 'dialogue':
        if len(en) > UNIT_BYTES:
            warns.append('%d bytes > %d' % (len(en), UNIT_BYTES))
    else:
        width = max([CHOICE_PX if k == 'choice' else 0] + [measure(l) for l in jp.split(b'\n')])
        for i, l in enumerate(en.split(b'\n')):
            if measure(l) > width:
                warns.append('line %d is %d px > %d' % (i + 1, measure(l), width))
        if en.count(b'\n') > jp.count(b'\n'):
            warns.append('%d lines > %d' % (en.count(b'\n') + 1, jp.count(b'\n') + 1))
    return errs, warns, en

def english_file(f, units_en, log, use_memory=True):
    """Apply {(script, n): text} to clean script file f -> rebuilt bytes (None if unchanged)."""
    sf, us = units(f)
    index = {(k, n): (ins, j) for k, n, ins, j in us}
    changed = False
    rec = record_names()
    for k, n, ins, j in us:
        if ins.op in NAME_OPS and j == 0:
            new = rec.get((ins.strs[0], ins.strs[1]))
            if new:
                ins.strs[0], ins.strs[1] = new
                ins.strs[2] = ins.strs[3] = b''
                changed = True
    if use_memory:
        mem = memory()
        units_en = dict(units_en)
        for k, n, ins, j in us:
            if (k, n) not in units_en and kind(ins, j) != 'name':
                src = mem.get((kind(ins, j), ins.strs[j]))
                if src is not None:
                    units_en[(k, n)] = src
    for key, src in sorted(units_en.items()):
        tag = '%02d@%d.%d' % ((f,) + key)
        if key not in index:
            log('%s ERROR no such string' % tag, True); continue
        if src.strip() == '=':
            continue
        ins, j = index[key]
        try:
            en = english_bytes(src)
        except (ValueError, UnicodeError) as x:
            log('%s ERROR %s' % (tag, x), True); continue
        errs, warns, final = check(ins.strs[j], en, kind(ins, j))
        for x in errs:
            log('%s ERROR %s' % (tag, x), True)
        for x in warns:
            log('%s warn  %s' % (tag, x), False)
        if not errs:
            ins.strs[j] = final
            changed = True
    if os.environ.get('TR4_EVTAG'):          # debug build: every string shows its key
        for k, n, ins, j in us:
            if kind(ins, j) in ('dialogue', 'choice'):
                ins.strs[j] = b'%d.%d.%d ' % (f, k, n) + ins.strs[j]
                changed = True
    if not changed:
        return None
    try:
        data = sf.build()
    except evscript.ParseError as x:
        log('%02d ERROR %s' % (f, x), True)
        return None
    for k, (items, tail) in enumerate(sf.scripts):
        size = len(evscript.build_list(items)) + tail
        if size > evscript.SCRIPT_BUFFER:
            log('%02d ERROR script %d is %d bytes > %d (tools/scriptbuf.py MAX)'
                % (f, k, size, evscript.SCRIPT_BUFFER), True)
    return data

def apply(f, batch=None):
    path = tl_path(f)
    lock = open(os.path.join(TL_EV, '.lock'), 'w') if os.path.isdir(TL_EV) else None
    if lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
    units_en = parse_tl(path)
    new = {}
    if batch and os.path.abspath(batch) != os.path.abspath(path):
        new = parse_tl(batch)
        units_en.update(new)
        print('%02d: %d blocks from %s' % (f, len(new), batch))
    bad = []
    def log(msg, err):
        print(msg)
        if err:
            bad.append(msg)
    english_file(f, units_en, log, use_memory=False)
    if bad and new:
        print('%02d: %d errors: nothing written' % (f, len(bad)))
    elif new:
        write_tl(path, new)
    total = sum(1 for k, n, ins, j in _units_ro(f) if kind(ins, j) != 'name')
    print('%02d: %d/%d strings translated here, %d errors' % (f, len(units_en), total, len(bad)))
    return not bad

def apply_all():
    """For build.py: {61: English entry} (None if nothing is translated); exits on errors."""
    bad = []
    def log(msg, err):
        if err:
            bad.append(msg)
    head, files, end_id = _files()
    own = set(tl_files())
    out, changed = [], 0
    for f, (fid, data) in enumerate(files):
        new = english_file(f, parse_tl(tl_path(f)) if f in own else {}, log)
        if new is not None:
            changed += 1
        out.append((fid, new if new is not None else data))
    if bad:
        sys.exit('errors in tl/ev:\n' + '\n'.join(bad))
    for pair in filter(None, os.environ.get('TR4_EVSWAP', '').split(',')):
        # debug build: "88.37=00.5" plays script 00.5 where 88.37 (first town visit) runs
        dst, src = [tuple(map(int, x.split('.'))) for x in pair.split('=')]
        body = evscript.ScriptFile(out[src[0]][1]).scripts[src[1]]
        sf = evscript.ScriptFile(out[dst[0]][1])
        sf.scripts[dst[1]] = body
        out[dst[0]] = (out[dst[0]][0], sf.build())
        changed += 1
    if not changed:
        return None, 0
    return evscript.join(head, out, end_id), changed

# ---------------------------------------------------------------- show / stats

@functools.lru_cache(None)
def owner():
    """(kind, Japanese) -> the lowest file that has it: only that file translates it
    (`show --todo` hides it elsewhere; the memory fills the copies at build time)."""
    out = {}
    for f in range(file_count()):
        for k, n, ins, j in _units_ro(f):
            out.setdefault((kind(ins, j), ins.strs[j]), f)
    return out

def show(f, script=None, todo=False):
    us = _units_ro(f)
    done = parse_tl(tl_path(f))
    mem = memory() if todo else {}
    own = owner()
    count = {}
    for k, n, ins, j in us:
        key = (kind(ins, j), ins.strs[j])
        count[key] = count.get(key, 0) + 1
    seen = set()
    for k, n, ins, j in us:
        if script is not None and not script[0] <= k <= script[1] or kind(ins, j) == 'name':
            continue
        key = (kind(ins, j), ins.strs[j])
        if todo:
            if (k, n) in done or key in mem or key in seen or own[key] != f:
                continue
            seen.add(key)
        s = text.decode(ins.strs[j]).replace('\n', '⏎')
        who = speaker(ins)
        print('@%d.%d%s [%s%s%s]%s  %s' % (
            k, n, ' [done]' if (k, n) in done else '',
            evscript.OP_NAMES.get(ins.op, '%02X' % ins.op), '.%d' % j if len(ins.strs) > 1 else '',
            ' ' + who if who else '', ' x%d' % count[key] if todo and count[key] > 1 else '', s))

def list_names():
    seen = {}
    rec = record_names()
    for f in range(file_count()):
        for k, n, ins, j in _units_ro(f):
            if ins.op not in NAME_OPS or j != 0:
                continue
            jp = (ins.strs[0], ins.strs[1])
            if jp in rec:
                continue
            if jp not in seen:
                seen[jp] = ['@%d.%d.%d' % (f, k, n), 0]
            seen[jp][1] += 1
    for jp, (key, c) in sorted(seen.items(), key=lambda x: -x[1][1]):
        print('%-12s %4d  %s | %s' % (key, c, text.decode(jp[0]), text.decode(jp[1])))
    print('%d pairs without English' % len(seen))

def stats():
    tot = done = 0
    mem = memory()
    for f in range(file_count()):
        own = parse_tl(tl_path(f))
        us = [(k, n, ins, j) for k, n, ins, j in _units_ro(f) if kind(ins, j) != 'name']
        d = sum(1 for k, n, ins, j in us if (k, n) in own or (kind(ins, j), ins.strs[j]) in mem)
        tot += len(us); done += d
        if d:
            print('%02d %5d/%5d' % (f, d, len(us)))
    print('total %d/%d strings' % (done, tot))

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    args = [a for a in sys.argv[2:] if a != '--todo']
    if cmd == 'show':
        rng = None
        if len(args) > 1:
            a, _, b = args[1].partition('-')
            rng = (int(a), int(b) if b else int(a))
        show(int(args[0]), rng, '--todo' in sys.argv)
    elif cmd == 'apply':
        sys.exit(0 if apply(int(args[0]), args[1] if len(args) > 1 else None) else 1)
    elif cmd == 'stats':
        stats()
    elif cmd == 'names':
        list_names()
    else:
        sys.exit(__doc__)
