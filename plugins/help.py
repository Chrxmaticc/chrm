"""Help menu rendered through Discord's component-embed unfurler.

Discord refuses Components V2 *message payloads* from user accounts
(``50006`` on v9 and v10 alike). What a self-bot can do is post a
`discord.builders` share link: that page decompresses the payload server-side and
emits

    <script id="discord:component-embed" type="application/json">
      {"component": {...}}
    </script>

Discord's link unfurler reads that script tag and renders the component as a
native card. So the menu is sent as a masked link (zero-width space as the text)
and the card *is* the menu:

    .help              -> category index card (name + count + how to open it)
    .help <category>   -> that category's commands
    .help text [cat]   -> plain text instead
    .help url          -> the raw link, for copying

The unfurl surface is stingy: one root container, at most 40 components and a
hard **3,000-byte** JSON document cap. An oversize payload does not degrade to a
plain link preview -- it renders as "content unavailable", which looks exactly
like a client bug. That is why the commands are split per category instead of
sitting in one card, and why every card is measured before it is sent
(``components_v2.embed_fits``).
"""
import re

from discord.ext import commands

from core import components_v2 as v2

ACCENT = 0x1F1F23

#: Invisible link text -- shows only the unfurled component card.
MASK = "."

TAGLINE = "*chrm on top.*"

# category -> [(usage, description)] ; usage is rendered as inline code.
# Keep descriptions short: each category card has to stay under
# components_v2.MAX_EMBED_BYTES.
CATEGORIES = {
    "triggers": [
        ("responder add <trigger> <response>", "auto-reply on match. alias `respond`"),
        ("responder remove <trigger>", "delete an auto-reply"),
        ("responder list", "show every auto-reply"),
        ("reaction add <trigger> <emoji>", "auto-react on match. alias `react`"),
        ("reaction remove <trigger>", "delete an auto-reaction"),
        ("reaction list", "show every auto-reaction"),
        ("afk [msg] / unafk", "away auto-reply"),
        ("addcmd <trigger> <response>", "custom text command"),
        ("delcmd <trigger> / listcmds", "remove or list custom commands"),
        ("alias add <alias> <command>", "make a command shortcut"),
        ("alias remove <alias> / alias list", "drop or show shortcuts"),
    ],
    "messages": [
        ("schedule <time> <channel> <message>", "send a message later"),
        ("alibi <time> <channel> <message>", "look active on a timer"),
        ("listschedules / clearschedules", "show or wipe schedules"),
        ("purge [amount]", "delete your own messages"),
    ],
    "sniping": [
        ("snipe [index]", "last deleted message"),
        ("editsnipe [index]", "last edited message"),
        ("reactionsnipe [index]", "last removed reaction"),
    ],
    "presence & rpc": [
        ("rpc <type> <name> | <details> | <state> | <img>", "custom rich presence"),
        ("clearstatus", "wipe the active rpc"),
        ("iconplay [app_id] / smalliconplay [app_id]", "swap rpc icons"),
        ("startrotator <statuses> / stoprotator", "rotate statuses"),
        ("fakeplay <game> / stopfakeplay", "fake a game activity"),
        ("spotify <song> - <artist> / stopspotify", "fake spotify"),
        ("lyrics <song> / stoplyrics", "lyrics in your status"),
        ("autobadges [amount] [secs] / stopbadges", "farm playtime"),
        ("device <platform>", "ios, android, windows, xbox"),
        ("testrpc", "presence sanity check"),
    ],
    "profile": [
        ("setname <name>", "display name"),
        ("setavatar [url] / setbanner [url]", "avatar or banner (or attach)"),
        ("namerotator <names> <interval> / stopname", "rotate names"),
        ("addrotation avatar|banner [url]", "queue profile art"),
        ("startrotation [hours] / stoprotation", "rotate profile art"),
    ],
    "utility": [
        ("ai <prompt>", "chromed ai chat"),
        ("fakechat <text> [user=] [theme=]", "fake message image"),
        ("rblxuser / rblxavatar / rblxheadshot / rblxgroups", "roblox lookups"),
        ("sysinfo", "engine stats"),
        ("blacktea", "house special"),
    ],
    "config": [
        ("prefixes", "active prefixes"),
        ("addprefix / removeprefix <prefix>", "add or drop a prefix"),
        ("resetprefix", "back to `.` `,` `?`"),
        ("reload <plugin>", "hot reload one plugin"),
        ("restart", "restart your instance"),
        ("help [category]", "this menu"),
    ],
}

#: Words that also open a category, e.g. `.help rpc` or `.help presence`.
EXTRA_KEYS = {
    "presence": "presence & rpc",
    "rpc": "presence & rpc",
    "status": "presence & rpc",
    "msg": "messages",
    "schedules": "messages",
    "snipe": "sniping",
    "pfp": "profile",
    "aliases": "triggers",
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


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _prefix(self, ctx=None):
        prefix = self.bot.command_prefix
        prefix = prefix[0] if isinstance(prefix, (list, tuple)) else prefix
        # command_prefix on a self-bot instance can be a callable
        if callable(prefix):
            prefix = "."
        return prefix

    def _total(self) -> int:
        return sum(len(entries) for entries in CATEGORIES.values())

    # ------------------------------------------------------------ cards
    def build_index_components(self, prefix: str):
        """The category index: names, counts and how to open each one."""
        lines = []
        for name, entries in CATEGORIES.items():
            key = name.split(" & ")[0]
            lines.append(f"**{name}** · {len(entries)} · `{prefix}help {key}`")

        children = [
            v2.text(f"### {self.bot.user.name} — selfbot commands"),
            v2.text(f"prefix `{prefix}` · {len(CATEGORIES)} categories · {self._total()} commands"),
            v2.separator(spacing=1),
            v2.text("\n".join(lines)),
            v2.separator(spacing=2),
            v2.text(f"run `{prefix}help <category>` to list one · {TAGLINE}"),
        ]
        return [v2.container(*children, accent_color=ACCENT)]

    def build_category_components(self, prefix: str, name: str):
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

    # ------------------------------------------------------------ plain text
    def build_plain(self, prefix: str, name: str = None) -> str:
        names = [name] if name else list(CATEGORIES)
        out = [f"**{self.bot.user.name} — selfbot commands**", f"*prefix: `{prefix}`*", ""]
        for category in names:
            out.append(f"**{category}**")
            out.extend(f"`{prefix}{usage}`" for usage, _ in CATEGORIES[category])
            out.append("")
        out.append(TAGLINE)
        return "\n".join(out)

    def build_index_plain(self, prefix: str) -> str:
        out = [
            f"**{self.bot.user.name} — selfbot commands**",
            f"*prefix: `{prefix}` · {len(CATEGORIES)} categories · {self._total()} commands*",
            "",
        ]
        for name, entries in CATEGORIES.items():
            key = name.split(" & ")[0]
            out.append(f"**{name}** · {len(entries)} · `{prefix}help {key}`")
        out.append("")
        out.append(TAGLINE)
        return "\n".join(out)

    # ------------------------------------------------------------ sending
    async def _send_card(self, ctx, components, prefix: str, name: str = None):
        """Post the card as a masked discord.builders link, or plain text if oversized."""
        if components is None or not v2.embed_fits(components):
            where = f"category `{name}`" if name else "menu"
            return await ctx.send(
                f"{where} is over Discord's {v2.MAX_EMBED_BYTES}-byte embed limit, "
                f"showing text instead:\n\n{self.build_plain(prefix, name) if name else self.build_index_plain(prefix)}"
            )
        await ctx.send(f"[{MASK}]({v2.share_url(components)})")

    @commands.command(name="help")
    async def help_command(self, ctx, *, arg: str = None):
        """category index card. `.help <category>` for commands. `.help text` for plain text."""
        prefix = self._prefix(ctx)
        arg = (arg or "").strip().lower()

        # .help url -> the raw index link, for copying
        if arg in ("url", "raw", "link"):
            components = self.build_index_components(prefix)
            if not v2.embed_fits(components):
                return await ctx.send(self.build_index_plain(prefix))
            # <> stops Discord from turning the long URL into a preview card.
            return await ctx.send(f"<{v2.share_url(components)}>")

        # .help text / .help text <category>
        if arg == "text" or arg.startswith("text "):
            name = resolve_category(arg[5:]) if arg.startswith("text ") else None
            return await ctx.send(self.build_plain(prefix, name))

        if not arg:
            return await self._send_card(ctx, self.build_index_components(prefix), prefix)

        name = resolve_category(arg)
        if name is None:
            return await ctx.send(
                f"no category `{arg}`. try `.help` for the list, or `.help text` for everything."
            )

        await self._send_card(ctx, self.build_category_components(prefix, name), prefix, name)


async def setup(bot):
    await bot.add_cog(Help(bot))
