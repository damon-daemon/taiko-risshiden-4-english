"""Person names: Japanese from the disc, English from tl/names_persons.json.

Runtime names live in the scenario files (TR4DATA 62-68 = scenarios 1-7, ILNK subfile
10): 735 x 32 bytes, family[9] | given[9] | 14 bytes unused (zero in every scenario).
CPersonElement::LoadScenario 0x3048B0 reads them into this+0x1883C (the table is saved
and loaded as one 0x5BE0-byte block); person+4 points to the record (CPerson::Initialize).
Ids: 0-649 officers (CBushou), 650-707 other people (CPersonNormal), 708-734 roles
(gatekeeper, innkeeper...). Readings: subfile 9, 708 x 48 bytes, family reading[9] |
given reading[9] (half-width kana) | data; person+8 points to it (kept Japanese).

English layout: family at +0 and given at **+16**, 15 bytes + NUL each (the given name
moves into the unused bytes). Every reader of the given name at +9 is patched (found by
scanning for `lw x,4(obj)` .. `addiu y,x,9` and `jal getter; lw v0,4(v0); addiu y,v0,9`;
the other +9 hits are lord flag bytes):
  NewExtractMessageCore 0x1ADE00 (event text), ActChangeName 0x1C1248 (event rename,
  copy lengths 9/7 -> 16/16), MakeNewBushouName 0x1DE234 / 0x1DE33C, save header
  SetScenarioData 0x1EBB48, CMPHouse::SelectMPCommand 0x2E3398, message field
  dwGetPersonParam 0x36E380; CPerson::strGetFullName 0x304110 is rewritten in place:
  family + ' ' + given (no space when a part is empty).
Event renames (木下藤吉郎 -> 羽柴秀吉) copy names from the event scripts: Japanese
until the events are translated.

tl/names_persons.json: [{"id": n, "en": [family, given], "s3": [..] override}, ...]
(s1-s7 = scenarios 1-7). `init` builds it once from TR5's English (exact pairs, then
parts) and the readings (Hepburn, long vowels short); edit it by hand afterwards.

usage: names.py export | init
"""
import collections, json, os, re, struct, sys, unicodedata

sys.path.insert(0, os.path.dirname(__file__))
import datafile
from asm import assemble, hi, lo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL = os.path.join(ROOT, 'tl', 'names_persons.json')
SCRIPT = os.path.join(ROOT, 'script', 'names_persons.json')
TR5 = os.path.expanduser('~/Projects/taiko_risshiden_5_translation')
SCENARIOS = range(62, 69)            # TR4DATA entries of scenarios 1-7
SUB, REC, COUNT = 10, 32, 735
READ_SUB, READ_REC, READ_COUNT = 9, 48, 708
GIVEN = 16                           # new offset of the given name in a record
ROOM = 15                            # bytes per part (+ NUL)

BASE, FOFF = 0x100000, 0x80
GIVEN_SITES = [0x1ADE00, 0x1C1248, 0x1DE234, 0x1DE33C, 0x1EBB48, 0x2E3398, 0x36E380]
CHANGE_LEN = [(0x1C1234, 9), (0x1C124C, 7)]  # addiu a2, zero, n: szStrNCpy family / given
FULL_NAME = 0x304110                 # CPerson::strGetFullName, 0x304110-0x3041AC
FULL_END = 0x3041B0
RING, GET_BUFFER, STRCAT = 0x53F470, 0x36BD20, 0x385DA0

def field(b):
    return b.split(b'\0')[0].decode('cp932', 'replace')

def ilnk_sub(entry, k):
    n = struct.unpack_from('<I', entry, 4)[0]
    offs = [struct.unpack_from('<I', entry, 8 + 4 * i)[0] for i in range(n)] + [len(entry)]
    return offs[k], offs[k + 1]

def scenario_names(entry):
    a, b = ilnk_sub(entry, SUB)
    assert b - a == COUNT * REC
    return [(field(entry[a + i * REC:a + i * REC + 9]), field(entry[a + i * REC + 9:a + i * REC + 18]))
            for i in range(COUNT)]

def readings(entry):
    a, b = ilnk_sub(entry, READ_SUB)
    assert b - a == READ_COUNT * READ_REC
    return [(field(entry[a + i * READ_REC:a + i * READ_REC + 9]),
             field(entry[a + i * READ_REC + 9:a + i * READ_REC + 18])) for i in range(READ_COUNT)]

def disc_names(data, elf):
    """{scenario 1-7: [(family, given)] x 735}, readings of scenario 1."""
    names = {s + 1: scenario_names(datafile.entry(data, elf, e)) for s, e in enumerate(SCENARIOS)}
    return names, readings(datafile.entry(data, elf, SCENARIOS[0]))

# ---------------------------------------------------------------- romanization

KANA = {
    'きゃ': 'kya', 'きゅ': 'kyu', 'きょ': 'kyo', 'しゃ': 'sha', 'しゅ': 'shu', 'しょ': 'sho',
    'ちゃ': 'cha', 'ちゅ': 'chu', 'ちょ': 'cho', 'にゃ': 'nya', 'にゅ': 'nyu', 'にょ': 'nyo',
    'ひゃ': 'hya', 'ひゅ': 'hyu', 'ひょ': 'hyo', 'みゃ': 'mya', 'みゅ': 'myu', 'みょ': 'myo',
    'りゃ': 'rya', 'りゅ': 'ryu', 'りょ': 'ryo', 'ぎゃ': 'gya', 'ぎゅ': 'gyu', 'ぎょ': 'gyo',
    'じゃ': 'ja', 'じゅ': 'ju', 'じょ': 'jo', 'ぢゃ': 'ja', 'ぢゅ': 'ju', 'ぢょ': 'jo',
    'びゃ': 'bya', 'びゅ': 'byu', 'びょ': 'byo', 'ぴゃ': 'pya', 'ぴゅ': 'pyu', 'ぴょ': 'pyo',
    'あ': 'a', 'い': 'i', 'う': 'u', 'え': 'e', 'お': 'o',
    'か': 'ka', 'き': 'ki', 'く': 'ku', 'け': 'ke', 'こ': 'ko',
    'さ': 'sa', 'し': 'shi', 'す': 'su', 'せ': 'se', 'そ': 'so',
    'た': 'ta', 'ち': 'chi', 'つ': 'tsu', 'て': 'te', 'と': 'to',
    'な': 'na', 'に': 'ni', 'ぬ': 'nu', 'ね': 'ne', 'の': 'no',
    'は': 'ha', 'ひ': 'hi', 'ふ': 'fu', 'へ': 'he', 'ほ': 'ho',
    'ま': 'ma', 'み': 'mi', 'む': 'mu', 'め': 'me', 'も': 'mo',
    'や': 'ya', 'ゆ': 'yu', 'よ': 'yo', 'ら': 'ra', 'り': 'ri', 'る': 'ru', 'れ': 're', 'ろ': 'ro',
    'わ': 'wa', 'ゐ': 'i', 'ゑ': 'e', 'を': 'o', 'ん': 'n',
    'が': 'ga', 'ぎ': 'gi', 'ぐ': 'gu', 'げ': 'ge', 'ご': 'go',
    'ざ': 'za', 'じ': 'ji', 'ず': 'zu', 'ぜ': 'ze', 'ぞ': 'zo',
    'だ': 'da', 'ぢ': 'ji', 'づ': 'zu', 'で': 'de', 'ど': 'do',
    'ば': 'ba', 'び': 'bi', 'ぶ': 'bu', 'べ': 'be', 'ぼ': 'bo',
    'ぱ': 'pa', 'ぴ': 'pi', 'ぷ': 'pu', 'ぺ': 'pe', 'ぽ': 'po',
    'ぁ': 'a', 'ぃ': 'i', 'ぅ': 'u', 'ぇ': 'e', 'ぉ': 'o', 'ー': '',
}

def hiragana(s):
    s = unicodedata.normalize('NFKC', s)
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)

def romaji(kana):
    """Hepburn, long vowels written short (ou/oo -> o, uu -> u)."""
    kana = hiragana(kana)
    out, i = '', 0
    while i < len(kana):
        if kana[i] == 'っ' and i + 1 < len(kana):
            nxt = KANA.get(kana[i + 1:i + 3]) or KANA.get(kana[i + 1], '')
            out += 't' if nxt.startswith('ch') else nxt[:1]
            i += 1
            continue
        two = KANA.get(kana[i:i + 2])
        if two:
            out += two
            i += 2
            continue
        out += KANA.get(kana[i], kana[i])
        i += 1
    out = re.sub('ou(?![aiueo])|oo', 'o', out)
    out = re.sub('uu', 'u', out)
    return out.capitalize()

# ---------------------------------------------------------------- tl file

def load_tl():
    return {r['id']: r for r in json.load(open(TL, encoding='utf-8'))}

def english(rec, scen):
    return rec.get('s%d' % scen, rec['en'])

# Names that are not in TR5 or have no reading (roles, foreigners, women, ninja chiefs).
MANUAL = {
    599: ['New', 'Officer'],
    655: ['', 'Frois'], 656: ['', 'Almeida'], 671: ['', 'Miranda'], 672: ['', 'Enrique'],
    668: ['', 'Lady Yodo'], 670: ['', 'Emperor'], 673: ['', 'Sanboshi'], 674: ['', 'Nene'],
    675: ['', 'Naka'], 676: ['', 'Oichi'], 677: ['', 'Matsu'], 678: ['Izumo no', 'Okuni'],
    679: ['', 'Ginchiyo'], 680: ['', 'Megohime'], 681: ['', 'Yoshihime'], 682: ['', 'Gohime'],
    683: ['', 'Tama'], 684: ['', 'Kicho'], 685: ['', 'Lady Tsukiyama'], 686: ['', 'Tokuhime'],
    687: ['', 'Sae'], 688: ['', 'Hatsu'], 689: ['', 'Tsu'], 690: ['', 'Kinu'], 691: ['', 'Shino'],
    692: ['', 'Aya'], 693: ['', 'Suzu'], 694: ['', 'Yae'], 695: ['', 'Ito'],
    696: ['Kurohabaki', 'Jonin'], 697: ['Fuma', 'Jonin'], 698: ['Suppa', 'Jonin'],
    699: ['Iga', 'Jonin'], 700: ['Nokizaru', 'Jonin'], 701: ['Koga', 'Jonin'],
    702: ['Gaibun', 'Jonin'], 703: ['Yamakuguri', 'Jonin'],
    704: ['', 'Monk'], 705: ['', 'Merchant'], 706: ['', 'Ninja'], 707: ['', 'Head Clerk'],
    708: ['', 'Gatekeeper'], 709: ['', 'Rice Dealer'], 710: ['', 'Horse Dealer'],
    711: ['', 'Tavern Keeper'], 712: ['', 'Innkeeper'], 713: ['', 'Farmer'],
    714: ['', 'Farm Woman'], 715: ['', 'Townsman'], 716: ['', 'Townswoman'],
    717: ['', 'Merchant'], 718: ['', 'Monk'], 719: ['', 'Dojo Master'], 720: ['', 'Courtier'],
    721: ['', 'Ninja'], 722: ['', 'Ashigaru'], 723: ['', 'Traveler'], 724: ['', 'Drunk Man'],
    725: ['', 'Drunk Woman'], 726: ['', 'Shady Girl'], 727: ['', 'Kunoichi'],
    728: ['', 'Peddler'], 729: ['', 'Page'], 730: ['', 'Bodyguard'], 731: ['', 'Bandit'],
    732: ['', 'Jonin'], 733: ['', 'Unit Leader'], 734: ['', 'Guild Boss'],
}

def init(data, elf):
    """Write tl/names_persons.json from TR5's English and the readings (once)."""
    if os.path.exists(TL):
        sys.exit('%s exists: edit it by hand' % TL)
    jp5 = json.load(open(os.path.join(TR5, 'script', 'names_persons.json'), encoding='utf-8'))
    en5 = {r['id']: r for r in json.load(open(os.path.join(TR5, 'tl', 'names_persons.json'), encoding='utf-8'))}
    pair, fam, giv = {}, collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    for r in jp5:
        e = en5.get(r['id'])
        if not e:
            continue
        for s, (f, g) in sorted(r['jp'].items()):
            en = e.get(s, e['en'])
            pair.setdefault((f, g), en)
            if f and en[0]:
                fam[f][en[0]] += 1
            if g and en[1]:
                giv[g][en[1]] += 1
    names, reads = disc_names(data, elf)
    stats = collections.Counter()
    def guess(i, f, g):
        if (f, g) in pair:
            stats['pair'] += 1
            return list(pair[(f, g)])
        rf, rg = reads[i] if i < READ_COUNT else ('', '')
        ef = fam[f].most_common(1)[0][0] if f in fam else romaji(rf) if rf else ''
        eg = giv[g].most_common(1)[0][0] if g in giv else romaji(rg) if rg else ''
        stats['parts' if f in fam and g in giv else 'reading'] += 1
        return [ef, eg]
    out = []
    for i in range(COUNT):
        per = {s: (MANUAL[i] if i in MANUAL else guess(i, *names[s][i])) for s in names}
        base = collections.Counter(tuple(v) for v in per.values()).most_common(1)[0][0]
        rec = {'id': i, 'en': list(base)}
        for s, v in per.items():
            if tuple(v) != base:
                rec['s%d' % s] = v
        out.append(rec)
    os.makedirs(os.path.dirname(TL), exist_ok=True)
    with open(TL, 'w', encoding='utf-8') as f:
        f.write('[\n' + ',\n'.join(json.dumps(r, ensure_ascii=False) for r in out) + '\n]\n')
    print('%s: %d persons (%s)' % (TL, len(out), dict(stats)))

def export(data, elf):
    names, reads = disc_names(data, elf)
    tl = load_tl() if os.path.exists(TL) else {}
    out = []
    for i in range(COUNT):
        r = {'id': i, 'jp': {'s%d' % s: list(names[s][i]) for s in names}}
        if i < READ_COUNT:
            r['reading'] = list(reads[i])
        if i in tl:
            r['en'] = {'s%d' % s: english(tl[i], s) for s in names}
        out.append(r)
    os.makedirs(os.path.dirname(SCRIPT), exist_ok=True)
    json.dump(out, open(SCRIPT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('%s: %d persons' % (SCRIPT, len(out)))

# ---------------------------------------------------------------- build

def _off(va):
    return va - BASE + FOFF

def _word(elf, va):
    return struct.unpack_from('<I', elf, _off(va))[0]

def _put(elf, va, b):
    elf[_off(va):_off(va) + len(b)] = b

def full_name_code(space):
    return assemble(FULL_NAME, [
        ('addiu', 'sp', 'sp', -0x30),
        ('sq', 'ra', 32, 'sp'),
        ('sq', 's1', 16, 'sp'),
        ('sq', 's0', 0, 'sp'),
        ('addu', 's1', 'a0', 'zero'),
        ('lui', 'a0', hi(RING)),
        ('jal', GET_BUFFER),
        ('addiu', 'a0', 'a0', lo(RING)),
        ('addu', 's0', 'v0', 'zero'),         # strGetBuffer leaves it empty
        ('lw', 'a1', 4, 's1'),
        ('jal', STRCAT),                      # family
        ('addu', 'a0', 's0', 'zero'),
        ('lw', 'v0', 4, 's1'),
        ('lbu', 'v1', 0, 'v0'),
        ('beqz', 'v1', 'given'),
        ('lbu', 'v1', GIVEN, 'v0'),
        ('beqz', 'v1', 'given'),
        ('lui', 'a1', hi(space)),
        ('addu', 'a0', 's0', 'zero'),
        ('jal', STRCAT),                      # ' '
        ('addiu', 'a1', 'a1', lo(space)),
        'given:',
        ('lw', 'a1', 4, 's1'),
        ('addiu', 'a1', 'a1', GIVEN),
        ('jal', STRCAT),
        ('addu', 'a0', 's0', 'zero'),
        ('addu', 'v0', 's0', 'zero'),
        ('lq', 'ra', 32, 'sp'),
        ('lq', 's1', 16, 'sp'),
        ('lq', 's0', 0, 'sp'),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 0x30),
    ])

def records(entry, scen, tl):
    """Scenario entry with English name records (Japanese kept where tl has none)."""
    e = bytearray(entry)
    a, _ = ilnk_sub(e, SUB)
    errors = []
    for i, (f, g) in enumerate(scenario_names(entry)):
        if i in tl:
            ef, eg = english(tl[i], scen)
            bf, bg = ef.encode('ascii'), eg.encode('ascii')
        else:
            bf, bg = f.encode('cp932'), g.encode('cp932')
        for b in (bf, bg):
            if len(b) > ROOM:
                errors.append('person %d s%d: %r is %d bytes > %d' % (i, scen, b, len(b), ROOM))
        e[a + i * REC:a + (i + 1) * REC] = bf[:ROOM].ljust(GIVEN, b'\0') + bg[:ROOM].ljust(REC - GIVEN, b'\0')
    return bytes(e), errors

def apply(elf, data, seg):
    """Patch the given-name readers; -> {entry: bytes} with English records."""
    for va in GIVEN_SITES:
        w = _word(elf, va)
        assert w >> 26 == 0x09 and w & 0xFFFF == 9, hex(va)
        _put(elf, va, struct.pack('<I', (w & 0xFFFF0000) | GIVEN))
    for va, n in CHANGE_LEN:
        assert _word(elf, va) == 0x24060000 | n, hex(va)
        _put(elf, va, assemble(va, [('addiu', 'a2', 'zero', ROOM + 1)]))
    space = seg.add(b' \0', 4)
    code = full_name_code(space)
    assert len(code) <= FULL_END - FULL_NAME
    _put(elf, FULL_NAME, code.ljust(FULL_END - FULL_NAME, b'\0'))
    tl = load_tl()
    changes, errors = {}, []
    for s, ent in enumerate(SCENARIOS):
        new, err = records(datafile.entry(data, elf, ent), s + 1, tl)
        changes[ent] = new
        errors += err
    if errors:
        sys.exit('names:\n' + '\n'.join(errors))
    return changes

if __name__ == '__main__':
    import cdimage, disc
    img = cdimage.Image(disc.CLEAN)
    recs = img.records()
    elf = img.read_file(disc.ELF, recs)
    data = img.read_file(disc.DATA, recs)
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'init':
        init(data, elf)
    elif cmd == 'export':
        export(data, elf)
    else:
        sys.exit(__doc__)
