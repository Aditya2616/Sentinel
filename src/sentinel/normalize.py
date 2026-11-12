"""Input normalisation.

Attackers hide instructions with zero-width characters, look-alike letters,
leetspeak, spaced-out letters and encodings. Matching rules against the raw
string misses those, so the text is first expanded into several *views*. Each
view keeps a map from its characters back to the original string, so a match
found in any view can be highlighted on what the user actually sent.
"""

from __future__ import annotations

import base64
import binascii
import codecs
import re
import unicodedata
from dataclasses import dataclass, field

# Invisible or direction-changing characters that have no business in a prompt.
_INVISIBLE = set(
    list(range(0x200B, 0x2010))  # zero-width space/joiners, LRM, RLM
    + list(range(0x202A, 0x202F))  # bidi embeddings and overrides
    + list(range(0x2060, 0x2065))  # word joiner, invisible operators
    + list(range(0x2066, 0x206A))  # bidi isolates
    + [0xFEFF, 0x00AD, 0x180E, 0x034F, 0x061C, 0x115F, 0x1160, 0x3164]
)
_TAG_LO, _TAG_HI = 0xE0000, 0xE007F  # Unicode "tag" block: invisible ASCII smuggling

# Cyrillic and Greek letters that render like Latin ones.
_HOMOGLYPHS = {
    **dict(zip("асеорхуіјѕԁӏкмнтв", "aceopxyijsdlkmhtb", strict=True)),
    **dict(zip("АВЕКМНОРСТХУІЈЅ", "ABEKMHOPCTXYIJS", strict=True)),
    **dict(zip("αβεικνορτυχ", "abeiknoptux", strict=True)),
    **dict(zip("ΑΒΕΖΗΙΚΜΝΟΡΤΥΧ", "ABEZHIKMNOPTYX", strict=True)),
}
_LEET = {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i", "|": "l", "+": "t"}

_B64_RE = re.compile(r"(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/_-]{20,}={0,2}(?![A-Za-z0-9+/=_-])")
_HEX_RE = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}[\s:,-]?){10,}(?![0-9A-Fa-f])")
_SPACED_RE = re.compile(r"(?<![A-Za-z])(?:[A-Za-z][ .\-_*]){3,}[A-Za-z](?![A-Za-z])")


@dataclass
class View:
    """One normalised rendering of the input plus a map back to the original."""

    name: str
    text: str
    # spans[i] = (start, end) in the ORIGINAL string for character i of `text`
    spans: list[tuple[int, int]]
    note: str = ""

    def original_span(self, a: int, b: int) -> tuple[int, int]:
        if not self.spans:
            return (0, 0)
        a = max(0, min(a, len(self.spans) - 1))
        b = max(a + 1, min(b, len(self.spans)))
        return (min(s for s, _ in self.spans[a:b]), max(e for _, e in self.spans[a:b]))


@dataclass
class Normalized:
    original: str
    views: list[View]
    notes: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    @property
    def base(self) -> View:
        return self.views[0]

    @property
    def obfuscated(self) -> bool:
        return any(self.stats.get(k, 0) for k in ("invisible", "tags", "homoglyph_tokens", "decoded", "spaced"))


def _is_leet_token_char(tok: str, i: int) -> bool:
    c = tok[i]
    if c not in _LEET:
        return False
    prev_alpha = i > 0 and tok[i - 1].isalpha()
    next_alpha = i + 1 < len(tok) and tok[i + 1].isalpha()
    return prev_alpha or next_alpha


def _build_base(text: str) -> tuple[View, dict[str, int], str]:
    out: list[str] = []
    spans: list[tuple[int, int]] = []
    invisible = tags = 0
    tag_chars: list[str] = []
    for i, ch in enumerate(text):
        cp = ord(ch)
        if _TAG_LO <= cp <= _TAG_HI:
            tags += 1
            if 0xE0020 <= cp <= 0xE007E:
                tag_chars.append(chr(cp - 0xE0000))
            continue
        if cp in _INVISIBLE:
            invisible += 1
            continue
        for c2 in unicodedata.normalize("NFKC", ch):
            if unicodedata.category(c2) == "Cc" and c2 not in "\n\t":
                c2 = " "
            out.append(c2)
            spans.append((i, i + 1))
    # fold homoglyphs only inside tokens that mix scripts (so real Russian/Greek text is left alone)
    s = "".join(out)
    folded_tokens = 0
    res: list[str] = []
    for m in re.finditer(r"\S+|\s+", s):
        tok = m.group()
        has_latin = any("a" <= c.lower() <= "z" for c in tok)
        has_conf = any(c in _HOMOGLYPHS for c in tok)
        if has_latin and has_conf:
            tok = "".join(_HOMOGLYPHS.get(c, c) for c in tok)
            folded_tokens += 1
        elif has_conf and sum(c in _HOMOGLYPHS for c in tok) == len([c for c in tok if c.isalpha()]) and len(tok) >= 4:
            # a token written entirely in look-alike letters inside otherwise Latin text
            latin_ratio = sum("a" <= c.lower() <= "z" for c in s) / max(1, sum(c.isalpha() for c in s))
            if latin_ratio > 0.5:
                tok = "".join(_HOMOGLYPHS.get(c, c) for c in tok)
                folded_tokens += 1
        res.append(tok)
    s2 = "".join(res)
    nfkc_changed = int(unicodedata.normalize("NFKC", text) != text)
    stats = {"invisible": invisible, "tags": tags, "homoglyph_tokens": folded_tokens, "nfkc": nfkc_changed}
    return View("base", s2, spans), stats, "".join(tag_chars)


def _leet_view(base: View) -> View | None:
    s = base.text
    out = list(s)
    changed = False
    for m in re.finditer(r"\S+", s):
        tok = m.group()
        if sum(c.isalpha() for c in tok) < 2:
            continue
        for i in range(len(tok)):
            if _is_leet_token_char(tok, i):
                out[m.start() + i] = _LEET[tok[i]]
                changed = True
    if not changed:
        return None
    return View("leet", "".join(out), base.spans, "leetspeak folded")


def _spaced_view(base: View) -> View | None:
    s = base.text
    out: list[str] = []
    spans: list[tuple[int, int]] = []
    pos = 0
    changed = False
    for m in _SPACED_RE.finditer(s):
        out.append(s[pos : m.start()])
        spans.extend(base.spans[pos : m.start()])
        letters = [(c, base.spans[m.start() + k]) for k, c in enumerate(m.group()) if c.isalpha()]
        out.append("".join(c for c, _ in letters))
        spans.extend(sp for _, sp in letters)
        pos = m.end()
        changed = True
    if not changed:
        return None
    out.append(s[pos:])
    spans.extend(base.spans[pos:])
    return View("spaced", "".join(out), spans, "spaced-out letters collapsed")


def _printable_ratio(b: bytes) -> tuple[str, float]:
    try:
        t = b.decode("utf-8")
    except UnicodeDecodeError:
        return "", 0.0
    if not t:
        return "", 0.0
    ok = sum(c.isprintable() or c in "\n\t" for c in t)
    return t, ok / len(t)


def _decoded_views(base: View) -> list[View]:
    views: list[View] = []
    s = base.text
    for m in _B64_RE.finditer(s):
        tok = m.group()
        pad = tok + "=" * (-len(tok) % 4)
        try:
            raw = base64.b64decode(pad.replace("-", "+").replace("_", "/"), validate=False)
        except (binascii.Error, ValueError):
            continue
        t, ratio = _printable_ratio(raw)
        letters = sum(c.isalpha() or c == " " for c in t)
        if ratio > 0.97 and len(t) >= 8 and letters / max(1, len(t)) > 0.7:
            sp = base.original_span(m.start(), m.end())
            views.append(View("base64", t, [sp] * len(t), "base64 payload decoded"))
    for m in _HEX_RE.finditer(s):
        hx = re.sub(r"[^0-9A-Fa-f]", "", m.group())
        if len(hx) % 2:
            continue
        t, ratio = _printable_ratio(bytes.fromhex(hx))
        if ratio > 0.97 and len(t) >= 6 and sum(c.isalpha() or c == " " for c in t) / len(t) > 0.7:
            sp = base.original_span(m.start(), m.end())
            views.append(View("hex", t, [sp] * len(t), "hex payload decoded"))
    return views


def _rot13_view(base: View) -> View | None:
    letters = sum(c.isalpha() for c in base.text)
    if letters < 12 or len(base.text) > 4000:
        return None
    return View("rot13", codecs.encode(base.text, "rot13"), base.spans, "rot13 view")


def normalize(text: str) -> Normalized:
    """Expand ``text`` into matchable views and report what was undone."""
    base, stats, tag_text = _build_base(text)
    views = [base]
    notes: list[str] = []
    if stats["invisible"]:
        notes.append(f"removed {stats['invisible']} invisible character(s)")
    if stats["tags"]:
        notes.append(f"removed {stats['tags']} Unicode tag character(s) (hidden ASCII)")
    if stats["homoglyph_tokens"]:
        notes.append(f"folded look-alike letters in {stats['homoglyph_tokens']} word(s)")
    if stats["nfkc"]:
        notes.append("compatibility characters normalised (NFKC)")
    if tag_text:
        views.append(View("tags", tag_text, [(0, len(text))] * len(tag_text), "hidden tag-character text revealed"))
    leet = _leet_view(base)
    if leet:
        views.append(leet)
        notes.append("leetspeak folded")
        stats["leet"] = 1
    spaced = _spaced_view(base)
    if spaced:
        views.append(spaced)
        notes.append("spaced-out letters collapsed")
        stats["spaced"] = 1
    decoded = _decoded_views(base)
    for v in decoded:
        notes.append(v.note)
    views.extend(decoded)
    stats["decoded"] = len(decoded)
    rot = _rot13_view(base)
    if rot:
        views.append(rot)
    return Normalized(original=text, views=views, notes=notes, stats=stats)
