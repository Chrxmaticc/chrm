import discord
from discord.ext import commands
import asyncio
import random

class Automation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def human_delay(self):
        settings = self.bot.config.data.get("settings", {})
        if settings.get("delays_enabled", True):
            min_d = settings.get("delay_min", 1.5)
            max_d = settings.get("delay_max", 4.5)
            await asyncio.sleep(random.uniform(min_d, max_d))

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore our own messages and DMs
        if message.author.id == self.bot.user.id or not message.guild:
            return

        # SAFELY grab features to prevent crashes
        features = self.bot.config.data.get("features", {})
        
        # 1. AFK Check
        afk = features.get("afk", {})
        if afk.get("enabled") and self.bot.user.mentioned_in(message):
            await self.human_delay()
            await message.reply(afk.get("message", "afk"), mention_author=True)
            return

        content_lower = message.content.lower()
        
        # 2. Autorespond Check
        autorespond = features.get("autorespond", {})
        for trigger, response in autorespond.items():
            if trigger.lower() in content_lower:
                await self.human_delay()
                await message.channel.send(str(response).lower())
                break

        # 3. Autoreact Check
        autoreact = features.get("autoreact", {})
        for trigger, emoji in autoreact.items():
            if trigger.lower() in content_lower:
                await self.human_delay()
                try:
                    await message.add_reaction(emoji)
                except:
                    pass
                break

    @commands.command()
    async def delay(self, ctx, seconds: float = 2.0):
        if "settings" not in self.bot.config.data:
            self.bot.config.data["settings"] = {}
        self.bot.config.data["settings"]["delays_enabled"] = True
        self.bot.config.data["settings"]["delay_min"] = seconds
        self.bot.config.data["settings"]["delay_max"] = seconds
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} delay set to **{seconds}s**")

    @commands.command()
    async def toggledelay(self, ctx):
        if "settings" not in self.bot.config.data:
            self.bot.config.data["settings"] = {}
        current = self.bot.config.data["settings"].get("delays_enabled", True)
        self.bot.config.data["settings"]["delays_enabled"] = not current
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} delays are now **{'on' if not current else 'off'}**")

    @commands.command()
    async def prefix(self, ctx, new_prefix: str):
        self.bot.command_prefix = new_prefix
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} prefix changed to `{new_prefix}`")

    @commands.command()
    async def addrespond(self, ctx, trigger, *, response):
        self.bot.config.data["features"]["autorespond"][trigger.lower()] = response.lower()
        emoji = self.bot.config.get_emoji("success")
        await ctx.send(f"{emoji} will respond to `{trigger.lower()}`")

    @commands.command()
    async def addreact(self, ctx, trigger, emoji):
        self.bot.config.data["features"]["autoreact"][trigger.lower()] = emoji
        success = self.bot.config.get_emoji("success")
        await ctx.send(f"{success} will react to `{trigger.lower()}`")

async def setup(bot):
    await bot.add_cog(Automation(bot))
