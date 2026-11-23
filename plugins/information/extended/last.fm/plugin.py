"""``.lastfm`` -- what a Libre.fm account is playing, and what it plays most.

Libre.fm runs GNU FM, which serves Last.fm's 2.0 API, so no key or account
setup is involved here: a username is enough. Read-only -- it never scrobbles.
"""
import aiohttp
import discord
from discord.ext import commands

from .helpers import PERIODS, PERIOD_LABELS, UA, LastFMError, profile, recent, top_artists

#: libre.fm's error codes for "no such resource"; that is a bad username here.
MISSING_USER_CODES = {"6", "7"}


def _escape(value):
    return discord.utils.escape_markdown(value or "")


def _display(stats, user):
    return (stats or {}).get("name") or user


def _render_track(stats, tracks, user):
    display = _escape(_display(stats, user))
    if not tracks or not tracks[0]["name"]:
        return f"-# **{display}** has no scrobbles on libre.fm yet."

    track = tracks[0]
    if track["now"]:
        head = f"**{display}** is listening to"
    elif track["played"]:
        head = f"**{display}** last played <t:{track['played']}:R>"
    else:
        head = f"**{display}** last played"

    body = f"{head}\n**{_escape(track['name'])}** — {_escape(track['artist']) or 'unknown artist'}"
    if track["album"]:
        body += f"\n*{_escape(track['album'])}*"

    bits = []
    if stats and stats.get("plays"):
        bits.append(f"{stats['plays']:,} scrobbles")
    if track["url"]:
        bits.append(f"[track]({track['url']})")
    if stats and stats.get("url"):
        bits.append(f"[profile]({stats['url']})")
    if bits:
        body += "\n-# " + " · ".join(bits)
    return body


def _render_top(stats, artists, user, period):
    display = _escape(_display(stats, user))
    label = PERIOD_LABELS.get(period, period)
    lines = [f"**{display}'s top artists** · {label}"]
    if not artists:
        lines.append(f"no plays in the last {label}.")
    for rank, artist in enumerate(artists, start=1):
        name = _escape(artist["name"])
        if artist["url"]:
            name = f"[{name}]({artist['url']})"
        lines.append(f"`{rank:02d}` {name} · {artist['plays']:,} plays")
    if stats and stats.get("url"):
        lines.append(f"-# [profile]({stats['url']})")
    return "\n".join(lines)


def parse_query(query):
    """``[top] <user> [period]`` -> ``(top, user, period, problem)``."""
    parts = query.split()
    top = bool(parts) and parts[0].lower() == "top"
    if top:
        parts = parts[1:]

    if not parts:
        usage = "usage: `.lastfm <user>` or `.lastfm top <user> [period]`"
        return top, "", "overall", usage

    user = parts[0].lstrip("@")
    period = "overall"
    if len(parts) > 1:
        raw = parts[1].lower()
        if raw not in PERIODS:
            ranges = ", ".join(PERIOD_LABELS)
            return top, user, period, f"unknown range `{raw}`. try one of: {ranges}."
        period = PERIODS[raw]
    return top, user, period, None


class LastFMMixin:
    """Commands for this sub-cog; assembled into the package cog."""

    async def _lastfm_profile(self, session, user):
        """Totals are a bonus: a throttled second call must not lose the track."""
        try:
            return await profile(session, user)
        except LastFMError:
            return None

    @commands.command(name="lastfm")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def lastfm(self, ctx, *, query: str = ""):
        """libre.fm now playing / last scrobble / top artists. usage: .lastfm <user> | .lastfm top <user> [period]"""
        error = self.bot.config.get_emoji("error")
        loading = self.bot.config.get_emoji("loading")

        top, user, period, problem = parse_query(query)
        if problem:
            return await ctx.send(f"{error} {problem}")

        msg = await ctx.send(f"{loading} checking libre.fm for `{user}`...")
        try:
            async with aiohttp.ClientSession(headers={"User-Agent": UA}) as session:
                # The real lookup goes first: a bad username fails before the
                # optional totals call spends another request on Cloudflare.
                if top:
                    artists = await top_artists(session, user, period)
                    text = _render_top(await self._lastfm_profile(session, user), artists, user, period)
                else:
                    tracks = await recent(session, user)
                    text = _render_track(await self._lastfm_profile(session, user), tracks, user)
        except LastFMError as exc:
            reason = "no such user on libre.fm." if str(exc.code) in MISSING_USER_CODES else str(exc)
            return await msg.edit(content=f"{error} {reason}")

        await msg.edit(content=text)
