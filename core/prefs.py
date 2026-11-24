"""Per-account preferences shared by the config cog, the games and the engine.

Everything lives under ``settings.features.prefs`` so it rides the same blob as
the other features and survives a redeploy. Values are deliberately few and
typed: the config commands validate them, everything else only reads.

The engine consults :func:`is_disabled` and :func:`cooldown_left` in
``ChrmInstance.invoke`` -- the one place every command passes through -- so a
disabled command costs one dict lookup and a cooldown costs one compare.
"""
from __future__ import annotations

import time

#: every preference and the value used when it has never been set
DEFAULTS = {
    "wordle_hard": False,
    "wordle_colorblind": False,
    "wordle_spoiler": False,
    "timezone": "UTC",
    "disabled": [],
    "cooldown": 0.0,
    "ignored_channels": [],
}

#: commands that keep working even when everything else is disabled, so the
#: account can never lock itself out of turning things back on
BYPASS = frozenset({"help", "enable", "disable", "disabled", "settings", "prefs"})

#: commands that still run inside an ignored channel -- without these, ignoring
#: the channel you are standing in would leave no way to undo it
CHANNEL_BYPASS = BYPASS | {"ignorechannel", "unignorechannel", "ignoredchannels"}


def raw(bot) -> dict:
    """The mutable preference dict, created on first use."""
    features = bot.config.data.setdefault("features", {})
    prefs = features.get("prefs")
    if not isinstance(prefs, dict):
        prefs = {}
        features["prefs"] = prefs
    return prefs


def get(bot, key: str, default=None):
    """Preference value, else its default, else ``default``."""
    value = raw(bot).get(key)
    if value is None:
        value = DEFAULTS.get(key, default)
    return value


def put(bot, key: str, value) -> None:
    """Write locally. Callers persist with ``api.save_feature``."""
    raw(bot)[key] = value


def reset(bot) -> None:
    """Drop every preference back to its default (wordle stats are elsewhere)."""
    features = bot.config.data.setdefault("features", {})
    features["prefs"] = {
        key: (list(value) if isinstance(value, list) else value)
        for key, value in DEFAULTS.items()
    }


def disabled_names(bot) -> list:
    value = get(bot, "disabled", [])
    return [str(name) for name in value] if isinstance(value, list) else []


def is_disabled(bot, name: str) -> bool:
    return name in disabled_names(bot)


def is_allowed(bot, name: str) -> bool:
    """True when ``name`` may run: not disabled, or on the bypass list."""
    return name in BYPASS or not is_disabled(bot, name)


def ignored_channels(bot) -> list:
    """Channel ids where command dispatch is silenced (``.ignorechannel``)."""
    value = get(bot, "ignored_channels", [])
    if not isinstance(value, list):
        return []
    numbers = []
    for item in value:
        try:
            numbers.append(int(item))
        except (TypeError, ValueError):
            continue
    return numbers


def ignores_channel(bot, channel_id) -> bool:
    return channel_id in ignored_channels(bot)


def cooldown_seconds(bot) -> float:
    try:
        return max(0.0, float(get(bot, "cooldown", 0.0)))
    except (TypeError, ValueError):
        return 0.0


def cooldown_left(bot) -> float:
    """Seconds still to wait before the next command, 0 when ready."""
    wait = cooldown_seconds(bot)
    if wait <= 0:
        return 0.0
    last = float(getattr(bot, "_prefs_last_command", 0.0) or 0.0)
    return max(0.0, wait - (time.monotonic() - last))


def mark(bot) -> None:
    """Record that a command just ran."""
    bot._prefs_last_command = time.monotonic()
