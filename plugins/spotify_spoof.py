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
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
TIMEOUT = aiohttp.ClientTimeout(total=12)

#: Fallback length when a provider knows the track but not how long it is.
FALLBACK_MS = 180_000

SPOTIFY_TRACK_RE = re.compile(r"open\.spotify\.com/track/([A-Za-z0-9]{22})")
IMAGE_RE = re.compile(r"/image/([A-Za-z0-9]+)")


class Track:
    """Whatever a provider managed to tell us about a song."""

    __slots__ = ("title", "artists", "album", "duration_ms", "track_id", "cover_url")

    def __init__(self, title, artists, album, duration_ms, track_id=None, cover_url=None):
        self.title = title
        self.artists = [a for a in (artists or []) if a]
        self.album = album
        self.duration_ms = duration_ms or 0
        self.track_id = track_id
        self.cover_url = cover_url

    def __repr__(self):
        return f"<Track {self.title!r} by {self.artists!r} id={self.track_id}>"


def mmss(ms):
    """205000 -> '3:25'."""
    total = int((ms or 0) / 1000)
    return f"{total // 60}:{total % 60:02d}"


async def _get_json(session, url, **kwargs):
    """GET json, or None for any failure. Providers are allowed to be flaky."""
    try:
        async with session.get(url, timeout=TIMEOUT, **kwargs) as resp:
            if resp.status != 200:
                return None
            return await resp.json(content_type=None)
    except Exception:
        return None


# --------------------------------------------------------------------- spotify
async def _spotify_token(session):
    """App credentials if the owner set them, else the anonymous web player token."""
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if client_id and client_secret:
        try:
            async with session.post(
                "https://accounts.spotify.com/api/token",
                data={"grant_type": "client_credentials"},
                auth=aiohttp.BasicAuth(client_id, client_secret),
                timeout=TIMEOUT,
            ) as resp:
                if resp.status == 200:
                    token = (await resp.json(content_type=None)).get("access_token")
                    if token:
                        return token
        except Exception:
            pass

    payload = await _get_json(
        session,
        "https://open.spotify.com/get_access_token",
        params={"reason": "transport", "productType": "web_player"},
        headers={"User-Agent": UA, "Accept": "application/json", "Referer": "https://open.spotify.com/"},
    )
    return (payload or {}).get("accessToken")


async def _spotify_search(session, query):
    """Exact track via the Web API: ids, duration and the real cover hash."""
    token = await _spotify_token(session)
    if not token:
        return None

    data = await _get_json(
        session,
        "https://api.spotify.com/v1/search",
        params={"q": query, "type": "track", "limit": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    items = ((data or {}).get("tracks") or {}).get("items") or []
    if not items:
        return None

    item = items[0]
    album = item.get("album") or {}
    images = album.get("images") or []
    return Track(
        title=item.get("name"),
        artists=[a.get("name") for a in item.get("artists") or []],
        album=album.get("name"),
        duration_ms=item.get("duration_ms"),
        track_id=item.get("id"),
        cover_url=images[0].get("url") if images else None,
    )


async def _cover_from_track_id(session, track_id):
    """Public oEmbed -> https://i.scdn.co/image/<hash> (the only form Spotify art resolves in)."""
    data = await _get_json(
        session,
        "https://open.spotify.com/oembed",
        params={"url": f"https://open.spotify.com/track/{track_id}"},
    )
    match = IMAGE_RE.search((data or {}).get("thumbnail_url") or "")
    return f"https://i.scdn.co/image/{match.group(1)}" if match else None


# ----------------------------------------------------------------------- deezer
async def _deezer_search(session, query):
    """No auth needed; returns the track plus its ISRC so Spotify can be looked up."""
    data = await _get_json(session, "https://api.deezer.com/search", params={"q": query, "limit": 1})
    items = (data or {}).get("data") or []
    if not items:
        return None, None

    item = items[0]
    album = item.get("album") or {}
    track = Track(
        title=item.get("title"),
        artists=[(item.get("artist") or {}).get("name")],
        album=album.get("title"),
        duration_ms=int(item.get("duration") or 0) * 1000,
        cover_url=album.get("cover_xl") or album.get("cover_big"),
    )
    return track, item.get("isrc")


async def _spotify_id_from_isrc(session, isrc):
    """MusicBrainz maps the ISRC to a Spotify track URL; that gives us the id."""
    if not isrc:
        return None, None

    data = await _get_json(
        session,
        f"https://musicbrainz.org/ws/2/isrc/{urllib.parse.quote(isrc)}",
        params={"fmt": "json", "inc": "url-rels"},
        headers={"User-Agent": "chrm/1.0 (https://github.com/Chrxmaticc/chrm)"},
    )
    for recording in (data or {}).get("recordings") or []:
        for relation in recording.get("relations") or []:
            match = SPOTIFY_TRACK_RE.search(((relation.get("url") or {}).get("resource") or ""))
            if match:
                track_id = match.group(1)
                return track_id, await _cover_from_track_id(session, track_id)
    return None, None


async def resolve(session, query):
    """song+artist -> Track, best source first. None when nothing matches."""
    track = await _spotify_search(session, query)
    if track:
        return track

    track, isrc = await _deezer_search(session, query)
    if not track:
        return None

    track_id, cover = await _spotify_id_from_isrc(session, isrc)
    if track_id:
        track.track_id = track_id
    if cover:
        track.cover_url = cover
    return track


class SpotifySpoof(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._task = None
        self._track = None

    def cog_unload(self):
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


async def setup(bot):
    await bot.add_cog(SpotifySpoof(bot))
