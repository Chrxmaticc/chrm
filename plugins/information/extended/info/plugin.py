"""Lookups: who someone is, where you are, and the art on a profile.

Everything here is read-only, so nothing touches the dashboard. Each command
accepts a mention, a raw id, or nothing at all (meaning you), which keeps them
usable in DMs where there is no member list to pick from.
"""
import discord
from discord.ext import commands

class InfoMixin:
    """Commands for this sub-cog; assembled into the package cog."""
    async def _resolve(self, ctx, query):
        """Mention / id / 'me' -> User or Member. None when nothing matches."""
        if not query or query.lower() in ("me", "self"):
            return ctx.author
        try:
            return await commands.UserConverter().convert(ctx, query)
        except (commands.BadArgument, commands.UserNotFound):
            return None

    @staticmethod
    def _when(dt) -> str:
        """Discord timestamp markup, or a plain fallback for naive datetimes."""
        try:
            return f"<t:{int(dt.timestamp())}:R>"
        except Exception:
            return "unknown"

    @commands.command(name="userinfo", aliases=["whois", "ui"])
    async def userinfo(self, ctx, *, query: str = None):
        """account age, ids, roles. usage: .userinfo [@user | id]"""
        error = self.bot.config.get_emoji("error")
        user = await self._resolve(ctx, query)
        if user is None:
            return await ctx.send(f"{error} couldn't find that user.")

        created = discord.utils.snowflake_time(user.id)
        lines = [
            f"**{user.display_name}** `{user.id}`",
            f"created {self._when(created)}",
        ]

        # Only members carry join date / roles; a plain User means we are in a DM
        # or the person is not in this server.
        if isinstance(user, discord.Member):
            if user.joined_at:
                lines.append(f"joined {self._when(user.joined_at)}")
            top = user.top_role
            if top and top != user.guild.default_role:
                lines.append(f"top role {top.mention}")
            roles = [r.mention for r in user.roles if r != user.guild.default_role]
            if roles:
                shown = " ".join(roles[:8])
                extra = f" +{len(roles) - 8}" if len(roles) > 8 else ""
                lines.append(f"roles ({len(roles)}) {shown}{extra}")
            if getattr(user, "premium_since", None):
                lines.append(f"boosting since {self._when(user.premium_since)}")
        if user.bot:
            lines.append("bot account")
        if user.avatar:
            lines.append(f"avatar [link]({user.avatar.url})")

        await ctx.send("\n".join(lines))

    @commands.command(name="serverinfo", aliases=["guildinfo", "si"])
    async def serverinfo(self, ctx):
        """server stats. usage: .serverinfo"""
        error = self.bot.config.get_emoji("error")
        guild = ctx.guild
        if guild is None:
            return await ctx.send(f"{error} this only works in a server.")

        owner = guild.owner.mention if guild.owner else f"`{guild.owner_id}`"
        lines = [
            f"**{guild.name}** `{guild.id}`",
            f"created {self._when(guild.created_at)}",
            f"members **{guild.member_count}** · boosts **{guild.premium_subscription_count}** (tier {guild.premium_tier})",
            f"channels **{len(guild.channels)}** · roles **{len(guild.roles)}** · emojis **{len(guild.emojis)}**",
            f"owner {owner}",
        ]
        if guild.icon:
            lines.append(f"icon [link]({guild.icon.url})")
        if guild.banner:
            lines.append(f"banner [link]({guild.banner.url})")

        await ctx.send("\n".join(lines))

    @commands.command(name="avatar", aliases=["av", "pfp"])
    async def avatar(self, ctx, *, query: str = None):
        """profile picture links. usage: .avatar [@user | id]"""
        error = self.bot.config.get_emoji("error")
        user = await self._resolve(ctx, query)
        if user is None:
            return await ctx.send(f"{error} couldn't find that user.")

        lines = [f"**{user.display_name}**"]
        # A server avatar wins visually, so show it first and keep the global one too.
        if isinstance(user, discord.Member) and user.guild_avatar:
            lines.append(f"server avatar [link]({user.guild_avatar.url})")
        if user.avatar:
            lines.append(f"avatar [link]({user.avatar.url})")
        if len(lines) == 1:
            lines.append(f"{error} no avatar set.")

        await ctx.send("\n".join(lines))

    @commands.command(name="banner")
    async def banner(self, ctx, *, query: str = None):
        """profile banner link. usage: .banner [@user | id]"""
        error = self.bot.config.get_emoji("error")
        user = await self._resolve(ctx, query)
        if user is None:
            return await ctx.send(f"{error} couldn't find that user.")

        # Cached user objects often have no banner -- fetch to be sure.
        try:
            fetched = await self.bot.fetch_user(user.id)
        except discord.HTTPException:
            fetched = user

        banner = getattr(fetched, "banner", None)
        if not banner:
            return await ctx.send(f"{error} no banner set.")

        await ctx.send(f"**{user.display_name}** banner\n{banner.url}")
