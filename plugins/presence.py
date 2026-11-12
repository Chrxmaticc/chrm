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
        if self.bot.is_ready() and not self.bot.config.get_feature("custom_status"):
            current = next(self.statuses)
            await self.bot.change_presence(activity=discord.CustomActivity(name=current))

    @rotate_status.before_loop
    async def before_rotate(self):
        await self.bot.wait_until_ready()

    @commands.command()
    async def status(self, ctx, *, text):
        self.bot.config.data["features"]["custom_status"] = text
        await self.bot.change_presence(activity=discord.CustomActivity(name=text.lower()))
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} status locked to: {text.lower()}")

    @commands.command()
    async def unlockstatus(self, ctx):
        self.bot.config.data["features"]["custom_status"] = None
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} status rotator unlocked.")

    @commands.command()
    async def rpc(self, ctx, activity_type: str, *, text):
        types = {
            "playing": discord.ActivityType.playing,
            "watching": discord.ActivityType.watching,
            "listening": discord.ActivityType.listening
        }
        act_type = types.get(activity_type.lower(), discord.ActivityType.playing)
        await self.bot.change_presence(activity=discord.Activity(type=act_type, name=text.lower()))
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} rpc set to {activity_type.lower()} {text.lower()}")

    @commands.command()
    async def lyricsync(self, ctx):
        emoji = self.bot.config.get_emoji("loading")
        await ctx.send(f"{emoji} starting lyric sync... (requires spotify api hookup)")

async def setup(bot):
    await bot.add_cog(Presence(bot))
