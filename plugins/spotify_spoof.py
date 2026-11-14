import discord
from discord.ext import commands

class SpotifySpoof(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def spotify(self, ctx, *, query):
        """fakes listening to spotify. usage: .spotify song name - artist name"""
        if " - " not in query:
            error = self.bot.config.get_emoji("error")
            return await ctx.send(f"{error} format must be: `.spotify song name - artist name`")

        song, artist = query.split(" - ", 1)
        
        # We set the activity type to LISTENING and add details to mimic Spotify
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name=song.strip(),
            details=song.strip(),
            state=artist.strip()
        )
        
        self.bot.locked_presence = True
        await self.bot.change_presence(activity=activity)
        
        success = self.bot.config.get_emoji("success")
        await ctx.send(f"{success} now spoofing spotify: **{song.strip()}** by {artist.strip()}")

    @commands.command()
    async def stopspotify(self, ctx):
        self.bot.locked_presence = False
        await self.bot.change_presence(activity=discord.CustomActivity(name="chrm on top"))
        success = self.bot.config.get_emoji("success")
        await ctx.send(f"{success} stopped spotify spoof.")

async def setup(bot):
    await bot.add_cog(SpotifySpoof(bot))
