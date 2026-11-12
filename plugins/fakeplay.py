import discord
from discord.ext import commands
import aiohttp
import re

class FakePlay(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games_cache = None
        self.cache_url = "https://cdn.phaseworld.top/Discord/badge.txt"

    async def get_games(self):
        """downloads the game list once and caches it in memory"""
        if self.games_cache:
            return self.games_cache

        async with aiohttp.ClientSession() as session:
            async with session.get(self.cache_url) as resp:
                text = await resp.text()
        
        # extract name and id
        matches = re.findall(r'\["(.*?)","(\d{17,20})"\]', text)
        self.games_cache = matches
        return matches

    @commands.command()
    async def fakeplay(self, ctx, *, game_query: str):
        """fakes playing a game with its official icon. usage: .fakeplay roblox"""
        loading = self.bot.config.get_emoji("loading")
        msg = await ctx.send(f"{loading} searching for `{game_query}`...")

        try:
            games = await self.get_games()
        except Exception as e:
            error = self.bot.config.get_emoji("error")
            return await msg.edit(content=f"{error} failed to download game database.")

        matched_game = None
        # search for a close match
        for name, app_id in games:
            if game_query.lower() in name.lower():
                matched_game = (name, app_id)
                break

        self.bot.locked_presence = True

        if matched_game:
            name, app_id = matched_game
            activity = discord.Activity(
                type=discord.ActivityType.playing, 
                name=name, 
                application_id=app_id
            )
            await self.bot.change_presence(activity=activity)
            success = self.bot.config.get_emoji("success")
            await msg.edit(content=f"{success} now fake playing: **{name}**")
        else:
            # fallback if the game isn't in the database
            activity = discord.Activity(
                type=discord.ActivityType.playing, 
                name=game_query
            )
            await self.bot.change_presence(activity=activity)
            success = self.bot.config.get_emoji("success")
            await msg.edit(content=f"{success} now fake playing: **{game_query}** *(no official icon found)*")

    @commands.command()
    async def stopfakeplay(self, ctx):
        """stops the fake game and unlocks the status rotator"""
        self.bot.locked_presence = False
        await self.bot.change_presence(activity=discord.CustomActivity(name="chrm on top"))
        success = self.bot.config.get_emoji("success")
        await ctx.send(f"{success} stopped fake play. rotator unlocked.")

async def setup(bot):
    await bot.add_cog(FakePlay(bot))
