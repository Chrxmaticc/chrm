"""Information: anything that fetches information about someone else.

Sub-cogs (``extended/``):

    info     ``.userinfo`` / ``.serverinfo`` / ``.avatar`` / ``.banner``
    roblox   ``.rblxuser`` / ``.rblxavatar`` / ``.rblxheadshot`` / ``.rblxgroups``
    ai       ``.ai`` chat
    lyrics   ``.lyrics`` / ``.stoplyrics`` synced lyrics
    lastfm   ``.lastfm`` libre.fm now playing and top artists

Read-only outward calls (Discord, Roblox, the lyrics and AI endpoints); nothing
here writes to the dashboard except the lyrics task handle.
"""
from discord.ext import commands

from plugins.information.extended.ai import AIMixin
from plugins.information.extended.info import InfoMixin
from plugins.information.extended.lastfm import LastFMMixin
from plugins.information.extended.lyrics import LyricsMixin
from plugins.information.extended.roblox import RobloxMixin

#: sent with every Roblox request; their endpoints reject the default user agent
ROBLOX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json",
}


class Information(InfoMixin, RobloxMixin, AIMixin, LyricsMixin, LastFMMixin, commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.headers = dict(ROBLOX_HEADERS)
        # lyrics
        self.lyric_task = None


async def setup(bot):
    await bot.add_cog(Information(bot))
