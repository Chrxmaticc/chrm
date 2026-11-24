"""Server lookups answered by Discord itself, not by a third-party API.

Members, roles, permission overwrites, audit entries, invites and boosts are all
already in the gateway cache, so none of this can be refused the way Pinterest
refuses a datacenter IP. Every command is read-only except ``.clean``, which is
the filtered sibling of ``.purge``: ``.purge`` stays the "delete my own messages"
one-liner, and ``.clean`` adds bots, links, images, embeds and one member.

Output is plain text with ``###`` headings, capped so a 300-channel server does
not paste a 300-line wall into the chat.
"""
from __future__ import annotations

import discord
from discord.ext import commands

#: hard cap on one ``.clean`` run
MAX_PURGE = 100

#: hard cap on the channel tree, headers and ellipses included
MAX_LINES = 40

#: the permissions worth printing in ``.perms`` -- the rest is noise
KEY_PERMISSIONS = (
    ("administrator", "administrator"),
    ("manage_guild", "manage server"),
    ("manage_channels", "manage channels"),
    ("manage_roles", "manage roles"),
    ("manage_messages", "manage messages"),
    ("kick_members", "kick members"),
    ("ban_members", "ban members"),
    ("view_audit_log", "view audit log"),
    ("mention_everyone", "mention everyone"),
    ("embed_links", "embed links"),
    ("attach_files", "attach files"),
    ("read_message_history", "read history"),
    ("send_messages", "send messages"),
    ("view_channel", "view channels"),
)

#: one-character marker per channel kind, so the tree stays one line each
CHANNEL_MARKS = {
    discord.ChannelType.text: "#",
    discord.ChannelType.news: "#",
    discord.ChannelType.voice: "v",
    discord.ChannelType.stage_voice: "s",
    discord.ChannelType.forum: "f",
    discord.ChannelType.media: "m",
}


def clip(text, limit: int = 120) -> str:
    """One line, collapsed whitespace, never longer than ``limit``."""
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def stamp(moment) -> str:
    """``3 days ago`` plus the short date, for anything with a timestamp."""
    if moment is None:
        return "unknown"
    return f"{discord.utils.format_dt(moment, 'R')} · {discord.utils.format_dt(moment, 'd')}"


class NativeMixin:
    """Commands for this sub-cog; assembled into the package cog."""

    # ---------------------------------------------------------------- helpers
    async def _member(self, ctx, query: str = ""):
        """``(member, error)``; no argument means whoever ran the command."""
        if ctx.guild is None:
            return None, "this one needs a server."
        query = (query or "").strip()
        if not query:
            if isinstance(ctx.author, discord.Member):
                return ctx.author, None
            me = getattr(ctx.guild, "me", None)
            if me is None:
                return None, "discord has not cached your membership yet."
            return me, None
        try:
            return await commands.MemberConverter().convert(ctx, query), None
        except commands.BadArgument:
            pass
        getter = getattr(ctx.guild, "get_member_named", None)
        found = getter(query) if callable(getter) else None
        if found is not None:
            return found, None
        return None, f"no member called **{clip(query, 40)}** in this server."

    def _target_channel(self, ctx, query: str):
        """A channel from ``#name``, an id or a mention; ``None`` when it is neither."""
        query = (query or "").strip()
        if not query or ctx.guild is None:
            return None
        token = query.strip("<#>")
        getter = getattr(ctx.guild, "get_channel", None)
        if token.isdigit() and callable(getter):
            found = getter(int(token))
            if found is not None:
                return found
        if query.startswith("#"):
            name = query.lstrip("#")
            for channel in list(getattr(ctx.guild, "channels", []) or []):
                if getattr(channel, "name", "") == name:
                    return channel
        return None

    async def _send_perms(self, ctx, perms, subject: str):
        lines = [f"### perms {subject}"]
        for attr, label in KEY_PERMISSIONS:
            lines.append(f"{'✅' if bool(getattr(perms, attr, False)) else '❌'} {label}")
        await ctx.send("\n".join(lines))

    # ------------------------------------------------------------- commands
    @commands.command(name="joined", aliases=["jointime", "firstseen"])
    async def joined(self, ctx, *, query: str = ""):
        """when someone joined. usage: .joined @user"""
        member, error = await self._member(ctx, query)
        if error:
            return await ctx.deny(error)
        lines = [f"### {clip(member.display_name, 40)}", f"-# id `{member.id}`"]
        joined_at = getattr(member, "joined_at", None)
        created = getattr(member, "created_at", None)
        lines.append(f"joined {stamp(joined_at)}")
        lines.append(f"account created {stamp(created)}")
        if joined_at is not None and created is not None:
            here = (discord.utils.utcnow() - joined_at).days
            age = (discord.utils.utcnow() - created).days
            lines.append(f"**{here}** days in this server · account is **{age}** days old")
        premium_since = getattr(member, "premium_since", None)
        if premium_since is not None:
            lines.append(f"boosting since {stamp(premium_since)}")
        top = getattr(member, "top_role", None)
        if top is not None and not top.is_default():
            lines.append(f"top role {top.mention} · position **{top.position}**")
        nick = getattr(member, "nick", None)
        if nick:
            lines.append(f"nickname **{clip(nick, 40)}**")
        await ctx.send("\n".join(lines))

    @commands.command(name="roles", aliases=["rolelist"])
    async def roles(self, ctx, *, query: str = ""):
        """roles a member has, highest first. usage: .roles @user"""
        member, error = await self._member(ctx, query)
        if error:
            return await ctx.deny(error)
        held = [role for role in reversed(list(getattr(member, "roles", []) or [])) if not role.is_default()]
        lines = [f"### roles — {clip(member.display_name, 40)}", f"**{len(held)}** roles"]
        if not held:
            lines.append("-# only @everyone")
        for role in held[:30]:
            colour = getattr(getattr(role, "colour", None), "value", 0) or 0
            bits = [role.mention, f"`#{colour:06x}`" if colour else "`no colour`"]
            if getattr(role, "hoist", False):
                bits.append("hoisted")
            if getattr(role, "managed", False):
                bits.append("managed")
            lines.append(" · ".join(bits))
        if len(held) > 30:
            lines.append(f"-# and {len(held) - 30} more")
        await ctx.send("\n".join(lines))

    @commands.command(name="perms", aliases=["permissions"])
    async def perms(self, ctx, *, query: str = ""):
        """what the account, or one member, may do. usage: .perms #channel"""
        if ctx.guild is None:
            return await ctx.deny("this one needs a server.")
        me = getattr(ctx.guild, "me", None)
        channel = self._target_channel(ctx, query)
        if channel is not None:
            if me is None:
                return await ctx.deny("discord has not cached your membership yet.")
            try:
                perms = channel.permissions_for(me)
            except Exception as exc:  # noqa: BLE001 - a dead channel object
                return await ctx.deny(f"could not read permissions there: {exc}")
            return await self._send_perms(ctx, perms, f"in #{getattr(channel, 'name', 'channel')}")
        if query.strip():
            member, error = await self._member(ctx, query)
            if error:
                return await ctx.deny(error)
            return await self._send_perms(
                ctx, member.guild_permissions, f"for {clip(member.display_name, 40)}"
            )
        if me is None:
            return await ctx.deny("discord has not cached your membership yet.")
        await self._send_perms(ctx, me.guild_permissions, f"for {clip(me.display_name, 40)}")

    @commands.command(name="pins", aliases=["pinlist"])
    async def pins(self, ctx, *, query: str = ""):
        """pinned messages. usage: .pins #channel"""
        channel = self._target_channel(ctx, query) or ctx.channel
        name = getattr(channel, "name", "channel")
        try:
            pinned = await channel.pins()
        except discord.Forbidden:
            return await ctx.deny("i cannot read this channel's pins.")
        except Exception as exc:  # noqa: BLE001 - a dead channel must not traceback
            return await ctx.deny(f"could not read pins: {exc}")
        if not pinned:
            return await ctx.warn(f"nothing is pinned in **#{name}**.")
        lines = [f"### pins — #{name}", f"**{len(pinned)}** pinned"]
        for index, message in enumerate(pinned[:8], start=1):
            body = clip(message.content, 70)
            if not body:
                body = f"({len(message.attachments)} attachment)" if message.attachments else "(no text)"
            author = getattr(getattr(message, "author", None), "display_name", "unknown")
            lines.append(f"`{index}` **{clip(author, 24)}** — {body}")
            lines.append(f"-# [jump]({message.jump_url}) · {stamp(message.created_at)}")
        if len(pinned) > 8:
            lines.append(f"-# and {len(pinned) - 8} more")
        await ctx.send("\n".join(lines))

    @commands.command(name="audit", aliases=["auditlog"])
    async def audit(self, ctx, count: int = 5):
        """recent audit log entries. usage: .audit 10"""
        if ctx.guild is None:
            return await ctx.deny("this one needs a server.")
        count = max(1, min(int(count or 5), 25))
        lines = [f"### audit log — {clip(ctx.guild.name, 40)}"]
        seen = 0
        try:
            async for entry in ctx.guild.audit_logs(limit=count):
                seen += 1
                action = str(getattr(entry.action, "name", entry.action)).replace("_", " ")
                actor = getattr(getattr(entry, "user", None), "display_name", "someone")
                lines.append(f"**{action}** · {clip(actor, 24)} · {stamp(entry.created_at)}")
                reason = getattr(entry, "reason", None)
                if reason:
                    lines.append(f"-# {clip(reason, 100)}")
        except discord.Forbidden:
            return await ctx.deny("i need **view audit log** for that.")
        except Exception as exc:  # noqa: BLE001
            return await ctx.deny(f"could not read the audit log: {exc}")
        if not seen:
            lines.append("-# nothing logged yet")
        await ctx.send("\n".join(lines))

    @commands.command(name="boosters", aliases=["boosts"])
    async def boosters(self, ctx):
        """boost level, count and who is boosting."""
        if ctx.guild is None:
            return await ctx.deny("this one needs a server.")
        tier = int(getattr(ctx.guild, "premium_tier", 0) or 0)
        count = int(getattr(ctx.guild, "premium_subscription_count", 0) or 0)
        lines = [
            f"### boosts — {clip(ctx.guild.name, 40)}",
            f"level **{tier}** · **{count}** boosts",
        ]
        need = {0: 2, 1: 7, 2: 14}.get(tier)
        if need is None:
            lines.append("-# max level reached")
        elif count < need:
            lines.append(f"-# **{need - count}** more for level **{tier + 1}**")
        else:
            lines.append(f"-# level **{tier + 1}** unlocks at **{need}** boosts")
        subscribers = list(getattr(ctx.guild, "premium_subscribers", []) or [])
        for member in subscribers[:15]:
            since = getattr(member, "premium_since", None)
            lines.append(
                f"**{clip(member.display_name, 28)}**" + (f" · {stamp(since)}" if since else "")
            )
        if len(subscribers) > 15:
            lines.append(f"-# and {len(subscribers) - 15} more boosters")
        if not subscribers:
            lines.append("-# no boosters cached — discord sends them with the member list")
        await ctx.send("\n".join(lines))

    @commands.command(name="emojis", aliases=["emotelist"])
    async def emojis(self, ctx):
        """custom emojis and stickers on this server."""
        if ctx.guild is None:
            return await ctx.deny("this one needs a server.")
        all_emojis = list(getattr(ctx.guild, "emojis", []) or [])
        static = [item for item in all_emojis if not getattr(item, "animated", False)]
        animated = [item for item in all_emojis if getattr(item, "animated", False)]
        stickers = list(getattr(ctx.guild, "stickers", []) or [])
        lines = [
            f"### emojis — {clip(ctx.guild.name, 40)}",
            f"**{len(static)}** static · **{len(animated)}** animated · **{len(stickers)}** stickers",
        ]
        for emoji in all_emojis[:30]:
            lines.append(f"`:{emoji.name}:`" + (" · animated" if getattr(emoji, "animated", False) else ""))
        if len(all_emojis) > 30:
            lines.append(f"-# and {len(all_emojis) - 30} more")
        if stickers:
            lines.append("stickers " + ", ".join(clip(item.name, 20) for item in stickers[:10]))
        await ctx.send("\n".join(lines))

    @commands.command(name="channels", aliases=["channellist", "channelree"])
    async def channels(self, ctx):
        """the channel tree, grouped by category."""
        if ctx.guild is None:
            return await ctx.deny("this one needs a server.")
        every = list(getattr(ctx.guild, "channels", []) or [])

        def is_category(channel) -> bool:
            return getattr(channel, "type", None) is discord.ChannelType.category

        categories = sorted(
            [item for item in every if is_category(item)],
            key=lambda item: getattr(item, "position", 0),
        )
        loose = [
            item
            for item in every
            if not is_category(item) and getattr(item, "category_id", None) is None
        ]
        counts = {}
        for channel in every:
            if is_category(channel):
                continue
            key = getattr(getattr(channel, "type", None), "name", "text")
            counts[key] = counts.get(key, 0) + 1
        summary = " · ".join(f"**{value}** {key}" for key, value in sorted(counts.items()))
        lines = [f"### channels — {clip(ctx.guild.name, 40)}", summary or "no channels"]

        def render(channel):
            mark = CHANNEL_MARKS.get(getattr(channel, "type", None), "?")
            extra = ""
            if getattr(channel, "type", None) is discord.ChannelType.voice:
                extra = f" · {getattr(channel, 'user_limit', 0) or '∞'} slots"
            elif getattr(channel, "nsfw", False):
                extra = " · nsfw"
            return f"`{mark}` {clip(getattr(channel, 'name', 'channel'), 40)}{extra}"

        for channel in loose[:10]:
            lines.append(render(channel))
        for category in categories:
            if len(lines) >= MAX_LINES:
                break
            lines.append(f"**{clip(getattr(category, 'name', 'category'), 40)}**")
            children = sorted(
                [item for item in every if getattr(item, "category_id", None) == category.id],
                key=lambda item: getattr(item, "position", 0),
            )
            for channel in children[:12]:
                lines.append(render(channel))
            if len(children) > 12:
                lines.append(f"-# and {len(children) - 12} more")
        if len(lines) > MAX_LINES:
            lines = lines[:MAX_LINES] + ["-# truncated"]
        await ctx.send("\n".join(lines))

    @commands.command(name="invites", aliases=["invitelist"])
    async def invites(self, ctx):
        """live invites, their uses and who made them."""
        if ctx.guild is None:
            return await ctx.deny("this one needs a server.")
        try:
            invites = await ctx.guild.invites()
        except discord.Forbidden:
            return await ctx.deny("i need **manage server** to read invites.")
        except Exception as exc:  # noqa: BLE001
            return await ctx.deny(f"could not read invites: {exc}")
        if not invites:
            return await ctx.warn("no live invites.")
        lines = [f"### invites — {clip(ctx.guild.name, 40)}", f"**{len(invites)}** live"]
        for invite in invites[:15]:
            inviter = getattr(invite, "inviter", None)
            who = clip(getattr(inviter, "display_name", "unknown"), 24)
            max_age = int(getattr(invite, "max_age", 0) or 0)
            expiry = "never" if max_age == 0 else f"{max_age // 60}m"
            max_uses = int(getattr(invite, "max_uses", 0) or 0)
            uses = f"{getattr(invite, 'uses', 0)}/{max_uses or '∞'}"
            lines.append(f"`{invite.code}` · **{uses}** uses · {who} · expires {expiry}")
        if len(invites) > 15:
            lines.append(f"-# and {len(invites) - 15} more")
        await ctx.send("\n".join(lines))

    @commands.command(name="serverbanner", aliases=["sbanner", "guildbanner"])
    async def serverbanner(self, ctx):
        """icon, banner, splash and discovery art links."""
        if ctx.guild is None:
            return await ctx.deny("this one needs a server.")
        lines = [f"### art — {clip(ctx.guild.name, 40)}"]
        assets = (
            ("icon", getattr(ctx.guild, "icon", None)),
            ("banner", getattr(ctx.guild, "banner", None)),
            ("splash", getattr(ctx.guild, "splash", None)),
            ("discovery", getattr(ctx.guild, "discovery_splash", None)),
        )
        found = 0
        for label, asset in assets:
            if asset is None:
                continue
            found += 1
            try:
                link = asset.with_size(1024).url
            except Exception:  # noqa: BLE001 - some assets are already urls
                link = getattr(asset, "url", "")
            lines.append(f"**{label}** [open]({link})")
        if not found:
            lines.append("-# this server has no art set")
        await ctx.send("\n".join(lines))

    @commands.command(name="clean", aliases=["purgefilter"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def clean(self, ctx, amount: int = 50, *, filters: str = ""):
        """delete by filter: bots, links, images, embeds, @user, all. usage: .clean 40 bots"""
        if amount < 1:
            return await ctx.deny("give me a number above zero.")
        if amount > MAX_PURGE:
            return await ctx.warn(f"capped at **{MAX_PURGE}** messages per run.")
        tokens = (filters or "").lower().split()
        member = None
        if (filters or "").strip().startswith(("<@", "@")):
            try:
                member = await commands.MemberConverter().convert(ctx, (filters or "").strip().split()[0])
            except commands.BadArgument:
                member = None

        def keep(message) -> bool:
            if getattr(message, "pinned", False):
                return False
            if "all" in tokens:
                return True
            if "bots" in tokens:
                return bool(getattr(message.author, "bot", False))
            if member is not None:
                return message.author.id == member.id
            body = message.content or ""
            if "links" in tokens:
                return "http://" in body or "https://" in body
            if "images" in tokens:
                attachments = list(getattr(message, "attachments", []) or [])
                if any(str(getattr(item, "content_type", "") or "").startswith("image/") for item in attachments):
                    return True
                return bool(getattr(message, "embeds", None))
            if "embeds" in tokens:
                return bool(getattr(message, "embeds", None))
            return message.author.id == self.bot.user.id

        try:
            deleted = await ctx.channel.purge(limit=amount, check=keep)
        except AttributeError:
            # direct messages have no bulk delete endpoint
            deleted = 0
            async for message in ctx.channel.history(limit=amount):
                if keep(message):
                    try:
                        await message.delete()
                        deleted += 1
                    except Exception:  # noqa: BLE001 - one bad message is not fatal
                        pass
        except discord.Forbidden:
            return await ctx.deny("i need **manage messages** in this channel.")
        except Exception as exc:  # noqa: BLE001
            return await ctx.deny(f"could not delete: {exc}")
        await ctx.approve(f"deleted **{len(deleted)}** messages")
