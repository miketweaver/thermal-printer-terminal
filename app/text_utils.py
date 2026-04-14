"""
Unicode-to-ASCII text sanitization for thermal printer output.

The Epson TM-m30III only handles printable ASCII (0x20-0x7E).
This module translates common Unicode characters to their closest
ASCII equivalents and strips anything that can't be printed.

Used by both the form validation layer (models.py) and the
print engine safety net (printer.py).
"""

import re
import unicodedata

# Unicode → ASCII translation table
CHAR_MAP = str.maketrans({
    # Quotes
    '\u201c': '"',   # "
    '\u201d': '"',   # "
    '\u2018': "'",   # '
    '\u2019': "'",   # '
    '\u201a': ',',   # ‚
    '\u201e': '"',   # „
    '\u2039': '<',   # ‹
    '\u203a': '>',   # ›
    '\u00ab': '<<',  # «
    '\u00bb': '>>',  # »
    # Dashes
    '\u2014': '--',  # —
    '\u2013': '-',   # –
    '\u2012': '-',   # ‒
    '\u2015': '--',  # ―
    # Whitespace
    '\u00a0': ' ',   # non-breaking space
    '\u2002': ' ',   # en space
    '\u2003': ' ',   # em space
    '\u2009': ' ',   # thin space
    # Dots / bullets
    '\u2026': '...',  # …
    '\u2022': '*',    # •
    '\u2023': '>',    # ‣
    '\u25cf': '*',    # ●
    '\u25cb': 'o',    # ○
    # Math / symbols
    '\u00b0': 'deg',  # °
    '\u00b1': '+/-',  # ±
    '\u00d7': 'x',    # ×
    '\u00f7': '/',    # ÷
    '\u2260': '!=',   # ≠
    '\u2264': '<=',   # ≤
    '\u2265': '>=',   # ≥
    '\u221e': 'inf',  # ∞
    # Arrows
    '\u2190': '<-',   # ←
    '\u2192': '->',   # →
    '\u2194': '<->',  # ↔
    # Intellectual property
    '\u00a9': '(c)',   # ©
    '\u00ae': '(R)',   # ®
    '\u2122': '(TM)',  # ™
    # Fractions
    '\u00bc': '1/4',  # ¼
    '\u00bd': '1/2',  # ½
    '\u00be': '3/4',  # ¾
    # Zero-width / invisible
    '\ufeff': '',     # BOM
    '\u200b': '',     # zero-width space
    '\u200c': '',     # zero-width non-joiner
    '\u200d': '',     # zero-width joiner
})


def sanitize_text(text: str) -> str:
    """Translate common Unicode to ASCII equivalents.

    Applies the character map, then NFKD decomposition to handle
    accented characters (e.g. e -> e, n -> n). Keeps only printable
    ASCII plus newline and tab.
    """
    text = text.translate(CHAR_MAP)
    nfkd = unicodedata.normalize('NFKD', text)
    out = []
    for ch in nfkd:
        if ch in ('\n', '\t'):
            out.append(ch)
        elif 32 <= ord(ch) <= 126:
            out.append(ch)
        elif unicodedata.category(ch) == 'Mn':
            pass  # drop combining marks from decomposition
    return ''.join(out)


def find_unprintable(text: str) -> list[str]:
    """Return characters from text that survive neither translation nor decomposition."""
    bad = set()
    translated = text.translate(CHAR_MAP)
    nfkd = unicodedata.normalize('NFKD', translated)
    for ch in nfkd:
        if ch in ('\n', '\t'):
            continue
        if 32 <= ord(ch) <= 126:
            continue
        if unicodedata.category(ch) == 'Mn':
            continue
        bad.add(ch)
    return sorted(bad)


def clean_for_form(text: str) -> str:
    """Validate and sanitize user input for thermal printing.

    - Strips control characters
    - Collapses excessive blank lines
    - Rejects remaining unprintable characters with a user-friendly error
    - Returns sanitized ASCII-safe text
    """
    if text is None:
        return text
    # Remove control chars except newline/tab
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Collapse triple+ newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    # Check for unprintable characters before sanitizing
    bad = find_unprintable(text)
    if bad:
        chars = ' '.join(f'"{c}" (U+{ord(c):04X})' for c in bad[:5])
        raise ValueError(
            f"Contains characters the printer can't handle: {chars}. "
            f"Please use plain text only."
        )
    return sanitize_text(text)
