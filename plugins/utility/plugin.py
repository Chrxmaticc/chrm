"""Utility: group chats, cleanup, deleted-message sniping, transcripts.

Sub-cogs (``extended/``):

    groups      ``.gc*`` group-chat management, auto-add / auto-leave
    utility     ``.purge``, ``.blacktea``
    native      discord-native lookups: ``.joined``, ``.roles``, ``.perms``, ``.pins``,
                ``.audit``, ``.boosters``, ``.emojis``, ``.channels``, ``.invites``,
                ``.serverbanner`` and the filtered ``.clean``
    clone       ``.clone`` rebuilds a server's roles and channels into a new one
    sniper      ``.snipe`` / ``.editsnipe`` / ``.reactionsnipe`` + the caches behind them
    transcript  ``.transcript`` HTML export
    typing      ``.type`` hold the typing indicator without sending anything
    reminders   ``.remind`` / ``.reminders`` / ``.unremind`` / ``.todo`` -- persisted

Endpoints on the framework side are unchanged; the sniper keeps a bounded deque
per channel for deletes, edits and removed reactions, so the caches live here
rather than in the sub-cog: every listener that fills them belongs to this one cog.
"""
from collections import deque

from discord.ext import commands

from plugins.utility.extended.cleanup import CleanupMixin
from plugins.utility.extended.clone import CloneMixin
from plugins.utility.extended.groups import GroupChatMixin
from plugins.utility.extended.native import NativeMixin
from plugins.utility.extended.reminders import RemindersMixin
from plugins.utility.extended.sniper import SniperMixin
from plugins.utility.extended.transcript import TranscriptMixin
from plugins.utility.extended.typing import TypingMixin

#: how many messages per channel each snipe cache keeps
CACHE_SIZE = 50


class Utility(
    NativeMixin,
    CloneMixin,
    GroupChatMixin,
    RemindersMixin,
    CleanupMixin,
    SniperMixin,
    TranscriptMixin,
    TypingMixin,
    commands.Cog,
):
    def __init__(self, bot):
        self.bot = bot
        self.deleted_cache = {}
        self.edited_cache = {}
        self.reaction_cache = {}
        self.check_due.start()

    def cog_unload(self):
        self.check_due.cancel()

    def _cache(self, channel_id) -> deque:
        """Bounded per-channel cache for one of the snipe listeners."""
        return self.deleted_cache.setdefault(channel_id, deque(maxlen=CACHE_SIZE))


async def setup(bot):
    await bot.add_cog(Utility(bot))
