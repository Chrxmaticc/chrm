import discord
from discord.ext import commands
import asyncio
import re
import aiohttp
from urllib.parse import quote
import syncedlyrics

class SpotifyLyrics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lyric_task = None
        self.current_track_id = None
        # Start the background presence watcher
        self.watcher_task = self.bot.loop.create_task(self.watch_presence())

    def cog_unload(self):
        if self.watcher_task:
            self.watcher_task.cancel()
        if self.lyric_task:
            self.lyric_task.cancel()

    async def watch_presence(self):
        """Continuously checks your own status for Spotify activity."""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                # Check our own presence
                member = self.bot.user
                if member and member.activities:
                    for activity in member.activities:
                        # If we find a Spotify activity
                        if isinstance(activity, discord.Spotify):
                            # Check if the track has changed
                            if activity.track_id != self.current_track_id:
                                self.current_track_id = activity.track_id
                                print(f"[spotify] detected track change: {activity.title} by {activity.artist}")
                                
                                # Cancel previous lyrics if they are running
                                if self.lyric_task and not self.lyric_task.done():
                                    self.lyric_task.cancel()
                                    
                                # Start new lyrics sync
                                self.lyric_task = self.bot.loop.create_task(
                                    self.sync_lyrics(activity.title, activity.artist, activity.start)
                                )
                            else:
                                # Same track, do nothing
                                pass
            except Exception as e:
                print(f"[spotify] watcher error: {e}")
            
            await asyncio.sleep(5) # Check every 5 seconds

    async def sync_lyrics(self, title, artist, start_time):
        """Fetches and syncs lyrics for a specific song."""
        query = f"{title} {artist}"
        print(f"[spotify] fetching lyrics for: {query}")
        
        synced = None
        # Try LRCLIB first
        safe_query = quote(query)
        url = f"https://lrclib.net/api/search?q={safe_query}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for result in data:
                            if result.get("syncedLyrics"):
                                synced = result["syncedLyrics"]
                                break
        except Exception as e:
            print(f"[spotify] lrclib error: {e}")

        # Fallback to syncedlyrics
        if not synced:
            try:
                synced = await asyncio.to_thread(syncedlyrics.search, query)
            except Exception as e:
                print(f"[spotify] syncedlyrics error: {e}")

        if not synced:
            print(f"[spotify] no synced lyrics found for {query}")
            return

        # Parse lyrics
        lines = []
        for line in synced.split("\n"):
            match = re.match(r"\[(\d+):(\d+)(?:\.(\d+))?\](.*)", line)
            if match:
                minutes = int(match.group(1))
                seconds = int(match.group(2))
                ms = int(match.group(3)) / 100 if match.group(3) else 0
                text = match.group(4).strip()
                if text:
                    lines.append(((minutes * 60) + seconds + ms, text))

        if not lines:
            return

        # Sync the lyrics to the actual playback start time
        self.bot.locked_presence = True
        try:
            # Wait until the song actually starts (if there's a delay)
            # We use the activity.start timestamp to sync perfectly
            now = discord.utils.utcnow()
            start_timestamp = start_time.timestamp()
            current_timestamp = now.timestamp()
            
            # The song might have been playing for a few seconds already
            playback_offset = current_timestamp - start_timestamp
            
            for time_sec, text in lines:
                # If the line is in the past, skip it (we're already past it)
                if time_sec < playback_offset:
                    continue
                    
                # Calculate how long to wait from now
                wait_time = time_sec - playback_offset
                
                # Wait at least 2 seconds to avoid rate limits
                actual_wait = max(wait_time, 2.0)
                await asyncio.sleep(actual_wait)
                
                await self.bot.change_presence(
                    activity=discord.CustomActivity(name=f"🎵 {text[:120]}")
                )
                
                # Update our offset so we don't drift
                playback_offset += actual_wait

            # Song ended
            await asyncio.sleep(5)
            self.bot.locked_presence = False
            await self.bot.change_presence(activity=discord.CustomActivity(name="chrm on top"))
            
        except asyncio.CancelledError:
            # This happens when a new song starts
            self.bot.locked_presence = False

async def setup(bot):
    await bot.add_cog(SpotifyLyrics(bot))
