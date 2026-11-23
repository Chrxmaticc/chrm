"""Text transforms: the level 1/2/4/6 commands that rewrite what you typed.

Every function here is a pure ``str -> str`` (base64 can also return a
:class:`~plugins.levels.base.Usage`), so they are trivial to test and the
catalogue only has to wrap them with an argument check.
"""
from __future__ import annotations

import base64 as _b64
import codecs
import hashlib
import random
import re

from plugins.levels.base import usage

_COMBINING = "\u0300\u0301\u0302\u0303\u0308\u030a\u0323\u0327\u0336\u0337\u0352\u035c\u0360\u0361"


def mock(text: str) -> str:
    out = []
    upper = False
    for ch in text:
        if ch.isalpha():
            out.append(ch.upper() if upper else ch.lower())
            upper = not upper
        else:
            out.append(ch)
    return "".join(out)


def reverse(text: str) -> str:
    return text[::-1]


def clap(text: str) -> str:
    return " 👏 ".join(text.split())


def vaporwave(text: str) -> str:
    out = []
    for ch in text:
        code = ord(ch)
        if ch == " ":
            out.append("\u3000")
        elif 33 <= code <= 126:
            out.append(chr(code + 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)


def owo(text: str) -> str:
    table = (
        ("ove", "uv"), ("OVE", "UV"), ("th", "ff"), ("Th", "Ff"),
        ("r", "w"), ("R", "W"), ("l", "w"), ("L", "W"), ("n", "ny"), ("N", "Ny"),
    )
    out = text
    for old, new in table:
        out = out.replace(old, new)
    return f"{out} {'uwu' if random.random() < 0.5 else 'owo'}"


def emojify(text: str) -> str:
    out = []
    for ch in text:
        if ch.isalpha() and ch.isascii():
            out.append(chr(0x1F1E6 + (ord(ch.lower()) - ord("a"))))
        elif ch.isdigit():
            out.append(f"{ch}\ufe0f\u20e3")
        else:
            out.append(ch)
    return "".join(out)


def spoiler(text: str) -> str:
    return " ".join(f"||{word}||" for word in text.split())


def zalgo(text: str) -> str:
    out = []
    for ch in text:
        out.append(ch)
        if ch.strip():
            out.append("".join(random.choice(_COMBINING) for _ in range(random.randint(1, 3))))
    return "".join(out)


_SMALL = str.maketrans({
    "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ", "g": "ɢ", "h": "ʜ",
    "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ", "m": "ᴍ", "n": "ɴ", "o": "ᴏ", "p": "ᴘ",
    "q": "ǫ", "r": "ʀ", "s": "ꜱ", "t": "ᴛ", "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x",
    "y": "ʏ", "z": "ᴢ",
})


def smallcaps(text: str) -> str:
    return text.lower().translate(_SMALL)


def bubble(text: str) -> str:
    out = []
    for ch in text:
        if "a" <= ch <= "z":
            out.append(chr(0x24D0 + ord(ch) - ord("a")))
        elif "A" <= ch <= "Z":
            out.append(chr(0x24B6 + ord(ch) - ord("A")))
        elif "0" <= ch <= "9":
            out.append(chr(0x2460 + ord(ch) - ord("1")) if ch != "0" else "⓪")
        else:
            out.append(ch)
    return "".join(out)


_LEET = str.maketrans({"a": "4", "A": "4", "e": "3", "E": "3", "i": "1", "I": "1",
                       "o": "0", "O": "0", "s": "5", "S": "5", "t": "7", "T": "7"})


def leet(text: str) -> str:
    return text.translate(_LEET)


def shuffle(text: str) -> str:
    words = text.split()
    if len(words) < 2:
        return text[::-1]
    random.shuffle(words)
    return " ".join(words)


def binary(text: str) -> str:
    return " ".join(f"{ord(ch):08b}" for ch in text)


_MORSE = {
    "a": ".-", "b": "-...", "c": "-.-.", "d": "-..", "e": ".", "f": "..-.", "g": "--.",
    "h": "....", "i": "..", "j": ".---", "k": "-.-", "l": ".-..", "m": "--", "n": "-.",
    "o": "---", "p": ".--.", "q": "--.-", "r": ".-.", "s": "...", "t": "-", "u": "..-",
    "v": "...-", "w": ".--", "x": "-..-", "y": "-.--", "z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
}


def morse(text: str) -> str:
    words = []
    for word in text.lower().split():
        letters = [_MORSE[ch] for ch in word if ch in _MORSE]
        if letters:
            words.append(" ".join(letters))
    return " / ".join(words) or "nothing to encode."


_FLIP = str.maketrans(dict(zip(
    "abcdefghijklmnopqrstuvwxyz!?.,()[]{}",
    "ɐqɔpǝɟƃɥıɾʞlɯuodbɹsʇnʌʍxʎz¡¿˙'()[]{}",
)))


def upside(text: str) -> str:
    return text[::-1].translate(_FLIP)


_HOMOGLYPHS = {"a": "а", "e": "е", "o": "о", "p": "р", "c": "с", "x": "х", "y": "у",
               "i": "і", "s": "ѕ", "A": "А", "B": "В", "E": "Е", "O": "О", "P": "Р"}


def glitch(text: str) -> str:
    out = []
    for ch in text:
        if ch in _HOMOGLYPHS and random.random() < 0.5:
            out.append(_HOMOGLYPHS[ch])
        else:
            out.append(ch)
        if ch.strip() and random.random() < 0.2:
            out.append(random.choice(_COMBINING))
    return "".join(out)


def sparkle(text: str) -> str:
    return f"✧･ﾟ: *✧ {text} ✧*:･ﾟ✧"


def aesthetic(text: str) -> str:
    return " ".join(vaporwave(ch) for ch in text if ch.strip())


def quoteit(text: str) -> str:
    return "\n".join(f"> {line}" for line in text.splitlines())


def sign(text: str) -> str:
    body = text.splitlines() or [text]
    width = min(48, max((len(line) for line in body), default=0) + 2)
    top = "┌" + "─" * width + "┐"
    bottom = "└" + "─" * width + "┘"
    middle = [f"│ {line[:width - 2].ljust(width - 2)} │" for line in body]
    return "\n".join([top, *middle, bottom])


def count_text(text: str) -> str:
    return (
        f"**{len(text)}** characters · **{len(text.split())}** words · "
        f"**{len(text.splitlines())}** lines · **{len(text.encode())}** bytes"
    )


def palindrome(text: str) -> str:
    clean = re.sub(r"[^a-z0-9]", "", text.lower())
    if not clean:
        return "nothing to check."
    return f"yes — `{clean}` reads the same backwards." if clean == clean[::-1] else "no, that is not a palindrome."


def base64_cmd(text: str):
    parts = text.split(maxsplit=1)
    mode = parts[0].lower() if parts else ""
    body = parts[1] if len(parts) > 1 else ""
    if mode not in ("encode", "decode") or not body:
        return usage("usage: `.base64 encode|decode <text>`")
    try:
        if mode == "encode":
            return _b64.b64encode(body.encode()).decode()
        return _b64.b64decode(body + "=" * (-len(body) % 4)).decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - bad input is a user error, not a crash
        return usage(f"that is not valid base64: `{exc}`")


def rot13(text: str) -> str:
    return codecs.encode(text, "rot13")


def hash_text(algo: str):
    """``.md5`` / ``.sha256`` -- hash whatever text is given."""

    def run(text: str) -> str:
        return f"`{hashlib.new(algo, text.encode()).hexdigest()}`"

    return run
