import discord
from discord.ext import commands
import aiohttp
import asyncio
import re
from urllib.parse import quote
import syncedlyrics

class Lyrics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lyric_task = None

    @commands.command()
    async def lyrics(self, ctx, *, query):
        """usage: .lyrics angel cry bleood"""
        if self.lyric_task and not self.lyric_task.done():
            self.lyric_task.cancel()
            
        loading = self.bot.config.get_emoji("loading")
        msg = await ctx.send(f"{loading} searching for `{query}`...")

        synced = None
        track_name = query.title()
        artist_name = "unknown"

        # 1. Try LRCLIB API first
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
                                track_name = result.get("trackName", query)
                                artist_name = result.get("artistName", "unknown")
                                break
        except Exception as e:
            print(f"lrclib error: {e}")

        # 2. Fallback to syncedlyrics package if LRCLIB fails
        if not synced:
            print(f"falling back to syncedlyrics for: {query}")
            try:
                # syncedlyrics is a synchronous library, so we run it in a thread
                synced = await asyncio.to_thread(syncedlyrics.search, query)
            except Exception as e:
                print(f"syncedlyrics error: {e}")

        if not synced:
            error = self.bot.config.get_emoji("error")
            return await msg.edit(content=f"{error} no synced lyrics found for `{query}`. try searching just the song name.")

        # 3. Parse the lyrics safely
        lines = []
        for line in synced.split("\n"):
            # Matches [00:12.34] text
            match = re.match(r"\[(\d+):(\d+)(?:\.(\d+))?\](.*)", line)
            if match:
                minutes = int(match.group(1))
                seconds = int(match.group(2))
                ms = int(match.group(3)) / 100 if match.group(3) else 0
                text = match.group(4).strip()
                # Only add if there is actual text (no empty lines)
                if text:
                    lines.append(((minutes * 60) + seconds + ms, text))

        if not lines:
            error = self.bot.config.get_emoji("error")
            return await msg.edit(content=f"{error} found lyrics, but they aren't time-synced.")

        self.bot.locked_presence = True
        success = self.bot.config.get_emoji("success")
        await msg.edit(content=f"{success} syncing **{track_name}** by {artist_name}...")
        
        self.lyric_task = asyncio.create_task(self._run_live_lyrics(lines))

    async def _run_live_lyrics(self, lines):
        try:
            previous_time = 0
            for time_sec, text in lines:
                wait_time = time_sec - previous_time
                
                # DISCORD RATE LIMIT FIX: 
                # If the next line is less than 3 seconds away, just wait 3 seconds.
                # We also subtract 0.5 seconds to make it feel snappy.
                actual_wait = max((wait_time - 0.5), 3.0) 
                
                await asyncio.sleep(actual_wait)
                
                await self.bot.change_presence(activity=discord.CustomActivity(name=f"🎵 {text[:120]}"))
                previous_time = time_sec
                
            await asyncio.sleep(5)
            self.bot.locked_presence = False
            await self.bot.change_presence(activity=discord.CustomActivity(name="chrm on top"))
        except asyncio.CancelledError:
            self.bot.locked_presence = False

    @commands.command()
    async def stoplyrics(self, ctx):
        if self.lyric_task and not self.lyric_task.done():
            self.lyric_task.cancel()
            self.bot.locked_presence = False
            emoji = self.bot.config.get_emoji("success")
            await ctx.send(f"{emoji} lyrics sync stopped.")

async def setup(bot):
    await bot.add_cog(Lyrics(bot))
