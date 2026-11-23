"""Everything you can do on a ``commands.Context``: feedback and the help surface.

Feedback (used by every cog)::

    await ctx.approve("human delay is now **OFF**")
    await ctx.deny("invalid numbers.")
    await ctx.warn("max is 15 to prevent rate limits.")

Help::

    .help                 category index card
    .help <category>      one category's commands
    .help text [category] plain text instead of a card
    .help url             the raw discord.builders link, for copying

Both are installed onto ``commands.Context`` at import time, so the ``.help``
command in :class:`Help` below is only a thin wrapper over
:func:`send_bot_help` -- ``ctx.send_bot_help()`` works anywhere, including from a
listener or another cog, without a command context.

Emoji resolution: ``bot.config.get_emoji(...)`` (config.json / dashboard) first,
then the class defaults in :mod:`core.config` (``EMOJIS.DENY``), then a literal.
A half-filled config still renders something recognisable.

Why this file is not three files: the feedback helpers and the help card are the
same job -- "say something back on a context" -- and the help categories have to
stay next to the plugins they describe. Keeping them together also means one
``install()`` patch instead of one per feature.
"""
import re

from discord.ext import commands

from core.config import EMOJIS
from core.ui import cv2 as v2

# ==========================================
# 1. FEEDBACK: approve / deny / warn
# ==========================================
#: outcome -> key looked up in ``config.json -> emojis``
_EMOJI_KEY = {"approve": "success", "deny": "error", "warn": "error"}

#: used when the key is missing or the config is not loaded (yet)
_EMOJI_FALLBACK = {"approve": EMOJIS.APPROVE, "deny": EMOJIS.DENY, "warn": EMOJIS.WARN}


def _emoji(ctx, outcome: str) -> str:
    config = getattr(getattr(ctx, "bot", None), "config", None)
    if config is not None:
        try:
            value = config.get_emoji(_EMOJI_KEY[outcome])
        except Exception:  # noqa: BLE001 - a broken config must not break feedback
            value = ""
        if value:
            return value
    return _EMOJI_FALLBACK[outcome]


async def _emit(
    ctx,
    outcome: str,
    text: str = "",
    *,
    reply: bool = False,
    delete: bool = False,
    **kwargs,
):
    """Send ``<emoji> <text>`` and return the message, or ``None`` if sending failed.

    ``reply=True`` quotes the command message; ``delete=True`` removes the command
    message afterwards (falls back to a plain channel message once it is gone, so
    a selfbot that already deleted its own invocation still gets feedback).
    """
    body = f"{_emoji(ctx, outcome)} {text}".rstrip()
    message = None
    try:
        if reply:
            try:
                message = await ctx.send(body, reference=ctx.message, mention_author=False, **kwargs)
            except Exception:  # noqa: BLE001 - invoking message deleted/too old
                message = await ctx.send(body, **kwargs)
        else:
            message = await ctx.send(body, **kwargs)
    except Exception as exc:  # noqa: BLE001 - feedback must never raise
        print(f"[context] {outcome} failed in {getattr(ctx, 'command', None)}: {exc}")
    if delete:
        try:
            await ctx.message.delete()
        except Exception:  # noqa: BLE001
            pass
    return message


async def approve(ctx, text: str = "", **kwargs):
    """Something worked. ``await ctx.approve("saved")``"""
    return await _emit(ctx, "approve", text, **kwargs)


async def deny(ctx, text: str = "", **kwargs):
    """Something was rejected or errored. ``await ctx.deny(f"failed: {e}")``"""
    return await _emit(ctx, "deny", text, **kwargs)


async def warn(ctx, text: str = "", **kwargs):
    """Did not fail, but the user should know. ``await ctx.warn("capped at 15")``"""
    return await _emit(ctx, "warn", text, **kwargs)


# ==========================================
# 2. HELP CONTENT
# ==========================================
TAGLINE = "*chrm on top.*"

#: container accent colour for the cards
ACCENT = 0x1F1F23

#: invisible link text -- shows only the unfurled component card
MASK = "."

# category -> [(usage, description)] ; usage is rendered as inline code.
# Categories match the plugin folders in plugins/ : fun, utility, information, config.
# Keep descriptions short: each category card has to stay under
# core.ui.cv2.MAX_EMBED_BYTES.
CATEGORIES = {
    "levels": [
        ("levels", "xp bar, streak, what is next"),
        ("cmds [level] / unlocks", "every unlockable command, by level"),
        ("achievements", "the trophy case"),
        ("levelnotify on|off", "level-up and achievement messages"),
    ],
    "friends": [
        ("friendadd <@user | id | name>", "send a friend request"),
        ("friendcount / pending", "friends, blocked, ignored, requests"),
        ("request accept|deny <@user | id>", "answer a friend request"),
        ("friendrename <@user> <nick> / resetname <@user>", "friend nicknames"),
        ("unfriend <@user> / massunfriend confirm", "remove one friend, or all of them"),
        ("ignore <@user> / unignore <@user>", "hide someone without blocking"),
        ("mute [@user] / unmute [@user]", "silence a dm, or the one you are in"),
        ("unblock <@user>", "undo a block"),
        ("relationshipnotifier on|off", "friend, unfriend and server join posts"),
    ],
    "fun": [
        ("rpc <type> <name> | <details> | <state> | <img>", "custom rich presence"),
        ("rpcmenu", "interactive rpc builder"),
        ("presencedump", "what we actually send to discord"),
        ("stream <url> <title>", "fake twitch stream"),
        ("customstatus <text> / clearstatus", "plain status, or wipe it"),
        ("startrotator <statuses> / stoprotator", "rotate statuses"),
        ("spotify <song> - <artist> / stopspotify", "fake spotify"),
        ("fakeplay <game> [| details | state | 52%] [--listen]", "fake a game; also --watch --compete"),
        ("fakechat <text> [user=] [theme=]", "fake message image"),
        ("autobadges [amount] [secs] / stopbadges", "fake game rotation (cosmetic)"),
        ("farmtime [games] [hours_each]", "credit game time / variety telemetry"),
        ("device <platform>", "ios, android, windows, xbox"),
        ("pinterest <query> | board <user>/<board> | user <name>", "pins, boards, profiles"),
        ("testrpc", "presence sanity check"),
    ],
    "utility": [
        ("purge [amount]", "delete your own messages"),
        ("type <seconds>", "hold the typing indicator, send nothing"),
        ("snipe [index]", "last deleted message"),
        ("editsnipe [index]", "last edited message"),
        ("reactionsnipe [index]", "last removed reaction"),
        ("transcript [amount]", "export the chat to html"),
        ("gcname <name> / spamname <count> <name>", "rename a group chat"),
        ("gcadd / gcremove / gclist / gcnuke / gcleave", "group chat members"),
        ("autoleave / autoadd [@user]", "auto leave invites, auto add to gcs"),
        ("blacktea", "house special"),
    ],
    "information": [
        ("userinfo [@user | id]", "account age, ids, roles"),
        ("serverinfo", "server stats"),
        ("avatar [@user | id]", "profile picture links"),
        ("banner [@user | id]", "profile banner link"),
        ("rblxuser / rblxavatar / rblxheadshot / rblxgroups", "roblox lookups"),
        ("ai <prompt>", "chromed ai chat"),
        ("lyrics <song> / stoplyrics", "lyrics in your status"),
        ("lastfm <user> | top <user> [range]", "libre.fm / last.fm listening"),
    ],
    "config": [
        ("prefixes", "active prefixes"),
        ("addprefix / removeprefix <prefix>", "add or drop a prefix"),
        ("resetprefix", "back to `.` `,` `?`"),
        ("toggledelay [min] [max]", "human delay before commands"),
        ("responder add|remove|list", "auto-reply on match. alias `respond`"),
        ("reaction add|remove|list", "auto-react on match. alias `react`"),
        ("afk [msg] / unafk", "away auto-reply"),
        ("addcmd / delcmd / listcmds", "your own text commands"),
        ("alias add|remove|list", "command shortcuts"),
        ("schedule <time> <channel> <message>", "send a message later"),
        ("alibi <time> <channel> <message>", "look active on a timer"),
        ("setname / setavatar [url] / setbanner [url]", "profile fields"),
        ("addrotation / startrotation / stoprotation", "rotate profile art"),
        ("namerotator <names> <interval> / stopname", "rotate names"),
        ("reload <plugin> / restart", "hot reload, or restart the engine"),
        ("sysinfo / help [category]", "engine stats, this menu"),
    ],
}

#: Words that also open a category, e.g. `.help rpc` or `.help triggers`.
#: The old names are kept so muscle memory from before the rename still works.
EXTRA_KEYS = {
    "level": "levels",
    "xp": "levels",
    "progress": "levels",
    "achievement": "levels",
    "achievements": "levels",
    "trophy": "levels",
    "trophies": "levels",
    "unlocks": "levels",
    "command": "levels",
    "commands": "levels",
    "friend": "friends",
    "friends": "friends",
    "friendlist": "friends",
    "pending": "friends",
    "unfriend": "friends",
    "unblock": "friends",
    "ignore": "friends",
    "unignore": "friends",
    "mute": "friends",
    "unmute": "friends",
    "request": "friends",
    "presence": "fun",
    "rpc": "fun",
    "status": "fun",
    "spoof": "fun",
    "spoofing": "fun",
    "triggers": "config",
    "messages": "config",
    "msg": "config",
    "schedules": "config",
    "aliases": "config",
    "profile": "config",
    "pfp": "config",
    "automation": "config",
    "snipe": "utility",
    "sniping": "utility",
    "channels": "utility",
    "lookup": "information",
    "info": "information",
}


def resolve_category(arg: str):
    """Map what the user typed to a category name, or None."""
    wanted = " ".join(arg.lower().split())
    if wanted in EXTRA_KEYS:
        return EXTRA_KEYS[wanted]
    for name in CATEGORIES:
        keys = {name, name.replace(" & ", " "), name.replace(" ", ""), name.replace("&", "")}
        keys.update(part for part in re.split(r"[^a-z0-9]+", name) if part)
        if wanted in keys:
            return name
    return None


# ==========================================
# 3. HELP CARDS
# ==========================================
def _prefix(bot) -> str:
    prefix = getattr(bot, "command_prefix", ".")
    prefix = prefix[0] if isinstance(prefix, (list, tuple)) else prefix
    # command_prefix on a self-bot instance can be a callable
    if callable(prefix):
        prefix = "."
    return prefix


def _total() -> int:
    return sum(len(entries) for entries in CATEGORIES.values())


def build_index_components(bot, prefix: str):
    """The category index: names, counts and how to open each one."""
    lines = []
    for name, entries in CATEGORIES.items():
        key = name.split(" & ")[0]
        lines.append(f"**{name}** · {len(entries)} · `{prefix}help {key}`")

    name = getattr(getattr(bot, "user", None), "name", "chrm")
    children = [
        v2.text(f"### {name} — selfbot commands"),
        v2.text(f"prefix `{prefix}` · {len(CATEGORIES)} categories · {_total()} commands"),
    ]

    # The levels cog owns progression; show where the account is without
    # importing plugins/ into the framework. Older builds simply omit the line.
    levels = bot.get_cog("Levels") if hasattr(bot, "get_cog") else None
    if levels is not None and hasattr(levels, "level"):
        children.append(
            v2.text(
                f"your level **{levels.level}** · {levels.unlocked_count}/{levels.total} "
                f"unlocked · `{prefix}levels`"
            )
        )

    children += [
        v2.separator(spacing=1),
        v2.text("\n".join(lines)),
        v2.separator(spacing=2),
        v2.text(f"run `{prefix}help <category>` to list one · {TAGLINE}"),
    ]
    return [v2.container(*children, accent_color=ACCENT)]


def build_category_components(prefix: str, name: str):
    """One category's commands, plus the way back to the index."""
    lines = [f"`{prefix}{usage}` — {desc}" for usage, desc in CATEGORIES[name]]
    children = [
        v2.text(f"### {name}"),
        v2.text(f"{len(lines)} commands · prefix `{prefix}`"),
        v2.separator(spacing=1),
        v2.text("\n".join(lines)),
        v2.separator(spacing=2),
        v2.text(f"`{prefix}help` for the category list · {TAGLINE}"),
    ]
    return [v2.container(*children, accent_color=ACCENT)]


def build_plain(bot, prefix: str, name: str = None) -> str:
    names = [name] if name else list(CATEGORIES)
    user = getattr(getattr(bot, "user", None), "name", "chrm")
    out = [f"**{user} — selfbot commands**", f"*prefix: `{prefix}`*", ""]
    for category in names:
        out.append(f"**{category}**")
        out.extend(f"`{prefix}{usage}`" for usage, _ in CATEGORIES[category])
        out.append("")
    out.append(TAGLINE)
    return "\n".join(out)


def build_index_plain(bot, prefix: str) -> str:
    user = getattr(getattr(bot, "user", None), "name", "chrm")
    out = [
        f"**{user} — selfbot commands**",
        f"*prefix: `{prefix}` · {len(CATEGORIES)} categories · {_total()} commands*",
        "",
    ]
    for name, entries in CATEGORIES.items():
        key = name.split(" & ")[0]
        out.append(f"**{name}** · {len(entries)} · `{prefix}help {key}`")
    out.append("")
    out.append(TAGLINE)
    return "\n".join(out)


async def _send_card(ctx, components, prefix: str, name: str = None):
    """Post the card as a masked discord.builders link, or plain text if oversized."""
    if components is None or not v2.embed_fits(components):
        where = f"category `{name}`" if name else "menu"
        text = build_plain(ctx.bot, prefix, name) if name else build_index_plain(ctx.bot, prefix)
        return await ctx.send(
            f"{where} is over Discord's {v2.MAX_EMBED_BYTES}-byte embed limit, "
            f"showing text instead:\n\n{text}"
        )
    await ctx.send(f"[{MASK}]({v2.share_url(components)})")


async def send_bot_help(ctx, arg: str = None):
    """The whole help surface. ``ctx.send_bot_help()`` from anywhere, or via ``.help``."""
    prefix = _prefix(ctx.bot)
    arg = (arg or "").strip().lower()

    # .help url -> the raw index link, for copying
    if arg in ("url", "raw", "link"):
        components = build_index_components(ctx.bot, prefix)
        if not v2.embed_fits(components):
            return await ctx.send(build_index_plain(ctx.bot, prefix))
        # <> stops Discord from turning the long URL into a preview card.
        return await ctx.send(f"<{v2.share_url(components)}>")

    # .help text / .help text <category>
    if arg == "text" or arg.startswith("text "):
        name = resolve_category(arg[5:]) if arg.startswith("text ") else None
        return await ctx.send(build_plain(ctx.bot, prefix, name))

    if not arg:
        return await _send_card(ctx, build_index_components(ctx.bot, prefix), prefix)

    name = resolve_category(arg)
    if name is None:
        return await ctx.send(
            f"no category `{arg}`. try `.help` for the list, or `.help text` for everything."
        )

    await _send_card(ctx, build_category_components(prefix, name), prefix, name)


# ==========================================
# 4. HELP COG
# ==========================================
class Help(commands.Cog):
    """``.help`` -- a thin wrapper over :func:`send_bot_help`."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_command(self, ctx, *, arg: str = None):
        """category index card. `.help <category>` for commands. `.help text` for plain text."""
        return await send_bot_help(ctx, arg)


async def setup(bot):
    await bot.add_cog(Help(bot))


# ==========================================
# 5. INSTALL
# ==========================================
_PATCHES = {
    "approve": approve,
    "deny": deny,
    "warn": warn,
    "send_bot_help": send_bot_help,
}


def install() -> None:
    """Attach the helpers to ``commands.Context``. Safe to call more than once."""
    for name, func in _PATCHES.items():
        if not hasattr(commands.Context, name):
            setattr(commands.Context, name, func)


install()
