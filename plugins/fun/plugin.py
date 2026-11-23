"""Fun: everything that lies about what this account is doing or using.

Sub-cogs (``extended/``):

    rpc          ``.rpc`` / ``.stream`` / ``.customstatus`` / status rotator
    spotify      ``.spotify`` fake "listening to" with real album art + seek bar
    badges       ``.autobadges`` game rotation, ``.testrpc`` diagnostic
    fakeplay     ``.fakeplay`` a game with its official icon, flags and progress
    fakechat     ``.fakechat`` rendered fake message image
    device       client icon (desktop / phone / console / VR) via IDENTIFY

All of them end up calling ``change_presence`` on the same account, and before the
merge each one decided on its own whether it was allowed to. They now share one
cog, which is the natural place to arbitrate that: ``spotify`` holds a
``_track``, ``fakeplay``/``badges`` hold rotation tasks, ``rpc`` holds
``custom_rotator_task``. Nothing about the arbitration rules changed in this
merge -- the guards that existed (``fakeplay.stopfakeplay`` unlocking the
rotator, ``spotify._owns_presence``) are still the ones in force.
"""
from api_base import BASE_API
from discord.ext import commands

from plugins.fun.extended import gamecatalog

from plugins.fun.extended.badges import AutoBadgesMixin
from plugins.fun.extended.device import DeviceMixin
from plugins.fun.extended.fakechat import FakeChatMixin
from plugins.fun.extended.fakeplay import FakePlayMixin
from plugins.fun.extended.rpc import RPCMixin
from plugins.fun.extended.spotify import SpotifySpoofMixin

#: Discord's own "detectable games" catalogue, shared by fakeplay/badges lookups
GAME_CACHE_URL = gamecatalog.SOURCE


class Fun(
    RPCMixin,
    SpotifySpoofMixin,
    AutoBadgesMixin,
    FakePlayMixin,
    FakeChatMixin,
    DeviceMixin,
    commands.Cog,
):
    def __init__(self, bot):
        self.bot = bot
        # rpc
        self.custom_rotator_task = None
        # spotify
        self._task = None
        self._track = None
        # badges
        self.badge_task = None
        self.is_running = False
        self._analytics = {}
        self._hb_session = None
        self._launch_sig = None
        # fakeplay
        self.games_cache = None
        self.cache_url = GAME_CACHE_URL
        self.icon_cache = {}
        # device
        self.base_api = BASE_API

    def cog_unload(self):
        self.cog_unload_rpc()
        self.cog_unload_spotify()


async def setup(bot):
    await bot.add_cog(Fun(bot))
