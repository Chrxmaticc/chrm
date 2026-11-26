"""Runners for the level 7-10 unlocks: text tricks, data tools, tiny calculators.

``text.py`` and ``tools.py`` were already the size where one more section made
them hard to scan, and these arrive as their own tier, so they get their own
module. Everything here is offline and pure -- ``(cog, ctx, arg) -> str`` -- so
the harness can exercise it without a bot, a network or a clock.
"""
from __future__ import annotations

import base64
import json
import re
import unicodedata
from datetime import date
from urllib.parse import quote_plus

from plugins.levels.base import digest, usage

#: refuse anything longer than this instead of three messages of noise
MAX_TEXT = 400
#: unicode table rows
MAX_CHARS = 40

ROMAN = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]

VOYELS = set("aeiou")

MAJOR = [
    ("The Fool", "a leap of faith pays off", "look before you jump"),
    ("The Magician", "you have every tool you need", "you are missing one piece"),
    ("The High Priestess", "trust the thing you have not said", "stop keeping secrets from yourself"),
    ("The Empress", "something is growing", "you are overwatering it"),
    ("The Emperor", "structure will save you", "the plan has become a cage"),
    ("The Hierophant", "ask someone who has done it", "tradition is not an answer"),
    ("The Lovers", "choose the honest option", "you already know what you want"),
    ("The Chariot", "momentum is on your side", "you are steering with your eyes closed"),
    ("Strength", "patience beats force here", "you are pushing too hard"),
    ("The Hermit", "a quiet hour will fix this", "you are hiding, not resting"),
    ("Wheel of Fortune", "timing is about to shift", "do not gamble on the timing"),
    ("Justice", "the fair option is the right one", "something is unbalanced"),
    ("The Hanged Man", "wait; the angle changes everything", "waiting has become avoiding"),
    ("Death", "end it cleanly and start again", "you are refusing an ending"),
    ("Temperance", "mix the two halves", "you are all or nothing right now"),
    ("The Devil", "name the thing you are stuck on", "the trap is comfortable"),
    ("The Tower", "the collapse is the favour", "the warning is the favour"),
    ("The Star", "hope is a strategy today", "you are wishing instead of doing"),
    ("The Moon", "not everything is as it looks", "the doubt is the point"),
    ("The Sun", "say the thing out loud", "you are hiding your own good news"),
    ("Judgement", "the honest review helps", "you are judging too early"),
    ("The World", "finish the last 5%", "you are one step short"),
]

MOODS = [
    "quietly optimistic", "loudly fine", "one coffee from greatness",
    "dangerously curious", "suspiciously calm", "about to text first",
    "due a win", "two thoughts deep", "unbothered", "vibing on a delay",
]

ADVICE = [
    "say less and mean more", "reply to the message you are avoiding",
    "drink water before you decide", "the boring option is the correct one",
    "take the walk", "ask for the thing directly", "sleep on it once",
    "the small tidy-up pays for itself", "trust the first instinct, then check it",
]

CUTS = [
    (1, 20, "aquarius"), (2, 19, "pisces"), (3, 21, "aries"),
    (4, 20, "taurus"), (5, 21, "gemini"), (6, 21, "cancer"),
    (7, 23, "leo"), (8, 23, "virgo"), (9, 23, "libra"),
    (10, 23, "scorpio"), (11, 22, "sagittarius"), (12, 22, "capricorn"),
]

SIGN_EMOJI = {
    "aries": "♈", "taurus": "♉", "gemini": "♊", "cancer": "♋",
    "leo": "♌", "virgo": "♍", "libra": "♎", "scorpio": "♏",
    "sagittarius": "♐", "capricorn": "♑", "aquarius": "♒", "pisces": "♓",
}


def _text(arg, name: str, what: str = "<text>") -> str:
    """The argument, or ``""`` after handing back a usage line."""
    value = (arg or "").strip()
    if not value:
        return ""
    return value[:MAX_TEXT]


# ---------------------------------------------------------------- formatting
def progress(cog, ctx, arg):
    """``.progress 7 10`` or ``.progress 42`` -> a ten-cell bar."""
    parts = [part for part in re.split(r"[\s/,]+", (arg or "").strip()) if part]
    try:
        if len(parts) >= 2:
            done, total = float(parts[0]), float(parts[1])
        elif parts:
            done, total = float(parts[0]), 100.0
        else:
            return usage("usage: `.progress 42` or `.progress 7 10`")
    except ValueError:
        return usage("usage: `.progress 42` or `.progress 7 10`")
    if total <= 0:
        return usage("the total has to be above zero.")
    ratio = max(0.0, min(1.0, done / total))
    filled = round(ratio * 10)
    bar = "▰" * filled + "▱" * (10 - filled)
    return f"`{bar}` **{ratio * 100:.1f}%** · {done:g}/{total:g}"


def subtext(cog, ctx, arg):
    value = _text(arg, "subtext")
    if not value:
        return usage("usage: `.subtext <text>`")
    return "\n".join(f"-# {line}" if line else "-#" for line in value.splitlines())


def strikethrough(cog, ctx, arg):
    value = _text(arg, "strikethrough")
    if not value:
        return usage("usage: `.strikethrough <text>`")
    return f"~~{value}~~"


def underline(cog, ctx, arg):
    value = _text(arg, "underline")
    if not value:
        return usage("usage: `.underline <text>`")
    return f"__{value}__"


def codeblock(cog, ctx, arg):
    value = _text(arg, "codeblock")
    if not value:
        return usage("usage: `.codeblock <text>`")
    # a literal ``` would close the block early, so break it up
    safe = value.replace("```", "` ` `")
    return f"```\n{safe}\n```"


def unicode_lookup(cog, ctx, arg):
    value = _text(arg, "unicode")
    if not value:
        return usage("usage: `.unicode <text>`")
    rows = []
    for char in value[:MAX_CHARS]:
        name = unicodedata.name(char, "unassigned")
        rows.append(f"`U+{ord(char):04X}` {char} · {name.lower()}")
    extra = "" if len(value) <= MAX_CHARS else f"\n-# first {MAX_CHARS} of {len(value)} characters"
    return "\n".join(rows) + extra


# ---------------------------------------------------------------- data tools
def json_pretty(cog, ctx, arg):
    value = _text(arg, "json")
    if not value:
        return usage("usage: `.json {\"a\": 1}`")
    try:
        parsed = json.loads(value)
    except ValueError as exc:
        return usage(f"that is not json: {exc}")
    pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
    if len(pretty) > 1700:
        pretty = pretty[:1700] + "\n…"
    return f"```json\n{pretty}\n```"


def _b64_part(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def jwt(cog, ctx, arg):
    """Decode a JWT's header and payload. Signature is *not* verified."""
    token = _text(arg, "jwt")
    if not token:
        return usage("usage: `.jwt <token>`")
    parts = token.split(".")
    if len(parts) < 2:
        return usage("that does not look like a jwt (no dots).")
    lines = ["### jwt · header + payload, signature not verified"]
    for label, part in (("header", parts[0]), ("payload", parts[1])):
        try:
            decoded = json.loads(_b64_part(part).decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001 - a mangled segment is a user error
            return usage(f"could not decode the {label} segment.")
        body = json.dumps(decoded, indent=1, ensure_ascii=False)
        lines.append(f"**{label}**\n```json\n{body[:700]}\n```")
    return "\n".join(lines)


def slug(cog, ctx, arg):
    value = _text(arg, "slug")
    if not value:
        return usage("usage: `.slug Some Title Here`")
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    cleaned = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return f"`{cleaned or 'empty'}`"


def urlencode(cog, ctx, arg):
    value = _text(arg, "urlencode")
    if not value:
        return usage("usage: `.urlencode <text>`")
    return f"`{quote_plus(value)}`"


# ---------------------------------------------------------------- calculators
def caesar(cog, ctx, arg):
    """``.caesar 5 hello`` shifts; ``.caesar hello`` uses 3."""
    tokens = (arg or "").strip().split(None, 1)
    if not tokens:
        return usage("usage: `.caesar 5 hello`")
    if len(tokens) == 2 and tokens[0].lstrip("-").isdigit():
        shift, value = int(tokens[0]), tokens[1]
    else:
        shift, value = 3, (arg or "").strip()
    shift %= 26
    out = []
    for char in value[:MAX_TEXT]:
        if char.isupper():
            out.append(chr((ord(char) - 65 + shift) % 26 + 65))
        elif char.islower():
            out.append(chr((ord(char) - 97 + shift) % 26 + 97))
        else:
            out.append(char)
    return "".join(out)


def _to_roman(value: int) -> str:
    out = []
    for amount, glyph in ROMAN:
        while value >= amount:
            out.append(glyph)
            value -= amount
    return "".join(out)


def _from_roman(token: str):
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    for index, char in enumerate(token):
        if char not in values:
            return None
        value = values[char]
        if index + 1 < len(token) and values[token[index + 1]] > value:
            total -= value
        else:
            total += value
    return total if 0 < total < 4000 else None


def roman(cog, ctx, arg):
    token = (arg or "").strip().upper()
    if not token:
        return usage("usage: `.roman 1994` or `.roman MCMXCIV`")
    if token.isdigit():
        value = int(token)
        if not 0 < value < 4000:
            return usage("roman numerals cover 1-3999.")
        return f"**{value}** = `{_to_roman(value)}`"
    value = _from_roman(token)
    if value is None:
        return usage("that is not a roman numeral between 1 and 3999.")
    return f"`{token}` = **{value}**"


def percent(cog, ctx, arg):
    numbers = [float(item) for item in re.findall(r"-?\d+(?:\.\d+)?", arg or "")]
    if len(numbers) < 2:
        return usage("usage: `.percent 25 200`")
    part, whole = numbers[0], numbers[1]
    if whole == 0:
        return usage("the whole cannot be zero.")
    ratio = part / whole * 100
    return f"**{part:g}** is **{ratio:.2f}%** of **{whole:g}**"


def split_bill(cog, ctx, arg):
    numbers = [float(item) for item in re.findall(r"-?\d+(?:\.\d+)?", arg or "")]
    if len(numbers) < 2:
        return usage("usage: `.split 120 4 [tip%]`")
    amount, people = numbers[0], numbers[1]
    tip = numbers[2] if len(numbers) > 2 else 0.0
    if people < 1:
        return usage("at least one person has to pay.")
    total = amount * (1 + max(0.0, tip) / 100)
    each = total / people
    lines = [
        f"bill **{amount:.2f}** · tip **{max(0.0, tip):g}%**",
        f"total **{total:.2f}** across **{people:g}**",
        f"**{each:.2f}** each",
    ]
    if abs(each * people - total) > 0.005:
        lines.append(f"-# last person covers {total - each * (people - 1):.2f}")
    return "\n".join(lines)


def sort_lines(cog, ctx, arg):
    value = (arg or "").strip()
    if not value or "\n" not in value:
        return usage("usage: `.sort` with several lines of text")
    reverse = value.splitlines()[0].strip().lower() in ("desc", "reverse", "-r")
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if reverse and lines and lines[0].lower() in ("desc", "reverse", "-r"):
        lines = lines[1:]
    if not lines:
        return usage("nothing to sort.")
    lines.sort(reverse=reverse)
    return "\n".join(lines[:MAX_CHARS])


def dedupe(cog, ctx, arg):
    value = (arg or "").strip()
    if not value or "\n" not in value:
        return usage("usage: `.dedupe` with several lines of text")
    seen, out = set(), []
    for line in value.splitlines():
        if line.strip() and line not in seen:
            seen.add(line)
            out.append(line)
    removed = len([line for line in value.splitlines() if line.strip()]) - len(out)
    return "\n".join(out[:MAX_CHARS]) + f"\n-# {removed} duplicate line(s) dropped"


def sum_numbers(cog, ctx, arg):
    numbers = [float(item) for item in re.findall(r"-?\d+(?:\.\d+)?", arg or "")]
    if not numbers:
        return usage("usage: `.sum 1 2 3.5`")
    total = sum(numbers)
    mean = total / len(numbers)
    pretty = f"{total:g}"
    return (
        f"**{pretty}** total · **{len(numbers)}** numbers\n"
        f"mean **{mean:g}** · min **{min(numbers):g}** · max **{max(numbers):g}**"
    )


# ---------------------------------------------------------------- fun tables
def horoscope(cog, ctx, arg):
    today = date.today()
    sign = (arg or "").strip().lower()
    if sign:
        if sign not in SIGN_EMOJI:
            return usage("signs: " + ", ".join(f"`{name}`" for name in SIGN_EMOJI))
    else:
        sign = "capricorn"
        for month, day, name in CUTS:
            if (today.month, today.day) >= (month, day):
                sign = name
            else:
                break
    mood = MOODS[digest("mood", f"{sign}{today}", len(MOODS))]
    advice = ADVICE[digest("advice", f"{sign}{today}", len(ADVICE))]
    lucky = digest("lucky", f"{sign}{today}", 99) + 1
    return (
        f"{SIGN_EMOJI[sign]} **{sign}** · {today.strftime('%d %b %Y')}\n"
        f"mood **{mood}** · lucky number **{lucky}**\n"
        f"-# {advice}"
    )


def tarot(cog, ctx, arg):
    today = date.today()
    seed = f"{getattr(getattr(ctx, 'author', None), 'id', 0)}{today}"
    name, upright, reversed_meaning = MAJOR[digest("tarot", seed, len(MAJOR))]
    flipped = digest("flip", seed, 2) == 1
    meaning = reversed_meaning if flipped else upright
    return (
        f"**{name}**{' (reversed)' if flipped else ''}\n"
        f"{meaning}"
    )


def piglatin(cog, ctx, arg):
    value = _text(arg, "piglatin")
    if not value:
        return usage("usage: `.piglatin hello there`")
    out = []
    for word in value.split():
        letters = re.sub(r"[^a-z]", "", word.lower())
        if not letters:
            out.append(word)
            continue
        if letters[0] in VOYELS:
            out.append(f"{letters}yay")
            continue
        index = 0
        while index < len(letters) and letters[index] not in VOYELS:
            index += 1
        out.append(f"{letters[index:]}{letters[:index]}ay" if index else f"{letters}yay")
    return " ".join(out)
