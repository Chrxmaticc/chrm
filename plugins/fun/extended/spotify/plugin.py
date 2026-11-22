"""Spotify presence that looks like the real thing: album art, progress bar, Listen Along.

The old version built a generic ``Activity(name="Spotify")`` and hashed an
*iTunes* artwork URL into ``spotify:image:<hash>``. Spotify's CDN only serves its
own hashes, so the cover came back blank, and without ``sync_id``/``flags``
Discord rendered the song as a plain "listening to" line with no seek bar.

``discord.py-self`` 2.1 ships a user-constructible :class:`discord.Spotify` that
emits exactly the payload the official client sends -- ``flags`` 48 (sync|play),
``sync_id``, start *and* end timestamps (that pair is what draws the bar), the
``spotify:<user_id>`` party and the ``spotify:<hash>`` asset. Building that
instead of a bare Activity is the whole trick.

Track metadata is resolved in this order, so a blocked/failing provider degrades
instead of erroring:

1. Spotify Web API -- app credentials from ``SPOTIFY_CLIENT_ID`` /
   ``SPOTIFY_CLIENT_SECRET`` when set, otherwise an anonymous Web Player token.
   Exact ids, duration and art hash.
2. Deezer (no auth) for title/album/duration, then MusicBrainz (ISRC -> Spotify
   track id) + Spotify oEmbed for the real ``i.scdn.co`` cover hash.
3. Deezer alone: the right cover through Discord's media proxy, no ``sync_id``.
"""
import asyncio
import os
import re
import urllib.parse
from datetime import timedelta

import aiohttp
import discord
from discord.ext import commands

#: Spotify and MusicBrainz both 403 the default aiohttp agent.
from .helpers import UA, TIMEOUT, FALLBACK_MS, SPOTIFY_TRACK_RE, IMAGE_RE, Track, mmss, _get_json, _spotify_token, _spotify_search, _cover_from_track_id, _deezer_search, _spotify_id_from_isrc, resolve


class SpotifySpoofMixin:
    """Commands for this sub-cog; assembled into the package cog."""
    def cog_unload_spotify(self):
        self._cancel()

    def _cancel(self):
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        self._track = None

    def _activity(self, track, started):
        """The real payload: flags 48, sync_id, start+end (the bar), spotify: art."""
        duration_ms = track.duration_ms or FALLBACK_MS
        return discord.Spotify(
            title=track.title,
            track_id=track.track_id,
            artists=track.artists or ["unknown"],
            album=track.album,
            album_cover_url=track.cover_url,
            start_time=started,
            duration=timedelta(milliseconds=duration_ms),
            party_owner_id=self.bot.user_id,
        )

    def _owns_presence(self, track):
        """True while the live presence is still the Spotify activity we set."""
        for activity in self.bot.activities:
            if isinstance(activity, discord.Spotify):
                return (activity.sync_id or activity.details) == (track.track_id or track.title)
        return False

    async def _keep_playing(self, track):
        """Re-anchor the timestamps when the song ends so the bar keeps moving.

        Any other presence command (``.rpc``, ``.clearstatus``, ``.fakeplay``...)
        replaces what sits in ``bot.activities``, so the loop checks ownership
        before re-sending instead of stealing the presence back when the track
        ends.
        """
        while True:
            await asyncio.sleep(max(track.duration_ms / 1000, 30))
            if self._track is not track or not self._owns_presence(track):
                if self._track is track:
                    self._track = None
                return
            try:
                await self.bot.change_presence(activity=self._activity(track, discord.utils.utcnow()))
            except Exception as e:
                print(f"[SPOTIFY] keepalive failed: {e}")
                return

    @commands.command(name="spotify")
    async def spotify(self, ctx, *, query: str):
        """fakes listening to spotify, with album art and a progress bar. usage: .spotify song - artist"""
        error = self.bot.config.get_emoji("error")
        success = self.bot.config.get_emoji("success")
        loading = self.bot.config.get_emoji("loading")

        if " - " not in query:
            return await ctx.send(f"{error} format: `.spotify song - artist`")
        song, artist = (part.strip() for part in query.split(" - ", 1))
        search = f"{song} {artist}"

        msg = await ctx.send(f"{loading} looking up `{song}`...")

        try:
            async with aiohttp.ClientSession(headers={"User-Agent": UA}) as session:
                track = await resolve(session, search)
        except Exception as e:
            return await msg.edit(content=f"{error} lookup failed: `{e}`")

        if track is None or not track.title:
            return await msg.edit(
                content=f"{error} couldn't find `{query}`. try `.spotify song - artist`."
            )

        self._cancel()
        self._track = track
        self.bot.locked_presence = True
        await self.bot.change_presence(activity=self._activity(track, discord.utils.utcnow()))
        self._task = self.bot.loop.create_task(self._keep_playing(track))

        cover = "no art"
        if track.cover_url:
            cover = "spotify art" if "i.scdn.co" in track.cover_url else "proxied art"
        notes = [f"`{mmss(track.duration_ms)}`", "progress bar", cover]
        if not track.track_id:
            notes.append("no listen along")

        await msg.edit(content=(
            f"{success} listening to **{track.title}** — {', '.join(track.artists) or artist}\n"
            f"*{track.album or 'single'}* · " + " · ".join(notes)
        ))

    @commands.command(name="stopspotify")
    async def stopspotify(self, ctx):
        """stops the spotify spoof"""
        self._cancel()
        self.bot.locked_presence = False
        await self.bot.change_presence(activity=None)
        await ctx.send(f"{self.bot.config.get_emoji('success')} stopped spotify spoof.")
