"""The HTTP half of the friends cog: everything that talks to Discord.

User accounts get relationship endpoints the bot API does not expose, so these
calls go through ``bot.http`` with the same ``Route``s Discord's own client uses.
``discord.py-self`` wraps sending/removing a request and blocking, but not
ignores, friend nicknames or DM mutes -- those are here.

A DM mute is worth calling out: it is not a channel edit. It is a channel
*override* in the account's private-channel settings, i.e.
``PATCH /users/@me/guilds/@me/settings`` with ``channel_overrides`` -- a
``guild_id`` of ``@me`` means "private channels".
"""
from __future__ import annotations

import discord
from discord.enums import RelationshipAction
from discord.http import Route

#: relationship types, as integers in the API payloads
FRIEND = 1
BLOCKED = 2
INCOMING = 3
OUTGOING = 4

#: how many names a list command prints before summarising
LIST_LIMIT = 15

BASE = "/users/@me/relationships"


def node(entry: dict) -> dict:
    """The partial user inside a relationship payload."""
    user = entry.get("user")
    return user if isinstance(user, dict) else {}


def name(entry: dict) -> str:
    """``global_name`` first, then username, then the id -- never empty."""
    user = node(entry)
    return user.get("global_name") or user.get("username") or str(entry.get("id", "?"))


def user_name(user) -> str:
    return (
        getattr(user, "display_name", None)
        or getattr(user, "global_name", None)
        or getattr(user, "name", None)
        or str(getattr(user, "id", "them"))
    )


def listing(entries) -> str:
    """One line of names, bounded so a 1000-friend account cannot blow the limit."""
    shown = [f"`{name(entry)[:24]}`" for entry in entries[:LIST_LIMIT]]
    line = " ".join(shown)
    if len(entries) > LIST_LIMIT:
        line += f" … +{len(entries) - LIST_LIMIT} more"
    return line


async def relationships(bot):
    """Raw relationship rows -- the objects drop ``user_ignored`` and nicknames."""
    data = await bot.http.request(Route("GET", BASE))
    return data if isinstance(data, list) else []


async def resolve(bot, ctx, raw: str = ""):
    """Mention, then id, then nothing. Usernames are handled by ``.friendadd``."""
    mentions = getattr(getattr(ctx, "message", None), "mentions", None) or []
    if mentions:
        return mentions[0]

    token = (raw or "").strip()
    if token.startswith("<@") and token.endswith(">"):
        token = token.strip("<@!>")
    token = token.lstrip("@").strip()
    if not token.isdigit():
        return None

    user_id = int(token)
    user = bot.get_user(user_id)
    if user is not None:
        return user
    try:
        return await bot.fetch_user(user_id)
    except discord.HTTPException:
        return None


async def fail(ctx, exc: Exception):
    """One sentence, Discord's own reason when there is one."""
    if isinstance(exc, discord.HTTPException):
        detail = (getattr(exc, "text", None) or str(exc)).strip()
        return await ctx.deny(f"discord said no: {detail} ({exc.status})")
    return await ctx.deny(f"that failed: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------- requests
async def send_request(bot, user_id: int) -> None:
    await bot.http.add_relationship(int(user_id), action=RelationshipAction.send_friend_request)


async def send_request_by_name(bot, username: str, discriminator: str = "0") -> None:
    """Old-style ``name#1234`` (and plain usernames, where the discriminator is 0)."""
    await bot.send_friend_request(username, discriminator or "0")


async def accept_request(bot, user_id: int) -> None:
    await bot.http.request(
        Route("PUT", "/users/@me/relationships/{user_id}", user_id=int(user_id)),
        json={"type": FRIEND, "confirm_stranger_request": True},
    )


async def deny_request(bot, user_id: int) -> None:
    await bot.http.remove_relationship(int(user_id), action=RelationshipAction.deny_request)


# ---------------------------------------------------------------- edit
async def unfriend(bot, user_id: int) -> None:
    await bot.http.remove_relationship(int(user_id), action=RelationshipAction.unfriend)


async def unblock(bot, user_id: int) -> None:
    await bot.http.remove_relationship(int(user_id), action=RelationshipAction.unblock)


async def drop(bot, user_id: int) -> None:
    """Plain DELETE -- used by ``.massunfriend``, which does not need a context."""
    await bot.http.request(
        Route("DELETE", "/users/@me/relationships/{user_id}", user_id=int(user_id))
    )


async def set_nickname(bot, user_id: int, nickname) -> None:
    await bot.http.edit_relationship(int(user_id), nickname=nickname)


async def ignore(bot, user_id: int, on: bool = True) -> None:
    await bot.http.request(
        Route(
            "PUT" if on else "DELETE",
            "/users/@me/relationships/{user_id}/ignore",
            user_id=int(user_id),
        )
    )


# ---------------------------------------------------------------- dms
async def dm_channel_id(bot, user) -> int:
    """Existing DM channel id, or open one so it can be muted."""
    channel = getattr(user, "dm_channel", None)
    if channel is not None:
        return int(channel.id)
    payload = await bot.http.start_private_message(int(user.id))
    return int(payload["id"])


async def set_muted(bot, channel_id: int, muted: bool) -> None:
    """Mute/unmute a private channel through the account's DM notifications."""
    await bot.http.request(
        Route("PATCH", "/users/@me/guilds/@me/settings"),
        json={
            "channel_overrides": {
                str(channel_id): {"muted": muted, "mute_config": None}
            }
        },
    )
