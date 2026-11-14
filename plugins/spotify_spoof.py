import discord
from discord.ext import commands
import aiohttp
from datetime import datetime
import urllib.parse

class SpotifySpoof(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def spotify(self, ctx, *, query):
        """fakes listening to spotify with real album art. usage: .spotify blinding lights - the weeknd"""
        if " - " not in query:
            return await ctx.send(f"{self.bot.config.get_emoji('error')} format: `.spotify song name - artist`")

        song, artist = query.split(" - ", 1)
        song, artist = song.strip(), artist.strip()

        loading = await ctx.send(f"{self.bot.config.get_emoji('loading')} fetching spotify data...")

        # We use a public Spotify search API (Spotify's own web search)
        safe_query = urllib.parse.quote(f"{song} {artist}")
        url = f"https://api.spotify.com/v1/search?q={safe_query}&type=track&limit=1" 
        # Wait, Spotify API requires a token. Let's use a free proxy or iTunes with mp:external bypass
        
        # Since Discord only accepts spotify:image: we have to use the Apple Music / iTunes API 
        # to get the artwork, then format it as an external Spotify proxy.
        album_art_id = None
        try:
            search_query = f"{song} {artist}".replace(" ", "+")
            itunes_url = f"https://itunes.apple.com/search?term={search_query}&limit=1&entity=song"
            async with aiohttp.ClientSession() as session:
                async with session.get(itunes_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data["resultCount"] > 0:
                            # Extract the unique image ID from the iTunes URL
                            raw_url = data["results"][0]["artworkUrl100"]
                            # Example: https://is1-ssl.mzstatic.com/image/thumb/.../100x100bb.jpg
                            # Discord wants the hash from the end of the URL
                            image_hash = raw_url.split("/")[-1].split(".")[0]
                            album_art_id = image_hash
        except Exception:
            pass

        if not album_art_id:
            # Fallback to generic Spotify logo if iTunes fails
            album_art_id = "ab6761610000e5eb51d312f8b2781b175ab4db71"

        # The magic format Discord accepts for Spotify images
        formatted_art = f"spotify:image:{album_art_id}"

        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name="Spotify",
            details=song,
            state=artist,
            assets={
                "large_image": formatted_art,
                "large_text": song
            },
            timestamps={"start": int(datetime.now().timestamp())}
        )
        
        self.bot.locked_presence = True
        await self.bot.change_presence(activity=activity)
        
        await loading.edit(content=f"{self.bot.config.get_emoji('success')} now spoofing spotify: **{song}** by {artist}")

    @commands.command()
    async def stopspotify(self, ctx):
        self.bot.locked_presence = False
        await self.bot.change_presence(activity=None)
        await ctx.send(f"{self.bot.config.get_emoji('success')} stopped spotify spoof.")

async def setup(bot):
    await bot.add_cog(SpotifySpoof(bot))
