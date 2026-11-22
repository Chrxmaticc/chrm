"""Lyrics for whatever the account is actually playing on Spotify.

``on_presence_update`` sees Discord's own Spotify activity and rebuilds it line by
line with the current lyric in the artist slot. The title, the cover and -- most
importantly -- the original start/end pair are reused, so the progress bar keeps
the real playback position instead of restarting at every line. Older versions
replaced the presence with a ``CustomActivity``, which is why the card and its bar
disappeared the moment lyrics kicked in.

Nothing here touches a presence unless a Spotify activity is what is showing, so
``.rpc``/``.fakeplay``/``.customstatus`` are never stolen.
"""
import discord
from discord.ext import commands

from plugins.lyrics import fetch_lyrics, parse_lines
from plugins.spotify_spoof import Track, run_lyric_presence


class SpotifyLyrics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lyric_task = None
        self.current_track_id = None

    def cog_unload(self):
        if self.lyric_task and not self.lyric_task.done():
            self.lyric_task.cancel()

    @commands.Cog.listener()
    async def on_presence_update(self, before, after):
        # Only care about OUR OWN status
        if after.id != self.bot.user.id:
            return

        spotify_activity = next(
            (activity for activity in after.activities if isinstance(activity, discord.Spotify)),
            None,
        )

        # A new track (or the first one) starts a sync. Our own lyric writes keep the
        # same track id, so they do not re-trigger this.
        if spotify_activity and spotify_activity.track_id != self.current_track_id:
            self.current_track_id = spotify_activity.track_id
            print(f"[spotify-lyrics] detected: {spotify_activity.title} by {spotify_activity.artist}")

            if self.lyric_task and not self.lyric_task.done():
                self.lyric_task.cancel()

            self.lyric_task = self.bot.loop.create_task(self.sync_lyrics(spotify_activity))

        elif not spotify_activity and self.current_track_id:
            self.current_track_id = None
            if self.lyric_task and not self.lyric_task.done():
                self.lyric_task.cancel()
            self.bot.locked_presence = False

    async def sync_lyrics(self, activity):
        query = f"{activity.title} {activity.artist}".strip()
        synced, _, _ = await fetch_lyrics(query)
        lines = parse_lines(synced)
        if not lines:
            print(f"[spotify-lyrics] no synced lyrics for {query!r}")
            return

        # Reuse the live activity's own metadata so the rebuilt card is identical.
        track = Track(
            title=activity.title,
            artists=activity.artists,
            album=activity.album,
            duration_ms=int(activity.duration.total_seconds() * 1000),
            track_id=activity.track_id,
            cover_url=activity.album_cover_url or None,
        )
        print(f"[spotify-lyrics] {len(lines)} lines for {track.title!r}")
        await run_lyric_presence(self.bot, track, activity.start, lines)


async def setup(bot):
    await bot.add_cog(SpotifyLyrics(bot))
