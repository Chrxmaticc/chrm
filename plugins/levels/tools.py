"""Generators and tools: dice, coins, ratings, hashes, ids, timestamps.

Runners here take ``(cog, ctx, arg)`` so the catalogue can register them
uniformly; most ignore ``cog`` and ``ctx``, except ``.rate``/``.ship`` which
seed on the author so the score stays stable for that person.
"""
from __future__ import annotations

import random
import re
import secrets
import time
import uuid as _uuid
from datetime import datetime, timezone

from plugins.levels.base import digest, usage

EIGHT_BALL = [
    "it is certain.", "without a doubt.", "yes, definitely.", "you may rely on it.",
    "most likely.", "outlook good.", "yes.", "signs point to yes.",
    "reply hazy, try again.", "ask again later.", "better not tell you now.",
    "cannot predict now.", "concentrate and ask again.", "don't count on it.",
    "my reply is no.", "my sources say no.", "outlook not so good.", "very doubtful.",
    "absolutely not.", "in your dreams.",
]


def eight_ball(cog, ctx, arg):
    question = (arg or "").strip()
    if not question:
        return usage("usage: `.8ball <question>`")
    return f"🎱 {random.choice(EIGHT_BALL)}"


def coinflip(cog, ctx, arg):
    return f"🪙 **{random.choice(['heads', 'tails'])}**"


def roll(cog, ctx, arg):
    spec = (arg or "").strip().lower() or "1d6"
    match = re.fullmatch(r"(\d*)d(\d+)|(\d+)", spec)
    if not match:
        return usage("usage: `.roll [XdY]` — e.g. `.roll 2d20`")
    if match.group(3):
        count, sides = 1, int(match.group(3))
    else:
        count = int(match.group(1) or 1)
        sides = int(match.group(2))
    count = max(1, min(count, 20))
    sides = max(2, min(sides, 1000))
    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls)
    shown = " + ".join(map(str, rolls))
    return f"🎲 {f'{shown} = ' if count > 1 else ''}**{total}**  ({count}d{sides})"


def choose(cog, ctx, arg):
    options = [part.strip() for part in re.split(r"\s*\|\s*|\s*,\s*", arg or "") if part.strip()]
    if len(options) < 2:
        return usage("usage: `.choose pizza | sushi | tacos`")
    return f"👉 **{random.choice(options)}**"


def rate(cog, ctx, arg):
    thing = (arg or "").strip()
    if not thing:
        return usage("usage: `.rate <thing>`")
    score = digest(str(getattr(getattr(ctx, "author", None), "id", 0)), thing, 11)
    verdict = "certified mid." if score == 5 else ("peak." if score >= 9 else ("rough." if score <= 2 else "not bad."))
    return f"**{thing}** — **{score}/10** · {verdict}"


def ship(cog, ctx, arg):
    names = [part.strip() for part in re.split(r"\s*(?:\+|&|,|\band\b)\s*", arg or "") if part.strip()]
    if len(names) < 2:
        author = getattr(getattr(ctx, "author", None), "display_name", "you")
        names = [author, (arg or "").strip().lstrip("@")] if (arg or "").strip() else []
        if len(names) < 2 or not names[1]:
            return usage("usage: `.ship <one> <two>`")
    key = " + ".join(sorted(name.lower() for name in names))
    score = digest("ship", key, 101)
    filled = round(score / 10)
    hearts = "💗" * filled + "🤍" * (10 - filled)
    return f"**{names[0]}** + **{names[1]}**\n{hearts} **{score}%**"


def rps(cog, ctx, arg):
    move = (arg or "").strip().lower()
    if move not in ("rock", "paper", "scissors"):
        return usage("usage: `.rps rock|paper|scissors`")
    bot_move = random.choice(["rock", "paper", "scissors"])
    beats = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
    if move == bot_move:
        result = "tie."
    elif beats[move] == bot_move:
        result = "you win."
    else:
        result = "i win."
    icon = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
    return f"{icon[move]} vs {icon[bot_move]} — **{result}** ({move} vs {bot_move})"


def random_number(cog, ctx, arg):
    parts = [part for part in (arg or "").replace(",", " ").split() if part]
    try:
        if len(parts) >= 2:
            low, high = int(parts[0]), int(parts[1])
        elif parts:
            low, high = 1, int(parts[0])
        else:
            low, high = 1, 100
    except ValueError:
        return usage("usage: `.random [max]` or `.random <min> <max>`")
    if low > high:
        low, high = high, low
    if high - low > 10_000_000:
        high = low + 10_000_000
    return f"🎲 **{random.randint(low, high)}** ({low}–{high})"


def uuid4(cog, ctx, arg):
    return f"`{_uuid.uuid4()}`"


def password(cog, ctx, arg):
    try:
        length = max(8, min(int((arg or "").strip() or 16), 64))
    except ValueError:
        length = 16
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%^&*-_=+"
    return f"`{''.join(secrets.choice(alphabet) for _ in range(length))}`"


def timestamp(cog, ctx, arg):
    raw = (arg or "").strip()
    try:
        stamp = int(float(raw)) if raw else int(time.time())
    except ValueError:
        return usage("usage: `.timestamp [unix seconds]`")
    if stamp > 10_000_000_000:  # milliseconds
        stamp //= 1000
    when = datetime.fromtimestamp(stamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"unix `{stamp}` · {when} · <t:{stamp}:F> · <t:{stamp}:R>"


def topcmd(cog, ctx, arg):
    used = (cog.state.get("stats") or {}).get("used") or {}
    if not used:
        return "no commands counted yet."
    ranked = sorted(used.items(), key=lambda item: (-item[1], item[0]))[:5]
    medals = ["🥇", "🥈", "🥉", "4.", "5."]
    lines = [f"{medals[i]} `.{name}` — **{count}**" for i, (name, count) in enumerate(ranked)]
    return "**your most used commands**\n" + "\n".join(lines)
