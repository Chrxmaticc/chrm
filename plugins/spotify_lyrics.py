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

    @commands.Cog.listener()
    async def on_presence_update(self, before, after):
        # Only care about OUR OWN status
        if after.id != self.bot.user.id:
            return

        spotify_activity = None
        for activity in after.activities:
            if isinstance(activity, discord.Spotify):
                spotify_activity = activity
                break

        # If we are playing spotify and the track changed
        if spotify_activity and spotify_activity.track_id != self.current_track_id:
            self.current_track_id = spotify_activity.track_id
            print(f"[spotify] detected: {spotify_activity.title} by {spotify_activity.artist}")
            
            if self.lyric_task and not self.lyric_task.done():
                self.lyric_task.cancel()
                
            self.lyric_task = self.bot.loop.create_task(
                self.sync_lyrics(spotify_activity.title, spotify_activity.artist, spotify_activity.start)
            )
            
        # If we stopped playing spotify entirely
        elif not spotify_activity and self.current_track_id:
            self.current_track_id = None
            if self.lyric_task and not self.lyric_task.done():
                self.lyric_task.cancel()
            self.bot.locked_presence = False

    async def sync_lyrics(self, title, artist, start_time):
        query = f"{title} {artist}"
        synced = None
        
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
        except Exception:
            pass

        if not synced:
            try:
                synced = await asyncio.to_thread(syncedlyrics.search, query)
            except Exception:
                pass

        if not synced:
            return

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

        self.bot.locked_presence = True
        try:
            now = discord.utils.utcnow()
            start_timestamp = start_time.timestamp()
            current_timestamp = now.timestamp()
            playback_offset = current_timestamp - start_timestamp
            
            for time_sec, text in lines:
                if time_sec < playback_offset:
                    continue
                    
                wait_time = time_sec - playback_offset
                actual_wait = max(wait_time, 1.2) # faster minimum wait
                await asyncio.sleep(actual_wait)
                
                await self.bot.change_presence(
                    activity=discord.CustomActivity(name=text[:120])
                )
                playback_offset += actual_wait

            await asyncio.sleep(5)
            self.bot.locked_presence = False
        except asyncio.CancelledError:
            self.bot.locked_presence = False

async def setup(bot):
    await bot.add_cog(SpotifyLyrics(bot))
