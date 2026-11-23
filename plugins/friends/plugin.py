"""Friends: your Discord relationships, from chat.

``friendadd`` and ``request`` drive friend requests, ``pending`` lists them,
``friendrename`` / ``resetname`` set the private nickname only you see, and
``friendcount`` is the overview. Removal, ignores, DM mutes and the notifier live
in :mod:`plugins.friends.social`; every route they use is in
:mod:`plugins.friends.actions`.

Why it is split three ways: the HTTP layer is worth reading on its own (a DM mute
is a private-channel *override*, not a channel edit, and ignores are user-account
only endpoints the bot API never exposes), and both halves of the command surface
share that layer without importing each other.
"""
from __future__ import annotations

import discord
from discord.ext import commands

from plugins.friends import actions
from plugins.friends.actions import BLOCKED, FRIEND, INCOMING, LIST_LIMIT, OUTGOING
from plugins.friends.social import SocialMixin

#: longest friend nickname Discord accepts
NICK_LIMIT = 32


class Friends(SocialMixin, commands.Cog):
    """Friend requests, friend lists, nicknames, ignores, mutes and notifications."""

    def __init__(self, bot):
        self.bot = bot

        features = bot.config.data.setdefault("features", {})
        stored = features.get("friends")
        stored = stored if isinstance(stored, dict) else {}
        #: what ``.relationshipnotifier`` persists
        self.state = {
            "notify": bool(stored.get("notify", False)),
            "channel": stored.get("channel"),
        }
        features["friends"] = self.state

    # ------------------------------------------------------------ add
    @commands.command(name="friendadd", aliases=["addfriend"])
    async def friendadd_command(self, ctx, *, target: str = ""):
        """send someone a friend request"""
        raw = (target or "").strip()
        if not raw and not (getattr(ctx.message, "mentions", None) or []):
            return await ctx.warn(
                "usage: `.friendadd @user`, `.friendadd 123456789` or `.friendadd name`"
            )

        try:
            user = await actions.resolve(self.bot, ctx, raw)
            if user is not None:
                await actions.send_request(self.bot, user.id)
                return await ctx.approve(
                    f"friend request sent to **{actions.user_name(user)}**."
                )

            token = raw.lstrip("@").strip()
            username, _, discriminator = token.partition("#")
            username = username.strip()
            if not username or " " in username:
                return await ctx.warn(
                    "that is not a mention, an id or a username — try `.friendadd @user`."
                )
            await actions.send_request_by_name(self.bot, username, discriminator.strip())
            return await ctx.approve(f"friend request sent to **{username}**.")
        except discord.HTTPException as exc:
            return await actions.fail(ctx, exc)

    # ------------------------------------------------------------ list
    @commands.command(name="friendcount", aliases=["friends", "friendlist"])
    async def friendcount_command(self, ctx):
        """count your friends, blocked and ignored accounts"""
        try:
            rows = await actions.relationships(self.bot)
        except discord.HTTPException as exc:
            return await actions.fail(ctx, exc)

        friends = [row for row in rows if row.get("type") == FRIEND]
        blocked = [row for row in rows if row.get("type") == BLOCKED]
        ignored = [row for row in rows if row.get("user_ignored")]
        incoming = [row for row in rows if row.get("type") == INCOMING]
        outgoing = [row for row in rows if row.get("type") == OUTGOING]

        lines = [
            f"### friends · {len(friends)}",
            f"**{len(blocked)}** blocked · **{len(ignored)}** ignored · "
            f"**{len(incoming)}** pending in · **{len(outgoing)}** pending out",
        ]
        if friends:
            lines.append(actions.listing(friends))
        if ignored:
            lines.append(f"ignored: {actions.listing(ignored)}")
        if incoming:
            lines.append("`.pending` to see requests · `.request accept @user` to answer")
        await ctx.send("\n".join(lines))

    @commands.command(name="pending")
    async def pending_command(self, ctx):
        """list friend requests going in and out"""
        try:
            rows = await actions.relationships(self.bot)
        except discord.HTTPException as exc:
            return await actions.fail(ctx, exc)

        incoming = [row for row in rows if row.get("type") == INCOMING]
        outgoing = [row for row in rows if row.get("type") == OUTGOING]
        if not incoming and not outgoing:
            return await ctx.approve("no pending friend requests.")

        lines = [f"### pending · {len(incoming)} in · {len(outgoing)} out"]
        if incoming:
            lines.append("**incoming**")
            lines.extend(
                f"`{actions.name(row)}` · `{row.get('id')}`" for row in incoming[:LIST_LIMIT]
            )
        if outgoing:
            lines.append("**outgoing**")
            lines.extend(
                f"`{actions.name(row)}` · `{row.get('id')}`" for row in outgoing[:LIST_LIMIT]
            )
        lines.append("`.request accept @user` or `.request deny @user`")
        await ctx.send("\n".join(lines))

    @commands.command(name="request")
    async def request_command(self, ctx, action: str = "", *, target: str = ""):
        """accept or deny a friend request"""
        verb = (action or "").strip().lower()
        if verb not in ("accept", "deny"):
            return await ctx.warn(
                "usage: `.request accept @user` or `.request deny @user` — `.pending` lists them"
            )

        try:
            user = await actions.resolve(self.bot, ctx, target)
            if user is None:
                return await ctx.warn("give me a mention or a user id.")
            if verb == "accept":
                await actions.accept_request(self.bot, user.id)
                return await ctx.approve(
                    f"you are now friends with **{actions.user_name(user)}**."
                )
            await actions.deny_request(self.bot, user.id)
            return await ctx.approve(f"denied the request from **{actions.user_name(user)}**.")
        except discord.HTTPException as exc:
            return await actions.fail(ctx, exc)

    # ------------------------------------------------------------ nicknames
    @commands.command(name="friendrename", aliases=["friendnick"])
    async def friendrename_command(self, ctx, *, arg: str = ""):
        """set the private nickname you see for a friend"""
        parts = (arg or "").split(maxsplit=1)
        target = parts[0] if parts else ""
        nickname = parts[1].strip() if len(parts) > 1 else ""
        if not target or not nickname:
            return await ctx.warn("usage: `.friendrename @user <nickname>`")

        try:
            user = await actions.resolve(self.bot, ctx, target)
            if user is None:
                return await ctx.warn("mention the friend you want to rename.")
            if not 1 <= len(nickname) <= NICK_LIMIT:
                return await ctx.warn(f"a nickname is 1–{NICK_LIMIT} characters.")
            await actions.set_nickname(self.bot, user.id, nickname)
            return await ctx.approve(
                f"**{actions.user_name(user)}** is now `{nickname}` to you."
            )
        except discord.HTTPException as exc:
            return await actions.fail(ctx, exc)

    @commands.command(name="resetname")
    async def resetname_command(self, ctx, *, target: str = ""):
        """clear a friend nickname"""
        if not target and not (getattr(ctx.message, "mentions", None) or []):
            return await ctx.warn("usage: `.resetname @user`")
        try:
            user = await actions.resolve(self.bot, ctx, target)
            if user is None:
                return await ctx.warn("mention the friend whose nickname you want gone.")
            await actions.set_nickname(self.bot, user.id, None)
            return await ctx.approve(f"cleared the nickname for **{actions.user_name(user)}**.")
        except discord.HTTPException as exc:
            return await actions.fail(ctx, exc)


async def setup(bot):
    await bot.add_cog(Friends(bot))
