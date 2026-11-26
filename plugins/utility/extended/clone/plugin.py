"""Copy a server's structure into a brand new one -- or into the one you are in.

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

``--here`` skips the new server: it rebuilds the server the command was used in.
Channels are replaced, while roles are reused by name so the members who already
have them keep them; ``--prune`` also deletes roles the source does not have.
The channel the command was typed in survives, so the progress message and the
summary stay readable.
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

#: smart punctuation rewrites "--" as an em dash on macOS and iOS
_DASHES = str.maketrans({"\u2014": "-", "\u2013": "-", "\u2212": "-", "\u2010": "-", "\u2011": "-"})


def clip(text, limit: int = 100) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def normalize(options: str) -> str:
    """Turn every dash spelling of a flag into ``--flag``.

    A phone keyboard sends ``.clone 123 —go``; the exact-match test used to
    call that a plain flag-less plan, so the command looked broken. Single
    dashes, em dashes and dashes separated from the word are accepted too.
    """
    text = str(options or "").translate(_DASHES).replace("`", "").strip()
    tokens = []
    pending = ""
    for token in text.split():
        if token and not token.strip("-"):
            # a dash on its own: "-- go" and "- go" mean the same thing
            pending = "--"
            continue
        if token.startswith("-"):
            token = "--" + token.lstrip("-")
        if pending:
            token = pending + token.lstrip("-")
            pending = ""
        tokens.append(token)
    return " ".join(tokens)


def flag(options: str, name: str) -> str:
    """``--name Dune`` -> ``"Dune"``; everything after the flag, up to the next one."""
    tokens = (options or "").split()
    lowered = [token.lower() for token in tokens]
    if name.lower() not in lowered:
        return ""
    index = lowered.index(name.lower()) + 1
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

    async def _wipe_channels(self, target, keep=None) -> int:
        """Delete every channel except the one the command was used in.

        An in-place rebuild cannot delete the channel it is talking in without
        losing the progress message, so that one is spared and reused later.
        """
        removed = 0
        channels = list(getattr(target, "channels", []) or [])
        try:
            channels = list(await target.fetch_channels())
        except Exception as exc:  # noqa: BLE001 - the cache list still works
            print(f"[CLONE] fetch_channels failed: {exc}")
        keep_id = getattr(keep, "id", None)
        for channel in [item for item in channels if not is_category(item)]:
            if keep_id is not None and getattr(channel, "id", None) == keep_id:
                continue
            try:
                await channel.delete()
                removed += 1
            except Exception as exc:  # noqa: BLE001
                print(f"[CLONE] deleting {getattr(channel, 'name', '?')!r} failed: {exc}")
        for category in [item for item in channels if is_category(item)]:
            if keep_id is not None and getattr(category, "id", None) == keep_id:
                continue
            try:
                await category.delete()
                removed += 1
            except Exception as exc:  # noqa: BLE001
                print(f"[CLONE] deleting category {getattr(category, 'name', '?')!r} failed: {exc}")
        return removed

    def _role_index(self, target) -> dict:
        """Target roles by casefolded name, so an in-place clone can reuse them.

        Deleting and recreating every role would strip them from members; a
        role with the source's name is repainted instead, which keeps every
        member who already had it.
        """
        index = {}
        for role in getattr(target, "roles", []) or []:
            if role.is_default() or getattr(role, "managed", False):
                continue
            index.setdefault(role.name.casefold(), role)
        return index

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
        """copy a server's shape into a new server, or into this one with --here. usage: .clone <id> --go"""
        options = normalize(options)
        flags = {token.lower() for token in options.split()}
        in_place = "--here" in flags
        prune = "--prune" in flags
        here = getattr(ctx, "guild", None)

        if source.lower() in {"here", "this", "current"}:
            source = str(getattr(here, "id", "") or "")
        if not source and in_place:
            # .clone --here --go rebuilds the server it was used in from itself
            source = str(getattr(here, "id", "") or "")

        guilds = [guild for guild in getattr(self.bot, "guilds", [])]
        if not source:
            lines = [
                "### clone",
                "usage: `.clone <server id | name> [--go] [--here] [--emojis] [--name <name>]`",
                "-# copies roles, categories, channels, overwrites and settings; never messages",
                "-# `--here` rebuilds the server you are in instead of creating a new one",
            ]
            if guilds:
                lines.append("-# servers you are in:")
                lines += [f"`{guild.id}` {clip(guild.name, 50)}" for guild in guilds[:15]]
            return await ctx.send("\n".join(lines))

        origin, error = self._source(source)
        if error:
            return await ctx.deny(error)
        if in_place and here is None:
            return await ctx.deny("`--here` needs a server — use it in one, not a dm.")

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
        go = "--go" in flags
        copy_emojis = "--emojis" in flags
        capped = len(channels) > MAX_CHANNELS

        lines = [
            f"### clone — {clip(origin.name, 45)}",
            f"roles **{len(roles)}** · categories **{len(categories)}** · "
            f"channels **{len(channels)}** · emojis **{len(emojis)}**",
        ]
        if in_place:
            live_channels = [
                channel
                for channel in getattr(here, "channels", []) or []
                if not is_category(channel)
            ]
            live_roles = [
                role
                for role in getattr(here, "roles", []) or []
                if not role.is_default() and not getattr(role, "managed", False)
            ]
            source_names = {role.name.casefold() for role in roles}
            extras = [role for role in live_roles if role.name.casefold() not in source_names]
            lines.append(f"-# rebuilding **{clip(here.name, 60)}** in place — no new server is created")
            lines.append(
                f"-# replaces **{len(live_channels)}** channels and their messages · "
                f"**{len(live_roles) - len(extras)}** roles match by name and are kept"
            )
            if extras:
                lines.append(
                    f"-# **{len(extras)}** roles are not in the source: "
                    + ("`--prune` deletes them" if prune else "they are kept")
                )
        else:
            lines.append(f"-# new server name: **{clip(name, 80)}**")
        if capped:
            lines.append(f"-# only the first **{MAX_CHANNELS}** channels would be created")
        if not go:
            lines.append("-# this is a plan and nothing was created — add `--go` to build it")
            lines.append("-# `--emojis` copies emoji art too, `--name <text>` renames the copy")
            if in_place:
                lines.append("-# deleted channels and their messages cannot be recovered")
            if flags and not flags & {"--go", "--emojis", "--name", "--here", "--prune"}:
                lines.append(
                    f"-# saw `{clip(options, 60)}` but only `--go`, `--emojis`, `--name`, "
                    "`--here` and `--prune` are used"
                )
            return await ctx.send("\n".join(lines))

        if in_place:
            target = here
            keep = getattr(ctx, "channel", None)
            seeded = []
            status = await ctx.send(f"-# rebuilding **{clip(target.name, 60)}** — preparing…")
            failures = []
        else:
            try:
                created = await self.bot.create_guild(name=clip(name, 95))
            except discord.HTTPException as exc:
                code = getattr(exc, "code", None)
                detail = clip(getattr(exc, "text", "") or exc, 140)
                if code == 30001:
                    return await ctx.deny(
                        "this account is already at discord's server limit — leave one first."
                    )
                if "captcha" in detail.lower() or "verify" in detail.lower():
                    return await ctx.deny(
                        "discord wants a captcha for new servers on this account — "
                        "create one by hand once, then retry, or use `--here` to rebuild the server you are in."
                    )
                return await ctx.deny(f"discord refused the create (`{code or 'http'}`): {detail}")
            except Exception as exc:  # noqa: BLE001
                return await ctx.deny(f"could not create the server: {clip(exc, 140)}")

            status = await ctx.send(
                f"-# building **{clip(getattr(created, 'name', name), 60)}** — preparing…"
            )
            target, seeded = await self._settle(created)
            keep = None
            failures = []

        await self._progress(status, "-# building — server settings…")
        copied_settings = await self._settings(origin, target)

        default_role = getattr(target, "default_role", None)
        if default_role is not None:
            try:
                await default_role.edit(permissions=origin.default_role.permissions)
            except Exception as exc:  # noqa: BLE001
                print(f"[CLONE] @everyone permissions failed: {exc}")

        if in_place:
            cleared = await self._wipe_channels(target, keep)
        else:
            cleared = await self._clear(target, seeded)
        await self._progress(status, f"-# building — roles… (#{cleared} items removed)")

        # Discord drops every new role at the bottom of the hierarchy, so the
        # highest role has to go in first for the stack to come out the right
        # way up. Positions are then asserted in one bulk call.
        existing_roles = self._role_index(target) if in_place else {}
        role_map = {}
        made_roles = []
        reused_roles = 0
        created_roles = 0
        for role in sorted(roles, key=lambda item: item.position, reverse=True):
            try:
                reused = existing_roles.pop(role.name.casefold(), None)
                if reused is not None:
                    made_role = await reused.edit(
                        name=clip(role.name, 95),
                        permissions=role.permissions,
                        colour=role.colour,
                        hoist=role.hoist,
                        mentionable=role.mentionable,
                    ) or reused
                    reused_roles += 1
                else:
                    made_role = await target.create_role(
                        name=clip(role.name, 95),
                        permissions=role.permissions,
                        colour=role.colour,
                        hoist=role.hoist,
                        mentionable=role.mentionable,
                    )
                    created_roles += 1
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

        pruned = 0
        if in_place and prune:
            for leftover_name, leftover in list(existing_roles.items()):
                try:
                    await leftover.delete()
                    pruned += 1
                    existing_roles.pop(leftover_name, None)
                except Exception as exc:  # noqa: BLE001
                    print(f"[CLONE] pruning role {leftover_name!r} failed: {exc}")
        extra_kept = len(existing_roles)

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
        keep_used = False
        for channel in sorted(channels, key=lambda item: item.position)[:MAX_CHANNELS]:
            category = category_map.get(getattr(channel, "category_id", None))
            overwrites = self._overwrites(channel, role_map, target)
            label = clip(getattr(channel, "name", "channel"), 95)
            kind = getattr(channel, "type", discord.ChannelType.text)

            # The in-place channel the command ran in is repainted instead of
            # being deleted and recreated, so the status message survives and
            # the source channel keeps its slot.
            if (
                keep is not None
                and not keep_used
                and kind in (discord.ChannelType.text, discord.ChannelType.news)
                and str(getattr(keep, "name", "")).casefold() == str(label).casefold()
            ):
                try:
                    placed = await keep.edit(
                        name=label,
                        topic=clip(getattr(channel, "topic", ""), 1000) or None,
                        slowmode_delay=int(getattr(channel, "slowmode_delay", 0) or 0),
                        nsfw=bool(getattr(channel, "nsfw", False)),
                        overwrites=overwrites,
                        category=category,
                        position=channel.position,
                    )
                    made += 1
                    keep_used = True
                    channel_map[channel.id] = placed or keep
                    continue
                except Exception as exc:  # noqa: BLE001 - fall back to a fresh channel
                    print(f"[CLONE] reusing {label!r} failed: {exc}")

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
            present = {
                str(getattr(emoji, "name", "")).casefold()
                for emoji in (getattr(target, "emojis", []) or [])
            }
            for emoji in emojis[: max(0, slots)]:
                label = str(getattr(emoji, "name", ""))
                if label.casefold() in present:
                    continue
                try:
                    await target.create_custom_emoji(name=label, image=await emoji.read())
                    copied_emojis += 1
                    present.add(label.casefold())
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"emoji {clip(label, 30)}")
                    print(f"[CLONE] emoji {label!r} failed: {exc}")

        invite_link = ""
        if not in_place:
            try:
                await target.fetch_channels()
                for channel in target.text_channels:
                    invite_link = (await channel.create_invite(max_age=0, max_uses=0)).url
                    break
            except Exception:  # noqa: BLE001 - an invite is a nicety, not the point
                invite_link = ""

        if in_place:
            summary = [
                f"### clone done — rebuilt {clip(target.name, 50)} in place",
                f"roles **{reused_roles} matched** · **{created_roles}** new · "
                f"categories **{len(category_map)}** · channels **{made}**"
                + (f" · emojis **{copied_emojis}**" if copy_emojis else ""),
                f"-# id `{target.id}` · settings **{copied_settings}** · messages are never copied",
            ]
            if keep is not None and not keep_used:
                summary.append(
                    f"-# kept **#{clip(getattr(keep, 'name', '?'), 40)}** because the command ran there"
                )
            if pruned or extra_kept:
                summary.append(
                    f"-# pruned **{pruned}** roles · kept **{extra_kept}** extra roles"
                    + ("" if prune else " (`--prune` removes them)")
                )
        else:
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
        elif not in_place:
            summary.append("-# no invite could be made; you are the owner, so open it from your server list")
        await self._progress(status, "\n".join(summary))
