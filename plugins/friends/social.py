"""Removal and moderation half of the friends cog.

Everything that takes something away or silences it: ``unfriend``,
``massunfriend``, ``unblock``, ``ignore``/``unignore``, ``mute``/``unmute`` and the
``relationshipnotifier`` toggle with the listeners behind it.

Kept as a mixin so the cog in ``plugin.py`` can stay about adding friends and
looking at them, while all of this shares the one state dict and the one place
that posts a notification. ``plugins/utility`` splits its cog the same way.
"""
from __future__ import annotations

import asyncio

import discord
from discord.ext import commands

from core import api
from plugins.friends import actions

#: pause between mass-unfriend calls so Discord does not rate-limit the account
BULK_DELAY = 0.4


class SocialMixin:
    """Commands that remove, block, ignore or mute; plus the notifier."""

    # ------------------------------------------------------------ remove
    @commands.command(name="unfriend")
    async def unfriend_command(self, ctx, *, target: str = ""):
        """remove a friend"""
        if not target and not (getattr(ctx.message, "mentions", None) or []):
            return await ctx.warn("usage: `.unfriend @user`")
        try:
            user = await actions.resolve(self.bot, ctx, target)
            if user is None:
                return await ctx.warn("give me a mention or a user id.")
            await actions.unfriend(self.bot, user.id)
            return await ctx.approve(f"unfriended **{actions.user_name(user)}**.")
        except discord.HTTPException as exc:
            return await actions.fail(ctx, exc)

    @commands.command(name="unblock")
    async def unblock_command(self, ctx, *, target: str = ""):
        """unblock a user"""
        if not target and not (getattr(ctx.message, "mentions", None) or []):
            return await ctx.warn("usage: `.unblock @user`")
        try:
            user = await actions.resolve(self.bot, ctx, target)
            if user is None:
                return await ctx.warn("give me a mention or a user id.")
            await actions.unblock(self.bot, user.id)
            return await ctx.approve(f"unblocked **{actions.user_name(user)}**.")
        except discord.HTTPException as exc:
            return await actions.fail(ctx, exc)

    @commands.command(name="massunfriend")
    async def massunfriend_command(self, ctx, confirm: str = ""):
        """unfriend everyone — needs `confirm`"""
        try:
            rows = await actions.relationships(self.bot)
        except discord.HTTPException as exc:
            return await actions.fail(ctx, exc)

        friends = [row for row in rows if row.get("type") == actions.FRIEND]
        if not friends:
            return await ctx.approve("no friends to remove.")

        if (confirm or "").strip().lower() not in ("confirm", "yes", "y"):
            return await ctx.warn(
                f"that would unfriend **{len(friends)}** people: {actions.listing(friends)}\n"
                f"run `.massunfriend confirm` if you mean it."
            )

        removed = failed = 0
        for row in friends:
            try:
                await actions.drop(self.bot, int(row["id"]))
                removed += 1
            except discord.HTTPException as exc:
                failed += 1
                print(f"[friends] could not unfriend {row.get('id')}: {exc}")
            except (KeyError, TypeError, ValueError) as exc:
                failed += 1
                print(f"[friends] bad relationship row {row!r}: {exc}")
            await asyncio.sleep(BULK_DELAY)

        summary = f"unfriended **{removed}**"
        if failed:
            summary += f" · **{failed}** failed (rate limit or already gone)"
        await ctx.approve(summary)

    # ------------------------------------------------------------ ignore
    @commands.command(name="ignore")
    async def ignore_command(self, ctx, *, target: str = ""):
        """ignore a user without blocking them"""
        if not target and not (getattr(ctx.message, "mentions", None) or []):
            return await ctx.warn("usage: `.ignore @user`")
        try:
            user = await actions.resolve(self.bot, ctx, target)
            if user is None:
                return await ctx.warn("give me a mention or a user id.")
            await actions.ignore(self.bot, user.id, True)
            return await ctx.approve(
                f"ignoring **{actions.user_name(user)}** — their messages are hidden, they are not told."
            )
        except discord.HTTPException as exc:
            return await actions.fail(ctx, exc)

    @commands.command(name="unignore")
    async def unignore_command(self, ctx, *, target: str = ""):
        """stop ignoring a user"""
        if not target and not (getattr(ctx.message, "mentions", None) or []):
            return await ctx.warn("usage: `.unignore @user`")
        try:
            user = await actions.resolve(self.bot, ctx, target)
            if user is None:
                return await ctx.warn("give me a mention or a user id.")
            await actions.ignore(self.bot, user.id, False)
            return await ctx.approve(f"no longer ignoring **{actions.user_name(user)}**.")
        except discord.HTTPException as exc:
            return await actions.fail(ctx, exc)

    # ------------------------------------------------------------ mute
    async def _mute_target(self, ctx, target: str):
        """``(channel id, label)`` for the DM to mute, or ``(None, reason)``."""
        if target or (getattr(ctx.message, "mentions", None) or []):
            user = await actions.resolve(self.bot, ctx, target)
            if user is None:
                return None, "mention the user whose DMs you want muted."
            return await actions.dm_channel_id(self.bot, user), actions.user_name(user)

        if getattr(ctx, "guild", None) is None:
            return int(ctx.channel.id), "this DM"

        return None, "usage: `.mute @user` — or run it inside the DM itself."

    @commands.command(name="mute")
    async def mute_command(self, ctx, *, target: str = ""):
        """mute a user's DMs"""
        try:
            channel_id, label = await self._mute_target(ctx, target)
            if channel_id is None:
                return await ctx.warn(label)
            await actions.set_muted(self.bot, channel_id, True)
            return await ctx.approve(f"muted **{label}** — no more pings from that DM.")
        except discord.HTTPException as exc:
            return await actions.fail(ctx, exc)

    @commands.command(name="unmute")
    async def unmute_command(self, ctx, *, target: str = ""):
        """unmute a user's DMs"""
        try:
            channel_id, label = await self._mute_target(ctx, target)
            if channel_id is None:
                return await ctx.warn(label)
            await actions.set_muted(self.bot, channel_id, False)
            return await ctx.approve(f"unmuted **{label}**.")
        except discord.HTTPException as exc:
            return await actions.fail(ctx, exc)

    # ------------------------------------------------------------ notifier
    @commands.command(
        name="relationshipnotifier", aliases=["friendnotify", "relnotifier"]
    )
    async def relationshipnotifier_command(self, ctx, state: str = ""):
        """toggle friend and server join notifications"""
        value = (state or "").strip().lower()
        if value in ("", "status"):
            where = self.state.get("channel")
            current = "on" if self.state.get("notify") and where else "off"
            place = f" in <#{where}>" if where and self.state.get("notify") else ""
            return await ctx.approve(f"relationship notifications are **{current}**{place}.")
        if value not in ("on", "off", "true", "false", "yes", "no"):
            return await ctx.warn("usage: `.relationshipnotifier on|off`")

        self.state["notify"] = value in ("on", "true", "yes")
        if self.state["notify"]:
            self.state["channel"] = int(ctx.channel.id)
        await api.save_feature(self.bot, "friends", self.state, tag="FRIENDS")
        if self.state["notify"]:
            return await ctx.approve(
                f"i will post friend requests, unfriends and server joins here (<#{ctx.channel.id}>)."
            )
        return await ctx.approve("relationship notifications off.")

    async def _notify(self, text: str) -> None:
        """Post one line, if the notifier is on and its channel still resolves."""
        if not self.state.get("notify"):
            return
        channel_id = self.state.get("channel")
        if not channel_id:
            return
        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except discord.HTTPException as exc:
                print(f"[friends] notifier channel {channel_id} is gone: {exc}")
                return
        try:
            await channel.send(text)
        except discord.HTTPException as exc:
            print(f"[friends] could not notify: {exc}")

    @commands.Cog.listener()
    async def on_relationship_add(self, relationship):
        kind = getattr(getattr(relationship, "type", None), "name", "")
        who = actions.user_name(getattr(relationship, "user", relationship))
        if kind == "incoming_request":
            return await self._notify(f"📨 **{who}** sent you a friend request.")
        if kind == "friend":
            return await self._notify(f"✅ you are now friends with **{who}**.")
        if kind == "blocked":
            return await self._notify(f"🚫 you blocked **{who}**.")
        return await self._notify(f"➕ **{who}** ({kind or 'relationship'}).")

    @commands.Cog.listener()
    async def on_relationship_remove(self, relationship):
        kind = getattr(getattr(relationship, "type", None), "name", "")
        who = actions.user_name(getattr(relationship, "user", relationship))
        await self._notify(f"➖ relationship removed: **{who}** (was {kind or 'unknown'}).")

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        members = getattr(guild, "member_count", None)
        count = f" · **{members:,}** members" if members else ""
        await self._notify(f"📥 joined **{getattr(guild, 'name', 'a server')}**{count}.")
