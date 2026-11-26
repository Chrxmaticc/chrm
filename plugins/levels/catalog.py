"""The unlock catalogue: one table of commands, grouped by level.

Each row is a :class:`~plugins.levels.base.Unlock` -- name, level, description and
a ``run`` callable from :mod:`plugins.levels.text`, :mod:`plugins.levels.tools` or
:mod:`plugins.levels.content`. ``run`` is ``(cog, ctx, arg) -> str | None`` and may
be a coroutine; ``None`` means "already answered" and a
:class:`~plugins.levels.base.Usage` is sent as a warning.

The table is data rather than 66 decorated methods, so the cog registers exactly
what exists and ``.cmds`` renders the whole ladder from the same rows.
"""
from __future__ import annotations

import random

from plugins.levels.base import Unlock, Usage, usage
from plugins.levels.content import (
    BONK, COMPLIMENTS, CONGRATS, DARES, EXCUSES, FACTS, FORTUNES, HIGHFIVE, HUG,
    JOKES, KISS, PAT, PICKUP, QUOTES, ROASTS, SIMP, SLAP, TRUTHS, WYR,
    hype, poll, pretty_duration, timer, topic,
)
from plugins.levels import extra, text, tools

__all__ = [
    "Usage", "Unlock", "usage", "UNLOCKS", "TIERS", "by_level", "find",
    "total_for_level", "pretty_duration",
]


# ==========================================
# 1. BUILDERS
# ==========================================
def _text(name: str, func, what: str = "<text>"):
    """Wrap a pure ``str -> str`` transform, refusing to run on nothing."""

    def run(cog, ctx, arg):
        value = (arg or "").strip()
        if not value:
            return usage(f"usage: `.{name} {what}`")
        return func(value)

    return run


def _lines(choices, prefix: str = ""):
    """Pick one line at random, optionally with a leading label."""

    def run(cog, ctx, arg):
        line = random.choice(choices)
        return f"{prefix}{line}" if prefix else line

    return run


def _target(ctx, arg: str, fallback: str = "themselves") -> str:
    mentions = getattr(getattr(ctx, "message", None), "mentions", None) or []
    if mentions:
        return getattr(mentions[0], "display_name", "them")
    name = (arg or "").strip().lstrip("@").strip()
    return name or fallback


def _pair(verbs):
    """Action aimed at whoever you mention (or name)."""

    def run(cog, ctx, arg):
        who = _target(ctx, arg)
        author = getattr(getattr(ctx, "author", None), "display_name", "you")
        return random.choice(verbs).format(a=author, b=who)

    return run


#: level -> tier name shown in ``.cmds`` and level-up toasts
TIERS = {
    1: "starter pack",
    2: "text lab",
    3: "vibes",
    4: "toolbox",
    5: "social",
    6: "deluxe",
    7: "nightshift",
    8: "workshop",
    9: "guild",
    10: "legend",
}

UNLOCKS = [
    # ---------------------------------- level 1: starter pack
    Unlock("8ball", 1, "ask the magic 8ball", tools.eight_ball),
    Unlock("coinflip", 1, "heads or tails", tools.coinflip),
    Unlock("roll", 1, "roll dice, e.g. 2d20", tools.roll),
    Unlock("choose", 1, "pick between options (a | b | c)", tools.choose),
    Unlock("rate", 1, "rate anything out of 10", tools.rate),
    Unlock("ship", 1, "ship two people", tools.ship),
    Unlock("mock", 1, "sPoNgEbOb a message", _text("mock", text.mock)),
    Unlock("reverse", 1, "reverse a message", _text("reverse", text.reverse)),
    Unlock("clap", 1, "clap between words", _text("clap", text.clap)),
    Unlock("vaporwave", 1, "ａｅｓｔｈｅｔｉｃ text", _text("vaporwave", text.vaporwave)),
    Unlock("joke", 1, "a random joke", _lines(JOKES)),

    # ---------------------------------- level 2: text lab
    Unlock("owo", 2, "owoify a message", _text("owo", text.owo)),
    Unlock("emojify", 2, "turn text into letters + emoji", _text("emojify", text.emojify)),
    Unlock("spoiler", 2, "spoiler-tag every word", _text("spoiler", text.spoiler)),
    Unlock("zalgo", 2, "c̸u̷r̶s̵e̴ a message", _text("zalgo", text.zalgo)),
    Unlock("smallcaps", 2, "sᴍᴀʟʟ ᴄᴀᴘꜱ", _text("smallcaps", text.smallcaps)),
    Unlock("bubble", 2, "ⓑⓤⓑⓑⓛⓔ text", _text("bubble", text.bubble)),
    Unlock("leet", 2, "sp34k l1k3 th15", _text("leet", text.leet)),
    Unlock("shuffle", 2, "shuffle the words around", _text("shuffle", text.shuffle)),
    Unlock("binary", 2, "text as 8-bit binary", _text("binary", text.binary)),
    Unlock("morse", 2, "text as morse code", _text("morse", text.morse)),
    Unlock("upside", 2, "ʇxǝʇ uʍop ǝpᴉsdn", _text("upside", text.upside)),

    # ---------------------------------- level 3: vibes
    Unlock("truth", 3, "a truth question", _lines(TRUTHS)),
    Unlock("dare", 3, "a dare", _lines(DARES)),
    Unlock("wyr", 3, "would you rather...", _lines(WYR)),
    Unlock("fact", 3, "a random fact", _lines(FACTS)),
    Unlock("quote", 3, "a random quote", _lines(QUOTES)),
    Unlock("pickup", 3, "a terrible pickup line", _lines(PICKUP)),
    Unlock("fortune", 3, "your fortune", _lines(FORTUNES)),
    Unlock("excuse", 3, "an excuse for anything", _lines(EXCUSES)),
    Unlock("showerthought", 3, "a shower thought", topic),
    Unlock("compliment", 3, "compliment someone", _pair(COMPLIMENTS)),
    Unlock("roast", 3, "roast someone", _pair(ROASTS)),

    # ---------------------------------- level 4: toolbox
    Unlock("rps", 4, "rock paper scissors", tools.rps),
    Unlock("random", 4, "random number in a range", tools.random_number),
    Unlock("uuid", 4, "a fresh uuid4", tools.uuid4),
    Unlock("password", 4, "generate a password", tools.password),
    Unlock("base64", 4, "encode / decode base64", _text("base64", text.base64_cmd, "encode|decode <text>")),
    Unlock("rot13", 4, "rot13 a message", _text("rot13", text.rot13)),
    Unlock("md5", 4, "md5 hash of text", _text("md5", text.hash_text("md5"))),
    Unlock("sha256", 4, "sha256 hash of text", _text("sha256", text.hash_text("sha256"))),
    Unlock("count", 4, "characters, words, lines, bytes", _text("count", text.count_text)),
    Unlock("palindrome", 4, "is it a palindrome?", _text("palindrome", text.palindrome)),
    Unlock("timestamp", 4, "unix time -> discord timestamps", tools.timestamp),

    # ---------------------------------- level 5: social
    Unlock("slap", 5, "slap someone", _pair(SLAP)),
    Unlock("hug", 5, "hug someone", _pair(HUG)),
    Unlock("pat", 5, "pat someone", _pair(PAT)),
    Unlock("bonk", 5, "bonk someone", _pair(BONK)),
    Unlock("kiss", 5, "kiss someone", _pair(KISS)),
    Unlock("highfive", 5, "high-five someone", _pair(HIGHFIVE)),
    Unlock("poll", 5, "make a poll", poll),
    Unlock("timer", 5, "set a timer, e.g. 10m", timer),
    Unlock("hype", 5, "hype something up", hype),
    Unlock("congrats", 5, "congratulate someone", _pair(CONGRATS)),
    Unlock("simp", 5, "call someone out", _pair(SIMP)),

    # ---------------------------------- level 6: deluxe
    Unlock("shrug", 6, "¯\\_(ツ)_/¯", lambda c, x, a: "¯\\_(ツ)_/¯"),
    Unlock("tableflip", 6, "(╯°□°)╯︵ ┻━┻", lambda c, x, a: "(╯°□°)╯︵ ┻━┻"),
    Unlock("unflip", 6, "┬─┬ノ( º _ ºノ)", lambda c, x, a: "┬─┬ノ( º _ ºノ)"),
    Unlock("lenny", 6, "( ͡° ͜ʖ ͡°)", lambda c, x, a: "( ͡° ͜ʖ ͡°)"),
    Unlock("disapprove", 6, "ಠ_ಠ", lambda c, x, a: "ಠ_ಠ"),
    Unlock("sparkle", 6, "✧･ﾟ: *✧ text ✧*:･ﾟ✧", _text("sparkle", text.sparkle)),
    Unlock("aesthetic", 6, "ａ ｅ ｓ ｔ ｈ ｅ ｔ ｉ ｃ", _text("aesthetic", text.aesthetic)),
    Unlock("glitch", 6, "g̷l̶i̵t̴c̸h̷ a message", _text("glitch", text.glitch)),
    Unlock("quoteit", 6, "turn text into a blockquote", _text("quoteit", text.quoteit)),
    Unlock("sign", 6, "box your text", _text("sign", text.sign)),
    Unlock("topcmd", 6, "your most used commands", tools.topcmd),

    # ---------------------------------- level 7: nightshift
    Unlock("progress", 7, "ten-cell bar for any fraction", extra.progress),
    Unlock("subtext", 7, "small grey text", extra.subtext),
    Unlock("strikethrough", 7, "~~cross it out~~", extra.strikethrough),
    Unlock("underline", 7, "underline a message", extra.underline),
    Unlock("codeblock", 7, "wrap text in a code block", extra.codeblock),

    # ---------------------------------- level 8: workshop
    Unlock("unicode", 8, "codepoints for a string", extra.unicode_lookup),
    Unlock("json", 8, "pretty-print json", extra.json_pretty),
    Unlock("jwt", 8, "decode a jwt header and payload", extra.jwt),
    Unlock("slug", 8, "slugify a title", extra.slug),
    Unlock("urlencode", 8, "url-encode text", extra.urlencode),

    # ---------------------------------- level 9: guild
    Unlock("caesar", 9, "caesar shift, default 3", extra.caesar),
    Unlock("roman", 9, "roman numerals both ways", extra.roman),
    Unlock("percent", 9, "what percent is a of b", extra.percent),
    Unlock("split", 9, "split a bill with tip", extra.split_bill),
    Unlock("sort", 9, "sort lines of text", extra.sort_lines),

    # ---------------------------------- level 10: legend
    Unlock("dedupe", 10, "drop duplicate lines", extra.dedupe),
    Unlock("sum", 10, "total, mean, min and max", extra.sum_numbers),
    Unlock("horoscope", 10, "today's reading, offline", extra.horoscope),
    Unlock("tarot", 10, "draw a major arcana card", extra.tarot),
    Unlock("piglatin", 10, "ellohay orldway", extra.piglatin),
]


def by_level(level: int):
    return [entry for entry in UNLOCKS if entry.level == level]


def find(name: str):
    for entry in UNLOCKS:
        if entry.name == name:
            return entry
    return None


def total_for_level(level: int) -> int:
    return len(by_level(level))
