"""TAI5MSG message grammar: split a message into text and control codes.

Worked out from the message interpreter (0x347940 reads a character, 0x347A60
handles bytes < 0x20) and the expression evaluator of the game's message object
(vtable 0x64C940). Bytes >= 0x20 are text, except where a code consumes them as
arguments:

  0A                  newline              08 09        passed to the renderer
  1B x  1A x          x = K/k/H kana mode, C/V/W renderer codes ({1B}C<digit> = colour)
  01 C lo hi          insert message lo|hi<<8 (< 1000: msg00 entry, else block
                      id//1000 entry id%1000) and continue here
  01 J lo hi          continue with that message instead
  01 S expr           pick variant number expr of the following END-terminated variants
  01 M 02 x expr      register x = expr     01 R expr     return value
  01 F x [expr]       expr only if x = 'd'  01 other      that byte only
  05 05 04 cond       IF: when cond is false skip to the matching END
  05 05 05            END: return from the message (or from the current IF body)
  05 (anything else)  end of message
  02 ...              print an expression (other bytes < 0x20 do nothing)
  % [digits] [letter] printf-style field filled in by the caller (the renderer treats
                      '%' as a control character: English text uses full-width ％)

  expr = term (03 op term)*        cond = cmp (06 &| cmp)*
  cmp  = expr (04 op expr)?        op = = ! < > { }
  term = 02 x [field]   x = 01-84 (persons, castles, items, registers...): field
                        is the next byte if it is >= 0x20
       | 02 C8 f args   function f (0x64-0x96): 1 or 2 expression arguments
       | 02 x           any other x
       | % digits  |  digit digits     a number (at most 10 more digits)
       | any other byte (consumed, value 0)

A message is a block: (IF cond block)* text END. Text runs between structural codes
(IF/cond, END, S/M/R/F) are the translatable units; inline codes (02 prints, 01 C/J,
1B/1A, 08, 09, stray control bytes) stay inside them.
"""

class ParseError(ValueError):
    pass

# functions 02 C8 f: number of expression arguments (handler 0x2F7710, table 0x5914F0)
FUNC_ARGS = {**{f: 2 for f in range(0x6E, 0x92)}, 0x64: 1, 0x65: 1, 0x8B: 1, 0x96: 1}

def _var_cat(x):
    if 1 <= x <= 0x82 or x in (0x83, 0x84):
        return 'var'
    return 'func' if x == 0xC8 else None

class _Reader:
    def __init__(self, b):
        self.b, self.i = b, 0

    def get(self):
        if self.i >= len(self.b):
            raise ParseError('unexpected end at %d' % self.i)
        c = self.b[self.i]
        self.i += 1
        return c

    def peek(self):
        return self.b[self.i] if self.i < len(self.b) else None

    def number(self, first):
        n = 0
        while n < 10 and (c := self.peek()) is not None and 0x30 <= c <= 0x39:
            self.i += 1
            n += 1

    def term(self):
        c = self.get()
        if c == 0x02:
            x = self.get()
            cat = _var_cat(x)
            if cat == 'var':
                if (c := self.peek()) is not None and c >= 0x20:
                    self.i += 1
            elif cat == 'func':
                if (f := self.peek()) is not None and f >= 0x20:
                    self.i += 1
                    for _ in range(FUNC_ARGS.get(f, 0)):
                        self.expr()
        elif c == 0x25 or 0x30 <= c <= 0x39:
            self.number(c)

    def expr(self):
        self.term()
        while self.peek() == 0x03:
            self.i += 1
            self.get()
            self.term()

    def cmp(self):
        self.expr()
        if self.peek() == 0x04:
            self.i += 1
            self.get()
            self.expr()

    def cond(self):
        self.cmp()
        while self.peek() == 0x06:
            self.i += 1
            self.get()
            self.cmp()

def _sjis_lead(c):
    return 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC

def tokens(b):
    """-> [(kind, bytes)], kind 'text' | 'nl' | 'inline' | 'if' | 'end' | 'cmd'.
    Concatenating the bytes gives b back."""
    r = _Reader(b)
    out = []
    def add(kind, start):
        if kind == 'text' and out and out[-1][0] == 'text':
            out[-1] = ('text', out[-1][1] + b[start:r.i])
        else:
            out.append((kind, b[start:r.i]))
    while r.i < len(b):
        s = r.i
        c = r.get()
        if c == 0x25:                       # printf-style field filled in by the caller
            while (d := r.peek()) is not None and 0x30 <= d <= 0x39:
                r.i += 1
            if (d := r.peek()) is not None and (0x41 <= d <= 0x5A or 0x61 <= d <= 0x7A):
                r.i += 1
            add('inline', s)
        elif c >= 0x20:
            if _sjis_lead(c) and r.peek() is not None:
                r.i += 1
            add('text', s)
        elif c == 0x0A:
            add('nl', s)
        elif c == 0x02:
            r.i -= 1
            r.expr()
            add('inline', s)
        elif c in (0x1B, 0x1A):
            x = r.get()
            if x == 0x43 and (d := r.peek()) is not None and 0x30 <= d <= 0x39:
                r.i += 1                    # {1B}C<digit>: colour
            add('inline', s)
        elif c == 0x01:
            x = r.get()
            if x in (0x43, 0x4A):          # C, J
                if r.i + 2 > len(b):       # 3 messages end in 01 J: the engine takes
                    r.i = len(b)           # the next message's first bytes (05 05)
                    add('cmd', s)
                    continue
                r.i += 2
                add('inline', s)
                continue
            if x in (0x53, 0x52):          # S, R
                r.expr()
            elif x == 0x4D:                # M
                if r.get() != 0x02:
                    raise ParseError('M without 02 at %d' % s)
                r.get()
                r.expr()
            elif x == 0x46:                # F
                if r.get() == 0x64:
                    r.expr()
            add('cmd', s)
        elif c == 0x05:
            if r.peek() == 0x05 and r.i + 1 < len(b) and b[r.i + 1] == 0x04:
                r.i += 2
                r.cond()
                add('if', s)
            elif r.peek() == 0x05 and r.i + 1 < len(b) and b[r.i + 1] == 0x05:
                r.i += 2
                add('end', s)
            else:
                add('cmd', s)
        else:
            add('inline', s)
    return out

INLINE = ('text', 'nl', 'inline')

def units(b):
    """-> (toks, spans): spans = [(start, end)] token index ranges of text runs that
    hold visible text (anything but spaces)."""
    toks = tokens(b)
    spans, i = [], 0
    while i < len(toks):
        if toks[i][0] in INLINE:
            j = i
            while j < len(toks) and toks[j][0] in INLINE:
                j += 1
            if any(k == 'text' and t.strip(b' ') and t.replace(b'\x81\x40', b'').strip(b' ')
                   for k, t in toks[i:j]):
                spans.append((i, j))
            i = j
        else:
            i += 1
    return toks, spans
