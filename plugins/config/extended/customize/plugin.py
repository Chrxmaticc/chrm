"""Make the account look however you want: profile fields, presence and the cards.

The profile half talks to ``ClientUser.edit``. Avatar, banner, global name, bio
and accent colour are all settable without a password -- exactly the subset a
self-bot should touch. ``username`` is deliberately not exposed: Discord wants
the account password for it, and no command here should ever ask for that.

The card half writes ``settings.brand`` / ``settings.tagline`` / ``settings.card_color``,
which ``core/context.py`` reads when it builds ``.help``, so the menu stops saying
"chrm" the moment you rename it. Feedback emoji already live in ``settings.emojis``
(``.setemoji``), and prefixes in ``settings.prefixes``.
"""
from __future__ import annotations

import re

import discord
from discord.ext import commands

from core import api

#: Discord's own limit for "about me"
MAX_BIO = 190
#: status words -> discord.Status
STATUSES = {
    "online": discord.Status.online,
    "idle": discord.Status.idle,
    "dnd": discord.Status.dnd,
    "busy": discord.Status.dnd,
    "invisible": discord.Status.invisible,
    "offline": discord.Status.invisible,
}
#: activity words -> discord.ActivityType
ACTIVITIES = {
    "playing": discord.ActivityType.playing,
    "watching": discord.ActivityType.watching,
    "listening": discord.ActivityType.listening,
    "competing": discord.ActivityType.competing,
}


def colour(token: str):
    """``#1f1f23`` / ``1f1f23`` / ``0x1f1f23`` -> int, or ``None``."""
    value = (token or "").strip().lower().rstrip(">").lstrip("<#")
    if value.startswith("0x"):
        value = value[2:]
    if not re.fullmatch(r"[0-9a-f]{6}", value):
        return None
    return int(value, 16)


class CustomizeMixin:
    """Commands for this sub-cog; assembled into the package cog."""

    # ------------------------------------------------------------ helpers
    def _settings(self) -> dict:
        return self.bot.config.data.setdefault("settings", {})

    async def _save_settings(self, **values):
        self._settings().update(values)
        return await api.save_settings(self.bot, **values)

    def _presence(self):
        """``(status, activity)`` as the library currently has them."""
        activity = getattr(self.bot, "activity", None)
        status = getattr(self.bot, "status", discord.Status.online)
        return status, activity

    async def _apply_presence(self, *, status=None, activity=discord.utils.MISSING):
        current_status, current_activity = self._presence()
        kwargs = {"status": status if status is not None else current_status}
        if activity is not discord.utils.MISSING:
            kwargs["activity"] = activity
        elif current_activity is not None:
            kwargs["activity"] = current_activity
        await self.bot.change_presence(**kwargs)

    def _nick_targets(self, ctx, args: str = ""):
        """``(user, nickname)`` — mentions first, then the raw argument text."""
        mentions = list(getattr(getattr(ctx, "message", None), "mentions", None) or [])
        nick = " ".join(
            token for token in (args or "").split() if not token.startswith("<@")
        ).strip()
        if not nick:
            # fall back to the raw message minus the invocation and the mentions
            content = getattr(getattr(ctx, "message", None), "content", "") or ""
            words = content.split()[1:]
            nick = " ".join(word for word in words if not word.startswith("<@")).strip()
        target = mentions[0] if mentions else getattr(ctx, "author", None)
        return target, nick

    # ------------------------------------------------------------ profile
    @commands.command(name="setbio", aliases=["setabout"])
    async def setbio(self, ctx, *, text: str = ""):
        """set your about-me. usage: .setbio building things"""
        value = (text or "").strip()
        if not value:
            return await ctx.warn("usage: `.setbio <text>` — `.clearbio` removes it")
        if len(value) > MAX_BIO:
            return await ctx.warn(f"bios cap at {MAX_BIO} characters ({len(value)} given).")
        try:
            await self.bot.user.edit(bio=value)
        except Exception as exc:  # noqa: BLE001 - report, never traceback
            return await ctx.deny(f"discord refused the bio: {exc}")
        await ctx.approve("bio updated.")

    @commands.command(name="clearbio")
    async def clearbio(self, ctx):
        """wipe your about-me. usage: .clearbio"""
        try:
            await self.bot.user.edit(bio=None)
        except Exception as exc:  # noqa: BLE001
            return await ctx.deny(f"discord refused it: {exc}")
        await ctx.approve("bio cleared.")

    @commands.command(name="setaccent", aliases=["setcolour", "setcolor"])
    async def setaccent(self, ctx, token: str = ""):
        """set your profile accent colour. usage: .setaccent #1f1f23"""
        value = colour(token)
        if value is None:
            return await ctx.warn("usage: `.setaccent #1f1f23` (six hex digits)")
        try:
            await self.bot.user.edit(accent_color=discord.Colour(value))
        except Exception as exc:  # noqa: BLE001
            return await ctx.deny(f"discord refused that colour: {exc}")
        await ctx.approve(f"profile accent is now **#{value:06x}**.")

    @commands.command(name="clearaccent")
    async def clearaccent(self, ctx):
        """drop the profile accent colour. usage: .clearaccent"""
        try:
            await self.bot.user.edit(accent_color=None)
        except Exception as exc:  # noqa: BLE001
            return await ctx.deny(f"discord refused it: {exc}")
        await ctx.approve("profile accent cleared.")

    # ------------------------------------------------------------ presence
    @commands.command(name="setstatus", aliases=["status"])
    async def setstatus(self, ctx, state: str = ""):
        """online, idle, dnd or invisible. usage: .setstatus idle"""
        word = (state or "").strip().lower()
        if not word:
            current = getattr(self.bot, "status", discord.Status.online)
            return await ctx.warn(f"status is **{current}** — `.setstatus online|idle|dnd|invisible`")
        status = STATUSES.get(word)
        if status is None:
            return await ctx.warn("pick `online`, `idle`, `dnd` or `invisible`.")
        try:
            await self._apply_presence(status=status)
        except Exception as exc:  # noqa: BLE001
            return await ctx.deny(f"discord refused the presence change: {exc}")
        await ctx.approve(f"status is now **{word}**.")

    @commands.command(name="setactivity", aliases=["setpresence"])
    async def setactivity(self, ctx, kind: str = "", *, text: str = ""):
        """playing / watching / listening / competing. usage: .setactivity playing minecraft"""
        word = (kind or "").strip().lower()
        if word not in ACTIVITIES:
            return await ctx.warn(
                "usage: `.setactivity playing minecraft` — types: "
                + ", ".join(f"`{name}`" for name in ACTIVITIES)
            )
        value = (text or "").strip()
        if not value:
            return await ctx.warn("what should it say? `.setactivity playing minecraft`")
        if len(value) > 128:
            return await ctx.warn("that is too long for an activity (128 max).")
        activity = discord.Activity(type=ACTIVITIES[word], name=value)
        try:
            await self._apply_presence(activity=activity)
        except Exception as exc:  # noqa: BLE001
            return await ctx.deny(f"discord refused the activity: {exc}")
        await ctx.approve(f"now **{word}** {value}.")

    @commands.command(name="clearactivity", aliases=["stopactivity"])
    async def clearactivity(self, ctx):
        """remove the current activity. usage: .clearactivity"""
        try:
            await self._apply_presence(activity=None)
        except Exception as exc:  # noqa: BLE001
            return await ctx.deny(f"discord refused it: {exc}")
        await ctx.approve("activity cleared.")

    @commands.command(name="setnick", aliases=["nick"])
    async def setnick(self, ctx, *, args: str = ""):
        """change a nickname in this server. usage: .setnick chrxm | .setnick @user chrxm"""
        if ctx.guild is None:
            return await ctx.deny("nicknames only exist inside a server.")
        user, nick = self._nick_targets(ctx, args)
        value = nick or (args or "").strip()
        if not user:
            user = getattr(ctx, "author", None)
        if not value:
            return await ctx.warn("usage: `.setnick <name>` or `.setnick @user <name>`")
        if len(value) > 32:
            return await ctx.warn("nicknames cap at 32 characters.")
        try:
            member = ctx.guild.get_member(user.id) if hasattr(ctx.guild, "get_member") else None
            if member is None:
                return await ctx.deny("that user is not in this server.")
            await member.edit(nick=value)
        except Exception as exc:  # noqa: BLE001
            return await ctx.deny(f"could not rename: {exc}")
        await ctx.approve(f"**{getattr(user, 'display_name', 'they')}** is now **{value}** here.")

    @commands.command(name="clearnick", aliases=["resetnick"])
    async def clearnick(self, ctx, user: discord.User = None):
        """put a nickname back to the default. usage: .clearnick [@user]"""
        if ctx.guild is None:
            return await ctx.deny("nicknames only exist inside a server.")
        target = user or ctx.author
        try:
            member = ctx.guild.get_member(target.id) if hasattr(ctx.guild, "get_member") else None
            if member is None:
                return await ctx.deny("that user is not in this server.")
            await member.edit(nick=None)
        except Exception as exc:  # noqa: BLE001
            return await ctx.deny(f"could not reset it: {exc}")
        await ctx.approve("nickname reset.")

    # ------------------------------------------------------------ help cards
    @commands.command(name="setbrand", aliases=["brand"])
    async def setbrand(self, ctx, *, name: str = ""):
        """the name on the .help cards. usage: .setbrand chroma"""
        value = (name or "").strip()
        if not value:
            return await ctx.warn("usage: `.setbrand <name>` — `.setbrand reset` clears it")
        if value.lower() == "reset":
            await self._save_settings(brand="")
            return await ctx.approve("card brand reset to your discord name.")
        await self._save_settings(brand=value[:40])
        await ctx.approve(f"cards now say **{value[:40]}**.")

    @commands.command(name="settagline", aliases=["tagline"])
    async def settagline(self, ctx, *, text: str = ""):
        """the line at the bottom of the cards. usage: .settagline built different"""
        value = (text or "").strip()
        if not value:
            return await ctx.warn("usage: `.settagline <text>` — `.settagline reset` clears it")
        if value.lower() == "reset":
            await self._save_settings(tagline="")
            return await ctx.approve("tagline reset.")
        await self._save_settings(tagline=value[:80])
        await ctx.approve(f"tagline set to *{value[:80]}*.")

    @commands.command(name="cardcolor", aliases=["setcard"])
    async def cardcolor(self, ctx, token: str = ""):
        """accent colour of the .help cards. usage: .cardcolor #5865f2"""
        value = colour(token)
        if value is None:
            return await ctx.warn("usage: `.cardcolor #5865f2` (six hex digits)")
        await self._save_settings(card_color=value)
        await ctx.approve(f"cards are now accented **#{value:06x}**.")

    @commands.command(name="customize", aliases=["look", "profilecard"])
    async def customize(self, ctx):
        """everything you can change about the look. usage: .customize"""
        settings = self._settings()
        user = getattr(self.bot, "user", None)
        brand = settings.get("brand") or getattr(user, "name", "chrm")
        tagline = settings.get("tagline") or "chrm on top."
        accent = settings.get("card_color")
        accent_text = f"#{int(accent):06x}" if isinstance(accent, int) else "default"
        status = getattr(self.bot, "status", "online")
        activity = getattr(self.bot, "activity", None)
        activity_text = (
            f"{activity.type.name.lower()} {activity.name}" if activity is not None else "none"
        )
        lines = [
            "### customize",
            f"name **{getattr(user, 'name', '?')}** · display **{getattr(user, 'global_name', None) or '—'}**",
            f"cards say **{brand}** · accent **{accent_text}** · tagline *{tagline}*",
            f"status **{status}** · activity **{activity_text}**",
            "**profile** `.setname` `.setavatar` `.setbanner` `.setbio` `.setaccent`",
            "**presence** `.setstatus` `.setactivity` `.clearactivity` `.ghost`",
            "**server** `.setnick` `.clearnick` `.namerotator`",
            "**cards** `.setbrand` `.settagline` `.cardcolor`",
            "**engine** `.setemoji` `.addprefix` `.customstatus` `.rpc` `.autodelete`",
        ]
        await ctx.send("\n".join(lines))
