"""Turn what the recogniser heard into what should actually be typed.

Three jobs, in order:

1. **Spoken punctuation** - "Dear Sir comma" -> ``Dear Sir,``
2. **Spelled-out codes**  - "R P zero zero zero two four four two" -> ``RP0002442``
3. **Identifier casing**  - "can000410" -> ``CAN000410``

Everything is deliberately conservative: a run of characters is only collapsed
into a code when it *looks* like one, so ordinary text ("Anand Trading Company",
"Bennikal Village, Hoovina Hadagali") passes through untouched.
"""

from __future__ import annotations

import re
from typing import Dict, List

# --------------------------------------------------------------------------
# 1. Spoken punctuation
# --------------------------------------------------------------------------
PUNCTUATION: Dict[str, str] = {
    "comma": ",",
    "full stop": ".",
    "fullstop": ".",
    "period": ".",
    "dot": "\x01",          # sentinel: tight on both sides (example dot com)
    "question mark": "?",
    "exclamation mark": "!",
    "exclamation point": "!",
    "colon": ":",
    "semicolon": ";",
    "semi colon": ";",
    "hyphen": "-",
    "dash": "-",
    "minus sign": "-",
    "underscore": "_",
    "slash": "/",
    "forward slash": "/",
    "back slash": "\\",
    "backslash": "\\",
    "at the rate": "@",
    "at sign": "@",
    "at symbol": "@",
    "ampersand": "&",
    "and sign": "&",
    "hash": "#",
    "hash tag": "#",
    "percent sign": "%",
    "plus sign": "+",
    "equals sign": "=",
    "asterisk": "*",
    "star sign": "*",
    "open bracket": "(",
    "close bracket": ")",
    "open parenthesis": "(",
    "close parenthesis": ")",
    "open square bracket": "[",
    "close square bracket": "]",
    "quote": '"',
    "double quote": '"',
    "single quote": "'",
    "apostrophe": "'",
    "rupee symbol": "\u20b9",
    "rupees symbol": "\u20b9",
}

# Longest first so "full stop" wins over "stop", "at the rate" over "at".
_PUNCT_PATTERN = re.compile(
    r"(?<![\w])(" + "|".join(re.escape(k) for k in sorted(PUNCTUATION, key=len, reverse=True)) + r")(?![\w])",
    re.IGNORECASE,
)

_NEWLINE_PATTERN = re.compile(r"(?<![\w])(new line|newline|next line|line break)(?![\w])", re.IGNORECASE)
_TAB_PATTERN = re.compile(r"(?<![\w])(tab character|insert tab)(?![\w])", re.IGNORECASE)

NO_SPACE_BEFORE = set(",.?!:;)]%")
NO_SPACE_AFTER = set("([#\u20b9")
TIGHT_BOTH = set("-_/\\@\x01")
_DOT_SENTINEL = "\x01"

# --------------------------------------------------------------------------
# 2. Spelled-out codes
# --------------------------------------------------------------------------
DIGIT_WORDS: Dict[str, str] = {
    "zero": "0", "oh": "0", "o": "0", "nought": "0", "naught": "0",
    "one": "1", "won": "1",
    "two": "2", "to": "2", "too": "2",
    "three": "3", "tree": "3",
    "four": "4", "for": "4", "fore": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8", "ate": "8",
    "nine": "9",
}

# NATO / Indian phonetic alphabet, for dictating codes character by character.
PHONETIC: Dict[str, str] = {
    "alpha": "A", "alfa": "A", "apple": "A",
    "bravo": "B", "boy": "B", "ball": "B",
    "charlie": "C", "cat": "C",
    "delta": "D", "dog": "D",
    "echo": "E", "elephant": "E",
    "foxtrot": "F", "fish": "F",
    "golf": "G", "girl": "G",
    "hotel": "H", "house": "H",
    "india": "I", "ink": "I",
    "juliet": "J", "juliett": "J", "jug": "J",
    "kilo": "K", "kite": "K",
    "lima": "L", "lion": "L",
    "mike": "M", "monkey": "M",
    "november": "N", "nest": "N",
    "oscar": "O", "orange": "O",
    "papa": "P", "parrot": "P",
    "quebec": "Q", "queen": "Q",
    "romeo": "R", "rose": "R",
    "sierra": "S", "sun": "S",
    "tango": "T", "tiger": "T",
    "uniform": "U", "umbrella": "U",
    "victor": "V", "van": "V",
    "whiskey": "W", "watch": "W",
    "xray": "X", "x-ray": "X",
    "yankee": "Y", "yellow": "Y",
    "zulu": "Z", "zebra": "Z",
}

_MULTIPLIERS = {"double": 2, "triple": 3, "twice": 2, "thrice": 3}

_CODE_LIKE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9][A-Za-z0-9\-/]*$")
_PURE_LETTERS_SHORT = re.compile(r"^[A-Za-z]$")


def apply_punctuation(text: str, enabled: bool = True) -> str:
    """Replace spoken punctuation words with the real characters."""
    if not enabled or not text:
        return text

    result = _NEWLINE_PATTERN.sub("\n", text)
    result = _TAB_PATTERN.sub("\t", result)
    result = _PUNCT_PATTERN.sub(lambda m: PUNCTUATION[m.group(1).lower()], result)
    return _fix_spacing(result).replace(_DOT_SENTINEL, ".")


def _fix_spacing(text: str) -> str:
    """Tidy the spaces left behind after substituting punctuation."""
    out: List[str] = []
    for index, char in enumerate(text):
        if char == " " and index + 1 < len(text) and text[index + 1] in NO_SPACE_BEFORE:
            continue
        if char == " " and out and out[-1] in NO_SPACE_AFTER:
            continue
        if char == " " and out and out[-1] in TIGHT_BOTH:
            continue
        if char in TIGHT_BOTH and out and out[-1] == " ":
            out.pop()
        out.append(char)
    cleaned = "".join(out)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    return cleaned.strip()


def _token_to_char(token: str) -> str | None:
    """Return the single character a token represents, else None."""
    low = token.lower().strip(".")
    if len(token) == 1 and token.isalnum():
        return token.upper()
    if low in DIGIT_WORDS:
        return DIGIT_WORDS[low]
    if low in PHONETIC:
        return PHONETIC[low]
    return None


def collapse_spelled_code(text: str, enabled: bool = True, min_run: int = 3) -> str:
    """Join runs of dictated characters into a single identifier.

    "type R P zero zero zero two four four two" -> ``RP0002442``
    "type C A N triple zero four one zero"      -> ``CAN000410``

    A run must contain at least ``min_run`` character-tokens *and* at least one
    digit, which is what stops normal English ("to be or not to be") from being
    mangled.
    """
    if not enabled or not text:
        return text

    tokens = text.split(" ")
    output: List[str] = []
    index = 0

    while index < len(tokens):
        run: List[str] = []
        cursor = index
        multiplier = 1
        while cursor < len(tokens):
            token = tokens[cursor]
            low = token.lower()
            if low in _MULTIPLIERS and cursor + 1 < len(tokens):
                nxt = _token_to_char(tokens[cursor + 1])
                if nxt is None:
                    break
                multiplier = _MULTIPLIERS[low]
                cursor += 1
                continue
            char = _token_to_char(token)
            if char is None:
                break
            run.extend([char] * multiplier)
            multiplier = 1
            cursor += 1

        joined = "".join(run)
        if len(run) >= min_run and any(c.isdigit() for c in joined) and any(
            c.isalpha() for c in joined
        ):
            output.append(joined)
            index = cursor
        elif len(run) >= max(4, min_run) and joined.isdigit():
            output.append(joined)
            index = cursor
        else:
            output.append(tokens[index])
            index += 1

    return " ".join(output)


def uppercase_codes(text: str, enabled: bool = True) -> str:
    """Upper-case tokens that are clearly business identifiers.

    ``rp0002442`` -> ``RP0002442``   ``29aafcj4954l1zy`` -> ``29AAFCJ4954L1ZY``
    Plain words and normal names are left exactly as they are.
    """
    if not enabled or not text:
        return text

    def convert(match: re.Match[str]) -> str:
        token = match.group(0)
        core = token.strip(".,;:()[]")
        if len(core) < 3:
            return token
        if not _CODE_LIKE.match(core):
            return token
        if core.upper() == core:
            return token
        letters = sum(ch.isalpha() for ch in core)
        digits = sum(ch.isdigit() for ch in core)
        if letters and digits and (letters + digits) >= 4:
            return token.replace(core, core.upper())
        return token

    return re.sub(r"\S+", convert, text)


def normalize_typed_text(
    text: str,
    auto_punctuation: bool = True,
    normalize_codes: bool = True,
    uppercase_alphanumeric: bool = True,
) -> str:
    """Full pipeline used by the ``type_text`` action."""
    if not text:
        return ""
    result = text.strip()
    result = collapse_spelled_code(result, enabled=normalize_codes)
    result = apply_punctuation(result, enabled=auto_punctuation)
    result = uppercase_codes(result, enabled=uppercase_alphanumeric)
    return result.strip()


def strip_trailing_politeness(text: str) -> str:
    """Remove 'please', 'thank you', 'for me' tails that recognisers love to add."""
    return re.sub(
        r"[\s,]*(please|thanks|thank you|for me|ok|okay)[\s.!]*$", "", text, flags=re.IGNORECASE
    ).strip()
