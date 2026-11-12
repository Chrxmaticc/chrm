import discord
from discord.ext import commands, tasks
import itertools

class Presence(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.statuses = itertools.cycle(["chrm on top", "vibing", "afk", "learning python"])
        self.rotate_status.start()

    def cog_unload(self):
        self.rotate_status.cancel()

    @tasks.loop(seconds=60)
    async def rotate_status(self):
        # only rotate if locked_presence is False
        if self.bot.is_ready() and not getattr(self.bot, 'locked_presence', False):
            current = next(self.statuses)
            await self.bot.change_presence(activity=discord.CustomActivity(name=current))

    @rotate_status.before_loop
    async def before_rotate(self):
        await self.bot.wait_until_ready()

    @commands.command()
    async def rpc(self, ctx, activity_type: str, *, text):
        """usage: .rpc playing minecraft"""
        types = {
            "playing": discord.ActivityType.playing,
            "watching": discord.ActivityType.watching,
            "listening": discord.ActivityType.listening,
            "competing": discord.ActivityType.competing
        }
        act_type = types.get(activity_type.lower())
        
        if not act_type:
            error = self.bot.config.get_emoji("error")
            return await ctx.send(f"{error} invalid type. use playing, watching, listening, or competing.")
        
        self.bot.locked_presence = True
        await self.bot.change_presence(activity=discord.Activity(type=act_type, name=text.lower()))
        
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} rpc updated: {activity_type.lower()} **{text.lower()}**")

    @commands.command()
    async def stream(self, ctx, url: str, *, title):
        """usage: .stream https://twitch.tv/you chrm on top"""
        if not url.startswith("http"):
            error = self.bot.config.get_emoji("error")
            return await ctx.send(f"{error} invalid url.")
            
        self.bot.locked_presence = True
        # THIS IS THE FIX: Use discord.Streaming, not discord.Activity
        await self.bot.change_presence(activity=discord.Streaming(name=title.lower(), url=url))
        
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} now streaming: **{title.lower()}**")

    @commands.command()
    async def customstatus(self, ctx, *, text):
        self.bot.locked_presence = True
        await self.bot.change_presence(activity=discord.CustomActivity(name=text.lower()))
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} custom status set: {text.lower()}")

    @commands.command()
    async def clearstatus(self, ctx):
        self.bot.locked_presence = False
        await self.bot.change_presence(activity=discord.CustomActivity(name=next(self.statuses)))
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} presence cleared & rotator unlocked.")

async def setup(bot):
    await bot.add_cog(Presence(bot))
