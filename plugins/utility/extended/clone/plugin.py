"""Copy a server's structure into a brand new one.

Roles, categories, channels, permission overwrites and (with a flag) emojis are
rebuilt from the gateway cache, written with the account's own permissions. No
third-party service is involved, so nothing here can be refused an IP.

Message history is never copied: Discord has no bulk import, and replaying a
channel through the send endpoint would sit in rate limits for hours. The aim is
"the same shape", not "the same conversation".

``.clone <server>`` only prints a plan. Adding ``--go`` creates the server, which
is why it is opt-in rather than the default.
"""
from __future__ import annotations

import asyncio

import discord
from discord.ext import commands

#: refusing to clone a server bigger than this keeps one command under a minute
MAX_CHANNELS = 200

#: emoji slots per boost tier
EMOJI_SLOTS = {0: 50, 1: 100, 2: 150, 3: 250}


def clip(text, limit: int = 100) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def flag(options: str, name: str) -> str:
    """``--name Dune`` -> ``"Dune"``; everything after the flag, up to the next one."""
    tokens = (options or "").split()
    if name not in tokens:
        return ""
    index = tokens.index(name) + 1
    collected = []
    while index < len(tokens) and not tokens[index].startswith("--"):
        collected.append(tokens[index])
        index += 1
    return " ".join(collected)


class CloneMixin:
    """Commands for this sub-cog; assembled into the package cog."""

    # ---------------------------------------------------------------- lookups
    def _source(self, source: str):
        """``(guild, error)`` from an id, an exact name or a name prefix."""
        source = (source or "").strip()
        if not source:
            return None, "give me a server id or name."
        guilds = [guild for guild in getattr(self.bot, "guilds", [])]
        if source.isdigit():
            for guild in guilds:
                if guild.id == int(source):
                    return guild, None
        lowered = source.lower()
        for guild in guilds:
            if guild.name.lower() == lowered:
                return guild, None
        for guild in guilds:
            if guild.name.lower().startswith(lowered):
                return guild, None
        return None, f"no server matching **{clip(source, 40)}** — `.clone` on its own lists them."

    def _overwrites(self, channel, role_map, target) -> dict:
        """Source overwrites retargeted onto the new roles, by role id."""
        mapped = {}
        for holder, overwrite in (getattr(channel, "overwrites", {}) or {}).items():
            if not isinstance(holder, discord.Role):
                # member-specific overwrites cannot follow a new server
                continue
            if holder.is_default():
                mapped[target.default_role] = overwrite
                continue
            replacement = role_map.get(holder.id)
            if replacement is not None:
                mapped[replacement] = overwrite
        return mapped

    async def _progress(self, message, text: str):
        """Edit the running status message; never let a deleted one stop the clone."""
        try:
            await message.edit(content=text)
        except Exception:  # noqa: BLE001
            pass

    # ----------------------------------------------------------------- command
    @commands.command(name="clone", aliases=["serverclone"])
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def clone(self, ctx, source: str = "", *, options: str = ""):
        """copy roles, categories and channels into a new server. usage: .clone <id> --go"""
        guilds = [guild for guild in getattr(self.bot, "guilds", [])]
        if not source:
            lines = [
                "### clone",
                "usage: `.clone <server id | name> [--go] [--emojis] [--name <name>]`",
                "-# copies roles, categories, channels and overwrites; never messages",
            ]
            if guilds:
                lines.append("-# servers you are in:")
                lines += [f"`{guild.id}` {clip(guild.name, 50)}" for guild in guilds[:15]]
            return await ctx.send("\n".join(lines))

        origin, error = self._source(source)
        if error:
            return await ctx.deny(error)

        roles = [
            role
            for role in getattr(origin, "roles", [])
            if not role.is_default() and not role.managed
        ]
        categories = list(getattr(origin, "categories", []) or [])
        channels = [
            channel
            for channel in getattr(origin, "channels", []) or []
            if not isinstance(channel, discord.CategoryChannel)
            and getattr(channel, "type", None) is not discord.ChannelType.category
        ]
        emojis = list(getattr(origin, "emojis", []) or [])
        name = flag(options, "--name") or f"{origin.name} (clone)"
        go = "--go" in (options or "").split()
        copy_emojis = "--emojis" in (options or "").split()

        lines = [
            f"### clone — {clip(origin.name, 45)}",
            f"roles **{len(roles)}** · categories **{len(categories)}** · "
            f"channels **{len(channels)}** · emojis **{len(emojis)}**",
            f"-# new server name: **{clip(name, 80)}**",
        ]
        if len(channels) > MAX_CHANNELS:
            lines.append(f"-# only the first **{MAX_CHANNELS}** channels would be created")
        if not go:
            lines.append("-# this is a plan and nothing was created — add `--go` to build it")
            lines.append("-# `--emojis` copies emoji art too, `--name <text>` renames the copy")
            return await ctx.send("\n".join(lines))

        try:
            target = await self.bot.create_guild(name=clip(name, 95))
        except discord.HTTPException as exc:
            code = getattr(exc, "code", None)
            if code == 30001:
                return await ctx.deny("this account is already in 10 servers — leave one first.")
            detail = clip(getattr(exc, "text", "") or exc, 120)
            return await ctx.deny(f"discord refused the create (`{code or 'http'}`): {detail}")
        except Exception as exc:  # noqa: BLE001
            return await ctx.deny(f"could not create the server: {exc}")

        # The gateway has to catch up before the new guild has channels to write into.
        await asyncio.sleep(2)
        target = self.bot.get_guild(target.id) or target
        status = await ctx.send(f"-# building **{clip(target.name, 60)}** — roles…")
        await self._progress(status, "-# building — roles…")

        icon = getattr(origin, "icon", None)
        if icon is not None:
            try:
                await target.edit(icon=await icon.read())
            except Exception:  # noqa: BLE001 - cosmetic only
                pass

        try:
            await target.default_role.edit(permissions=origin.default_role.permissions)
        except Exception:  # noqa: BLE001
            pass

        role_map = {}
        for role in roles:
            try:
                role_map[role.id] = await target.create_role(
                    name=clip(role.name, 95),
                    permissions=role.permissions,
                    colour=role.colour,
                    hoist=role.hoist,
                    mentionable=role.mentionable,
                )
            except Exception as exc:  # noqa: BLE001 - one bad role must not stop the rest
                print(f"[CLONE] role {role.name!r} failed: {exc}")
        await self._progress(status, f"-# building — {len(role_map)}/{len(roles)} roles, categories…")

        category_map = {}
        for category in sorted(categories, key=lambda item: item.position):
            try:
                category_map[category.id] = await target.create_category(
                    clip(category.name, 95),
                    overwrites=self._overwrites(category, role_map, target),
                    position=category.position,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[CLONE] category {category.name!r} failed: {exc}")

        made = 0
        for channel in sorted(channels, key=lambda item: item.position)[:MAX_CHANNELS]:
            category = category_map.get(getattr(channel, "category_id", None))
            overwrites = self._overwrites(channel, role_map, target)
            label = clip(getattr(channel, "name", "channel"), 95)
            kind = getattr(channel, "type", discord.ChannelType.text)
            try:
                if kind is discord.ChannelType.voice:
                    await target.create_voice_channel(
                        label,
                        bitrate=min(int(getattr(channel, "bitrate", 64000)), int(target.bitrate_limit)),
                        user_limit=int(getattr(channel, "user_limit", 0) or 0),
                        overwrites=overwrites,
                        category=category,
                        position=channel.position,
                    )
                elif kind is discord.ChannelType.stage_voice:
                    await target.create_stage_channel(
                        label,
                        topic=clip(getattr(channel, "topic", ""), 1000) or None,
                        overwrites=overwrites,
                        category=category,
                        position=channel.position,
                    )
                elif kind is discord.ChannelType.forum and hasattr(target, "create_forum"):
                    await target.create_forum(
                        label,
                        topic=clip(getattr(channel, "topic", ""), 1000) or None,
                        slowmode_delay=int(getattr(channel, "slowmode_delay", 0) or 0),
                        nsfw=bool(getattr(channel, "nsfw", False)),
                        overwrites=overwrites,
                        category=category,
                        position=channel.position,
                    )
                else:
                    # news and media channels become text channels: the create
                    # endpoint for those types is not exposed by the library
                    await target.create_text_channel(
                        label,
                        topic=clip(getattr(channel, "topic", ""), 1000) or None,
                        slowmode_delay=int(getattr(channel, "slowmode_delay", 0) or 0),
                        nsfw=bool(getattr(channel, "nsfw", False)),
                        overwrites=overwrites,
                        category=category,
                        position=channel.position,
                    )
                made += 1
            except Exception as exc:  # noqa: BLE001
                print(f"[CLONE] channel {label!r} failed: {exc}")

        copied_emojis = 0
        if copy_emojis:
            await self._progress(status, f"-# building — {made} channels, emojis…")
            slots = EMOJI_SLOTS.get(int(getattr(target, "premium_tier", 0) or 0), 50) - len(
                list(getattr(target, "emojis", []) or [])
            )
            for emoji in emojis[: max(0, slots)]:
                try:
                    await target.create_custom_emoji(name=emoji.name, image=await emoji.read())
                    copied_emojis += 1
                except Exception as exc:  # noqa: BLE001
                    print(f"[CLONE] emoji {emoji.name!r} failed: {exc}")

        invite_link = ""
        try:
            await target.fetch_channels()
            for channel in target.text_channels:
                invite_link = (await channel.create_invite(max_age=0, max_uses=0)).url
                break
        except Exception:  # noqa: BLE001 - an invite is a nicety, not the point
            invite_link = ""

        summary = [
            f"### clone done — {clip(target.name, 50)}",
            f"roles **{len(role_map)}** · categories **{len(category_map)}** · "
            f"channels **{made}**" + (f" · emojis **{copied_emojis}**" if copy_emojis else ""),
            f"-# id `{target.id}` · messages are never copied",
        ]
        if len(role_map) < len(roles) or made < len(channels):
            summary.append("-# some items failed; they are printed in the engine log")
        if invite_link:
            summary.append(invite_link)
        await self._progress(status, "\n".join(summary))
