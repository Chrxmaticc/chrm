"""Config: every command whose job is to change how the account or the bot behaves.

Sub-cogs (``extended/``):

    prefixes      ``.prefixes`` / ``.addprefix`` / ``.removeprefix`` / ``.resetprefix``
    delay         ``.toggledelay`` -- the ``human_delay`` range ``main.py`` applies
    owner         ``.restart`` / ``.reload`` / ``.sysinfo`` (hardcoded ``OWNER_ID``)
    profile       ``.setavatar`` / ``.setbanner`` / ``.setname`` + rotation loop
    nickname      ``.namerotator`` rotation loop
    responders    auto-replies, auto-reactions, ``.afk``
    aliases       rewrite ``.s`` into ``.snipe`` before dispatch
    custom_cmds   user-defined ``.addcmd`` triggers
    scheduler     delayed / repeating sends, incl. ``.alibi``
    prefs         ``.settings`` / ``.prefs`` / wordle toggles / ``.disable`` / ``.cooldown``
    toolkit       ``.backup`` / ``.restore`` / ``.ghost`` / ``.autoread`` /
                  ``.autodelete`` / ``.ignorechannel``

Grouping rule: if a command exists to be *configured* -- a prefix, a delay, a
rotation list, an auto-reply, an alias, a scheduled message -- it belongs here.
That is why the old ``automation`` cogs sit next to ``.addprefix``: they are all
writes into the same per-user settings blob, and they all need the same
``features`` / ``settings`` plumbing on load.

Three of the sub-cogs used to be separate Cogs, so three ``on_message``
listeners ran on every message of every bot instance -- on a box that hosts one
instance per dashboard user, that was three config lookups per message per user.
They are now dispatched from the single listener below, in the order the old
alphabetical load order produced (aliases, responders, custom_cmds).
"""
from discord.ext import commands

from plugins.config.extended.aliases import AliasesMixin
from plugins.config.extended.custom_cmds import CustomCommandsMixin
from plugins.config.extended.delay import DelayMixin
from plugins.config.extended.nickname import NicknameMixin
from plugins.config.extended.owner import OwnerMixin
from plugins.config.extended.prefs import PrefsMixin
from plugins.config.extended.prefixes import PrefixMixin
from plugins.config.extended.profile import ProfileMixin
from plugins.config.extended.responders import RespondersMixin
from plugins.config.extended.scheduler import SchedulerMixin
from plugins.config.extended.toolkit import ToolkitMixin


class Config(
    PrefixMixin,
    DelayMixin,
    OwnerMixin,
    ProfileMixin,
    NicknameMixin,
    RespondersMixin,
    AliasesMixin,
    CustomCommandsMixin,
    SchedulerMixin,
    PrefsMixin,
    ToolkitMixin,
    commands.Cog,
):
    def __init__(self, bot):
        self.bot = bot
        # nickname
        self.nick_task = None
        # aliases
        self.processed_messages = set()
        # custom_cmds
        if "features" not in self.bot.config.data:
            self.bot.config.data["features"] = {}
        if "custom_commands" not in self.bot.config.data["features"]:
            self.bot.config.data["features"]["custom_commands"] = {}
        # profile
        self.rotate_profile.start()
        # scheduler
        self.check_schedules.start()

    async def on_message(self, message):
        await self.on_message_aliases(message)
        await self.on_message_responders(message)
        await self.on_message_customs(message)
        await self.on_message_toolkit(message)

    def cog_unload(self):
        self.cog_unload_profile()
        self.cog_unload_scheduler()


async def setup(bot):
    await bot.add_cog(Config(bot))
