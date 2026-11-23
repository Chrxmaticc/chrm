"""XP, levels and achievements -- the numbers behind ``.levels``.

Nothing here touches discord or the network: it is pure state plus a table of
achievement predicates, so the cog in ``plugin.py`` stays about commands and the
tests can exercise the maths without a bot.

The curve is deliberately generous. One level is :data:`XP_PER_LEVEL` XP, a
command is worth :data:`COMMAND_XP`, so a level is roughly six commands or a mix
of commands and chatting. Levels stop at :data:`MAX_LEVEL`; XP keeps counting
past it (``.levels`` shows a plain total once you are maxed, and the last
achievement needs 1,000 XP).

State shape (what lands in ``settings.features.levels``)::

    {
      "xp": 140,
      "notify": true,
      "achievements": {"first_steps": 1720000000, ...},
      "stats": {
        "commands": 24, "messages": 311,
        "used": {"roll": 5, "8ball": 2, ...},
        "days": ["2026-11-20", ...], "best_streak": 4,
        "night": false, "early": true,
        "started": 1720000000
      }
    }
"""
from __future__ import annotations

import time
from datetime import date, timedelta

# ---------------------------------------------------------------- tuning
#: XP needed for one level
XP_PER_LEVEL = 60
#: last level; XP keeps accumulating past it
MAX_LEVEL = 6
#: XP for finishing any command
COMMAND_XP = 10
#: XP for a message you send, at most once per MESSAGE_COOLDOWN seconds
MESSAGE_XP = 2
MESSAGE_COOLDOWN = 40
#: how often dirty state is pushed to the dashboard
FLUSH_SECONDS = 45
#: level-up / achievement toasts in the channel you were in
NOTIFY_DEFAULT = True

#: what each level calls you
TITLES = {
    1: "chrmling",
    2: "chrmlet",
    3: "chrmite",
    4: "chrmster",
    5: "chrmlord",
    6: "chrmprime",
}

#: how many recent days of activity are kept for streaks
DAYS_KEPT = 120


# ---------------------------------------------------------------- levels
def level_for(xp) -> int:
    """Level for a total XP count. Level 1 starts at 0 XP."""
    return min(MAX_LEVEL, 1 + max(0, int(xp or 0)) // XP_PER_LEVEL)


def title_for(level: int) -> str:
    return TITLES.get(int(level), TITLES[MAX_LEVEL])


def xp_into(xp) -> int:
    """XP earned inside the current level."""
    if level_for(xp) >= MAX_LEVEL:
        return XP_PER_LEVEL
    return max(0, int(xp or 0)) % XP_PER_LEVEL


def xp_needed(xp) -> int:
    """XP the current level costs. Always XP_PER_LEVEL, kept for the card."""
    return XP_PER_LEVEL


def xp_to_next(xp) -> int:
    """XP still missing before the next level (0 when maxed)."""
    if level_for(xp) >= MAX_LEVEL:
        return 0
    return XP_PER_LEVEL - xp_into(xp)


def bar(xp, width: int = 10) -> str:
    """``▰▰▰▱▱▱▱▱▱▱`` for the current level."""
    into = xp_into(xp)
    filled = int(round(width * into / max(1, XP_PER_LEVEL)))
    filled = max(0, min(width, filled))
    return "▰" * filled + "▱" * (width - filled)


# ---------------------------------------------------------------- state
def default_stats() -> dict:
    return {
        "commands": 0,
        "messages": 0,
        "used": {},
        "days": [],
        "best_streak": 0,
        "night": False,
        "early": False,
        "started": int(time.time()),
    }


def empty_state() -> dict:
    return {
        "xp": 0,
        "notify": NOTIFY_DEFAULT,
        "achievements": {},
        "stats": default_stats(),
    }


def _int(value, fallback=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def normalise(state) -> dict:
    """Fill in every key :func:`merge` and the cog read, without dropping extras."""
    out = empty_state()
    if isinstance(state, dict):
        out.update(state)
    out["xp"] = max(0, _int(out.get("xp")))
    out["notify"] = bool(out.get("notify", NOTIFY_DEFAULT))

    achievements = out.get("achievements")
    out["achievements"] = dict(achievements) if isinstance(achievements, dict) else {}

    stats = out.get("stats")
    stats = dict(stats) if isinstance(stats, dict) else {}
    base = default_stats()
    base.update(stats)
    base["commands"] = max(0, _int(base.get("commands")))
    base["messages"] = max(0, _int(base.get("messages")))
    base["best_streak"] = max(0, _int(base.get("best_streak")))
    base["night"] = bool(base.get("night"))
    base["early"] = bool(base.get("early"))
    used = base.get("used")
    base["used"] = {str(k): max(0, _int(v)) for k, v in used.items()} if isinstance(used, dict) else {}
    days = base.get("days")
    base["days"] = sorted({str(d) for d in days})[-DAYS_KEPT:] if isinstance(days, list) else []
    out["stats"] = base
    return out


def merge(live: dict, incoming) -> dict:
    """Fold two states into one, keeping whichever side is further along.

    The dashboard owns the settings blob and its editor can send back an older
    copy of ``features``. Treating XP and counters as monotonic means a stale
    write can never delete progress, and achievements are a union.
    """
    live = normalise(live)
    if not isinstance(incoming, dict):
        return live
    incoming = normalise(incoming)

    live["xp"] = max(live["xp"], incoming["xp"])
    live["achievements"].update(incoming["achievements"])

    a, b = live["stats"], incoming["stats"]
    a["commands"] = max(a["commands"], b["commands"])
    a["messages"] = max(a["messages"], b["messages"])
    a["best_streak"] = max(a["best_streak"], b["best_streak"])
    a["night"] = a["night"] or b["night"]
    a["early"] = a["early"] or b["early"]
    a["started"] = min(a["started"], b["started"])
    for name, count in b["used"].items():
        a["used"][name] = max(a["used"].get(name, 0), count)
    a["days"] = sorted(set(a["days"]) | set(b["days"]))[-DAYS_KEPT:]
    return live


def touch_day(state: dict) -> None:
    """Record today as an active day and refresh the best streak."""
    today = date.today().isoformat()
    days = state["stats"]["days"]
    if today not in days:
        days.append(today)
        state["stats"]["days"] = days[-DAYS_KEPT:]
    state["stats"]["best_streak"] = max(state["stats"]["best_streak"], current_streak(state))


def current_streak(state: dict) -> int:
    """Consecutive active days ending today (or yesterday, before you've played)."""
    days = set(state.get("stats", {}).get("days") or [])
    if not days:
        return 0
    today = date.today()
    if today.isoformat() in days:
        start = today
    elif (today - timedelta(days=1)).isoformat() in days:
        start = today - timedelta(days=1)
    else:
        return 0

    length = 0
    while (start - timedelta(days=length)).isoformat() in days:
        length += 1
    return length


# ---------------------------------------------------------------- achievements
def _stats(state):
    return state.get("stats") or {}


def _used(state):
    return _stats(state).get("used") or {}


def _level(state) -> int:
    return level_for(state.get("xp"))


#: (id, name, description, emoji, test)
ACHIEVEMENTS = [
    ("first_steps", "first steps", "run your first command", "🐣",
     lambda s: _stats(s).get("commands", 0) >= 1),
    ("warmed_up", "warmed up", "reach level 2", "🔥",
     lambda s: _level(s) >= 2),
    ("halfway", "halfway there", "reach level 4", "🌗",
     lambda s: _level(s) >= 4),
    ("maxed", "maxed out", "reach level 6", "👑",
     lambda s: _level(s) >= 6),
    ("grinder", "grinder", "run 250 commands", "⚙️",
     lambda s: _stats(s).get("commands", 0) >= 250),
    ("chatterbox", "chatterbox", "send 1,000 messages", "💬",
     lambda s: _stats(s).get("messages", 0) >= 1000),
    ("streak_3", "three in a row", "be active 3 days in a row", "📅",
     lambda s: current_streak(s) >= 3),
    ("streak_7", "weekly", "be active 7 days in a row", "🗓️",
     lambda s: current_streak(s) >= 7),
    ("night_owl", "night owl", "run a command between 2am and 5am", "🌙",
     lambda s: bool(_stats(s).get("night"))),
    ("early_bird", "early bird", "run a command between 5am and 8am", "🌅",
     lambda s: bool(_stats(s).get("early"))),
    ("explorer", "explorer", "use 15 different commands", "🎲",
     lambda s: len(_used(s)) >= 15),
    ("completionist", "completionist", "use 50 different commands", "🧩",
     lambda s: len(_used(s)) >= 50),
    ("collector", "collector", "use .pinterest", "📌",
     lambda s: "pinterest" in _used(s)),
    ("gamer", "gamer", "use .fakeplay", "🎮",
     lambda s: "fakeplay" in _used(s)),
    ("shapeshifter", "shapeshifter", "use .rpc, .spotify and .fakeplay", "🎭",
     lambda s: {"rpc", "spotify", "fakeplay"} <= set(_used(s))),
    ("social", "social animal", "slap, hug and pat someone", "🤝",
     lambda s: {"slap", "hug", "pat"} <= set(_used(s))),
    ("farmer", "farmer", "run .farmtime", "🚜",
     lambda s: "farmtime" in _used(s)),
    ("four_digits", "four digits", "earn 1,000 xp", "💎",
     lambda s: _int(s.get("xp")) >= 1000),
]

#: id -> achievement tuple, for lookups
BY_ID = {entry[0]: entry for entry in ACHIEVEMENTS}


def evaluate(state: dict) -> list:
    """Award every achievement the state now qualifies for; return the new ones."""
    earned = state["achievements"]
    fresh = []
    for entry in ACHIEVEMENTS:
        key = entry[0]
        if key in earned:
            continue
        try:
            passed = entry[4](state)
        except Exception:  # noqa: BLE001 - a broken predicate must not break a command
            passed = False
        if passed:
            earned[key] = int(time.time())
            fresh.append(entry)
    return fresh


def unlocked(state: dict) -> list:
    earned = state.get("achievements") or {}
    return [entry for entry in ACHIEVEMENTS if entry[0] in earned]
