"""Discord lookups: where you are, what a channel or role is, and what the bot is.

All read-only and local (the invite lookup is the one Discord API call), so none
of this touches the dashboard.
"""
from __future__ import annotations

import platform
import time

import discord
from discord.ext import commands


def _snowflake(value: str):
    """A snowflake from a raw id or a mention, or ``None``."""
    digits = "".join(char for char in str(value) if char.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _channel_type(channel) -> str:
    kind = getattr(channel, "type", None)
    return getattr(kind, "name", str(kind or "unknown")).replace("_", " ")


class LookupsMixin:
    """Commands for this sub-cog; assembled into the package cog."""

    def _where(self, ctx) -> list:
        lines = [f"**guild** {ctx.guild.name} `{ctx.guild.id}`" if ctx.guild else "**guild** direct messages"]
        lines.append(f"**channel** {getattr(ctx.channel, 'name', 'dm')} `{ctx.channel.id}` · {_channel_type(ctx.channel)}")
        lines.append(f"**you** {ctx.author.display_name} `{ctx.author.id}`")
        lines.append(f"**message** `{getattr(ctx.message, 'id', '—')}`")
        return lines

    @commands.command(name="whereami", aliases=["where"])
    async def whereami(self, ctx):
        """ids for this server, channel and message. usage: .whereami"""
        await ctx.send("\n".join(self._where(ctx)))

    @commands.command(name="channelinfo", aliases=["ci"])
    async def channelinfo(self, ctx, *, query: str = ""):
        """details for a channel. usage: .channelinfo [#channel]"""
        channel = ctx.channel
        query = query.strip()
        if query:
            channel = None
            ident = _snowflake(query)
            if ctx.guild:
                if ident:
                    channel = ctx.guild.get_channel(ident)
                if channel is None:
                    name = query.lstrip("#").lower()
                    channel = discord.utils.find(
                        lambda ch: getattr(ch, "name", "").lower() == name, ctx.guild.channels
                    )
            if channel is None:
                return await ctx.warn("couldn't find that channel here.")

        lines = [
            f"**#{getattr(channel, 'name', 'dm')}** `{channel.id}`",
            f"type **{_channel_type(channel)}** · created <t:{int(channel.created_at.timestamp())}:R>",
        ]
        if getattr(channel, "category", None):
            lines.append(f"category **{channel.category.name}**")
        if getattr(channel, "topic", None):
            lines.append(f"topic {channel.topic[:180]}")
        if getattr(channel, "guild", None):
            lines.append(f"guild **{channel.guild.name}** `{channel.guild.id}`")
        if hasattr(channel, "members"):
            try:
                lines.append(f"members **{len(channel.members)}**")
            except TypeError:
                pass
        lines.append(f"position **{getattr(channel, 'position', '—')}**")
        await ctx.send("\n".join(lines))

    @commands.command(name="roleinfo", aliases=["ri"])
    async def roleinfo(self, ctx, *, query: str = ""):
        """details for a role. usage: .roleinfo <role>"""
        if not ctx.guild:
            return await ctx.warn("roles only exist in servers.")
        if not query.strip():
            return await ctx.warn("usage: `.roleinfo <role>`")
        ident = _snowflake(query)
        role = ctx.guild.get_role(ident) if ident else None
        if role is None:
            name = query.strip().lstrip("@").lower()
            role = discord.utils.find(lambda item: item.name.lower() == name, ctx.guild.roles)
        if role is None:
            return await ctx.warn("couldn't find that role.")

        lines = [
            f"**{role.name}** `{role.id}`",
            f"color **#{role.color.value:06x}** · position **{role.position}** · members **{len(role.members)}**",
            f"mentionable **{role.mentionable}** · hoisted **{role.hoist}** · managed **{role.managed}**",
            f"created <t:{int(role.created_at.timestamp())}:R>",
        ]
        if role.permissions.administrator:
            lines.append("permissions **administrator**")
        else:
            keys = [name.replace("_", " ") for name, value in role.permissions if value]
            if keys:
                lines.append("permissions " + ", ".join(keys[:15]) + (" …" if len(keys) > 15 else ""))
        await ctx.send("\n".join(lines))

    @commands.command(name="servericon", aliases=["guildicon"])
    async def servericon(self, ctx):
        """server icon, banner and splash links. usage: .servericon"""
        if not ctx.guild:
            return await ctx.warn("this only works in a server.")
        links = []
        for label, asset in (
            ("icon", ctx.guild.icon),
            ("banner", ctx.guild.banner),
            ("splash", ctx.guild.splash),
        ):
            if asset:
                links.append(f"{label} [link]({asset.url})")
        if not links:
            return await ctx.warn("this server has no icon set.")
        await ctx.send(f"**{ctx.guild.name}**\n" + "\n".join(links))

    @commands.command(name="inviteinfo", aliases=["inv"])
    async def inviteinfo(self, ctx, code: str = ""):
        """resolve a server invite. usage: .inviteinfo discord.gg/abc"""
        code = code.strip().split("/")[-1].split("?")[0]
        if not code:
            return await ctx.warn("usage: `.inviteinfo <code|link>`")
        try:
            invite = await self.bot.fetch_invite(code, with_counts=True)
        except discord.NotFound:
            return await ctx.warn("that invite is invalid or expired.")
        except discord.HTTPException as exc:
            return await ctx.deny(f"discord said no: {exc}")

        lines = [f"**{getattr(invite.guild, 'name', 'unknown server')}**"]
        if getattr(invite.guild, "id", None):
            lines.append(f"id `{invite.guild.id}`")
        if getattr(invite.guild, "description", None):
            lines.append(invite.guild.description[:200])
        if invite.channel:
            lines.append(f"channel **#{invite.channel.name}**")
        if invite.inviter:
            lines.append(f"inviter **{invite.inviter}** `{invite.inviter.id}`")
        if invite.approximate_member_count is not None:
            lines.append(
                f"members **{invite.approximate_member_count}** · "
                f"online **{invite.approximate_presence_count}**"
            )
        if invite.uses is not None:
            lines.append(f"uses **{invite.uses}**")
        await ctx.send("\n".join(lines))

    @commands.command(name="idinfo", aliases=["snowflake"])
    async def idinfo(self, ctx, ident: str = ""):
        """when a discord id was created. usage: .idinfo 123456789012345678"""
        value = _snowflake(ident)
        if value is None:
            return await ctx.warn("usage: `.idinfo <discord id>`")
        try:
            created = discord.utils.snowflake_time(value)
        except (ValueError, OverflowError):
            return await ctx.warn("that is not a valid snowflake.")
        stamp = int(created.timestamp())
        await ctx.send(
            f"`{value}`\ncreated <t:{stamp}:f> (<t:{stamp}:R>)\n"
            f"unix **{stamp}** · worker **{(value >> 17) & 0x1F}** · "
            f"process **{(value >> 12) & 0x1F}** · increment **{value & 0xFFF}**"
        )

    @commands.command(name="membercount", aliases=["mc"])
    async def membercount(self, ctx):
        """how many people are in this server. usage: .membercount"""
        if not ctx.guild:
            return await ctx.warn("this only works in a server.")
        guild = ctx.guild
        humans = sum(1 for member in guild.members if not member.bot)
        bots = sum(1 for member in guild.members if member.bot)
        await ctx.send(
            f"**{guild.name}**\nmembers **{guild.member_count}** · "
            f"cached humans **{humans}** · bots **{bots}**"
        )

    @commands.command(name="botinfo", aliases=["engineinfo"])
    async def botinfo(self, ctx):
        """uptime, latency and engine stats. usage: .botinfo"""
        uptime = max(0, time.time() - getattr(self, "started_at", time.time()))
        hours, rest = divmod(int(uptime), 3600)
        minutes, seconds = divmod(rest, 60)
        latency = f"{self.bot.latency * 1000:.0f} ms" if self.bot.latency else "—"
        await ctx.send(
            "### chrm engine\n"
            f"up **{hours}h {minutes}m {seconds}s** · gateway **{latency}**\n"
            f"guilds **{len(self.bot.guilds)}** · users **{len(self.bot.users)}** · "
            f"commands **{len(self.bot.commands)}**\n"
            f"plugins **{len(self.bot.extensions)}** loaded · "
            f"errors **{len(getattr(self.bot, 'load_errors', {}))}**\n"
            f"python **{platform.python_version()}** · discord.py-self **{discord.__version__}**"
        )

    @commands.command(name="plugins", aliases=["extensions"])
    async def plugins(self, ctx):
        """loaded plugins and load errors. usage: .plugins"""
        names = sorted(str(name).split(".")[-1] for name in self.bot.extensions)
        lines = [f"### plugins · {len(names)}", " ".join(f"`{name}`" for name in names)]
        errors = getattr(self.bot, "load_errors", {}) or {}
        if errors:
            lines.append("**failed**")
            lines.extend(f"`{name}` — {reason}" for name, reason in list(errors.items())[:8])
        await ctx.send("\n".join(lines))

    @commands.command(name="cmdinfo", aliases=["commandinfo"])
    async def cmdinfo(self, ctx, *, name: str = ""):
        """what a command does and where it comes from. usage: .cmdinfo purge"""
        name = name.strip().lstrip(".")
        if not name:
            return await ctx.warn("usage: `.cmdinfo <command>`")
        command = self.bot.get_command(name)
        if command is None:
            return await ctx.warn(f"no command called `{name}`.")

        lines = [f"**`{command.qualified_name}`**"]
        if command.aliases:
            lines.append("aliases " + " ".join(f"`{alias}`" for alias in command.aliases[:10]))
        lines.append(f"plugin **{command.cog_name or 'none'}**")
        usage = getattr(command, "usage", None)
        lines.append(f"usage `.{(command.qualified_name + ' ' + usage).strip()}`" if usage else f"`.{command.qualified_name}`")
        if command.help:
            lines.append(command.help)

        try:
            from plugins.levels import catalog

            entry = catalog.find(command.name)
        except Exception:  # noqa: BLE001 - levels is optional
            entry = None
        if entry is not None:
            levels = getattr(self.bot.get_cog("Levels"), "level", None)
            state = "unlocked" if levels is not None and levels >= entry.level else f"requires level {entry.level}"
            lines.append(f"level **{entry.level}** · {state}")
        await ctx.send("\n".join(lines))
