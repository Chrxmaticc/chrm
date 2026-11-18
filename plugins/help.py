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

    .help        -> [\u200b](https://discord.builders/embed?v1=1$...)
    .help url    -> the raw link, for copying
    .help text   -> plain text command list
"""
from discord.ext import commands

from core import components_v2 as v2

ACCENT = 0x1F1F23

#: Invisible link text -- shows only the unfurled component card.
MASK = "."

# title -> [(usage, description)] ; usage is rendered as inline code
CATEGORIES = {
    "automation": [
        ("addrespond <trigger> <response>", "auto-reply when a message matches the trigger"),
        ("addreact <trigger> <emoji>", "auto-react when a message matches the trigger"),
        ("afk <message> / unafk", "set or clear an afk auto-reply"),
        ("delay <seconds> / toggledelay", "human delay before commands reply"),
        ("prefix / addprefix / removeprefix", "manage command prefixes"),
    ],
    "presence & rpc": [
        ("rpc <type> <name> | <details> | <state> | <img> | elapsed", "full custom rich presence"),
        ("stream <url> <title>", "pretend to be streaming"),
        ("customstatus <text>", "set a plain custom status"),
        ("clearstatus", "wipe the rich presence"),
        ("togglerotator / addstatus", "rotate through saved statuses"),
    ],
    "utility & sniping": [
        ("purge <amount>", "bulk delete your own messages"),
        ("snipe / editsnipe", "show the last deleted or edited message"),
        ("userinfo [@user] / avatar [@user]", "inspect a user"),
        ("blacktea", "house special"),
    ],
    "music & games": [
        ("lyrics <song> / stoplyrics", "live lyrics in your status"),
        ("fakeplay <game> / stopfakeplay", "fake a game activity"),
        ("spotify <song> - <artist> / stopspotify", "fake spotify listening"),
    ],
}


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

    def build_components(self, prefix: str):
        """The component tree for the help menu -- this is what the share URL holds."""
        total = sum(len(cmds) for cmds in CATEGORIES.values())
        children = [
            v2.text(f"### {self.bot.user.name} — selfbot commands"),
            v2.text(f"prefix `{prefix}` · {total} commands · all lowercase"),
        ]

        for name, entries in CATEGORIES.items():
            lines = [f"**{name}**"]
            for usage, desc in entries:
                lines.append(f"`{prefix}{usage}` — {desc}")
            children.append(v2.separator(spacing=1))
            children.append(v2.text("\n".join(lines)))

        children.append(v2.separator(spacing=2))
        children.append(v2.text("*chrm on top.*"))
        return [v2.container(*children, accent_color=ACCENT)]

    def build_url(self, prefix: str) -> str:
        return v2.share_url(self.build_components(prefix))

    def build_plain(self, prefix: str) -> str:
        out = [f"**{self.bot.user.name} — selfbot commands**", f"*prefix: `{prefix}`*", ""]
        for name, entries in CATEGORIES.items():
            out.append(f"**{name}**")
            out.extend(f"`{prefix}{usage}`" for usage, _ in entries)
            out.append("")
        out.append("*chrm on top.*")
        return "\n".join(out)

    @commands.command(name="help")
    async def help_command(self, ctx, arg: str = None):
        """components v2 help menu via a masked share link. `.help text` for plain text."""
        prefix = self._prefix(ctx)
        arg = (arg or "").lower()

        if arg in ("text", "plain", "list"):
            return await ctx.send(self.build_plain(prefix))

        url = self.build_url(prefix)

        if arg in ("url", "raw", "link"):
            # <> stops Discord from turning the long URL into a preview card.
            return await ctx.send(f"<{url}>")

        # Masked link: zero-width text, so only the unfurled component card shows.
        await ctx.send(f"[{MASK}]({url})")


async def setup(bot):
    await bot.add_cog(Help(bot))
