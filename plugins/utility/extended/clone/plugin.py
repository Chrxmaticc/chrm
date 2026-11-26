"""Copy a server's structure into a brand new one.

Roles, categories, channels, permission overwrites, server settings and (with a
flag) emojis are rebuilt from the gateway cache, written with the account's own
permissions. No third-party service is involved, so nothing here can be refused
an IP.

A copy contains the name and icon, verification level, explicit-content filter,
notification default, AFK timeout, the role hierarchy in its original order,
categories, text/voice/stage/forum channels with topic, slowmode, nsfw, bitrate
and user limit, every role-based permission overwrite, the system and AFK
channels, and -- with ``--emojis`` -- the emoji art.

Message history is never copied: Discord has no bulk import, and replaying a
channel through the send endpoint would sit in rate limits for hours. The aim is
"the same shape", not "the same conversation". Member-specific overwrites are
skipped too: the copy starts with no members to attach them to.

``.clone <server>`` only prints a plan. Adding ``--go`` creates the server, which
is why it is opt-in rather than the default.
"""
from __future__ import annotations

import asyncio

import discord
from discord.ext import commands

#: refusing to clone a server bigger than this keeps one command under a minute
MAX_CHANNELS = 200

#: how many times to wait for the gateway to hand over the new guild
SETTLE_TRIES = 6

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


def is_category(channel) -> bool:
    return isinstance(channel, discord.CategoryChannel) or getattr(
        channel, "type", None
    ) is discord.ChannelType.category


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
        default_role = getattr(target, "default_role", None)
        for holder, overwrite in (getattr(channel, "overwrites", {}) or {}).items():
            if not isinstance(holder, discord.Role):
                # member-specific overwrites cannot follow a new server
                continue
            if holder.is_default():
                if default_role is not None:
                    mapped[default_role] = overwrite
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

    # ------------------------------------------------------------ preparation
    async def _settle(self, created):
        """Wait for the gateway, then return ``(guild, channels)`` for the new server.

        ``POST /guilds`` answers before the guild is in cache, and the object it
        returns is not guaranteed to carry roles. Writing roles or overwrites
        against it is what makes a clone create channels with no @everyone
        entry, so the server is fetched back properly first.
        """
        target = created
        for attempt in range(SETTLE_TRIES):
            await asyncio.sleep(1 if attempt == 0 else min(2 * attempt, 6))
            fetch = getattr(self.bot, "fetch_guild", None)
            if fetch is not None:
                try:
                    fetched = await fetch(created.id)
                    if fetched is not None:
                        target = fetched
                        break
                except Exception as exc:  # noqa: BLE001 - fall back to the cache
                    print(f"[CLONE] fetch_guild {created.id} failed: {exc}")
            cached = self.bot.get_guild(created.id) if hasattr(self.bot, "get_guild") else None
            if cached is not None:
                target = cached
                break
        else:
            await asyncio.sleep(2)

        channels = list(getattr(target, "channels", []) or [])
        try:
            channels = list(await target.fetch_channels())
        except Exception as exc:  # noqa: BLE001 - the cache list still works
            print(f"[CLONE] fetch_channels failed: {exc}")
        return target, channels

    async def _clear(self, target, channels) -> int:
        """Delete whatever the create endpoint seeded so the copy is exact.

        Creating a guild hands back a starter layout (and the library asks
        Discord for its default template). Those channels and roles are not in
        the source, so leaving them in makes the copy wrong.
        """
        removed = 0
        for channel in [item for item in channels if not is_category(item)]:
            try:
                await channel.delete()
                removed += 1
            except Exception as exc:  # noqa: BLE001
                print(f"[CLONE] clearing {getattr(channel, 'name', '?')!r} failed: {exc}")
        for channel in [item for item in channels if is_category(item)]:
            try:
                await channel.delete()
                removed += 1
            except Exception as exc:  # noqa: BLE001
                print(f"[CLONE] clearing category {getattr(channel, 'name', '?')!r} failed: {exc}")
        for role in list(getattr(target, "roles", []) or []):
            if role.is_default() or getattr(role, "managed", False):
                continue
            try:
                await role.delete()
                removed += 1
            except Exception as exc:  # noqa: BLE001
                print(f"[CLONE] clearing role {getattr(role, 'name', '?')!r} failed: {exc}")
        return removed

    async def _settings(self, origin, target) -> int:
        """Copy the server-level switches, one at a time so one refusal is not fatal."""
        copied = 0
        values = {}
        for field in (
            "verification_level",
            "explicit_content_filter",
            "default_notifications",
            "afk_timeout",
        ):
            value = getattr(origin, field, None)
            if value is not None:
                values[field] = value
        flags = getattr(origin, "system_channel_flags", None)
        if flags is not None:
            values["system_channel_flags"] = flags
        icon = getattr(origin, "icon", None)
        if icon is not None:
            try:
                values["icon"] = await icon.read()
            except Exception as exc:  # noqa: BLE001 - cosmetic only
                print(f"[CLONE] icon read failed: {exc}")
        for field, value in values.items():
            try:
                await target.edit(**{field: value})
                copied += 1
            except Exception as exc:  # noqa: BLE001
                print(f"[CLONE] {field} failed: {exc}")
        return copied

    # ----------------------------------------------------------------- command
    @commands.command(name="clone", aliases=["serverclone"])
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def clone(self, ctx, source: str = "", *, options: str = ""):
        """copy roles, categories, channels and settings into a new server. usage: .clone <id> --go"""
        guilds = [guild for guild in getattr(self.bot, "guilds", [])]
        if not source:
            lines = [
                "### clone",
                "usage: `.clone <server id | name> [--go] [--emojis] [--name <name>]`",
                "-# copies roles, categories, channels, overwrites and settings; never messages",
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
        capped = len(channels) > MAX_CHANNELS

        lines = [
            f"### clone — {clip(origin.name, 45)}",
            f"roles **{len(roles)}** · categories **{len(categories)}** · "
            f"channels **{len(channels)}** · emojis **{len(emojis)}**",
            f"-# new server name: **{clip(name, 80)}**",
        ]
        if capped:
            lines.append(f"-# only the first **{MAX_CHANNELS}** channels would be created")
        if not go:
            lines.append("-# this is a plan and nothing was created — add `--go` to build it")
            lines.append("-# `--emojis` copies emoji art too, `--name <text>` renames the copy")
            return await ctx.send("\n".join(lines))

        try:
            created = await self.bot.create_guild(name=clip(name, 95))
        except discord.HTTPException as exc:
            code = getattr(exc, "code", None)
            detail = clip(getattr(exc, "text", "") or exc, 140)
            if code == 30001:
                return await ctx.deny("this account is already at discord's server limit — leave one first.")
            if "captcha" in detail.lower() or "verify" in detail.lower():
                return await ctx.deny(
                    "discord wants a captcha for new servers on this account — "
                    "create one by hand once, then retry."
                )
            return await ctx.deny(f"discord refused the create (`{code or 'http'}`): {detail}")
        except Exception as exc:  # noqa: BLE001
            return await ctx.deny(f"could not create the server: {clip(exc, 140)}")

        status = await ctx.send(f"-# building **{clip(getattr(created, 'name', name), 60)}** — preparing…")
        target, seeded = await self._settle(created)
        failures = []

        await self._progress(status, "-# building — server settings…")
        copied_settings = await self._settings(origin, target)

        default_role = getattr(target, "default_role", None)
        if default_role is not None:
            try:
                await default_role.edit(permissions=origin.default_role.permissions)
            except Exception as exc:  # noqa: BLE001
                print(f"[CLONE] @everyone permissions failed: {exc}")

        cleared = await self._clear(target, seeded)
        await self._progress(status, f"-# building — roles… (#{cleared} starter items removed)")

        # Discord drops every new role at the bottom of the hierarchy, so the
        # highest role has to go in first for the stack to come out the right
        # way up. Positions are then asserted in one bulk call.
        role_map = {}
        made_roles = []
        for role in sorted(roles, key=lambda item: item.position, reverse=True):
            try:
                made_role = await target.create_role(
                    name=clip(role.name, 95),
                    permissions=role.permissions,
                    colour=role.colour,
                    hoist=role.hoist,
                    mentionable=role.mentionable,
                )
                role_map[role.id] = made_role
                made_roles.append((role, made_role))
            except Exception as exc:  # noqa: BLE001 - one bad role must not stop the rest
                failures.append(f"role {clip(role.name, 30)}")
                print(f"[CLONE] role {role.name!r} failed: {exc}")

        if made_roles:
            # rank, not the source's absolute index: managed roles are skipped,
            # so those numbers would collide once two of them are clamped.
            rank = {
                role.id: index + 1
                for index, role in enumerate(sorted(roles, key=lambda item: item.position))
            }
            positions = {
                made_role: rank.get(role.id, 1) for role, made_role in made_roles
            }
            try:
                await target.edit_role_positions(positions)
            except Exception as exc:  # noqa: BLE001 - creation order already helps
                print(f"[CLONE] role positions failed: {exc}")

        await self._progress(
            status, f"-# building — {len(role_map)}/{len(roles)} roles, categories…"
        )

        category_map = {}
        for category in sorted(categories, key=lambda item: item.position):
            try:
                category_map[category.id] = await target.create_category(
                    clip(category.name, 95),
                    overwrites=self._overwrites(category, role_map, target),
                    position=category.position,
                )
            except Exception as exc:  # noqa: BLE001
                failures.append(f"category {clip(category.name, 30)}")
                print(f"[CLONE] category {category.name!r} failed: {exc}")

        made = 0
        channel_map = {}
        for channel in sorted(channels, key=lambda item: item.position)[:MAX_CHANNELS]:
            category = category_map.get(getattr(channel, "category_id", None))
            overwrites = self._overwrites(channel, role_map, target)
            label = clip(getattr(channel, "name", "channel"), 95)
            kind = getattr(channel, "type", discord.ChannelType.text)
            try:
                if kind is discord.ChannelType.voice:
                    placed = await target.create_voice_channel(
                        label,
                        bitrate=min(int(getattr(channel, "bitrate", 64000)), int(target.bitrate_limit)),
                        user_limit=int(getattr(channel, "user_limit", 0) or 0),
                        overwrites=overwrites,
                        category=category,
                        position=channel.position,
                    )
                elif kind is discord.ChannelType.stage_voice:
                    placed = await target.create_stage_channel(
                        label,
                        topic=clip(getattr(channel, "topic", ""), 1000) or None,
                        overwrites=overwrites,
                        category=category,
                        position=channel.position,
                    )
                elif kind is discord.ChannelType.forum and hasattr(target, "create_forum"):
                    placed = await target.create_forum(
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
                    placed = await target.create_text_channel(
                        label,
                        topic=clip(getattr(channel, "topic", ""), 1000) or None,
                        slowmode_delay=int(getattr(channel, "slowmode_delay", 0) or 0),
                        nsfw=bool(getattr(channel, "nsfw", False)),
                        overwrites=overwrites,
                        category=category,
                        position=channel.position,
                    )
                made += 1
                if placed is not None:
                    channel_map[channel.id] = placed
            except Exception as exc:  # noqa: BLE001
                failures.append(f"channel {label}")
                print(f"[CLONE] channel {label!r} failed: {exc}")

        system = channel_map.get(getattr(origin, "system_channel_id", None))
        afk = channel_map.get(getattr(origin, "afk_channel_id", None))
        if system is not None or afk is not None:
            routing = {}
            if system is not None:
                routing["system_channel"] = system
            if afk is not None:
                routing["afk_channel"] = afk
            try:
                await target.edit(**routing)
            except Exception as exc:  # noqa: BLE001
                print(f"[CLONE] system/afk channel failed: {exc}")

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
                    failures.append(f"emoji {clip(emoji.name, 30)}")
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
            f"-# id `{target.id}` · settings **{copied_settings}** · messages are never copied",
        ]
        if capped:
            summary.append(f"-# capped at **{MAX_CHANNELS}** channels; the rest were not created")
        if failures:
            summary.append(f"-# {len(failures)} items failed — see the engine log for why")
        if invite_link:
            summary.append(invite_link)
        else:
            summary.append("-# no invite could be made; you are the owner, so open it from your server list")
        await self._progress(status, "\n".join(summary))
