"""Translation helper for the ELF text: name tables (elftables.py) and string literals
(elfstr.py). Batches are checked before anything is written to tl/.

  elftl.py show TABLE [--todo]                 TABLE = a table of elftables.TABLES
  elftl.py show strings [--todo] [LO [HI]]     string literals, vaddr range (hex)
  elftl.py apply TABLE|strings BATCH           merge a batch ("key<TAB>English" lines)
  elftl.py prefill                             exact TR5 matches that fit (only empty keys)
  elftl.py stats

show prints: key, room (bytes), Japanese px, owner (strings), Japanese, and a TR5 line when
TR5 has an English for the identical Japanese. Widths: Japanese 12 px a half-width char /
24 a full-width one; English with the game's proportional font. English wider than the
Japanese is a warning (labels in fixed columns get clipped or overlap); more bytes than the
room is an error for tables and for strings that cannot be moved (GP-relative references).
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
import elfstr, elftables, text, tl

ROOT = elftables.ROOT
TR5_TERMS = os.path.join(ROOT, 'notes', 'tr5_terms.tsv')
# literals that are data, not display text (name-entry kana, font code table)
SKIP_OWNERS = ('gs_strRubyList', 'gs_strRubyCode', 'gs_strNameList', 'g_abyHalfCodeTable')
FONT_SYMBOLS = set('●○◆◇■□▲△▼▽★☆←→↑↓《》「」『』【】・～×÷±…①②③④⑤⑥⑦⑧⑨')

def tr5_terms():
    out = {}
    if os.path.exists(TR5_TERMS):
        for line in open(TR5_TERMS, encoding='utf-8'):
            p = line.rstrip('\n').split('\t')
            if len(p) >= 2 and p[1]:
                out.setdefault(p[0], p[1])
    return out

def jp_px(s):
    return sum(12 if ord(c) < 0x80 or 0xFF61 <= ord(c) <= 0xFF9F else 24 for c in s if c not in '\n\x1b')

def en_px(s):
    w = tl.widths()
    best = cur = 0
    for c in text.fold(s):
        if c == '\n':
            cur = 0
            continue
        cur += w.get(c, 24) if ord(c) < 0x80 else 24
        best = max(best, cur)
    return best

def _line_px(s, f):
    return max((f(x) for x in s.split('\n')), default=0)

# ---------------------------------------------------------------- string literals

_LITS = None

def literals():
    """[{va, room, movable, owner, jp}] (display text only)."""
    global _LITS
    if _LITS is None:
        rows = json.load(open(elfstr.SCRIPT, encoding='utf-8')) if os.path.exists(elfstr.SCRIPT) else elfstr.export()
        _LITS = []
        for r in rows:
            owner = r['used'][0] if r['used'] else '-'
            if owner.split('$')[0] in SKIP_OWNERS:
                continue
            kinds = set(r['refs'])
            _LITS.append({'va': int(r['va'], 16), 'room': r['room'], 'owner': owner, 'jp': r['jp'],
                          'movable': bool(kinds) and kinds <= {'2', '5', '6'}})
    return _LITS

def check_string(lit, en):
    """-> (errors, warnings)"""
    err, warn = [], []
    jp = lit['jp']
    try:
        b = text.fold(en).encode('cp932')
    except UnicodeEncodeError as e:
        return ['not encodable: %r' % en[e.start:e.end]], []
    for c in text.fold(en):
        if ord(c) >= 0x80 and c not in FONT_SYMBOLS and not ('\u3000' <= c <= '\u9fff' or '\uff00' <= c <= '\uffef'):
            err.append('character %r is not in the font' % c)
    if re.search('[０-９Ａ-Ｚａ-ｚ]', en):
        err.append('full-width Latin letters/digits: use ASCII')
    jb = jp.encode('cp932')
    if elfstr.FMT.findall(b) != elfstr.FMT.findall(jb):
        err.append('conversions %s, Japanese has %s' % ([x.decode() for x in elfstr.FMT.findall(b)],
                                                          [x.decode() for x in elfstr.FMT.findall(jb)]))
    if re.findall(r'\x1b.', en) != re.findall(r'\x1b.', jp):
        err.append('escape codes differ from the Japanese (\\x1b + letter)')
    if en.count('\n') != jp.count('\n'):
        warn.append('%d line breaks, Japanese has %d' % (en.count('\n'), jp.count('\n')))
    if len(b) > lit['room'] and not lit['movable']:
        err.append('%d bytes > room %d and the string cannot be moved' % (len(b), lit['room']))
    ep, jpx = _line_px(en, en_px), _line_px(jp, jp_px)
    if ep > jpx:
        warn.append('%d px > Japanese %d px' % (ep, jpx))
    return err, warn

# ---------------------------------------------------------------- tables

_ELF = None

def table_rows(name):
    global _ELF
    if _ELF is None:
        _ELF = open(os.path.join(ROOT, 'extract', 'SLPM_621.05'), 'rb').read()
    room = elftables.text_end(_ELF, name) - elftables.TABLES[name][3] - 1
    if name in elftables.LONG:
        room = 30                      # names in the segment: no byte limit, keep labels short
    return room, [(i, jp.decode('cp932', 'replace')) for i, jp, rd in elftables.records(_ELF, name)]

def check_table(room, jp, en):
    err, warn = [], []
    if not en:
        err.append('empty')
    if any(not (0x20 <= ord(c) < 0x7F) for c in text.fold(en)):
        err.append('ASCII only')
    if len(text.fold(en)) > room:
        err.append('%d bytes > room %d' % (len(en), room))
    if en_px(en) > jp_px(jp):
        warn.append('%d px > Japanese %d px' % (en_px(en), jp_px(jp)))
    return err, warn

# ---------------------------------------------------------------- tl files

def tl_path(kind):
    return elfstr.TL if kind == 'strings' else os.path.join(elftables.TL, kind + '.txt')

def load(kind):
    return elfstr.load_tl() if kind == 'strings' else elftables.load_tl(kind)

def save(kind, d):
    path = tl_path(kind)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        if kind == 'strings':
            f.write('# ELF string literals: vaddr<TAB>English (tools/elfstr.py; \\n = line break)\n')
            for k in sorted(d):
                f.write('%x\t%s\n' % (k, d[k].replace('\n', '\\n')))
        else:
            f.write('# %s: index<TAB>English (tools/elftables.py)\n' % kind)
            for k in sorted(d):
                f.write('%d\t%s\n' % (k, d[k]))

def parse_batch(kind, path):
    out = {}
    for n, line in enumerate(open(path, encoding='utf-8').read().splitlines(), 1):
        if not line.strip() or line.startswith('#'):
            continue
        k, tab, v = line.partition('\t')
        if not tab:
            raise SystemExit('%s:%d: no TAB' % (path, n))
        out[int(k, 16) if kind == 'strings' else int(k)] = v.replace('\\n', '\n')
    return out

def entries(kind):
    """{key: (room, jp, check(en) -> (err, warn), extra)}"""
    if kind == 'strings':
        return {l['va']: (l['room'], l['jp'], lambda en, l=l: check_string(l, en),
                          '%s%s' % (l['owner'][:40], '' if l['movable'] else ' FIXED')) for l in literals()}
    room, rows = table_rows(kind)
    return {i: (room, jp, lambda en, jp=jp: check_table(room, jp, en), '') for i, jp in rows}

def apply(kind, batch):
    ents = entries(kind)
    new = parse_batch(kind, batch)
    errors = 0
    for k, en in sorted(new.items()):
        if k not in ents:
            print('ERROR %s: no such key' % (fmt_key(kind, k)))
            errors += 1
            continue
        err, warn = ents[k][2](en)
        for e in err:
            print('ERROR %s %r: %s' % (fmt_key(kind, k), en, e))
        for w in warn:
            print('warn  %s %r: %s' % (fmt_key(kind, k), en, w))
        errors += len(err)
    if errors:
        print('%d errors: nothing written' % errors)
        return 1
    import fcntl                       # parallel workers apply to the same file
    with open(tl_path(kind) + '.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        d = load(kind)
        d.update(new)
        save(kind, d)
    print('%s: %d written, %d/%d done' % (kind, len(new), len([k for k in d if k in ents]), len(ents)))
    return 0

def fmt_key(kind, k):
    return '%x' % k if kind == 'strings' else '%d' % k

def show(kind, todo=False, lo=0, hi=1 << 32):
    ents = entries(kind)
    done = load(kind)
    terms = tr5_terms()
    for k, (room, jp, check, extra) in sorted(ents.items()):
        if kind == 'strings' and not lo <= k < hi:
            continue
        if todo and k in done:
            continue
        mark = '' if k not in done else '  [done: %s]' % done[k].replace('\n', '\\n')
        print('%s\t%d\t%dpx\t%s\t%s%s' % (fmt_key(kind, k), room, _line_px(jp, jp_px), extra,
                                        jp.replace('\n', '\\n').replace('\x1b', '{1B}'), mark))
        if jp in terms:
            print('    TR5: ' + terms[jp])

def prefill():
    terms = tr5_terms()
    for kind in list(elftables.TABLES) + ['strings']:
        ents = entries(kind)
        d = load(kind)
        n = 0
        for k, (room, jp, check, extra) in ents.items():
            if k in d or jp not in terms:
                continue
            en = terms[jp]
            err, warn = check(en)
            if not err and not warn:
                d[k] = en
                n += 1
        if n:
            save(kind, d)
        print('%s: %d prefilled from TR5' % (kind, n))

def stats():
    for kind in list(elftables.TABLES) + ['strings']:
        ents, d = entries(kind), load(kind)
        print('%-12s %4d/%4d' % (kind, len([k for k in d if k in ents]), len(ents)))

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[:1] == ['show'] and len(a) >= 2:
        rest = [x for x in a[2:] if x != '--todo']
        rng = [int(x, 16) for x in rest] + [0, 1 << 32][len(rest):]
        show(a[1], '--todo' in a, *rng[:2])
    elif a[:1] == ['apply'] and len(a) == 3:
        sys.exit(apply(a[1], a[2]))
    elif a == ['prefill']:
        prefill()
    elif a == ['stats']:
        stats()
    else:
        sys.exit(__doc__)
