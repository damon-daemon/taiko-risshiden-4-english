"""Translation helper for the message file (TR4DATA entry 57): show units, validate + wrap + apply English.

A message is split into text units by tools/msgscript.py: the runs of text between
structural codes (conditions, END, variant/register commands). Only units are
translated; the structure around them is kept byte for byte.

tl/msgNN.txt holds the English (no Japanese), one block per unit:

    # comment (a line starting with #; English text never does)
    @<entry>          unit 0 of the entry (same as @<entry>.0)
    @<entry>.<unit>
    English text, possibly over several physical lines (joined with spaces).

  \\n or ||  forced line break        \\_  a space that line stripping would eat
  =          (whole block) keep the Japanese of this unit
  Inline codes are copied from `show` as printed ({02}{01}d = a variable,
  {01}C1{00} = insert msg00 entry 0x31, {1B}C3..{1B}C0 = colour, %w = field filled
  in by the game). They may move; {01}C/{02} inserts may be dropped (word endings,
  pronouns), not added. Kana toggles ({1B}K {1B}H {1B}k) are dropped from English.
  A '%' that is not one of the unit's %-fields becomes full-width ％.

Units are word-wrapped (proportional widths from tools/latinfont.py) to the box of
their block and checked: lines per page, the message buffer (window blocks), and the
whole message re-parsed must keep the Japanese structure.

usage:
    tl.py show  NN [from] [to] [--todo]  # print Japanese units (codes visible) to translate
    tl.py apply NN [batch.txt]     # merge batch into tl/msgNN.txt, validate, rebuild
                                   # script/msg/msgNN.json (no batch: tl/msgNN.txt only)
    tl.py stats                    # progress per block
"""
import collections, json, os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
import latinfont, msgfile, msgscript, setup, text

ROOT = setup.ROOT
TL = setup.TL

# Boxes per block: (width px, lines per page[, font, head lines]). Blocks not listed use FIT:
# each unit is wrapped to its widest Japanese line (at least the block's usual line width)
# and may not have more lines than the Japanese.
# Message window (measured 2026-11-08): wraps by pixels at 576 px, 3 lines a page, pages
# itself (meswin.py lifted the 72-character cap), so a unit may fill as many pages as its
# Japanese does when shown. Window-block units whose Japanese has more than 3 lines are
# panels (help, lists): FIT.
WINDOW = (576, 3)
WINDOW_BLOCKS = list(range(17)) + [21, 24]
BOXES = {n: WINDOW for n in WINDOW_BLOCKS}
# msg17-20 = officer bios (dates line, then a paragraph): CPersonInfoWin::DrawWindow, 22x24
# cells (half-width advance = latinfont width x 11/12, font 'bio'), wraps per character at
# x >= 242, max y 0x131 (about 11 rows of 28 px; 10 used until measured).
for _n in range(17, 21): BOXES[_n] = (242, 9, 'bio', 1)
# msg26-32 = help pages (DrawHelpMessage): 24 full-width columns, at most 10 lines in the
# Japanese. Not measured yet.
for _n in range(26, 33): BOXES[_n] = (576, 10, 'large', 0)
NOT_WINDOW = {}
ENTRY_BOXES = {}
STRICT = {}
STRICT_COLUMN = set()
UNIT_BYTES = 500          # CMessageManager expands a message into a 0x1FE-byte buffer
FULL_PX, HALF_PX = 24, 12  # full-width / half-width (kana) cells in the 24px font
VAR_PX, VAR_BYTES = 120, 20   # an inserted name or number ({02} print)
FIELD_PX, FIELD_BYTES = 40, 8  # %s-style field
FLOW_PX = 700             # wider Japanese lines are paragraphs the text object flows

KANA_TOGGLE = re.compile(rb'\x1b[KHk]')
FULL_LATIN = re.compile('[０-９Ａ-Ｚａ-ｚ]')

_W = {}
FONT = 'large'            # font of the box being wrapped (a 3rd element of a box sets it)

def widths():
    """Advances as the game draws them (vwf.width_fn: scaled by half/12 off the 12px cell)."""
    if FONT not in _W:
        half = {'bio': 11}.get(FONT, 12)
        _W[FONT] = {c: (g[1] * half * 2731 + 0x4000) >> 15 if half != 12 else g[1]
                    for c, g in latinfont.render('large').items()}
    return _W[FONT]

# ---------------------------------------------------------------- script access

def load(n):
    return json.load(open(setup.msg_json(n), encoding='utf-8'))

def save(n, rows):
    json.dump(rows, open(setup.msg_json(n), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

_ROWS = {}

def rows_of(n):
    if n not in _ROWS:
        _ROWS[n] = load(n)
    return _ROWS[n]

def target(lo, hi):
    """Message inserted by {01}C / {01}J lo hi -> (block, entry)."""
    i = lo | hi << 8
    return (0, i) if i < 1000 else (i // 1000, i % 1000)

# ---------------------------------------------------------------- measuring

def insert_size(code, depth=0):
    """(px, bytes) of an inline code when shown."""
    k = code[0]
    if k == 0x02:
        return VAR_PX, VAR_BYTES
    if k == 0x25:
        return FIELD_PX, FIELD_BYTES
    if k == 0x01 and len(code) == 4 and depth < 3:
        b, e = target(code[2], code[3])
        try:
            row = rows_of(b)[e]
        except (IndexError, FileNotFoundError):
            return 0, 0
        s = text.encode(row['en'] or row['jp'])
        toks, spans = msgscript.units(s)
        best = (0, 0)
        for a, z in spans:
            first = []
            for kind, t in toks[a:z]:
                if kind == 'nl':
                    break
                first.append((kind, t))
            best = max(best, measure(first, depth + 1))
        return best
    return 0, 0

def measure(toks, depth=0):
    """(px, bytes) of one line given as tokens."""
    px = nb = 0
    W = widths()
    for kind, t in toks:
        if kind == 'text':
            i = 0
            while i < len(t):
                c = t[i]
                if msgscript._sjis_lead(c) and i + 1 < len(t):
                    px += FULL_PX; nb += 2; i += 2
                    continue
                px += W.get(chr(c), HALF_PX) if c < 0x80 else HALF_PX
                nb += 1; i += 1
        elif kind == 'inline':
            p, b = insert_size(t, depth)
            px += p; nb += b
    return px, nb

def jp_px(toks):
    """Width of a Japanese line in the 24px font as the game shows it: half-width kana stand
    for full-width hiragana, the voicing marks combine with them."""
    px = 0
    for kind, t in toks:
        if kind == 'text':
            i = 0
            while i < len(t):
                c = t[i]
                if msgscript._sjis_lead(c) and i + 1 < len(t):
                    px += FULL_PX; i += 2; continue
                px += FULL_PX if 0xA1 <= c <= 0xDD else 0 if c in (0xDE, 0xDF) else HALF_PX
                i += 1
        elif kind == 'inline':
            px += insert_size(t)[0]
    return px

_ENDS = {}

def ends_line(code):
    """True if a {01}C/J insert's text ends with a newline (the line ends there)."""
    if not (code[0] == 0x01 and len(code) == 4):
        return False
    if code not in _ENDS:
        b, e = target(code[2], code[3])
        try:
            row = rows_of(b)[e]
        except (IndexError, FileNotFoundError):
            _ENDS[code] = False
            return False
        toks, spans = msgscript.units(text.encode(row['en'] or row['jp']))
        _ENDS[code] = any(toks[z - 1][0] == 'nl' for a, z in spans)
    return _ENDS[code]

def lines_of(toks):
    """Split tokens into display lines; a line ended by an insert that itself ends
    with a newline gets a ('soft', b'') marker (no newline is written after it)."""
    out, cur = [], []
    for kind, t in toks:
        if kind == 'nl':
            out.append(cur); cur = []
        else:
            cur.append((kind, t))
            if kind == 'inline' and ends_line(t):
                out.append(cur + [('soft', b'')]); cur = []
    return out + [cur]

def join_lines(lines):
    out = b''
    for i, l in enumerate(lines):
        out += b''.join(t for k, t in l)
        if i < len(lines) - 1 and not (l and l[-1][0] == 'soft'):
            out += b'\n'
    return out

# ---------------------------------------------------------------- wrapping

def words(toks):
    """Split a token line into words (lists of tokens) at ASCII spaces."""
    out, cur = [], []
    for kind, t in toks:
        if kind != 'text':
            cur.append((kind, t)); continue
        parts = t.split(b' ')
        for j, p in enumerate(parts):
            if j:
                out.append(cur); cur = []
            if p:
                cur.append(('text', p))
    out.append(cur)
    return [w for w in out if w]

def join(ws):
    toks = []
    for j, w in enumerate(ws):
        if j:
            toks.append(('text', b' '))
        toks += w
    return toks

def wrap(toks, width):
    """Word-wrap tokens (with 'nl' forced breaks) -> list of lines (token lists)."""
    out = []
    for para in lines_of(toks):
        line = []
        for w in words(para):
            if line and measure(join(line + [w]))[0] > width:
                out.append(join(line)); line = [w]
            else:
                line.append(w)
        out.append(join(line))
    return out

class Box:
    def __init__(self, n, rows):
        self.n = n
        self.fixed = BOXES.get(n)
        ws = []
        for r in rows:
            toks, spans = msgscript.units(text.encode(r['jp']))
            for a, z in spans:
                ls = lines_of(toks[a:z])
                if len(ls) > 1:
                    ws += [measure(l)[0] for l in ls if measure(l)[0] <= FLOW_PX]
        ws.sort()
        self.floor = ws[len(ws) * 3 // 4] if ws else 0
        self.column = 0
        if n in STRICT_COLUMN:
            for r in rows:
                if r['id'] in STRICT[n]:
                    toks, spans = msgscript.units(text.encode(r['jp']))
                    for a, z in spans:
                        ls = lines_of(toks[a:z])
                        if len(ls) == 1:
                            self.column = max(self.column, jp_px(ls[0]))

    def limits(self, jp_toks, entry=None):
        """(width px, max lines, lines per page or 0) for a unit."""
        jl = [measure(l)[0] for l in lines_of(jp_toks)]
        global FONT
        if entry in STRICT.get(self.n, ()):
            # wrapped in the 20px font at the Japanese width in that font: the English is
            # narrower than that in the 24px font too
            FONT = 'small'
            jl = [jp_px(l) for l in lines_of(jp_toks)]
            if len(jl) == 1 and self.column:
                return self.column * 20 // 24, 1, 0
            return max(jl) * 20 // 24, len(jl), 0
        fixed = next((b for r, b in ENTRY_BOXES.get(self.n, ()) if entry in r), None)
        if not fixed and entry not in NOT_WINDOW.get(self.n, ()):
            fixed = self.fixed
        FONT = fixed[2] if fixed and len(fixed) > 2 else 'large'
        if fixed:
            # the window wraps long lines itself: count the lines as shown
            w, page = fixed[:2]
            if len(fixed) > 2:          # a fixed panel: page = all the lines it holds
                head = fixed[3] if len(fixed) > 3 else 1
                return w, page + head, page  # + the dates line (bios), which goes to its own field
            shown = sum(max(1, -(-x // w)) for x in jl)
            return w, -(-shown // page) * page, page
        manual = [x for x in jl if x <= FLOW_PX]
        flowing = len(manual) < len(jl)
        return max([self.floor] + manual), 10 ** 6 if flowing else len(jl), 0

# ---------------------------------------------------------------- tl files

KEY = re.compile(r'@(\d+)(?:-(\d+))?(?:\.(\d+|\*))?\s*')

def parse_tl(path):
    """-> {key: text}, key as written without '@': '12', '12.3', '12.*' or '63-99.*'."""
    out, key, buf = {}, None, []
    def flush():
        if key is not None:
            out[key] = ' '.join(buf)
    for raw in open(path, encoding='utf-8'):
        line = raw.rstrip('\n')
        m = KEY.fullmatch(line)
        if m:
            flush()
            a, b, u = m.groups()
            if b and u != '*':
                sys.exit('%s: %s: a range needs .*' % (path, line))
            key = '%s%s%s' % (a, '-' + b if b else '', '.' + u if u and u != '0' else '')
            buf = []
        elif line.lstrip().startswith('#'):
            continue
        elif key is not None and line.strip():
            buf.append(line.strip())
    flush()
    return out

def _key_order(k):
    m = re.fullmatch(r'(\d+)(?:-(\d+))?(?:\.(\d+|\*))?', k)
    a, b, u = m.groups()
    return int(a), int(b or a), -1 if u == '*' else int(u or 0)

def expand(units, rows):
    """{key: text} -> {(entry, unit): text}; explicit units beat N.*, which beats ranges."""
    out = {}
    spec = sorted(units, key=lambda k: (('-' not in k) + ('*' not in k), _key_order(k)))
    for k in spec:
        a, b, u = _key_order(k)
        for e in range(a, (b if a == b else min(b, len(rows) - 1)) + 1):
            if u >= 0 or e >= len(rows):
                out[(e, max(u, 0))] = units[k]
            else:
                n = len(msgscript.units(text.encode(rows[e]['jp']))[1])
                for i in range(n):
                    out[(e, i)] = units[k]
    return out

def write_tl(path, new):
    """Merge {key: text} into a tl file: existing blocks are replaced in place (comments
    and order kept), new ones appended in key order."""
    lines = open(path, encoding='utf-8').read().split('\n') if os.path.exists(path) else []
    out, i, done = [], 0, set()
    while i < len(lines):
        m = KEY.fullmatch(lines[i])
        key = None
        if m:
            a, b, u = m.groups()
            key = '%s%s%s' % (a, '-' + b if b else '', '.' + u if u and u != '0' else '')
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
    for k in sorted(set(new) - done, key=_key_order):
        out += ['@' + k, new[k]]
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out) + '\n')

def english_bytes(src, jp_unit):
    """Batch text -> bytes: codes decoded, kana toggles dropped (a leading one is kept
    when the Japanese has it: it separates text from a number before it), '%' that
    is not one of the Japanese %-fields made full-width."""
    s = src.replace(' || ', '\n').replace('||', '\n').replace('\\n ', '\n').replace('\\n', '\n')
    s = s.replace('\\_', ' ').replace(' \n', '\n')
    b = text.encode(s)
    lead = KANA_TOGGLE.match(jp_unit)
    b = (lead.group() if lead else b'') + KANA_TOGGLE.sub(b'', b)
    fields = {t for k, t in msgscript.tokens(jp_unit) if k == 'inline' and t[:1] == b'%'}
    return b''.join(t if k != 'inline' or t[:1] != b'%' or t in fields else '％'.encode('cp932') + t[1:]
                    for k, t in msgscript.tokens(b))

# ---------------------------------------------------------------- validation

def code_str(t):
    """A code as written in tl/ files: printable ASCII as is, other bytes {XX}."""
    return ''.join(chr(c) if 0x20 <= c <= 0x7E and c not in (0x7B, 0x7D) else '{%02X}' % c for c in t)

def unit_str(toks):
    """Japanese unit for display: text decoded, codes via code_str, kana toggles dropped."""
    return ''.join(text.decode(t) if k in ('text', 'nl') else '' if KANA_TOGGLE.fullmatch(t) else code_str(t)
                   for k, t in toks)

def inline_codes(toks):
    return collections.Counter(t for k, t in toks if k == 'inline' and not KANA_TOGGLE.fullmatch(t))

DROPPABLE = (0x02, 0x25)

def check_unit(jp_toks, en):
    errs, warns = [], []
    try:
        et = msgscript.tokens(en)
    except msgscript.ParseError as e:
        return ['parse: %s' % e], warns, None
    bad = [t for k, t in et if k not in msgscript.INLINE]
    if bad:
        errs.append('structural code in English: %s' % ' '.join(code_str(t) for t in bad))
    jc, ec = inline_codes(jp_toks), inline_codes(et)
    extra = ec - jc
    for t in extra.elements():
        if t[0] == 0x02 and len(t) == 3:
            warns.append('added variable %s' % code_str(t))
        else:
            errs.append('code not in the Japanese: %s' % code_str(t))
    for t, n in (jc - ec).items():
        if t[0] == 0x01 and t[1] == 0x43 or t[0] in DROPPABLE:
            if t[0] == 0x02:
                warns.append('dropped variable %s' % code_str(t))
        else:
            errs.append('missing code %s' % code_str(t))
    if FULL_LATIN.search(en.decode('cp932', 'replace')):
        errs.append('full-width Latin/digits in English')
    return errs, warns, et

def build_entry(jp, units_en, box, tag, log):
    """Substitute English units into one message. -> en string ('' if none)."""
    global FONT
    jb = text.encode(jp)
    toks, spans = msgscript.units(jb)
    out = [t for k, t in toks]
    used = False
    for u, (a, z) in enumerate(spans):
        src = units_en.pop(u, None)
        if src is None:
            continue
        if src.strip() == '=':
            used = True
            continue
        jp_unit = b''.join(t for k, t in toks[a:z])
        try:
            en = english_bytes(src, jp_unit)
        except ValueError as e:
            log('%s.%d ERROR %s' % (tag, u, e), True); continue
        errs, warns, et = check_unit(toks[a:z], en)
        if et is None or errs:
            for e in errs:
                log('%s.%d ERROR %s' % (tag, u, e), True)
            for w in warns:
                log('%s.%d warn  %s' % (tag, u, w), False)
            continue
        width, max_lines, page = box.limits(toks[a:z], int(tag.split('@')[1]))
        lines = wrap(et, width)
        for i, l in enumerate(lines):
            px, nb = measure(l)
            if px > width:
                warns.append('line %d is %d px > %d' % (i + 1, px, width))
        strict = int(tag.split('@')[1]) in STRICT.get(box.n, ())
        if strict:
            errs += [w for w in warns if ' px > ' in w]
            warns = [w for w in warns if ' px > ' not in w]
            FONT = 'large'      # the same lines in the 24px font (spaces don't scale 20/24)
            for i, l in enumerate(lines):
                px = measure(l)[0]
                if px * 20 > width * 24 + 19:
                    errs.append('line %d is %d px > %d in the 24px font' % (i + 1, px, width * 24 // 20))
            FONT = 'small'
        nb = sum(measure(l)[1] + 1 for l in lines)
        if box.n in WINDOW_BLOCKS and nb > UNIT_BYTES:
            warns.append('%d bytes > %d (message buffer)' % (nb, UNIT_BYTES))
        if len(lines) > max_lines:
            (errs if strict else warns).append('%d lines > %d%s' % (len(lines), max_lines, ' (%d a page)' % page if page else ''))
        if errs:
            for e in errs:
                log('%s.%d ERROR %s' % (tag, u, e), True)
            for w in warns:
                log('%s.%d warn  %s' % (tag, u, w), False)
            continue
        for w in warns:
            log('%s.%d warn  %s' % (tag, u, w), False)
        new = join_lines(lines)
        for i in range(a, z):
            out[i] = b''
        out[a] = new
        used = True
    for u in units_en:
        log('%s.%d ERROR no such unit (entry has %d)' % (tag, u, len(spans)), True)
    if not used:
        return ''
    nb = b''.join(out)
    # the rebuilt message must parse to the same structure as the Japanese
    try:
        new_struct = [t for k, t in msgscript.tokens(nb) if k not in msgscript.INLINE]
    except msgscript.ParseError as e:
        log('%s ERROR rebuilt message does not parse: %s' % (tag, e), True)
        return ''
    if new_struct != [t for k, t in toks if k not in msgscript.INLINE]:
        log('%s ERROR English changes the message structure (text after a code eaten as '
            'its argument? a digit right after a condition number needs {1B}H before it)' % tag, True)
        return ''
    return text.decode(nb)

def apply(n, batch=None):
    path = os.path.join(TL, 'msg%02d.txt' % n)
    units = parse_tl(path) if os.path.exists(path) else {}
    if batch and os.path.abspath(batch) != os.path.abspath(path):
        new = parse_tl(batch)
        units.update(new)
        print('msg%02d: %d blocks from %s' % (n, len(new), batch))
    rows = load(n)
    _ROWS[n] = rows
    box = Box(n, rows)
    per = collections.defaultdict(dict)
    for (e, u), src in expand(units, rows).items():
        per[e][u] = src
    bad = []
    def log(msg, err):
        print(msg)
        if err:
            bad.append(msg)
    # two passes: an insert of a later entry of this block is measured as its English
    # from the first (silent) pass, not as its Japanese
    for r in rows:
        r['en'] = ''
    targets = {target(t[2], t[3])[1] for r in rows for k, t in msgscript.tokens(text.encode(r['jp']))
               if k == 'inline' and t[:2] == b'\x01C' and len(t) == 4 and target(t[2], t[3])[0] == n}
    first = {e: build_entry(rows[e]['jp'], dict(per[e]), box, 'msg%02d@%d' % (n, e), lambda m, err: None)
             for e in targets if e in per and e < len(rows)}
    for e, en in first.items():
        rows[e]['en'] = en
    for e, us in sorted(per.items()):
        if e >= len(rows):
            log('msg%02d@%d ERROR no such entry' % (n, e), True); continue
        rows[e]['en'] = build_entry(rows[e]['jp'], dict(us), box, 'msg%02d@%d' % (n, e), log)
    if bad and batch:
        print('msg%02d: %d errors: nothing written' % (n, len(bad)))
    else:
        save(n, rows)
        if batch and os.path.abspath(batch) != os.path.abspath(path):
            os.makedirs(TL, exist_ok=True)
            write_tl(path, new)
    total = sum(len(msgscript.units(text.encode(r['jp']))[1]) for r in rows)
    print('msg%02d: %d/%d units translated, %d errors' % (n, len(expand(units, rows)), total, len(bad)))
    return not bad

# ---------------------------------------------------------------- show / stats

def context(toks, a):
    """What leads to a unit: the structural code just before it."""
    for k, t in reversed(toks[:a]):
        if k == 'if':
            return 'if ' + text.decode(t[3:])
        if k == 'end':
            return 'else'
        if k == 'cmd':
            return text.decode(t)
        if k not in msgscript.INLINE:
            break
    return ''

TR5_MSG = os.path.expanduser('~/Projects/taiko_risshiden_5_translation/script/msg')
_TR5 = None

def tr5_hints():
    """{Japanese unit text (codes removed): TR5 English of that unit} from TR5's script/msg
    (same Koei wording; its insert codes differ, so the hint is a model, not a copy)."""
    global _TR5
    if _TR5 is None:
        _TR5 = {}
        if os.path.isdir(TR5_MSG):
            for f in sorted(os.listdir(TR5_MSG)):
                for r in json.load(open(os.path.join(TR5_MSG, f), encoding='utf-8')):
                    if not r['en']:
                        continue
                    try:
                        jt, js = msgscript.units(text.encode(r['jp']))
                        et, es = msgscript.units(text.encode(r['en']))
                    except (msgscript.ParseError, ValueError):
                        continue
                    if len(js) != len(es):
                        continue
                    for (a, z), (c, d) in zip(js, es):
                        key = b''.join(t for k, t in jt[a:z] if k == 'text')
                        _TR5.setdefault(key, unit_str(et[c:d]).replace('\n', '\\n'))
    return _TR5

def show(n, a=0, b=None, todo=False):
    rows = load(n)
    hints = tr5_hints()
    path = os.path.join(TL, 'msg%02d.txt' % n)
    done = expand(parse_tl(path), rows) if os.path.exists(path) else {}
    for r in rows[a:b]:
        toks, spans = msgscript.units(text.encode(r['jp']))
        for u, (x, z) in enumerate(spans):
            jp = unit_str(toks[x:z])
            ctx = context(toks, x)
            if todo and (r['id'], u) in done:
                continue
            print('@%d%s%s%s  %s' % (r['id'], '.%d' % u if u else '', ' [done]' if (r['id'], u) in done else '',
                                     '  # ' + ctx if ctx else '', jp.replace('\n', '⏎')))
            hint = hints.get(b''.join(t for k, t in toks[x:z] if k == 'text'))
            if hint:
                print('    TR5: ' + hint.replace('\n', '⏎'))

def stats():
    tot = done = 0
    for n in range(len(os.listdir(os.path.join(setup.SCRIPT, 'msg')))):
        rows = load(n)
        t = sum(len(msgscript.units(text.encode(r['jp']))[1]) for r in rows)
        path = os.path.join(TL, 'msg%02d.txt' % n)
        d = len(expand(parse_tl(path), rows)) if os.path.exists(path) else 0
        tot += t; done += d
        print('msg%02d %5d/%5d' % (n, d, t))
    print('total %d/%d units' % (done, tot))

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'show':
        args = [a for a in sys.argv[2:] if a != '--todo']
        show(int(args[0]), *(int(x) for x in args[1:3]), todo='--todo' in sys.argv)
    elif cmd == 'apply':
        sys.exit(0 if apply(int(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else None) else 1)
    elif cmd == 'stats':
        stats()
    else:
        sys.exit(__doc__)
