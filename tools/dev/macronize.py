"""Apply Hepburn macrons (ō ū Ō Ū) across the English text, as in the Oda Nobunaga-den project.

Tokens come from three sources:
  - person names: the game's kana readings (script/names_persons.json) romanized with long
    vowels; a part is changed only when the result minus macrons equals the current English;
  - footholds: the readings of the foothold table (script/tables/footholds.json), same rule;
  - MANUAL below: provinces, regions, clans, terms, temples, and the readings the rule misses.
A token -> (replacement, REQUIRE, KEEP): replaced only when the Japanese of the same record
contains one of REQUIRE (None = always); left alone when it contains one of KEEP; otherwise
reported. Glyphs: tools/latinfont.py MACRONS (spare ASCII codes), text.FOLD in the encoders.

usage: .venv/bin/python tools/dev/macronize.py [--apply]     (dry run without --apply)
"""
import collections, glob, json, os, re, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import names

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
A = None


def mac(kana):
    k = names.hiragana(kana)
    out, i = '', 0
    while i < len(k):
        if k[i] == 'ー':
            out += '-'
            i += 1
            continue
        if k[i] == 'っ' and i + 1 < len(k):
            nxt = names.KANA.get(k[i + 1:i + 3]) or names.KANA.get(k[i + 1], '')
            out += 't' if nxt.startswith('ch') else nxt[:1]
            i += 1
            continue
        two = names.KANA.get(k[i:i + 2])
        if two:
            out += two
            i += 2
            continue
        out += names.KANA.get(k[i], k[i])
        i += 1
    out = re.sub('([ou])-', lambda m: {'o': 'ō', 'u': 'ū'}[m.group(1)], out).replace('-', '')
    out = re.sub('ou(?![aieo])|oo', 'ō', out)
    out = re.sub('uu', 'ū', out)
    return out[:1].upper() + out[1:]


def plain(s):
    return s.translate(str.maketrans('ōūŌŪ', 'ouOU'))


# Ambiguous plain forms: (kanji that select the macron form, kanji that keep the plain one)
AMBIG = {
    'Mori': (('毛利',), ('森',)), 'Ono': (('大野',), ('小野',)), 'Koga': (('甲賀',), ('古河', '古賀')),
    'Ota': (('太田', '大田'), ()), 'Kono': (('河野',), ()), 'Yuki': (('結城',), ()),
    'Cho': (('長',), ()), 'Tsu': (('つう', 'ﾂｳ'), ('津',)), 'Toyama': (('遠山',), ('富山',)), 'Hyogo': (('兵庫',), ()),
    'Ito': (('伊東', '伊藤'), ('伊都',)), 'Soma': (('相馬',), ()), 'Indo': (('犬童',), ()),
    'Kato': (('加藤',), ()), 'Goto': (('後藤',), ()), 'Endo': (('遠藤',), ()),
    'Oura': (('大浦',), ()), 'Kano': (('狩野', '加納'), ('鹿野',)),
}

MANUAL = {
    # persons the reading rule misses (ou + vowel) or where TR5 reads differently
    'Ando': 'Andō', 'Anegakoji': 'Anegakōji', 'Shoun': 'Shōun', 'Joki': 'Jōki', 'Sojin': 'Sōjin',
    'Soeki': 'Sōeki', 'Koetsu': 'Kōetsu', 'Sanboshi': 'Sanbōshi', 'Rikyu': 'Rikyū', 'Nohime': 'Nōhime',
    # provinces / regions / cities
    'Kyoto': 'Kyōto', 'Osaka': 'Ōsaka', 'Omi': 'Ōmi', 'Kozuke': 'Kōzuke', 'Totomi': 'Tōtōmi',
    'Etchu': 'Etchū', 'Bitchu': 'Bitchū', 'Hoki': 'Hōki', 'Suo': 'Suō', 'Hyuga': 'Hyūga',
    'Osumi': 'Ōsumi', 'Shimosa': 'Shimōsa', 'Chugoku': 'Chūgoku', 'Kyushu': 'Kyūshū',
    'Kanto': 'Kantō', 'Tohoku': 'Tōhoku', 'Tokai': 'Tōkai', 'Tokaido': 'Tōkaidō', 'Koshin': 'Kōshin',
    'Nakasendo': 'Nakasendō', 'Sanyo': "San'yō", "San'yo": "San'yō", 'Sanin': "San'in",
    'Kofu': 'Kōfu', 'Otsu': 'Ōtsu', 'Ogaki': 'Ōgaki', 'Fuchu': 'Fuchū', 'Hachioji': 'Hachiōji',
    'Koriyama': 'Kōriyama', 'Ichijodani': 'Ichijōdani', 'Kitanosho': 'Kitanoshō', 'Nijo': 'Nijō',
    'Ryukyu': 'Ryūkyū', 'Tokyo': 'Tōkyō', 'Shoryuji': 'Shōryūji',
    # eras / terms
    'Tensho': 'Tenshō', 'Keicho': 'Keichō',
    'Koji': ('Kōji', ('弘治', '麹'), ()), 'Nihongo': 'Nihongō', 'Fudo': 'Fudō', 'Myoo': 'Myōō', 'Ikko': 'Ikkō', 'Jonin': 'Jōnin',
    'shogun': 'shōgun', 'Shogun': 'Shōgun', 'shogunate': 'shōgunate', 'Shogunate': 'Shōgunate',
    'daimyo': 'daimyō', 'Daimyo': 'Daimyō', 'daimyos': 'daimyōs', 'Daimyos': 'Daimyōs',
    'ronin': 'rōnin', 'Ronin': 'Rōnin', 'Taishogun': 'Taishōgun',
    'Hokoku': 'Hōkoku', 'sojutsu': 'sōjutsu', 'jujutsu': 'jūjutsu',
    'Yagyu': 'Yagyū', 'Shinkage-ryu': 'Shinkage-ryū', 'ryu': 'ryū', 'Ittoryu': 'Ittōryū',
    # temples (Oda project convention: hyphen before -ji)
    'Honnoji': 'Honnō-ji', 'Honganji': 'Hongan-ji', 'Enryakuji': 'Enryaku-ji',
    'Kofukuji': 'Kōfuku-ji', 'Todaiji': 'Tōdai-ji', 'Horyuji': 'Hōryū-ji', 'Myoshinji': 'Myōshin-ji',
    'Daitokuji': 'Daitoku-ji', 'Nanzenji': 'Nanzen-ji', 'Tofukuji': 'Tōfuku-ji', 'Ninnaji': 'Ninna-ji',
    'Kenninji': 'Kennin-ji', 'Myokakuji': 'Myōkaku-ji', 'Hokoji': 'Hōkō-ji', 'Zuiryuji': 'Zuiryū-ji',
}


def build():
    """-> {plain token: (form, require, keep)}, report lines"""
    D, rep = {}, []
    forms = collections.defaultdict(set)
    for r in json.load(open(os.path.join(ROOT, 'script', 'names_persons.json'), encoding='utf-8')):
        if 'reading' not in r or 'en' not in r:
            continue
        for p in range(2):
            rd, e, jp = r['reading'][p], r['en']['s1'][p], r['jp']['s1'][p]
            if rd and e:
                m = mac(rd)
                if m != e and plain(m) == e:
                    forms[e].add((m, jp))
    fh = load_table('footholds')
    for row in json.load(open(os.path.join(ROOT, 'script', 'tables', 'footholds.json'), encoding='utf-8'))['rows']:
        e = fh.get(row['id'])
        if e and row.get('reading'):
            m = mac(row['reading'])
            if m != e and plain(m) == e:
                forms[e].add((m, row['jp']))
    for e, s in forms.items():
        ms = {m for m, j in s}
        if len(ms) > 1:
            rep.append('conflict %s: %s' % (e, sorted(s)))
            continue
        m = ms.pop()
        if e in AMBIG:
            D[e] = (m,) + AMBIG[e]
        else:
            D[e] = (m, A, ())
    for k, v in MANUAL.items():
        D[k] = v if isinstance(v, tuple) else ((v,) + AMBIG[k] if k in AMBIG else (v, A, ()))
    return D, rep


def load_table(name):
    out = {}
    for line in open(os.path.join(ROOT, 'tl', 'tables', name + '.txt'), encoding='utf-8'):
        if line.startswith('#') or '\t' not in line:
            continue
        i, en = line.rstrip('\n').split('\t', 1)
        out[int(i)] = en
    return out


class Sub:
    def __init__(self, D):
        self.D = D
        self.pat = re.compile(r'(?:(?<![A-Za-zōūŌŪ\'-])|(?<=\\n))(' +
                              '|'.join(sorted(map(re.escape, D), key=len, reverse=True)) + r')(?![A-Za-zōūŌŪ])')
        self.counts, self.flags = collections.Counter(), []

    def __call__(self, s, jp, where):
        def rep(m):
            t = m.group(1)
            new, req, keep = self.D[t]
            if keep and any(k in jp for k in keep):
                return t
            if req is not None and not any(k in jp for k in req):
                self.flags.append('%s: %s (not changed; source has no %s)' % (where, t, '/'.join(req)))
                return t
            self.counts[t] += 1
            return new
        return self.pat.sub(rep, s)


def msg_jp(n):
    rows = json.load(open(os.path.join(ROOT, 'script', 'msg', 'msg%02d.json' % n), encoding='utf-8'))
    return {r['id']: r['jp'] for r in rows}


KEY = re.compile(r'@(\d+)(?:-(\d+))?(?:\.(\d+|\*))?')


def do_msg(sub, path, n):
    jps = msg_jp(n)
    out, jp = [], ''
    for line in open(path, encoding='utf-8'):
        m = KEY.fullmatch(line.rstrip('\n'))
        if m:
            a, b = int(m.group(1)), int(m.group(2) or m.group(1))
            jp = ''.join(jps.get(i, '') for i in range(a, b + 1))
            out.append(line)
        elif line.lstrip().startswith('#'):
            out.append(line)
        else:
            out.append(sub(line, jp, '%s %s' % (os.path.basename(path), line[:40].strip())))
    return ''.join(out)


def do_tsv(sub, path, jps):
    out = []
    for line in open(path, encoding='utf-8'):
        if line.startswith('#') or '\t' not in line:
            out.append(line)
            continue
        k, en = line.split('\t', 1)
        out.append(k + '\t' + sub(en, jps.get(k, ''), '%s %s' % (os.path.basename(path), k)))
    return ''.join(out)


def do_names(sub, path):
    jp = {r['id']: r for r in json.load(open(os.path.join(ROOT, 'script', 'names_persons.json'), encoding='utf-8'))}
    recs = json.load(open(path, encoding='utf-8'))
    for r in recs:
        j = ''.join(''.join(v) for v in jp[r['id']]['jp'].values())
        for k, v in r.items():
            if k != 'id':
                r[k] = [sub(x, j, 'person %d' % r['id']) for x in v]
    return '[\n' + ',\n'.join(json.dumps(r, ensure_ascii=False) for r in recs) + '\n]\n'


def main():
    apply = '--apply' in sys.argv
    D, rep = build()
    sub = Sub(D)
    new = {}
    for p in sorted(glob.glob(os.path.join(ROOT, 'tl', 'msg*.txt'))):
        new[p] = do_msg(sub, p, int(os.path.basename(p)[3:5]))
    elf = {r['va']: r['jp'] for r in json.load(open(os.path.join(ROOT, 'script', 'elfstr.json'), encoding='utf-8'))}
    new[os.path.join(ROOT, 'tl', 'elfstr.txt')] = do_tsv(sub, os.path.join(ROOT, 'tl', 'elfstr.txt'), elf)
    for p in sorted(glob.glob(os.path.join(ROOT, 'tl', 'tables', '*.txt'))):
        name = os.path.basename(p)[:-4]
        rows = json.load(open(os.path.join(ROOT, 'script', 'tables', name + '.json'), encoding='utf-8'))['rows']
        new[p] = do_tsv(sub, p, {str(r['id']): r['jp'] for r in rows})
    p = os.path.join(ROOT, 'tl', 'names_persons.json')
    new[p] = do_names(sub, p)
    p = os.path.join(ROOT, 'notes', 'glossary.md')
    new[p] = ''.join(sub(l, l, 'glossary') for l in open(p, encoding='utf-8'))   # lines hold the Japanese
    for line in rep:
        print(line)
    for f in sorted(set(sub.flags)):
        print('FLAG', f)
    print('%d replacements, %d tokens used of %d' % (sum(sub.counts.values()), len(sub.counts), len(D)))
    for t, c in sub.counts.most_common():
        print('  %s -> %s: %d' % (t, D[t][0], c))
    changed = [p for p, s in new.items() if s != open(p, encoding='utf-8').read()]
    print('%d files change' % len(changed))
    if apply:
        for p in changed:
            open(p, 'w', encoding='utf-8').write(new[p])
        print('written')

if __name__ == '__main__':
    main()
